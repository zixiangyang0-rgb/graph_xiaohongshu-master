"""
结构化日志系统（JSON 格式），支持控制台和文件双通道输出，
自动附加 request_id 以追踪完整请求链路。
"""
import os
import sys
import logging
import uuid
from pathlib import Path
from datetime import datetime
from typing import Any, Optional
from logging.handlers import TimedRotatingFileHandler
from contextvars import ContextVar

import structlog
from structlog.types import Processor

from app.core.pii_anonymizer import pii_anonymize_processor


# 每个请求一个独立 ID，互不干扰
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> str:
    """获取当前请求的 ID，没有就生成一个。"""
    rid = request_id_var.get()
    if rid is None:
        rid = str(uuid.uuid4())[:8]
        request_id_var.set(rid)
    return rid


def set_request_id(rid: str) -> None:
    request_id_var.set(rid)


def clear_request_id() -> None:
    request_id_var.set(None)


def add_request_id(logger, method_name, event_dict):
    """给每条日志加上 request_id。"""
    event_dict["request_id"] = request_id_var.get()
    return event_dict


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)


# =============================================================================
# 日志系统初始化
# =============================================================================

def setup_logging(
    log_level: str = "INFO",
    log_target: str = "both",
    log_dir: str = "logs",
    json_logs: bool = True,
    console_output: bool = True,
    pii_anonymize: bool = True,
) -> None:
    """配置 structlog，写到控制台和/或文件。"""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        add_request_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    if pii_anonymize:
        shared_processors.append(pii_anonymize_processor)

    if json_logs:
        shared_processors.append(structlog.processors.format_exc_info)

    structlog.configure(
        processors=shared_processors + [
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    if console_output or log_target in ("console", "both"):
        structlog.configure(
            processors=shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True)
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )

    if log_target in ("file", "both"):
        file_handler = TimedRotatingFileHandler(
            log_path / "app.log",
            when="midnight",
            backupCount=7,
        )
        file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        root_logger.addHandler(file_handler)
        root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        structlog.configure(
            processors=shared_processors + [
                structlog.processors.JSONRenderer()
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(file_handler),
            cache_logger_on_first_use=True,
        )


# =============================================================================
# 业务日志辅助类
# =============================================================================

class _AppLogger:
    """提供语义化日志方法，每种方法对应一种业务事件。"""

    def _log(self, level: str, event: str, **kwargs):
        log_fn = getattr(get_logger("app"), level)
        log_fn(event, **kwargs)

    def request_started(self, method: str, path: str, client_ip: str, query_params: str = None):
        self._log("info", "request_started", method=method, path=path, client_ip=client_ip, query_params=query_params)

    def request_finished(self, method: str, path: str, status_code: int, duration_ms: float):
        self._log("info", "request_finished", method=method, path=path, status_code=status_code, duration_ms=duration_ms)

    def request_error(self, method: str, path: str, error: str, status_code: int = 500):
        self._log("error", "request_error", method=method, path=path, error=error, status_code=status_code)

    def workflow_started(self, thread_id: str, topic_direction: str):
        self._log("info", "workflow_started", thread_id=thread_id, topic_direction=topic_direction)

    def workflow_stage_changed(self, thread_id: str, stage: str, topics_count: int = 0):
        self._log("info", "workflow_stage_changed", thread_id=thread_id, stage=stage, topics_count=topics_count)

    def workflow_error(self, thread_id: str, error: str, stage: str):
        self._log("error", "workflow_error", thread_id=thread_id, error=error, stage=stage)

    def topic_selected(self, thread_id: str, selected_topic: str):
        self._log("info", "topic_selected", thread_id=thread_id, selected_topic=selected_topic)

    def draft_approved(self, thread_id: str):
        self._log("info", "draft_approved", thread_id=thread_id)

    def draft_rejected(self, thread_id: str, feedback: str, revision_count: int):
        self._log("info", "draft_rejected", thread_id=thread_id, feedback=feedback, revision_count=revision_count)

    def db_connected(self, database_url: str):
        self._log("info", "db_connected", database_url=database_url)

    def db_disconnected(self):
        self._log("info", "db_disconnected")

    def service_started(self, app_name: str, debug: bool, log_level: str, docs_url: str):
        self._log("info", "service_started", app_name=app_name, debug=debug, log_level=log_level, docs_url=docs_url)

    def service_stopped(self, app_name: str):
        self._log("info", "service_stopped", app_name=app_name)

    def error(self, msg: str, **kwargs):
        self._log("error", msg, **kwargs)

    def warning(self, msg: str, **kwargs):
        self._log("warning", msg, **kwargs)

    def info(self, msg: str, **kwargs):
        self._log("info", msg, **kwargs)


app_logger = _AppLogger()
