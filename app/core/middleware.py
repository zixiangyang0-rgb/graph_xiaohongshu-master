"""
中间件模块。

可以把中间件理解成请求进出服务时会经过的一层公共处理：
一个负责记日志，一个负责把 request_id 往后传，方便链路排查。
"""
import time
import uuid
from typing import Callable

# FastAPI 里的 Request / Response 类型
from fastapi import Request, Response

# 自定义中间件常用的基类
from starlette.middleware.base import BaseHTTPMiddleware

# ASGI 应用的类型标注
from starlette.types import ASGIApp

# 日志相关工具
from app.core.logger import (
    app_logger,
    set_request_id,
    clear_request_id,
    get_request_id,
)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    给每个请求记一份开始和结束日志，顺手带上 request_id。
    这样查问题时，能把同一次请求的日志串起来看。
    """

    # 这些路径太基础，单独跳过能少很多日志噪音
    SKIP_PATHS = {"/health", "/", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}

    def __init__(self, app: ASGIApp):
        """
        初始化中间件。

        `app` 一般就是 FastAPI 实例，或者下一个中间件。
        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        这个方法会包住每一个请求。
        除了真正把请求交给后面的路由处理，还会补上 request_id、耗时和错误日志。
        """
        # 这些路径不需要单独记请求日志
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # 优先用上游传来的 request_id；没有的话就现场生成一个
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        # 放进 ContextVar，方便这次请求里的其他日志复用同一个 ID
        set_request_id(request_id)

        # 尽量拿到真实客户端 IP，而不是中间代理的 IP
        client_ip = self._get_client_ip(request)

        # 先记一条开始日志，后面好算整次请求耗时
        start_time = time.perf_counter()
        app_logger.request_started(
            method=request.method,
            path=request.url.path,
            client_ip=client_ip,
            # 有查询参数的话顺手记上，排查起来更直观
            query_params=str(request.query_params) if request.query_params else None,
        )

        # 先给个默认状态码，避免异常时这里没有值
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code

            # 把 request_id 回传给前端，查问题时更方便对日志
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # 请求在业务层报错时，也补一条错误日志
            app_logger.request_error(
                method=request.method,
                path=request.url.path,
                error=str(e),
                status_code=500,
            )
            raise

        finally:
            # 不管成功失败，都记下耗时和最终状态
            duration_ms = (time.perf_counter() - start_time) * 1000
            app_logger.request_finished(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
            )

            # 请求结束后把 request_id 清掉，避免串到下一次请求
            clear_request_id()

    def _get_client_ip(self, request: Request) -> str:
        """
        尽量拿到真实客户端 IP。

        如果前面挂了 Nginx、Cloudflare 之类的代理，`request.client.host`
        往往不是最初发请求的用户 IP，所以这里会优先读常见代理头。
        """
        # 代理链里通常最左边那个才是用户自己的 IP
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        # 有些代理只会传这个头
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # 没有代理头时，就退回到底层连接里的地址
        if request.client:
            return request.client.host

        return "unknown"


class LangSmithTracingMiddleware(BaseHTTPMiddleware):
    """
    把当前请求的 request_id 挂到 `request.state` 上。

    这样后面的 LangSmith / LangChain 逻辑就能拿到同一个 ID，
    把 HTTP 请求日志和模型调用日志串起来看。
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        把 request_id 放进 `request.state`，然后继续往后处理请求。
        """
        # 从 ContextVar 里拿当前请求的 request_id，可能为空
        request.state.request_id = get_request_id()

        # 继续处理请求
        response = await call_next(request)
        return response
