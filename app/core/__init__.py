"""
================================================================================
核心基础设施模块（app/core）
================================================================================

职责说明：
  包含应用运行所需的核心基础设施组件，是整个后端的"底层基座"。

模块内容：
  - config.py：Pydantic Settings，环境变量定义和读取
  - db.py：SQLAlchemy 异步引擎和 Session 管理
  - logger.py：structlog 结构化日志配置
  - security.py：JWT 认证和密码哈希（argon2）
  - middleware.py：请求日志中间件、LangSmith 追踪
  - pii_anonymizer.py：PII（个人身份信息）脱敏工具
  - callbacks.py：LangChain 回调（PII 脱敏注入到 LLM 调用）

典型导入方式：
  from app.core.config import get_settings
  from app.core.db import get_async_session, init_db, close_db
  from app.core.logger import setup_logging, get_logger
  from app.core.security import verify_password, create_access_token

与其他模块的关系：
  - 被 main.py 导入（lifespan 初始化、应用创建）
  - 被 dependencies/auth.py 导入（JWT 验证）
  - 被 api/v1/*.py 导入（所有 API 路由）
  - 被 services/*.py 导入（LLM 和图片服务）
  - 被 graph/*.py 导入（工作流节点）

设计原则：
  - 零循环依赖：core 不依赖 api/graph/services
  - 延迟导入：在函数内部 import，避免顶层循环依赖
  - 单例模式：config/settings, logger 使用单例
================================================================================
"""
