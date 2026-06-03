"""
日志系统模块
=============================================================================
职责说明：
  这个模块负责整个应用的日志记录系统，采用结构化日志（JSON 格式）输出。

核心设计：
  1. 使用 structlog 库实现结构化日志（非传统纯文本格式）
     结构化日志 = JSON 对象，每个字段都有明确含义，方便日志系统搜索和统计
  2. 支持双通道输出：控制台（彩色人类可读）+ 文件（JSON 机器可读）
  3. 集成 PII 脱敏，自动打码日志中的敏感信息
  4. 提供 request_id 链路追踪，每个请求有唯一 ID 串联所有日志

典型场景：
  - 调试开发：控制台彩色输出，看请求流程
  - 排查问题：在日志文件中搜索 request_id，还原完整请求链路
  - 日志收集：Filebeat/Logstash 收集 JSON 日志，存入 Elasticsearch

结构化日志 vs 普通文本日志：
  普通格式：2024-01-01 10:00:00 [INFO] User 123 logged in
  JSON 格式：{"time":"2024-01-01T10:00:00Z","level":"info","event":"user_login","user_id":"123","request_id":"abc123"}

为什么 JSON 更好？
  1. 字段可搜索：log_file | grep '"user_id":"123"'
  2. Kibana/Grafana 图表：按 level 统计、按时间聚合
  3. 日志收集系统自动解析，不用写正则匹配
=============================================================================
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

# structlog 是结构化日志库，比标准 logging 更适合现代日志收集系统
# 它会自动给日志加上时间戳、级别、调用位置等信息
import structlog
from structlog.types import Processor

# 导入 PII 脱敏处理器（放在最后避免循环依赖）
from app.core.pii_anonymizer import pii_anonymize_processor


# =============================================================================
# 第 1 步：定义 Context 变量（请求级状态传递）
# =============================================================================

# ContextVar 是 Python 3.7+ 的上下文变量，在协程间传递数据
# 这里用来在同一个请求的生命周期内传递 request_id
# 为什么要用 ContextVar 而不是全局变量？
#   因为 FastAPI 是异步的，一个协程可能处理多个请求
#   全局变量会被所有请求共享，造成混乱
#   ContextVar 为每个请求维护独立的值，互不干扰

# request_id_var：当前请求的 ID，用于串联同一次请求的所有日志
# 典型值："a1b2c3d4"（8 位短 UUID，方便日志阅读）
# 默认值为 None，表示当前没有活跃请求
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> str:
    """
    获取当前请求的 request_id
    ==========================================================================
    工作流程：
      第 1 步：尝试从 ContextVar 获取当前值
      第 2 步：如果为空（None），说明还没有 request_id，生成一个新的
      第 3 步：如果是新生成的需要设置回 ContextVar，供后续调用复用
      第 4 步：返回 request_id 字符串

    典型场景：
      请求 A 进入 -> get_request_id() -> 看到 None -> 生成 "abc123" -> 返回 "abc123"
      后续日志处理器调用 get_request_id() -> 看到 "abc123" -> 返回 "abc123"
      请求 A 结束 -> clear_request_id() -> 清空
      请求 B 进入 -> get_request_id() -> 看到 None -> 生成 "def456" -> ...
    """
    rid = request_id_var.get()
    if rid is None:
        # 生成 8 位短 UUID，可读性更好，全长 36 位太长
        rid = str(uuid.uuid4())[:8]
        request_id_var.set(rid)
    return rid


def set_request_id(rid: str) -> None:
    """
    设置当前请求的 request_id
    ==========================================================================
    典型场景：
      中间件从请求头读取 X-Request-ID（如果有的话），设置到这里
      这样整个请求链路的日志都能用同一个 ID
      好处：前端传 ID，方便和问题跟踪系统（如 Sentry）对接
    """
    request_id_var.set(rid)


def clear_request_id() -> None:
    """
    清除当前请求的 request_id
    ==========================================================================
    典型场景：
      请求结束时（finally 块），清除 ContextVar
      避免内存泄漏（虽然 ContextVar 通常会随协程结束自动清理）
      也避免下一个请求意外复用上一个请求的 ID
    """
    request_id_var.set(None)


# =============================================================================
# 第 2 步：定义自定义处理器（Processor）
# =============================================================================

# structlog 的 Processor 是函数，接收日志事件 dict，返回处理后的 dict
# 所有日志都会依次经过每个 Processor，可以修改、添加、删除字段


def add_request_id(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """
    处理器：自动给每条日志加上 request_id 字段
    ==========================================================================
    工作原理：
      从 ContextVar 获取当前请求的 request_id，加入日志字典。
      如果没有 request_id（ ContextVar 是 None），则跳过不加。

    日志字段含义：
      event_dict["request_id"]：当前请求的唯一标识
      用于在大量日志中筛选出同一个请求的所有日志

    典型场景：
      {"event": "user_login", "request_id": "abc123", "user_id": "456"}
      {"event": "workflow_started", "request_id": "abc123", "thread_id": "789"}
      搜索 "abc123" 可以看到用户登录后启动工作流的完整链路
    """
    rid = request_id_var.get()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def add_service_info(logger: logging.Logger, method_name: str, event_dict: dict) -> dict:
    """
    处理器：自动给每条日志加上服务名称字段
    ==========================================================================
    工作原理：
      从环境变量 APP_NAME 读取服务名，默认 "xiaohongshu-assistant"

    日志字段含义：
      event_dict["service"]：当前服务的名称
      当多个服务日志混在一起时，可以快速筛选单个服务

    典型场景：
      {"service": "xiaohongshu-assistant", "event": "db_connected", ...}
    """
    event_dict["service"] = os.getenv("APP_NAME", "xiaohongshu-assistant")
    return event_dict


# =============================================================================
# 第 3 步：配置日志系统
# =============================================================================

def setup_logging(
    log_level: str = "INFO",
    log_target: str = "file",
    log_dir: str = "logs",
    json_logs: bool = True,
    console_output: bool = True,
    pii_anonymize: bool = True,
) -> None:
    """
    配置日志系统（整个应用只需要调用一次）
    ==========================================================================
    参数详解：
      - log_level：记录哪些级别的日志
        DEBUG = 最低，所有日志都记（SQL 语句、变量值等，开发用）
        INFO = 一般信息（请求开始/结束、工作流阶段变化）
        WARNING = 警告（数据库连接不稳定、功能降级）
        ERROR = 错误（请求失败、异常）
      - log_target：日志输出目标，目前只实现了 "file"
      - log_dir：日志文件存放目录，默认为 "logs"
      - json_logs：控制台是否输出 JSON 格式（文件始终是 JSON）
        True = JSON 格式，适合日志收集系统
        False = 彩色文本，适合人类阅读
      - console_output：是否同时输出到控制台（终端）
      - pii_anonymize：是否开启 PII 脱敏（自动打码日志中的敏感信息）

    工作流程（分 4 步）：

    ---------- 第 1 步：确保日志目录存在 ----------
    创建 log_dir 目录，如果已存在则跳过

    ---------- 第 2 步：配置标准 logging ----------
    structlog 需要配合标准 logging 使用
    清空所有已有的 handlers，避免重复日志

    ---------- 第 3 步：创建 handlers ----------
    File Handler：
      - TimedRotatingFileHandler：按时间自动轮转日志文件
      - when="midnight"：每天 0 点创建一个新文件
      - backupCount=30：最多保留 30 个历史文件（约一个月）
      - suffix="%Y-%m-%d"：文件命名格式 xhs_2024-01-01.log

    Console Handler：
      - StreamHandler(sys.stdout)：输出到标准输出（终端）
      - 开发模式用彩色输出，看起来更舒服

    ---------- 第 4 步：配置 structlog ----------
    共享处理器列表（每个日志事件都会依次经过）：
      1. merge_contextvars：从 ContextVar 合并 request_id 等上下文
      2. add_request_id：自定义处理器，加上 request_id 字段
      3. add_service_info：加上 service 字段
      4. add_log_level：加上日志级别（debug/info/warning/error）
      5. add_logger_name：加上 logger 名称
      6. PositionalArgumentsFormatter：格式化位置参数
      7. TimeStamper：加上 ISO 格式的时间戳
      8. StackInfoRenderer：加上堆栈信息（DEBUG 模式）
      9. UnicodeDecoder：处理非 ASCII 字符（如中文）
      10. pii_anonymize_processor：PII 脱敏（在输出前打码敏感信息）

    渲染器选择：
      - console_output + not json_logs：彩色控制台（开发模式）
      - 其他情况：JSON 格式（生产模式）
    """
    # ---------- 第 1 步：创建日志目录 ----------
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 将日志级别字符串转为数字常量（logging.DEBUG = 10, INFO = 20...）
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # ---------- 第 2 步：清空标准 logging 的 handlers ----------
    # 避免重复日志（比如 uvicorn 已经配置了 logging）
    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.setLevel(numeric_level)

    # 创建 handlers 列表，后面统一添加到 root_logger
    handlers = []

    # ---------- File Handler：日志文件（JSON 格式，始终开启） ----------
    if log_target == "file":
        log_file = log_path / "app.log"
        file_handler = TimedRotatingFileHandler(
            filename=str(log_file),
            when="midnight",      # 每天 0 点轮转，产生新文件
            interval=1,           # 轮转间隔为 1 天
            backupCount=30,      # 最多保留 30 个历史文件
            encoding="utf-8",    # 确保中文日志正常写入
        )
        # 文件名后缀格式：app.log.2024-01-01（而不是 .log.1）
        file_handler.suffix = "%Y-%m-%d"
        file_handler.setLevel(numeric_level)
        handlers.append(file_handler)

    # ---------- Console Handler：终端输出 ----------
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        handlers.append(console_handler)

    # ---------- 添加所有 handlers ----------
    for handler in handlers:
        root_logger.addHandler(handler)

    # ---------- 第 3 步：配置 structlog ----------
    # 共享处理器：所有输出目标都使用这些处理器
    shared_processors: list[Processor] = [
        # 从 ContextVar 合并上下文变量（如 request_id）
        structlog.contextvars.merge_contextvars,
        # 加上 request_id（用于链路追踪）
        add_request_id,
        # 加上服务名称
        add_service_info,
        # 加上日志级别字段
        structlog.stdlib.add_log_level,
        # 加上 logger 名称（__name__）
        structlog.stdlib.add_logger_name,
        # 格式化 logger.info("user %s logged in", user_id) 的位置参数
        structlog.stdlib.PositionalArgumentsFormatter(),
        # 加上 ISO 格式时间戳（2024-01-01T10:00:00.000Z）
        structlog.processors.TimeStamper(fmt="iso"),
        # 加上堆栈信息（DEBUG 模式才有）
        structlog.processors.StackInfoRenderer(),
        # 处理 Unicode 编码
        structlog.processors.UnicodeDecoder(),
    ]

    # ---------- PII 脱敏处理器：输出前打码敏感信息 ----------
    if pii_anonymize:
        shared_processors.append(pii_anonymize_processor)

    # ---------- 选择渲染器 ----------
    # 彩色控制台：开发模式，人类可读
    if console_output and not json_logs:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON 输出：生产模式，机器可读
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)

    # ---------- 配置 structlog 主框架 ----------
    # processors：事件处理流水线
    # logger_factory：如何创建底层 logger（用标准 logging 的）
    # wrapper_class：包装后的 logger 类型
    # cache_logger_on_first_use：首次创建后缓存，减少开销
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ---------- 第 4 步：配置格式化器 ----------
    # ProcessorFormatter 负责把所有 Processor 的输出转换为最终格式

    # JSON 格式化器（文件用）
    json_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )

    # 彩色控制台格式化器（终端用）
    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
    )

    # ---------- 分别给每个 handler 设置格式化器 ----------
    for handler in root_logger.handlers:
        if isinstance(handler, TimedRotatingFileHandler):
            # 文件 Handler 永远用 JSON 格式，方便日志收集系统处理
            handler.setFormatter(json_formatter)
        elif isinstance(handler, logging.StreamHandler):
            # 控制台 Handler 用彩色格式，人类可读
            handler.setFormatter(console_formatter)


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """
    获取一个结构化 logger 实例
    ==========================================================================
    参数说明：
      - name：logger 的名字，通常用 __name__
        __name__ 在被导入时等于模块路径（如 app.core.logger）
        这样可以从日志中知道是哪行代码打的日志

    返回值：
      - structlog BoundLogger 实例，带结构化方法

    典型场景：
      logger = get_logger(__name__)
      logger.info("user_login", user_id="123")  # JSON: {"event": "user_login", "user_id": "123"}
      logger.warning("db_slow", duration_ms=5000)  # JSON: {"event": "db_slow", "duration_ms": 5000}
    """
    return structlog.get_logger(name)


# =============================================================================
# 第 4 步：业务日志辅助类
# =============================================================================

# 为什么需要 AppLogger 类？
# 普通 logger.info("请求完成") 太笼统
# AppLogger 提供语义化的方法，每个方法对应一种业务事件
# 自动附带常用字段，打日志时一行搞定，不用每次手动写

class AppLogger:
    """
    应用级别日志记录器
    ==========================================================================
    封装了常见业务场景的日志方法，自动附带标准字段。
    相比直接用 logger.info()，更简洁、更一致。

    典型场景：
      app_logger.request_started(method="POST", path="/api/v1/workflow/start")
      app_logger.workflow_completed(thread_id="xxx", duration_ms=5000)

    每种方法都自动包含：
      - 事件类型（event name）
      - 常见上下文（thread_id, duration_ms 等）
      - request_id（从 ContextVar 自动获取）
    """

    def __init__(self, name: str = "app"):
        # 创建底层的 structlog logger
        self._logger = get_logger(name)

    # --------------------------------------------------------------------------
    # 系统事件
    # --------------------------------------------------------------------------

    def service_started(self, **kwargs: Any) -> None:
        """服务启动事件"""
        self._logger.info("service_started", **kwargs)

    def service_stopped(self, **kwargs: Any) -> None:
        """服务停止事件"""
        self._logger.info("service_stopped", **kwargs)

    def db_connected(self, **kwargs: Any) -> None:
        """数据库连接成功事件"""
        self._logger.info("db_connected", **kwargs)

    def db_disconnected(self, **kwargs: Any) -> None:
        """数据库断开连接事件"""
        self._logger.info("db_disconnected", **kwargs)

    def db_error(self, error: str, **kwargs: Any) -> None:
        """数据库错误事件"""
        self._logger.error("db_error", error=error, **kwargs)

    # --------------------------------------------------------------------------
    # API 请求事件
    # --------------------------------------------------------------------------

    def request_started(
        self,
        method: str,
        path: str,
        client_ip: str = "",
        **kwargs: Any
    ) -> None:
        """记录 API 请求开始"""
        self._logger.info(
            "request_started",
            method=method,
            path=path,
            client_ip=client_ip,
            **kwargs
        )

    def request_finished(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        **kwargs: Any
    ) -> None:
        """记录 API 请求完成"""
        # 4xx/5xx 状态码用 warning 级别，正常用 info
        log_method = self._logger.info if status_code < 400 else self._logger.warning
        log_method(
            "request_finished",
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=round(duration_ms, 2),
            **kwargs
        )

    def request_error(
        self,
        method: str,
        path: str,
        error: str,
        status_code: int = 500,
        **kwargs: Any
    ) -> None:
        """记录 API 请求错误"""
        self._logger.error(
            "request_error",
            method=method,
            path=path,
            error=error,
            status_code=status_code,
            **kwargs
        )

    # --------------------------------------------------------------------------
    # 工作流事件
    # --------------------------------------------------------------------------

    def workflow_started(
        self,
        thread_id: str,
        topic_direction: str,
        **kwargs: Any
    ) -> None:
        """记录工作流启动"""
        self._logger.info(
            "workflow_started",
            thread_id=thread_id,
            topic_direction=topic_direction,
            **kwargs
        )

    def workflow_stage_changed(
        self,
        thread_id: str,
        stage: str,
        **kwargs: Any
    ) -> None:
        """记录工作流阶段变化"""
        self._logger.info(
            "workflow_stage_changed",
            thread_id=thread_id,
            stage=stage,
            **kwargs
        )

    def topic_selected(
        self,
        thread_id: str,
        selected_topic: str,
        **kwargs: Any
    ) -> None:
        """记录选题被选中"""
        self._logger.info(
            "topic_selected",
            thread_id=thread_id,
            selected_topic=selected_topic,
            **kwargs
        )

    def draft_generated(
        self,
        thread_id: str,
        word_count: int = 0,
        **kwargs: Any
    ) -> None:
        """记录文章草稿生成"""
        self._logger.info(
            "draft_generated",
            thread_id=thread_id,
            word_count=word_count,
            **kwargs
        )

    def draft_approved(self, thread_id: str, **kwargs: Any) -> None:
        """记录草稿审核通过"""
        self._logger.info(
            "draft_approved",
            thread_id=thread_id,
            **kwargs
        )

    def draft_rejected(
        self,
        thread_id: str,
        feedback: str = "",
        revision_count: int = 0,
        **kwargs: Any
    ) -> None:
        """记录草稿被驳回"""
        self._logger.info(
            "draft_rejected",
            thread_id=thread_id,
            feedback=feedback,
            revision_count=revision_count,
            **kwargs
        )

    def workflow_completed(
        self,
        thread_id: str,
        duration_ms: float = 0,
        **kwargs: Any
    ) -> None:
        """记录工作流完成"""
        self._logger.info(
            "workflow_completed",
            thread_id=thread_id,
            duration_ms=round(duration_ms, 2),
            **kwargs
        )

    def workflow_error(
        self,
        thread_id: str,
        error: str,
        stage: str = "",
        **kwargs: Any
    ) -> None:
        """记录工作流错误"""
        self._logger.error(
            "workflow_error",
            thread_id=thread_id,
            error=error,
            stage=stage,
            **kwargs
        )

    # --------------------------------------------------------------------------
    # 通用方法
    # --------------------------------------------------------------------------

    def info(self, message: str, **kwargs: Any) -> None:
        """记录 INFO 级别日志"""
        self._logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """记录 WARNING 级别日志"""
        self._logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """记录 ERROR 级别日志"""
        self._logger.error(message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        """记录 DEBUG 级别日志"""
        self._logger.debug(message, **kwargs)

    def exception(self, message: str, **kwargs: Any) -> None:
        """记录异常（自动包含堆栈信息）"""
        self._logger.exception(message, **kwargs)


# =============================================================================
# 全局 logger 实例
# =============================================================================

# 全局单例，整个项目用这一个实例
# 导入方式：from app.core.logger import app_logger
app_logger = AppLogger("xiaohongshu-assistant")
