# AI Content Operations Assistant Backend
# =============================================================================
# 职责说明：
#   本目录是整个后端应用的核心代码。
#
# 目录结构：
#   - core/：基础设施（配置、数据库、日志、安全、中间件）
#   - models/：数据库模型（User 等）
#   - dependencies/：FastAPI 依赖注入（认证等）
#   - services/：业务服务（LLM 服务、图片服务）
#   - graph/：LangGraph 工作流（状态、节点、子图、指标）
#   - api/：HTTP API 路由（认证、工作流、图片）
#   - main.py：应用入口
#
# 技术栈：
#   - FastAPI：Web 框架
#   - SQLAlchemy：ORM
#   - PostgreSQL：数据库
#   - LangGraph：AI 工作流编排
#   - 火山引擎 Doubao：LLM API
#   - Gemini：图片生成 API
