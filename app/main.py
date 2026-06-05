"""
FastAPI 应用入口模块
=============================================================================
职责说明：
  整个后端服务的入口点，负责：
  1. 初始化日志系统
  2. 创建 FastAPI 应用实例
  3. 配置中间件（CORS、请求日志）
  4. 注册所有路由（认证、工作流、图片）
  5. 管理应用生命周期（启动初始化、关闭清理）

典型场景：
  1. 开发者启动服务：uvicorn app.main:app --reload
     -> lifespan startup -> 初始化数据库、初始化 Checkpointer
  2. 用户访问 http://localhost:8000/docs
     -> 查看 Swagger API 文档
  3. 用户调用 POST /api/v1/auth/login
     -> 认证路由处理
  4. 用户调用 POST /api/v1/workflow/start
     -> 工作流路由处理
  5. 关闭服务时：lifespan shutdown -> 清理资源

应用架构图：
  ┌─────────────────────────────────────────────────────────┐
  │                    FastAPI App                           │
  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
  │  │ CORS 中间件   │  │ 日志中间件   │  │ 静态文件    │  │
  │  └─────────────┘  └─────────────┘  └─────────────┘  │
  │  ┌──────────────────────────────────────────────────┐  │
  │  │                   路由层                          │  │
  │  │  /api/v1/auth    /api/v1/workflow   /api/v1/image│  │
  │  └──────────────────────────────────────────────────┘  │
  │  ┌──────────────────────────────────────────────────┐  │
  │  │                  服务层                           │  │
  │  │  LLM Service    Image Service    Auth Service   │  │
  │  └──────────────────────────────────────────────────┘  │
  │  ┌──────────────────────────────────────────────────┐  │
  │  │                 LangGraph 工作流                   │  │
  │  │  选题规划 -> 人工选题 -> 写作 -> 审核 -> 配图    │  │
  │  └──────────────────────────────────────────────────┘  │
  │  ┌──────────────────────────────────────────────────┐  │
  │  │                  数据层                            │  │
  │  │  PostgreSQL (用户数据 + 工作流状态)               │  │
  │  └──────────────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────────────┘
=============================================================================
"""
import sys
from pathlib import Path

# 确保项目根目录在 Python 路径中
# 这样才能用 from app.xxx import yyy 这样的导入语句
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from contextlib import asynccontextmanager
from typing import AsyncGenerator

# FastAPI 核心
from fastapi import FastAPI

# CORS 中间件：解决跨域问题
from fastapi.middleware.cors import CORSMiddleware

# 静态文件服务：访问生成的图片
from fastapi.staticfiles import StaticFiles

# 导入配置
from app.core.config import settings

# 导入数据库生命周期管理
from app.core.db import init_db, close_db

# 导入日志系统
from app.core.logger import setup_logging, app_logger

# 导入中间件
from app.core.middleware import RequestLoggingMiddleware

# 导入工作流工具（Checkpointer 初始化/清理）
from app.graph.utils import setup_checkpointer, close_checkpointer

# 导入路由
from app.api.v1.workflow import router as workflow_router
from app.api.v1.image import router as image_router
from app.api.v1.auth import router as auth_router


# =============================================================================
# 第 1 步：初始化日志系统
# =============================================================================
# 为什么在导入其他模块之前初始化？
#   其他模块可能在导入时就打日志
#   如果日志系统还没初始化，那些日志就丢失了
# 为什么用 setup_logging() 而不是直接配置？
#   配置很复杂（handler、formatter、processor），封装成函数更简洁

setup_logging(
    log_level=settings.log_level,
    log_target=settings.log_target,
    log_dir=settings.log_dir,
    json_logs=settings.log_json,
    console_output=settings.log_console,
    pii_anonymize=settings.log_pii_anonymize,
)


# =============================================================================
# 第 2 步：定义应用生命周期管理
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    应用生命周期管理（异步上下文管理器）
    ==========================================================================
    为什么需要这个？
      FastAPI 应用有明确的启动和关闭阶段
      启动时需要初始化数据库连接、创建工作流
      关闭时需要清理连接、释放资源

    工作流程：

    ---------- 启动阶段（yield 之前） ----------
      第 1 步：打印启动信息
      第 2 步：初始化 SQLAlchemy 数据库连接
                -> 创建 users 表（如果不存在）
      第 3 步：初始化 LangGraph Checkpointer
                -> 创建 checkpoint 表（用于持久化工作流状态）
      第 4 步：打印启动成功信息
                -> 显示 API 文档地址

    ---------- 运行阶段（yield 期间） ----------
      FastAPI 处理所有 HTTP 请求
      每次请求都会经过中间件、路由、服务、工作流

    ---------- 关闭阶段（yield 之后） ----------
      第 1 步：打印关闭信息
      第 2 步：关闭 LangGraph Checkpointer 连接池
      第 3 步：关闭 SQLAlchemy 数据库连接
      第 4 步：打印关闭成功信息

    为什么用 try/except？
      启动可能失败（数据库连不上），需要捕获并正确报告
    """
    # ==================== 启动阶段 ====================

    # 打印启动日志
    app_logger.info(f"Starting {settings.app_name}...")

    try:
        # ---------- 第 2 步：初始化 SQLAlchemy 数据库 ----------
        app_logger.info("Initializing database connection...")
        await init_db()
        # 记录连接信息（注意：不记录密码！）
        # settings.database_url.split("@")[-1] 提取主机部分
        # 例如：postgresql://postgres:password@localhost:5432/aicontent -> localhost:5432/aicontent
        app_logger.db_connected(database_url=settings.database_url.split("@")[-1])

        # ---------- 第 3 步：初始化 LangGraph Checkpointer ----------
        # Checkpointer 负责把工作流状态快照持久化到 PostgreSQL
        # 这样即使服务重启，工作流也能从中断点恢复
        app_logger.info("Initializing LangGraph Checkpointer...")
        await setup_checkpointer()

        # ---------- 第 4 步：记录服务启动成功 ----------
        app_logger.service_started(
            app_name=settings.app_name,
            debug=settings.debug,
            log_level=settings.log_level,
            docs_url="http://localhost:8000/docs"
        )

        # 打印启动提示（print 在终端更显眼，方便开发者看到）
        print(f"[OK] {settings.app_name} started successfully!")
        print(f"[Docs] API docs: http://localhost:8000/docs")
        print(f"[Logs] Log files: {settings.log_dir}/")

    except Exception as e:
        # 启动失败：记录错误并重新抛出
        # 抛出后 uvicorn 会以非零退出码结束，CI/CD 可以检测到启动失败
        app_logger.error(f"Startup failed: {str(e)}", error=str(e))
        raise

    # ---------- 运行阶段：yield 后的代码在关闭时执行 ----------
    yield

    # ==================== 关闭阶段 ====================

    app_logger.info(f"Stopping {settings.app_name}...")

    try:
        # 关闭 Checkpointer 连接池（先关，保证不处理新请求）
        await close_checkpointer()

        # 关闭数据库连接（最后关，确保所有请求已处理完）
        await close_db()

        # 记录关闭信息
        app_logger.db_disconnected()
        app_logger.service_stopped(app_name=settings.app_name)
    except Exception as e:
        # 关闭阶段的错误通常不影响大局，记录警告即可
        app_logger.warning(f"Error during shutdown: {str(e)}", error=str(e))


# =============================================================================
# 第 3 步：创建 FastAPI 应用实例
# =============================================================================

app = FastAPI(
    # API 文档标题（浏览器 tab 显示）
    title=settings.app_name,
    swagger_ui_parameters={"persistAuthorization": True},
    # API 描述（文档页面顶部）
    description="""
## AI 内容运营助手 API

为教育培训公司提供的自动化内容生成工作流服务。

### 核心功能

- **选题生成**: AI 根据主题方向生成多个候选选题
- **文章撰写**: AI 根据选定选题生成技术文章
- **人工审核**: 支持通过/驳回机制，驳回后可重写
- **配图生成**: 自动提取视觉要点并生成配图

### 工作流程

1. 启动工作流，AI 生成候选选题
2. 人工选择一个选题
3. AI 生成文章草稿
4. 人工审核（通过/驳回）
5. 通过后自动生成配图
    """,
    # API 版本（前端可以用）
    version="1.0.0",
    # 生命周期管理器
    lifespan=lifespan,
)


# =============================================================================
# 第 4 步：注册中间件
# =============================================================================
# 重要：中间件注册顺序 = 执行顺序（后注册先执行）
# 建议顺序：日志中间件 -> CORS -> 其他

# ---------- 中间件 1：请求日志中间件 ----------
# 记录每个请求的开始/结束、耗时
# 注册在最前面，这样所有请求都会先经过它
app.add_middleware(RequestLoggingMiddleware)

# ---------- 中间件 2：CORS 中间件 ----------
# 解决前后端分离项目的跨域问题
# 前后端不在同一个域（如前端 localhost:3000，后端 localhost:8000）
# 浏览器安全策略阻止跨域请求，CORS 头告诉浏览器允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名，如 ["https://example.com"]
    allow_credentials=True,  # 允许携带 Cookie（注意：allow_origins 不能用 *）
    allow_methods=["*"],  # 允许所有 HTTP 方法（GET、POST、PUT、DELETE 等）
    allow_headers=["*"],  # 允许所有请求头
)


# =============================================================================
# 第 5 步：注册路由
# =============================================================================
# 路由 = URL 路径 -> 处理函数的映射

# 认证路由：/api/v1/auth/*
# 处理：登录、注册、获取当前用户
app.include_router(auth_router, prefix="/api/v1")

# 工作流路由：/api/v1/workflow/*
# 处理：启动工作流、查看状态、恢复执行、获取历史记录
app.include_router(workflow_router, prefix="/api/v1")

# 图片路由：/api/v1/image/*
# 处理：生成测试图片
app.include_router(image_router, prefix="/api/v1")


# =============================================================================
# 第 6 步：挂载静态文件目录
# =============================================================================
# 静态文件 = 不需要服务器处理的直接返回的文件（如图片、CSS、JS）
# 挂载后：访问 URL /static/images/generated/xxx.png -> 返回 static/images/generated/xxx.png

# 确保目录存在
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)

# 挂载静态文件目录
# /static：URL 前缀
# StaticFiles(directory=...)：文件系统目录
# name="static"：给这个挂载点起个名字
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# =============================================================================
# 第 7 步：健康检查接口
# =============================================================================

@app.get("/")
async def root():
    """
    根路径 - 服务信息
    ==========================================================================
    访问方式：GET http://localhost:8000/
    用途：
      - 确认服务是否在运行
      - 获取服务基本信息

    返回示例：
      {
        "service": "AI内容运营助手",
        "status": "running",
        "version": "1.0.0",
        "docs": "/docs"
      }
    """
    return {
        "service": settings.app_name,
        "status": "running",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """
    健康检查接口 - K8s/负载均衡器探测用
    ==========================================================================
    访问方式：GET http://localhost:8000/health
    用途：
      - K8s 探测服务是否存活
      - 负载均衡器判断哪些后端可用
      - 运维监控系统检查服务状态

    返回示例：
      {"status": "healthy", "service": "AI内容运营助手"}

    注意：
      这个接口不需要认证（CORS 白名单里有 "/"）
      因为 K8s Probe 无法携带 Token
    """
    return {
        "status": "healthy",
        "service": settings.app_name
    }


# =============================================================================
# 第 8 步：直接运行入口
# =============================================================================

# 为什么需要这个？
#   python app/main.py 可以直接启动服务
#   而 uvicorn app.main:app --reload 更适合开发

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
