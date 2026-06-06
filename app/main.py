"""
后端服务入口。

这里主要做几件事：
  1. 初始化日志
  2. 创建 FastAPI 应用
  3. 挂中间件
  4. 注册路由
  5. 管理启动和关闭时要做的事
"""
import sys
from pathlib import Path

# 保证 `from app...` 这类导入能正常工作
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.db import init_db, close_db
from app.core.logger import setup_logging, app_logger
from app.core.middleware import RequestLoggingMiddleware
from app.graph.utils import setup_checkpointer, close_checkpointer
from app.api.v1.workflow import router as workflow_router
from app.api.v1.image import router as image_router
from app.api.v1.auth import router as auth_router


# 初始化日志
setup_logging(
    log_level=settings.log_level,
    log_target=settings.log_target,
    log_dir=settings.log_dir,
    json_logs=settings.log_json,
    console_output=settings.log_console,
    pii_anonymize=settings.log_pii_anonymize,
)


# 定义应用生命周期管理

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
应用启动和关闭时要做的事情都放这里。

启动时主要连数据库、准备 checkpointer；
关闭时把这些连接好好收掉。
"""
    # ==================== 启动阶段 ====================
    app_logger.info(f"Starting {settings.app_name}...")

    try:
        # 初始化 SQLAlchemy 数据库
        app_logger.info("Initializing database connection...")
        await init_db()
        # 不记录密码，只记录主机部分
        app_logger.db_connected(database_url=settings.database_url.split("@")[-1])

        # 初始化 LangGraph Checkpointer
        # Checkpointer 负责把工作流状态快照持久化到 PostgreSQL
        app_logger.info("Initializing LangGraph Checkpointer...")
        await setup_checkpointer()

        # 记录服务启动成功
        app_logger.service_started(
            app_name=settings.app_name,
            debug=settings.debug,
            log_level=settings.log_level,
            docs_url="http://localhost:8000/docs"
        )

        print(f"[OK] {settings.app_name} started successfully!")
        print(f"[Docs] API docs: http://localhost:8000/docs")
        print(f"[Logs] Log files: {settings.log_dir}/")

    except Exception as e:
        app_logger.error(f"Startup failed: {str(e)}", error=str(e))
        raise

    yield

    # 关闭阶段
    app_logger.info(f"Stopping {settings.app_name}...")

    try:
        await close_checkpointer()
        await close_db()
        app_logger.db_disconnected()
        app_logger.service_stopped(app_name=settings.app_name)
    except Exception as e:
        app_logger.warning(f"Error during shutdown: {str(e)}", error=str(e))


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    swagger_ui_parameters={"persistAuthorization": True},
    description="""
AI 内容运营助手 API。

支持选题生成、文章撰写、人工审核和配图生成的工作流。
    """,
    version="1.0.0",
    lifespan=lifespan,
)


# 注册中间件（后注册先执行）
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# 注册路由
app.include_router(auth_router, prefix="/api/v1")
app.include_router(workflow_router, prefix="/api/v1")
app.include_router(image_router, prefix="/api/v1")


# 挂载静态文件目录（生成的图片放在这里）
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# 健康检查接口


@app.get("/health")
async def health_check():
    """K8s/负载均衡器探测用，不需要认证。"""
    return {"status": "healthy", "service": settings.app_name}


if __name__ == "__main__":
    import uvicorn

    # host="0.0.0.0"：监听所有网络接口（容器内必须这样）
    # port=8000：监听 8000 端口
    # reload=settings.debug：代码修改后自动重启（只在 debug 模式开启）
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )
