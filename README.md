# AI 内容运营助手 - 后端服务

<!--
================================================================================
项目概述
================================================================================

职责说明：
  一个基于 LangGraph 1.0+ 和 FastAPI 构建的自动化内容生成工作流服务。
  用户输入主题方向（如"AI技术"），AI 自动完成：选题生成 → 文章撰写 →
  人工审核 → 配图生成 的完整流程。

核心设计理念：
  - Human-in-the-loop（人在回路）：在选题和审稿环节引入人工决策，而非纯自动化
  - 状态持久化：通过 PostgreSQL + LangGraph Checkpointer 保存工作流状态，
    支持断点续传、故障恢复、多线程并行
  - 流式输出：使用 Server-Sent Events (SSE) 实现实时流式响应，
    提升用户体验（打字机效果）
  - PII 匿名化：在日志和 LLM 输入输出中自动脱敏敏感信息

技术栈分层：
  - API 层：FastAPI 处理 HTTP 请求/响应
  - 业务层：LangGraph 定义工作流（节点 + 边 + 子图）
  - AI 层：LangChain + Volcengine Doubao LLM + Gemini Image API
  - 数据层：SQLAlchemy 异步 ORM + PostgreSQL
  - 安全层：JWT 认证 + Argon2 密码哈希 + PII 脱敏

典型用户场景：
  1. 内容运营人员输入"AI技术"，AI 生成 5 个选题
  2. 人工选择第 3 个选题"LangGraph入门"
  3. AI 生成约 1500 字的技术文章草稿
  4. 人工审阅后点"通过"，AI 提取 5 个配图要点
  5. AI 并行生成 5 张配图，工作流完成
================================================================================
-->

## 功能特性

- **AI 选题生成**: 根据主题方向自动生成候选选题
  <!-- AI 使用结构化输出（JSON Mode）生成 3-5 个选题，保证格式一致 -->

- **AI 文章撰写**: 根据选定选题生成技术文章
  <!-- 支持流式输出（SSE），用户可以看到文章逐字生成的过程 -->

- **Human-in-the-loop**: 支持人工介入的选题和审稿机制
  <!-- 工作流在两个关键节点暂停（选题 + 审稿），等待人工操作后继续 -->

- **配图生成**: 自动提取视觉要点并生成配图
  <!-- 先由 LLM 提取图片描述，再调用 Gemini Image API 并行生成多张图片 -->

- **状态持久化**: 使用 PostgreSQL 持久化工作流状态
  <!-- 通过 LangGraph Checkpointer，每次状态变更都写入数据库，支持断点续传 -->

## 技术栈

<!-- 按层级组织，从底层基础设施到上层应用 -->

- **Python 3.10+**: 项目运行环境
- **FastAPI**: 异步 Web 框架，提供 REST API
- **LangGraph 1.0+**: 工作流编排引擎，支持 interrupt/Command/Checkpointer
- **PostgreSQL**: 关系型数据库，存储用户数据和 LangGraph 检查点
- **SQLAlchemy**: 异步 ORM，封装数据库操作
- **Pydantic**: 数据验证，定义请求/响应模型和环境变量配置
- **LangChain**: LLM 调用封装，对接火山引擎 Doubao API
- **火山引擎 Doubao**: 大语言模型（兼容 OpenAI 接口）
- **Gemini Image API**: 图像生成模型（通过 Volcengine 代理调用）
- **Server-Sent Events (SSE)**: 单向流式协议，前端实时接收 AI 生成内容

## 快速开始

### 1. 环境准备

确保本地已安装并运行 PostgreSQL：

```bash
# Windows - 确认 PostgreSQL 服务运行
# 可以在服务管理器中查看 postgresql 服务状态

# macOS - 使用 Homebrew 启动
brew services start postgresql@15

# Linux - 使用 systemctl
sudo systemctl start postgresql

# 创建数据库
psql -U postgres -c "CREATE DATABASE graph_xiaohongshu;"

# 验证连接
psql -U postgres -d graph_xiaohongshu
```

### 2. 安装依赖

```bash
# 进入项目根目录
cd /path/to/graph_xiaohongshu

# 创建虚拟环境（隔离项目依赖）
python -m venv venv

# Windows
.\venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# 安装所有依赖
pip install -r requirements.txt
```

### 3. 配置环境变量

在项目根目录创建 `.env` 文件：

```env
# 数据库连接字符串
# 格式：postgresql[+asyncpg|asyncpsycopg2]://用户名:密码@主机:端口/数据库名
DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/graph_xiaohongshu

# LangGraph Checkpointer 使用的连接字符串（psycopg 格式，不含 asyncpg）
POSTGRES_URI=postgresql://postgres:your_password@localhost:5432/graph_xiaohongshu

# JWT 密钥：用于签名用户 Token，建议使用 32+ 字符随机字符串
# 生成方法：python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your_super_secret_key_here_change_in_production

# 火山引擎（豆包/Doubao）API 配置
# 获取地址：https://console.volcengine.com/ark
VOLCENGINE_API_KEY=your_volcengine_api_key
# 通常为 "ep-xxxxx" 格式的 endpoint
VOLCENGINE_API_BASE=https://ark.cn-beijing.volcengineapi.com

# 图像生成 API（通过火山引擎代理的 Gemini）
IMAGE_API_KEY=your_image_api_key
IMAGE_API_BASE=https://ark.cn-beijing.volcengineapi.com

# LangSmith 可选（用于 AI 应用的可观测性和追踪）
# LANGCHAIN_API_KEY=your_langsmith_api_key
# LANGCHAIN_TRACING_V2=true
# LANGCHAIN_PROJECT=graph-xiaohongshu
```

### 4. 初始化数据库

运行数据库初始化脚本，创建 LangGraph Checkpointer 所需的表：

```bash
# 方式 1：直接执行 SQL
psql -U postgres -d graph_xiaohongshu -f scripts/init_db.sql

# 方式 2：启动应用后自动创建（FastAPI lifespan 事件中处理）
# 但 init_db.sql 会创建索引，首次启动前建议手动执行
```

### 5. 启动服务

```bash
# 方式 1: 使用 uvicorn（推荐开发模式）
# app.main:app 指定从 app/main.py 导入 FastAPI 实例
# --reload: 代码修改后自动重载（仅开发环境）
# --host 0.0.0.0: 允许外部设备访问
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 方式 2: 直接运行 Python 模块
python -m app.main
```

### 6. 访问 API 文档

打开浏览器访问: http://localhost:8000/docs

<!-- FastAPI 自动生成的 Swagger UI，支持在线调试 API -->

## API 接口

### 启动工作流

```bash
POST /api/v1/workflow/start
Content-Type: application/json
Authorization: Bearer <token>

{
    "topic_direction": "AI技术"
}
```

**请求字段说明：**
- `topic_direction`（必填）：主题方向，字符串
  - 典型值："AI技术"、"职场成长"、"数码评测"
  - 典型场景：内容运营人员想要生成哪个领域的内容

**响应示例:**

```json
{
    "thread_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "topics_generated",
    "generated_topics": [
        "LangGraph入门：构建你的第一个AI工作流 - AI技术方向",
        "AI Agent实战：从零搭建智能助手 - AI技术方向",
        "Python高并发编程：asyncio深度解析 - AI技术方向"
    ],
    "message": "工作流已启动，请选择一个选题继续"
}
```

**响应字段说明：**
- `thread_id`：线程唯一标识，用于后续 API 调用（如恢复工作流）
  - 典型值：UUID 字符串
  - 典型场景：用户关闭页面后，可通过 thread_id 恢复工作流
- `status`：当前工作流状态
  - 典型值："topics_generated"（选题已生成，等待选择）
  - 其他值：见工作流状态说明
- `generated_topics`：AI 生成的候选选题列表
  - 通常 3-5 个，每个选题包含方向关键词
- `message`：友好提示信息

### 获取工作流状态

```bash
GET /api/v1/workflow/state/{thread_id}
Authorization: Bearer <token>
```

**路径参数说明：**
- `thread_id`：工作流线程 ID（从 start 接口获取）

**响应示例:**

```json
{
    "thread_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "topics_generated",
    "topic_direction": "AI技术",
    "generated_topics": ["...", "..."],
    "selected_topic": null,
    "article_content": null,
    "visual_points": null,
    "image_urls": [],
    "interrupt_info": {
        "description": "请从上方选题列表中选择一个，或输入新的选题",
        "options": ["选题1", "选题2", "选题3"],
        "action": "select_topic"
    }
}
```

### 恢复工作流 - 选择选题

```bash
POST /api/v1/workflow/resume/{thread_id}
Content-Type: application/json
Authorization: Bearer <token>

{
    "action": "select_topic",
    "data": {
        "selected_topic": "LangGraph入门：构建你的第一个AI工作流"
    }
}
```

**请求字段说明：**
- `action`：操作类型
  - 典型值："select_topic"（选题）、"approve"（通过）、"reject"（驳回）
- `data`：操作附带数据
  - `selected_topic`：用户选中的选题（必须是 generated_topics 中的一个，或自定义新选题）

### 恢复工作流 - 审核通过

```bash
POST /api/v1/workflow/resume/{thread_id}
Content-Type: application/json
Authorization: Bearer <token>

{
    "action": "approve"
}
```

**典型场景：**
- 人工审阅完 AI 生成的文章草稿后
- 满意内容质量和风格，点击"通过"
- 工作流进入配图生成环节

### 恢复工作流 - 审核驳回

```bash
POST /api/v1/workflow/resume/{thread_id}
Content-Type: application/json
Authorization: Bearer <token>

{
    "action": "reject",
    "data": {
        "feedback": "请增加更多实际代码示例"
    }
}
```

**请求字段说明：**
- `feedback`：驳回原因/修改意见
  - 典型值："请增加更多代码示例"、"第二段逻辑不够清晰"、"字数太短"
  - 典型场景：LLM 会根据反馈重新生成文章草稿

## 工作流程图

```
┌─────────────────────────────────────────────────────────────────┐
│                         START                                    │
│                      (用户输入主题方向)                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     plan_topics                                  │
│                  (AI 生成 3-5 个选题)                            │
│  输入：topic_direction（如"AI技术"）                              │
│  输出：generated_topics 列表                                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              ⏸️ INTERRUPT: human_select_topic                    │
│                    (等待人工选题)                                 │
│  AI 暂停，等待用户选择（或自定义）选题                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      write_draft                                 │
│                  (AI 根据选题写长文)                              │
│  输入：selected_topic                                            │
│  输出：article_content（流式输出，支持 SSE）                       │
│  特殊：支持 revision 循环，根据 feedback 重写                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              ⏸️ INTERRUPT: human_review                          │
│                    (等待人工审稿)                                 │
│  AI 暂停，等待用户审核文章草稿                                     │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
         [approved]                      [rejected]
              │                               │
              ▼                               │
┌─────────────────────────┐                   │
│    extract_visuals      │                   │
│    (提炼图片要点)        │                   │
│  从文章内容提取 3-5 个   │                   │
│  适合配图的视觉描述       │                   │
└─────────────────────────┘                   │
              │                               │
              ▼                               ▼
┌─────────────────────────┐                   │
│    generate_images      │                   │
│    (生成配图)           │                   │
│  并行调用 Gemini Image   │                   │
│  API，生成多张图片       │                   │
└─────────────────────────┘                   │
              │                               │
              ▼                               ▼
┌─────────────────────────┐                   │
│          END            │◀──────────────────┘
│       (工作流完成)       │    (回到 write_draft 重写)
└─────────────────────────┘
```

**工作流状态说明：**

| 状态 | 含义 | 触发时机 |
|------|------|----------|
| `started` | 已启动 | 用户调用 /start |
| `topics_generated` | 选题已生成 | plan_topics 节点完成 |
| `topic_selected` | 选题已选择 | 用户调用 /resume 选择选题 |
| `article_writing` | 文章撰写中 | write_draft 节点执行中 |
| `article_generated` | 文章已生成 | write_draft 节点完成 |
| `under_review` | 审核中 | 进入 human_review_node |
| `visuals_extracted` | 视觉要点已提取 | extract_visuals 节点完成 |
| `images_generated` | 图片已生成 | generate_images 节点完成 |
| `completed` | 完成 | 工作流正常结束 |
| `rejected` | 驳回 | 用户驳回，等待重新生成 |

## 项目结构

```
graph_xiaohongshu/
│
├── app/                            # 后端应用根目录
│   ├── __init__.py                 # 包初始化
│   │
│   ├── main.py                     # 应用入口
│   │   # - setup_logging() 初始化日志
│   │   # - lifespan() 管理数据库连接池和 Checkpointer 生命周期
│   │   # - FastAPI 实例创建、路由注册、中间件配置
│   │
│   ├── core/                       # 核心基础设施
│   │   ├── config.py               # Pydantic Settings，环境变量管理
│   │   ├── db.py                  # SQLAlchemy 异步引擎和 Session
│   │   ├── logger.py              # structlog 配置和 AppLogger
│   │   ├── security.py            # JWT 签发/验证，密码哈希
│   │   ├── middleware.py          # 请求日志中间件，LangSmith 追踪
│   │   ├── pii_anonymizer.py      # PII 脱敏器（邮箱/手机号/身份证等）
│   │   └── callbacks.py           # LangChain 回调（PII 脱敏注入）
│   │
│   ├── models/                     # 数据库 ORM 模型
│   │   └── user.py                # User 表：id, username, password_hash
│   │
│   ├── dependencies/               # FastAPI 依赖注入
│   │   └── auth.py                # JWT Bearer 认证依赖
│   │
│   ├── api/v1/                     # API 路由
│   │   ├── auth.py                # 注册 / 登录 / 获取用户信息
│   │   ├── image.py               # 图像生成（测试用）
│   │   └── workflow.py            # 工作流：启动/恢复/状态/流式接口
│   │
│   ├── services/                   # 业务服务层
│   │   ├── llm_service.py         # LLM 调用：选题生成/文章撰写/视觉提取
│   │   │   # 支持多模型：plan/write/extract 不同模型
│   │   │   # 内置 PII 脱敏回调
│   │   │   # 流式输出支持
│   │   └── image_service.py       # 图片生成：Gemini Image API 调用
│   │       # retry 机制容错
│   │       # 保存到 static/images/generated/
│   │
│   └── graph/                      # LangGraph 工作流定义
│       ├── state.py                # AgentState TypedDict 定义
│       ├── workflow.py             # build_workflow_graph() 组装工作流
│       ├── metrics.py              # LLM 使用量追踪（token/延迟）
│       ├── utils.py                # Checkpointer 初始化工具
│       ├── nodes/                  # 节点实现
│       │   ├── planner.py         # plan_topics_node：选题生成
│       │   ├── writer.py          # write_draft_node：文章撰写
│       │   ├── visualizer.py     # extract_visuals_node + generate_images_node
│       │   └── human.py           # human_review_node（interrupt + Command）
│       └── subgraphs/              # 子图
│           └── topic_selection.py  # 选题选择子图（human_select_topic）
│
├── frontend/                       # Vue 3 前端
│   ├── index.html                 # HTML 入口
│   ├── vite.config.js             # Vite 配置（代理 /api 到后端）
│   ├── package.json               # npm 依赖
│   └── src/
│       ├── main.js                # Vue 应用创建入口
│       ├── App.vue                # 根组件（登录 + 工作流界面）
│       ├── api.js                 # Axios 封装，所有 API 调用
│       └── style.css              # 全局样式（小红书风格）
│
├── scripts/
│   └── init_db.sql                # LangGraph Checkpointer 表结构
│
├── static/                         # 静态资源（运行时生成）
│   └── images/generated/          # AI 生成的配图存储目录
│
├── requirements.txt               # Python 依赖清单
├── .gitignore                     # Git 忽略规则
├── .env.example                   # 环境变量模板（不含真实密钥）
└── README.md                      # 本文档
```

## 注意事项

1. **数据库连接**：
   - 确保 PostgreSQL 服务运行且可访问
   - DATABASE_URL 必须包含 `+asyncpg` 后缀（SQLAlchemy 异步驱动）
   - POSTGRES_URI 不含 `+asyncpg`（psycopg 的格式要求）

2. **LLM 配置**：
   - 在 `.env` 中配置火山引擎 Doubao API Key
   - 确保 VOLCENGINE_API_BASE 和 IMAGE_API_BASE 格式正确（无尾部斜杠）

3. **状态持久化**：
   - LangGraph Checkpointer 自动创建 checkpoints 和 checkpoint_writes 表
   - 首次启动前建议手动执行 `scripts/init_db.sql` 创建索引

4. **前端开发**：
   - 前端默认运行在 http://localhost:5173
   - 通过 vite.config.js 的 proxy 将 /api 请求转发到后端
   - API 代理在生产环境不生效，需要单独部署前后端

5. **生产环境**：
   - 替换 SECRET_KEY 为强随机值
   - 配置 HTTPS/SSL
   - 使用真实的数据库（而非本地 PostgreSQL）
   - 配置日志聚合（如 ELK Stack 或 Datadog）

## License

MIT
