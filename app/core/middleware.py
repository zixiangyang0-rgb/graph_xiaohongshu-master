"""
FastAPI 中间件模块
=============================================================================
职责说明：
  中间件是请求处理流水线上的"拦截器"，每个请求都要经过它们。
  本模块提供两个中间件：
  1. RequestLoggingMiddleware：记录每个 HTTP 请求的日志（开始、结束、耗时）
  2. LangSmithTracingMiddleware：将 request_id 传递给 LangSmith 实现链路追踪

核心设计：
  - 中间件按注册顺序执行（先注册的后执行）
  - 每个请求都生成唯一 request_id，方便在日志中追踪完整请求链路
  - 支持从请求头读取已有的 request_id（前端或网关传入的）
  - 自动获取真实客户端 IP（考虑代理、X-Forwarded-For 等）

典型场景：
  用户发起请求 -> 中间件记录开始 -> 执行业务代码 -> 中间件记录结束
  日志例子：
    {"request_id":"abc123","method":"POST","path":"/api/v1/workflow/start","duration_ms":1523.4}
=============================================================================
"""
import time
import uuid
from typing import Callable

# FastAPI 的 Request 和 Response 对象
from fastapi import Request, Response

# BaseHTTPMiddleware：自定义中间件的基类
# 它处理 ASGI 协议，让你可以用面向对象的方式写中间件
from starlette.middleware.base import BaseHTTPMiddleware

# ASGIApp：ASGI 应用的类型注解，代表一个 ASGI 应用（可以是中间件或主应用）
from starlette.types import ASGIApp

# 导入日志相关
from app.core.logger import (
    app_logger,
    set_request_id,
    clear_request_id,
    get_request_id,
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    请求日志中间件
    ==========================================================================
    功能说明：
      为每个 HTTP 请求生成唯一 request_id，并记录开始/结束日志。

    工作流程：
      1. 跳过白名单路径（健康检查等不需要记录的接口）
      2. 生成或接收 request_id
      3. 记录请求开始（时间、方法、路径、客户端 IP）
      4. 执行真正的请求处理（call_next）
      5. 记录请求结束（耗时、状态码）
      6. 清理 request_id（防止内存泄漏）

    request_id 用途：
      - 日志搜索：grep "abc123" 找到同一次请求的所有日志
      - 问题排查：通过 request_id 串联请求的完整生命周期
      - 前端追踪：把 request_id 返回给前端，方便用户反馈问题时提供

    典型场景：
      POST /api/v1/workflow/start 的日志：
      {
        "event": "request_started",
        "request_id": "a1b2c3d4",
        "method": "POST",
        "path": "/api/v1/workflow/start",
        "client_ip": "127.0.0.1",
        "duration_ms": 1523.45
      }
    """

    # 不需要记录的路径（减少日志噪音）
    # 这些是基础设施接口，记录没有意义
    SKIP_PATHS = {"/health", "/", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}

    def __init__(self, app: ASGIApp):
        """
        初始化中间件
        ==========================================================================
        参数说明：
          - app：ASGI 应用对象，通常是 FastAPI 实例或下一个中间件

        为什么需要这个 __init__？
          中间件需要访问 app 实例，所以需要显式调用 super().__init__(app)
        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        处理每个请求的核心方法
        ==========================================================================
        参数说明：
          - request：请求对象，包含所有请求信息
          - call_next：下一个处理器（路由函数）的引用
            调用 call_next(request) 才会真正执行业务代码

        工作流程（每一步都有明确目的）：
          第 1 步：跳过白名单路径
          第 2 步：获取/生成 request_id
          第 3 步：获取客户端真实 IP
          第 4 步：记录请求开始
          第 5 步：执行请求处理
          第 6 步：记录请求结束
          第 7 步：清理资源

        为什么用 try/except/finally？
          即使业务代码抛异常，也要确保日志被记录、request_id 被清理
        """
        # ---------- 第 1 步：跳过不需要记录的路径 ----------
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # ---------- 第 2 步：获取或生成 request_id ----------
        # 优先从请求头读取（前端或网关传入的），没有就随机生成一个
        # X-Request-ID 是标准的请求追踪头，很多网关会自动传递
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        # 设置到 ContextVar，让这次请求的所有日志都能获取到同一个 ID
        set_request_id(request_id)

        # ---------- 第 3 步：获取客户端真实 IP ----------
        client_ip = self._get_client_ip(request)

        # ---------- 第 4 步：记录请求开始 ----------
        start_time = time.perf_counter()
        app_logger.request_started(
            method=request.method,
            path=request.url.path,
            client_ip=client_ip,
            # 如果有查询参数（如 ?page=1）也记录下来
            query_params=str(request.query_params) if request.query_params else None,
        )

        # ---------- 第 5 步：执行业务代码 ----------
        status_code = 500  # 默认值，以防异常发生
        try:
            response = await call_next(request)
            status_code = response.status_code

            # 把 request_id 塞到响应头，方便前端和调试工具看到
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # ---------- 异常路径：记录错误 ----------
            app_logger.request_error(
                method=request.method,
                path=request.url.path,
                error=str(e),
                status_code=500,
            )
            raise

        finally:
            # ---------- 第 6 步：记录请求结束 ----------
            duration_ms = (time.perf_counter() - start_time) * 1000
            app_logger.request_finished(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
            )

            # ---------- 第 7 步：清理 request_id ----------
            # 防止 ContextVar 无限增长（虽然理论上协程结束会自动清理）
            clear_request_id()

    def _get_client_ip(self, request: Request) -> str:
        """
        获取客户端真实 IP 地址
        ==========================================================================
        为什么需要特殊处理？
          直接访问 request.client.host 不一定是最原始的客户端 IP。
          因为中间可能经过了 Nginx、Cloudflare、LB 等代理。

        优先级说明：
          1. X-Forwarded-For：最左边是非代理的真实 IP
             格式："client_ip, proxy1_ip, proxy2_ip"
             只取第一个逗号前的，就是真实客户端 IP
          2. X-Real-IP：某些代理会设置这个头
          3. request.client.host：直连情况下的客户端 IP
          4. "unknown"：以上都没有

        典型场景：
          用户 -> Nginx -> Cloudflare -> FastAPI
          X-Forwarded-For: "203.0.113.50, 198.51.100.1, 172.16.0.1"
          实际客户端 IP = "203.0.113.50"
        """
        # 优先从代理头获取（可能包含多个 IP，取第一个）
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        # 其次从 X-Real-IP 获取
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # 直连情况
        if request.client:
            return request.client.host

        return "unknown"


class LangSmithTracingMiddleware(BaseHTTPMiddleware):
    """
    LangSmith 链路追踪中间件
    ==========================================================================
    功能说明：
      将 request_id 传递给 LangSmith，实现 AI 模型调用的链路追踪关联。

    工作原理：
      1. 从 ContextVar 获取当前请求的 request_id
      2. 存储到 request.state（FastAPI 的请求级别状态存储）
      3. LangChain/LangSmith 在 LLM 调用时可以读取这个 ID
      4. 这样 AI 请求日志和应用请求日志就能通过 request_id 串联

    为什么需要这个？
      LangSmith 记录的是 AI 模型调用层面的日志（Prompt、Token 等）
      应用日志记录的是 HTTP 请求层面的日志（路径、参数等）
      有了 request_id，可以把两者对应起来，完整还原用户请求的 AI 部分

    典型场景：
      用户请求 /api/v1/workflow/start -> request_id: abc123
      AI 生成选题 -> LangSmith 记录: run_id, request_id=abc123
      日志搜索 "abc123" -> 看到 HTTP 请求日志 + AI 调用日志

    注意：
      这个中间件本身不主动调用 LangSmith
      它只是把 request_id 放到 request.state 里
      实际的追踪由 LangChain 的 traceable 装饰器完成
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        处理每个请求
        ==========================================================================
        工作流程：
          1. 获取当前请求的 request_id（可能为空，不强制要求）
          2. 存入 request.state，方便后续代码读取
          3. 调用下一个处理器
        """
        # 从 ContextVar 获取 request_id（可能为 None）
        request.state.request_id = get_request_id()

        # 处理请求
        response = await call_next(request)
        return response
