# 小红书 AI 内容运营助手 — 项目学习路线

> 本项目是一个基于 **LangGraph** + **FastAPI** + **PostgreSQL** 构建的 AI 内容生成工作流。用户输入主题，AI 自动完成选题生成 → 文章撰写 → 人工审核 → 配图生成的完整流程。

---

## 项目技术栈速查

| 层级 | 技术 | 说明 |
|------|------|------|
| API 层 | FastAPI | 异步 Web 框架，提供 REST API |
| 工作流层 | LangGraph 1.0+ | 工作流编排引擎，支持 interrupt/Command/Checkpointer |
| AI 层 | LangChain + 火山引擎 Doubao LLM | 调用大语言模型 |
| 图像层 | Gemini Image API | 生成配图 |
| 数据层 | SQLAlchemy 异步 ORM + PostgreSQL | 存储用户数据和 LangGraph 检查点 |
| 安全层 | JWT 认证 + Argon2 密码哈希 + PII 脱敏 | 认证和安全 |

---

## 项目架构总览

```
用户输入主题方向（如"AI技术"）
        │
        ▼
┌──────────────────┐
│  plan_topics     │  ← AI 生成 3-5 个选题
│  (选题生成节点)   │
└──────────────────┘
        │
        ▼
┌──────────────────┐
│  ⏸ 人工选题      │  ← interrupt() 暂停，等用户选择
└──────────────────┘
        │
        ▼
┌──────────────────┐
│  write_draft     │  ← AI 根据选题撰写文章（流式输出）
│  (文章撰写节点)   │
└──────────────────┘
        │
        ▼
┌──────────────────┐
│  ⏸ 人工审稿      │  ← interrupt() 暂停，等用户审核
└──────────────────┘
        │
        ▼
┌──────────────────┐
│  extract_visuals │  ← 从文章提取配图要点
│  generate_images │  ← 并行调用 Gemini 生成多张配图
└──────────────────┘
        │
        ▼
     工作流完成
```

---

## 项目结构

```
app/
├── main.py              # FastAPI 应用入口，lifespan 管理数据库连接
├── api/v1/
│   ├── auth.py          # 认证接口（登录/注册）
│   ├── workflow.py      # 工作流接口（启动/状态/恢复/流式）
│   └── image.py         # 图片接口
├── core/
│   ├── config.py        # 环境变量配置（Pydantic Settings）
│   ├── security.py      # JWT + 密码哈希
│   ├── db.py            # SQLAlchemy 异步引擎
│   ├── logger.py        # structlog 日志配置
│   ├── middleware.py    # 请求日志中间件
│   ├── pii_anonymizer.py # PII 脱敏（邮箱/手机号等）
│   └── callbacks.py     # LangChain 回调注入
├── graph/
│   ├── state.py         # WorkflowState TypedDict 定义
│   ├── workflow.py      # LangGraph 工作流组装
│   ├── metrics.py       # LLM 使用量追踪
│   ├── nodes/
│   │   ├── planner.py   # 选题生成节点
│   │   ├── writer.py    # 文章撰写节点（支持流式 SSE）
│   │   ├── visualizer.py # 配图提取和生成节点
│   │   └── human.py     # 人工审核节点（interrupt + Command）
│   └── subgraphs/
│       └── topic_selection.py # 选题选择子图
├── models/
│   └── user.py          # User 数据库模型
├── services/
│   ├── llm_service.py   # LLM 调用封装（支持多模型、流式、PII 脱敏）
│   └── image_service.py  # 图片生成（Gemini API + retry 机制）
└── dependencies/
    └── auth.py          # JWT Bearer 认证依赖

frontend/
├── vite.config.js       # Vite 配置，代理 /api 到后端
└── src/
    ├── App.vue          # 根组件（登录 + 工作流界面）
    ├── api.js           # Axios 封装，所有 API 调用
    └── style.css        # 全局样式（小红书风格）

scripts/
└── init_db.sql          # LangGraph Checkpointer 表结构
```

---

## 学习阶段总览

```
第一阶段：项目概览与运行       → 预计 1~2 天
第二阶段：前端代码导读          → 预计 1~2 天
第三阶段：后端 API 层          → 预计 2~3 天
第四阶段：数据库层              → 预计 1~2 天
第五阶段：LangGraph 工作流      → 预计 3~5 天
第六阶段：AI 服务层            → 预计 2~3 天
第七阶段：安全与中间件          → 预计 1~2 天
第八阶段：本地运行与调试        → 预计 1~2 天
───────────────────────────────────────────
总计：约 12~20 天
```

---

## 第一阶段：项目概览与运行

### 1.1 环境准备

确保已安装：
- **Python 3.10+**
- **PostgreSQL**（已运行）
- **火山引擎 API Key**（申请地址：https://console.volcengine.com/ark）

### 1.2 安装与启动

```bash
# 进入项目目录
cd d:\graph_xiaohongshu-master-main\graph_xiaohongshu-master-main

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境（Windows PowerShell）
.\venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 配置环境变量（复制 .env.example 为 .env，填入 API Key）
# DATABASE_URL=postgresql+asyncpg://postgres:密码@localhost:5432/graph_xiaohongshu
# SECRET_KEY=你的随机密钥
# VOLCENGINE_API_KEY=你的火山引擎 API Key

# 初始化数据库
psql -U postgres -c "CREATE DATABASE graph_xiaohongshu;"
psql -U postgres -d graph_xiaohongshu -f scripts/init_db.sql

# 启动后端
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 新开终端，启动前端
cd frontend
npm install
npm run dev
```

### 1.3 验证运行

- 前端页面：http://localhost:5173
- 后端 API 文档：http://localhost:8000/docs
- pgAdmin（数据库管理）：http://127.0.0.1:5050

---

## 第二阶段：前端代码导读

### 2.1 前端入口：App.vue

`frontend/src/App.vue` 是整个前端的核心，包含：

```vue
data() { ... }       // 响应式数据：用户状态、工作流状态、选题列表、文章内容
computed: { ... }    // 计算属性：派生状态
methods: { ... }     // 方法：登录、启动工作流、选择选题、审核文章等
```

### 2.2 API 调用：api.js

`frontend/src/api.js` 封装了所有后端接口调用：

| 方法 | 路径 | 功能 |
|------|------|------|
| `register(username, password)` | POST `/api/v1/auth/register` | 用户注册 |
| `login(username, password)` | POST `/api/v1/auth/login` | 用户登录，返回 JWT |
| `startWorkflow(topic)` | POST `/api/v1/workflow/start` | 启动工作流 |
| `getWorkflowState(threadId)` | GET `/api/v1/workflow/state/{threadId}` | 查询工作流状态 |
| `resumeWorkflow(threadId, action, data)` | POST `/api/v1/workflow/resume/{threadId}` | 恢复工作流 |

### 2.3 流式输出（SSE）

文章生成使用 Server-Sent Events 实现流式输出：

```javascript
// 核心逻辑在 App.vue 中
const eventSource = new EventSource(`/api/v1/workflow/stream/${threadId}`, {
  headers: { Authorization: `Bearer ${token}` }
});

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // data.content 逐字追加，实现打字机效果
  this.articleContent += data.content;
};
```

### 2.4 样式风格

`frontend/src/style.css` 采用小红书风格配色：
- 主色：`#FF2442`（小红书红）
- 背景：`#F5F5F5`
- 卡片白色 + 圆角阴影

---

## 第三阶段：后端 API 层

### 3.1 入口文件：main.py

`app/main.py` 负责：

1. **setup_logging()** — 初始化 structlog 日志
2. **lifespan()** — 管理数据库连接池和 Checkpointer 生命周期
3. 注册路由、中间件配置

### 3.2 认证接口：auth.py

路径：`app/api/v1/auth.py`

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/v1/auth/register` | POST | 用户注册（用户名 + 密码） |
| `/api/v1/auth/login` | POST | 登录，返回 JWT token |
| `/api/v1/auth/me` | GET | 获取当前用户信息 |

**登录流程**：
1. 接收 `username` 和 `password`
2. 查询数据库验证用户
3. 使用 `core/security.py` 中的 `verify_password` 验证密码哈希
4. 使用 `create_access_token` 生成 JWT
5. 返回 `{"access_token": "xxx", "token_type": "bearer"}`

### 3.3 工作流接口：workflow.py

路径：`app/api/v1/workflow.py`

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/v1/workflow/start` | POST | 启动工作流（输入主题） |
| `/api/v1/workflow/state/{thread_id}` | GET | 查询工作流状态 |
| `/api/v1/workflow/resume/{thread_id}` | POST | 恢复工作流（选题/审核） |
| `/api/v1/workflow/stream/{thread_id}` | GET | SSE 流式获取文章生成内容 |

### 3.4 理解请求/响应模型

FastAPI 使用 Pydantic 定义请求和响应模型：

```python
# app/api/v1/auth.py
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# app/api/v1/workflow.py
class WorkflowStartRequest(BaseModel):
    topic_direction: str = Field(..., min_length=1, max_length=200)

class ResumeRequest(BaseModel):
    action: str  # "select_topic" | "approve" | "reject"
    data: dict | None = None
```

---

## 第四阶段：数据库层

### 4.1 用户模型：user.py

路径：`app/models/user.py`

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

### 4.2 SQLAlchemy 异步操作

路径：`app/core/db.py`

```python
# 异步引擎
engine = create_async_engine(DATABASE_URL, echo=False)

# 异步会话
async with AsyncSession(engine) as session:
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
```

### 4.3 LangGraph Checkpointer 表

`scripts/init_db.sql` 创建 LangGraph 持久化所需的表：
- `checkpoints` — 存储工作流状态快照
- `checkpoint_writes` — 存储状态写入记录

### 4.4 理解数据库连接配置

```env
# SQLAlchemy 异步连接（带 +asyncpg）
DATABASE_URL=postgresql+asyncpg://postgres:密码@localhost:5432/graph_xiaohongshu

# LangGraph Checkpointer 连接（psycopg 格式，不带 +asyncpg）
POSTGRES_URI=postgresql://postgres:密码@localhost:5432/graph_xiaohongshu
```

---

## 第五阶段：LangGraph 工作流

### 5.1 状态定义：state.py

路径：`app/graph/state.py`

```python
class WorkflowState(TypedDict):
    # 输入
    topic_direction: str                    # 用户输入的主题方向
    # 选题阶段
    topics: Annotated[list, operator.add]  # AI 生成的选题列表
    selected_topic: str | None             # 用户选中的选题
    # 写作阶段
    article_content: str                   # 生成的文章内容
    # 审核阶段
    review_result: str | None              # "approved" | "rejected"
    feedback: str | None                   # 驳回时的反馈意见
    # 配图阶段
    visual_points: list[str]               # 从文章提取的配图要点
    generated_images: list[str]             # 生成的图片路径
    # 元数据
    thread_id: str | None
    user_id: int | None
```

### 5.2 工作流组装：workflow.py

路径：`app/graph/workflow.py`

```python
from langgraph.graph import StateGraph, END, START

# 创建图
graph = StateGraph(WorkflowState)

# 添加节点
graph.add_node("plan_topics", plan_topics_node)     # 选题
graph.add_node("write_draft", write_draft_node)     # 写作
graph.add_node("human_review", human_review_node)   # 人工审核
graph.add_node("extract_visuals", extract_visuals_node) # 提取配图要点
graph.add_node("generate_images", generate_images_node) # 生成图片

# 添加边（定义流程走向）
graph.add_edge(START, "plan_topics")
graph.add_edge("plan_topics", "human_review")   # 选题后中断
graph.add_edge("human_review", "write_draft")    # 选题通过 → 写作
graph.add_edge("write_draft", "human_review")   # 写作后中断（审核）
graph.add_edge("extract_visuals", "generate_images")
graph.add_edge("generate_images", END)

# 编译（启用 PostgresSaver 检查点持久化）
compiled_graph = graph.compile(
    checkpointer=PostgresSaver(async_engine=engine)
)
```

### 5.3 节点详解

#### planner.py — 选题生成节点

```python
async def plan_topics_node(state: WorkflowState) -> dict:
    # 1. 构建 prompt（系统提示词 + 用户主题）
    prompt = build_planner_prompt(state["topic_direction"])

    # 2. 调用 LLM（JSON Mode，返回结构化选题）
    response = await llm_service.invoke(prompt, json_mode=True)

    # 3. 解析选题列表
    topics = parse_topics(response)

    # 4. 返回更新状态
    return {"topics": topics}
```

#### writer.py — 文章撰写节点

```python
async def write_draft_node(state: WorkflowState) -> dict:
    # 1. 构建 prompt（选题 + 可选的反馈意见）
    prompt = build_writer_prompt(state["selected_topic"], feedback=state.get("feedback"))

    # 2. 调用 LLM（流式输出）
    content = ""
    async for chunk in llm_service.invoke_stream(prompt):
        content += chunk
        # 通过 SSE 实时推送
        await sse_manager.send(thread_id, {"content": chunk})

    return {"article_content": content}
```

#### human.py — 人工审核节点（interrupt 原理）

```python
async def human_review_node(state: WorkflowState) -> Command:
    # 关键：interrupt() 会暂停工作流，等待外部恢复
    # 状态自动保存到 PostgreSQL
    # 前端通过 resume 接口传入 action（select_topic / approve / reject）

    if state.get("review_result") == "approved":
        return Command(goto="extract_visuals")
    elif state.get("review_result") == "rejected":
        return Command(goto="write_draft", resume=True)
    else:
        # 初始进入，等待用户选题
        interrupt("等待用户选择选题")
```

### 5.4 interrupt（人工介入）原理

1. 节点返回后，遇到 `interrupt()` → 工作流暂停
2. LangGraph Checkpointer 自动将状态保存到 PostgreSQL
3. 前端轮询或 SSE 检测到 `interrupt_info`，显示操作界面
4. 用户操作后，调用 `/resume` 接口
5. 工作流从中断点恢复，继续执行

### 5.5 子图：topic_selection.py

路径：`app/graph/subgraphs/topic_selection.py`

选题选择子图负责在多个 AI 生成的选题中做选择，包括：
- 显示选题列表供用户选择
- 支持用户自定义选题
- 处理选题冲突

---

## 第六阶段：AI 服务层

### 6.1 LLM 服务：llm_service.py

路径：`app/services/llm_service.py`

**核心职责**：
1. 初始化 ChatOpenAI 客户端（对接火山引擎 Doubao）
2. 调用 LLM 生成选题 / 撰写文章 / 提取配图要点
3. 支持流式输出（SSE）
4. 注入 PII 脱敏回调

```python
# 初始化模型（火山引擎 Doubao，兼容 OpenAI 接口）
llm = ChatOpenAI(
    model="doubao-pro-32k",
    openai_api_key=os.getenv("VOLCENGINE_API_KEY"),
    openai_api_base=os.getenv("VOLCENGINE_API_BASE")
)

# 普通调用
response = await llm_service.invoke(prompt, json_mode=True)

# 流式调用
async for chunk in llm_service.invoke_stream(prompt):
    yield chunk
```

### 6.2 图片服务：image_service.py

路径：`app/services/image_service.py`

**核心职责**：
1. 调用 Gemini Image API 生成配图
2. retry 机制容错
3. 保存图片到 `static/images/generated/`

```python
# 调用 Gemini Image API
image_url = await image_service.generate_image(
    prompt="一张简约风格的科技感插图，主题是人工智能",
    retry=3
)
```

### 6.3 多模型支持

LLM 服务支持不同模型处理不同任务：

| 任务 | 模型 | 说明 |
|------|------|------|
| 选题生成 | doubao-pro-32k | 结构化输出（JSON Mode） |
| 文章撰写 | doubao-pro-32k | 流式输出 |
| 视觉提取 | doubao-pro-32k | 从文章提取配图描述 |

### 6.4 PII 脱敏

`app/core/pii_anonymizer.py` 自动脱敏日志和 LLM 输入中的敏感信息：
- 邮箱：`*@*.com`
- 手机号：`138****5678`
- 身份证：`110101********1234`

---

## 第七阶段：安全与中间件

### 7.1 JWT 认证

路径：`app/core/security.py`

```python
# 创建 JWT
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=24)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")
    return encoded_jwt

# 验证 JWT
def verify_token(token: str) -> dict:
    payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    return payload
```

### 7.2 密码哈希

```python
from argon2 import PasswordHasher

ph = PasswordHasher()

# 注册时哈希
password_hash = ph.hash(password)

# 登录时验证
ph.verify(password_hash, input_password)
```

### 7.3 中间件：middleware.py

路径：`app/core/middleware.py`

1. **请求日志中间件** — 记录每个请求的 method、path、status、duration
2. **LangSmith 追踪**（可选） — AI 应用的可观测性

### 7.4 LangChain 回调：callbacks.py

路径：`app/core/callbacks.py`

在 LangChain 调用时注入 PII 脱敏回调：
- 脱敏输入 prompt
- 脱敏输出 response
- 写入结构化日志

---

## 第八阶段：本地运行与调试

### 8.1 功能验证清单

```
[ ] 前端页面能打开（http://localhost:5173）
[ ] 能注册新账号并登录
[ ] 输入主题"AI技术"，能看到选题生成
[ ] 能选择一个选题
[ ] 能看到文章流式生成（SSE）
[ ] 能审核文章并通过
[ ] 能看到配图生成
[ ] 数据库中能看到 LangGraph 的 checkpoint 数据
```

### 8.2 调试技巧

| 问题 | 调试方法 |
|------|---------|
| 后端报错 | 看 uvicorn 控制台输出的 traceback |
| LLM 返回格式错误 | 打印 prompt 看实际发送的内容 |
| 前端接口调用失败 | 浏览器 F12 → Network → 找失败的请求 |
| 数据库问题 | pgAdmin 查看表数据 |
| SSE 流式不工作 | 用 curl 测试 SSE 端点 |

**测试 SSE 接口**：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/workflow/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-token>" \
  -d '{"topic_direction": "Python 编程"}'
```

### 8.3 扩展建议

| 方向 | 具体任务 |
|------|---------|
| 选题优化 | 添加"选题评分"节点，让 LLM 评估每个选题的潜力 |
| 多语言 | 支持英文文章生成 |
| 图片风格 | 让用户选择配图风格（科技感/插画风/照片风） |
| 数据分析 | 统计生成文章的数量、字数、耗时 |
| 部署上线 | 用 Docker + Nginx 部署到云服务器 |
| 自动化测试 | 写 pytest 测试用例覆盖核心流程 |

---

## 附录

### A. 常用命令速查

```bash
# Python 虚拟环境
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 后端
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev

# 数据库
psql -U postgres -d graph_xiaohongshu
```

### B. 推荐工具

| 工具 | 用途 |
|------|------|
| VS Code | 代码编辑器（主力开发工具） |
| pgAdmin | PostgreSQL 图形化管理 |
| Postman / Insomnia | API 调试工具 |
| DBeaver | 数据库客户端 |
| Vue DevTools | Vue 浏览器调试插件 |

### C. 遇到问题怎么办

1. **看报错信息**：错误信息本身就是答案
2. **搜索引擎**：CSDN、知乎、Stack Overflow
3. **AI 助手**：用 Kimi/ChatGPT 解释代码和报错
4. **官方文档**：FastAPI、LangGraph、Vue 都有中文文档
5. **项目 README**：本项目的 README.md 有详细说明
6. **问人**：技术社区提问要附上完整的报错信息和代码片段
