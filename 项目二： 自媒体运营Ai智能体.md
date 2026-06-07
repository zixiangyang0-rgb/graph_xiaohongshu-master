# 项目二： 自媒体运营Ai智能体

# 仓库地址

没有cursor的同学，可以直接拉代码跑，不影响学习。

建议自己玩一下cursor，试用期就靠它了\!

https://gitee\.com/mood6666/graph\_xiaohongshu

# 如何跟我的Claude4\.5环境一致？

1. 买VPN

2. 买Claude4\.5 正版

3. VPN区域选海外





# 现代程序员的工作方式：

1. Ai干活

2. 逐行解读

# 提示词（需求文档）：

我想用langGraph1\.0做一个自媒体运营项目，我们是一家教育培训公司，用于在小红书进行运营。

我们主要是做Ai编程培训（Ai应用开发、Ai训练师），需要每天根据用户喜欢的内容，生成技术干货类图片和技术分享文章。

核心功能：

1. Ai帮我进行选题，给几个选题我们进行选择，然后再生成内容

2. 选好题之后，Ai生成文案，这里需要人工介入审核，如果有问题就继续改，重新生成文案，确认再进行下一步

3. 根据文案内容生成3\-5张图片，比如说文案有1000字，图片可能是这1000字的文案的精简版

4. 同时这里生成的文案也可以在微信公众号进行发布，你可以理解为，生成的图片发小红书，文案内容发布到微信公众号



涉及的核心技术栈：

1. langGraph

2. PostgreSQL本地数据库持久化数据

3. LLM Api

4. 前端界面、后台服务、Ai服务

5. 语言Python

6. Fast Api



请你帮我进行方案设计，不用写代码。

只用设计代码结构，需要未来功能好扩展。





![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=OWI5N2IxZWIzNTg5MmRlNzlkM2YyMzI2ZGIyMWM0ODZfZGQyNDFkMzVhOGUxMjM0NzEwOGJjNzRlZDU5NDE4MzVfSUQ6NzU5OTY4MDcyNzQ1MzcxNTY1M18xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)





# 项目思路

1. 写提示词

2. 丢给Gemini做技术方案

3. **审核方案，非常重要**

    1. 大方向ok就行，架构设计ok就行

    2. 细节有瑕疵可以后面让Ai写代码的时候再改







# 第一步 Gemini方案设计

为了保证未来的扩展性（例如增加新的平台、更换LLM模型、增加视频生成功能），我们将系统分为四层。

- **表现层 \(Frontend ****前端****\):** 用于运营人员交互（选题、审稿、查看图片）。

- **接入层 \(FastAPI ****后台****\):** 处理HTTP请求，管理WebSocket（可选，用于流式输出），作为业务逻辑的入口。

- **核心编排层 \(LangGraph Core ****Ai流程****\):** 系统的“大脑”。定义状态机、节点逻辑、流转规则。

- **基础设施层 \(Infrastructure\):**

    - **PostgreSQL:** 存储业务数据（用户、项目） \+ **LangGraph Checkpoints \(记忆持久化\)**。

    - **Model Provider:** LLM \(GPT/Claude/DeepSeek\) \+ Image Gen \(DALL\-E 3/Midjourney/Flux\)。



我们需要定义一个全局状态 `AgentState`，在各个节点之间传递数据。

```Python
from typing import TypedDict, List, Annotated
import operator

class ArticleState(TypedDict):
    # 输入信息
    topic_direction: str          # 用户输入的初始方向（如“LangChain新特性”）
    
    # 选题阶段
    proposed_topics: List[str]    # AI生成的备选标题列表
    selected_topic: str           # 用户最终选择的标题
    
    # 写作阶段
    draft_content: str            # AI生成的文章初稿
    human_feedback: str           # 人工审核的修改意见
    final_content: str            # 最终确认的文章内容
    
    # 图片生成阶段
    image_prompts: List[str]      # 根据文章拆解的图片提示词
    image_urls: List[str]         # 生成的图片链接
    
    # 流程控制
    current_status: str           # 当前状态 (planning, writing, reviewing, completed)
    messages: Annotated[List[BaseMessage], operator.add] # 对话历史
```

### 节点流转图 \(Graph Workflow\)

这个流程包含两次关键的 **`interrupt_before`** \(中断\)，等待人工介入。

**节点 \(Nodes\) 说明：**

1. **`plan_topics`**: 根据 `topic_direction` 调用 LLM 生成 3\-5 个技术干货选题。

2. **`human_select_node`** \(虚拟节点/中断点\): 系统暂停，等待 API 传入用户选择的 `selected_topic`。

3. **`generate_draft`**: 根据 `selected_topic` 撰写技术长文。如果是“修改模式”，会参考 `human_feedback` 进行重写。

4. **`human_review_node`** \(虚拟节点/中断点\): 系统暂停，将草稿返回前端。用户选择“通过”或“修改意见”。

5. **`extract_visual_points`**: 核心逻辑。将 `final_content` \(如1000字\) 提炼为 3\-5 个关键知识点（用于做小红书图片的文字）。

6. **`generate_images`**: 并行调用绘图模型，生成技术配图（可叠加文字）。

**边 \(Edges\) 与 条件逻辑：**

- `plan_topics` \-\> **INTERRUPT** \-\> `generate_draft` \(携带用户选择\)

- `generate_draft` \-\> **INTERRUPT** \-\>

    - \(条件分支\) 如果用户反馈是 "Approve" \-\> `extract_visual_points`

    - \(条件分支\) 如果用户反馈是 "Reject/Revise" \-\> `generate_draft` \(回滚重写\)

- `extract_visual_points` \-\> `generate_images` \-\> `END`

### 项目代码结构设计 \(Project Layout\)

为了支持未来的扩展（比如增加视频生成、多Agent协作），建议采用 **模块化单体 \(Modular Monolith\)** 结构。

```Bash
project_root/
├── app/
│   ├── api/                  # FastAPI 路由层
│   │   ├── v1/
│   │   │   ├── workflows.py  # 触发工作流、获取状态
│   │   │   └── assets.py     # 图片、文章资源管理
│   │   └── deps.py           # 依赖注入 (DB, LLM clients)
│   │
│   ├── core/                 # 核心配置
│   │   ├── config.py         # 环境变量
│   │   └── database.py       # PostgreSQL 连接池
│   │
│   ├── graph/                # LangGraph 核心逻辑 (业务隔离)
│   │   ├── state.py          # State 定义
│   │   ├── nodes/            # 各个独立节点的逻辑
│   │   │   ├── writer.py     # 写作 Agent
│   │   │   ├── visualizer.py # 图片提示词 Agent
│   │   │   └── reviewer.py   # 自动质检逻辑(可选)
│   │   ├── edges.py          # 条件路由逻辑
│   │   └── workflow.py       # Graph 组装与编译
│   │
│   ├── services/             # 外部服务适配器 (解耦层)
│   │   ├── llm_service.py    # 封装 OpenAI/Claude 调用
│   │   ├── image_service.py  # 封装 DALL-E/MJ 调用
│   │   └── social_service.py # (未来) 封装公众号/小红书发布API
│   │
│   └── models/               # 数据库模型 (SQLAlchemy)
│       └── workflow_record.py# 记录每次运行的元数据
│
├── data/                     # 本地持久化目录 (如不做云存储)
├── main.py                   # 启动入口
├── requirements.txt
└── .env
```

### 数据持久化方案 \(PostgreSQL\)

LangGraph 1\.0 的 `PostgresSaver` 是关键。你不需要自己手动把每一步的对话存入业务表，LangGraph 会自动序列化状态。

我们需要两个层面的存储：

1. **LangGraph 状态存储 \(AsyncPostgresSaver\):**

- **用途:** 存储 Checkpoints（断点）。允许你在“选题”后关掉浏览器，第二天回来继续“生成文案”，上下文依然存在。

- **表结构:** LangGraph 库会自动创建 `checkpoints` 表 \(thread\_id, checkpoint\_id, state\_data\)。

2. **业务数据存储 \(Business Tables\):** 用于前端列表展示、历史归档。

- **Table: ****`content_projects`**

    - `id`: UUID

    - `user_id`: 操作员ID

    - `thread_id`: **关键字段**，关联 LangGraph 的 thread\_id

    - `topic`: 最终确定的选题

    - `platform`: \(Enum\) 小红书/公众号

    - `status`: \(Enum\) 选题中/撰稿中/审核中/生成图片中/已完成

    - `article_content`: JSON \(存储最终文案\)

    - `image_assets`: JSON \(存储图片URL列表\)

    - `created_at`: Timestamp

### API 交互流程 \(FastAPI 实现逻辑\)

前端如何与 LangGraph 交互？主要通过 `thread_id`。

**Step 1: 发起任务**

- `POST /api/v1/workflows/start`

- **Body:** `{"topic_direction": "AI Agent开发教程"}`

- **Action:** 创建 thread\_id，运行 Graph 直到遇到第一个 `interrupt` \(即生成完选题后暂停\)。

- **Return:** `thread_id`, `next_step`: "human\_select", `payload`: \[选题A, 选题B, 选题C\]

**Step 2: 人工选题**

- `POST /api/v1/workflows/{thread_id}/resume`

- **Body:** `{"action": "select_topic", "data": "AI Agent开发教程-LangGraph实战"}`

- **Action:** 使用 `graph.update_state` 更新状态，然后 `graph.stream(..., command=Command(resume=...))` 继续运行直到下一个断点（文案生成完毕）。

**Step 3: 人工审稿**

- `POST /api/v1/workflows/{thread_id}/resume`

- **Body:** `{"action": "review", "status": "reject", "feedback": "第二段太罗嗦，要加代码示例"}`

- **Action:** 路由回退到写作节点。



### 扩展性设计亮点

1. **AI 服务抽象化 \(****`services/`****\):**

    - 目前你可能用 OpenAI 生成文案。未来如果有针对编程更好的模型（如 DeepSeek Coder），你只需修改 `llm_service.py`，LangGraph 的逻辑层不需要动。

2. **图片生成的解耦:**

    - `extract_visual_points` 节点只负责生成 "Prompt"。

    - `generate_images` 节点负责调 API。如果未来需要生成的不是图片而是**技术代码截图**（Carbon 等工具），只需替换这个节点的具体实现，流程不变。

3. **多渠道适配:**

    - 小红书需要图片\+短文，公众号需要长文。

    - 在 Graph 中可以设计并行分支：文案确认后，分支 A 去生成公众号排版格式，分支 B 去做小红书图片摘要。









# 第二步 让Gemini生成提示词

```Python
你的方案我看了，没问题，非常好。
我准备让claude4.5帮我实现，请帮我生成给Claude的完整提示词。
直接输出完整的md格式，先输出服务端的，前端提示词暂时不给。
```

```Markdown
# Role (角色设定)
你是一位精通 Python 的高级后端架构师，专注于 Generative AI 工作流开发。
你非常熟悉 **LangGraph(1.0 架构)**、`FastAPI`、`PostgreSQL` 以及异步编程模式。

# Goal (项目目标)
为一家教育培训公司构建“AI 内容运营助手”的后端服务。
**核心目标：** 实现一个自动化的工作流，用于生成微信公众号技术文章和小红书配图文案。
**关键特性：** 必须包含 **Human-in-the-loop (人工介入)** 机制，允许用户在“选题阶段”和“审稿阶段”介入决策。

# Tech Stack (技术栈)
1.  **Language**: Python 3.10+
2.  **Web Framework**: FastAPI (Async)
3.  **Orchestration**: **LangGraph 1.0+** (必须使用 `StateGraph`, `AsyncPostgresSaver` 进行持久化, 以及 `interrupt_before` 中断模式)。
4.  **Database**: 本地 PostgreSQL (不使用 Docker，假设本地已安装，连接串为 localhost)。
5.  **ORM**: SQLAlchemy (Async) + Pydantic。
6.  **Services**: 使用 Mock (模拟) 服务来代替真实的 LLM/绘图 API，以便快速跑通逻辑。
请注意langChain和langGraph的版本一定要1.0以上。


# Workflow Logic (工作流逻辑)
这是一个包含循环的状态机（State Machine）：
1.  **Start** -> 节点: `plan_topics` (AI 生成 3-5 个选题)。
2.  **INTERRUPT (中断)**: 等待人工选题。
3.  **Human Action**: 用户通过 API 选择一个选题（更新 State）。
4.  **Resume** -> 节点: `write_draft` (AI 根据选题写长文)。
5.  **INTERRUPT (中断)**: 等待人工审稿。
6.  **Human Action**: 用户通过 API 提交审核结果。
    * *情况 A (通过)*: -> 节点: `extract_visuals` (提炼图片点) -> 节点: `generate_images` -> **End**。
    * *情况 B (驳回)*: -> 更新 State 中的反馈意见 -> 路由回退到 节点: `write_draft` (重写)。

# Project Structure (项目结构)
请保持模块化设计，**先在本地跑PostgreSQL **。请严格遵循以下目录结构：
```text
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       └── workflow.py      # 核心接口：启动、查看状态、恢复运行
│   ├── core/
│   │   ├── config.py            # 配置 (数据库URL等)
│   │   └── db.py                # 数据库连接 (AsyncEngine)
│   ├── graph/                   # LangGraph 核心逻辑
│   │   ├── state.py             # State 定义 (TypedDict)
│   │   ├── nodes/               # 节点逻辑 (Planner, Writer, Visualizer)
│   │   ├── workflow.py          # Graph 组装 & Checkpointer 配置
│   │   └── utils.py             # 用于初始化 Checkpointer 数据库表的工具函数
│   ├── services/                # Mock 服务
│   │   ├── llm_mock.py
│   │   └── image_mock.py
│   └── main.py                  # App 入口
├── requirements.txt
└── .env

Implementation Instructions (分步实施指南)
请按照以下步骤生成代码。请确保使用 **LangGraph 1.0+ 的最新语法**。

Step 1: 依赖与配置
**requirements.txt**: 必须包含 fastapi, uvicorn, langgraph, langchain-openai, langchain-postgres, psycopg-binary, sqlalchemy, pydantic-settings。
**.env**: 提供 DATABASE_URL 模板 (例如: postgresql+asyncpg://postgres:password@localhost:5432/aicontent)。
**app/core/db.py**: 配置 SQLAlchemy 的 AsyncSession。

Step 2: 状态定义 (app/graph/state.py)
使用 TypedDict 定义 AgentState，必须包含：
topic_direction: str (用户初始输入)
generated_topics: List[str] (AI 推荐的选题)
selected_topic: str (用户选中的)
article_content: str (文章内容)
review_feedback: str (用户的修改意见)
visual_points: List[str] (图片文案)
image_urls: List[str] (图片链接)
status: str (当前状态描述)

Step 3: Mock 服务 (app/services/)
为了开发方便，请实现 MockLLMService：
plan_topics: 返回固定列表 ["LangGraph入门", "AI Agent实战", "Python高并发"]。
write_draft: 返回一段 500 字的伪技术文章。如果检测到 review_feedback，请在文章开头加上 "【根据意见已修改】" 字样以验证逻辑。
generate_images: 返回占位符图片 URL。

Step 4: 构建 LangGraph (app/graph/workflow.py)
**这是最关键的部分。**
**持久化 (Checkpointer)**: 使用 langgraph.checkpoint.postgres.aio.AsyncPostgresSaver。
*关键要求*: 请编写一个 setup_checkpointer 函数，确保在应用启动时自动在本地数据库创建 checkpoints 所需的表结构。
**节点 (Nodes)**: 调用上面的 Mock 服务。
**图逻辑 (Graph Logic)**:
使用 interrupt_before=["human_selection_node", "human_review_node"] (或者你认为在 1.0 中更优的写法，如明确的 Human Node)。
**条件边 (Conditional Edge)**: 在审稿节点之后，判断是 Approve 还是 Reject，决定是向下走还是回退。

Step 5: FastAPI 接口 (app/api/v1/workflow.py)
实现 3 个核心接口来驱动 Graph：

**POST /start**:
接收 topic_direction。
调用 graph.invoke，运行直到第一个中断点。
返回 thread_id 和当前的选题列表。

**GET /state/{thread_id}**:
调用 graph.get_state(config) 获取当前快照（用于前端展示草稿或选题）。

**POST /resume/{thread_id}**:
接收 action (比如 "select_topic" 或 "approve") 和 data。

**核心逻辑**:
使用 graph.update_state(config, {"selected_topic": ...}) 更新用户的选择。
使用 graph.stream(None, config) 恢复运行，直到下一个中断或结束。

Step 6: 入口与初始化 (main.py)
初始化 FastAPI。
使用 @asynccontextmanager 定义 lifespan。在启动时，必须初始化数据库连接池并确保持久化所需的表 (checkpoints) 已经创建。
Constraints (约束条件)
**Local DB**: 代码应假设连接的是本地 localhost 的 Postgres，无需 Docker 配置，但要提供 SQL 建表语句或 Python 自动建表逻辑。
**LangGraph Version**: 必须严格遵循 LangGraph 1.0 语法（例如 State Management 和 Persistence 的正确用法）。
**Code Quality**: 代码必须包含完整的 Type Hints (类型注解) 和 异常处理。

请生成完整、可直接运行的代码结构，不需要过多的解释性废话，直接给我代码。


```




## 安装python依赖

安装依赖

```Python
# 在终端进入项目 backend 目录后执行 
pip install -r requirements.txt
```



升级依赖

```Python
pip install -U --upgrade-strategy eager -r requirements.txt

pip freeze > requirements.txt
```

```Markdown
*# Web Framework*
fastapi>=0.115.0
uvicorn[standard]>=0.30.0

*# LangGraph & LangChain (1.0+)*
langgraph>=0.2.0
langchain>=0.3.0
langchain-core>=0.3.0
langchain-openai>=0.2.0
langgraph-checkpoint-postgres>=2.0.0

*# Database*
psycopg[binary,pool]>=3.2.0
psycopg-pool>=3.2.0
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0

*# Configuration & Validation*
pydantic>=2.0.0
pydantic-settings>=2.0.0
python-dotenv>=1.0.0

*# Utilities*
httpx>=0.27.0

```



# 第三步 代码开始肯定跑不通

让Claude4\.5数据全部mock  让我们先能运行起来

```Python
我现在准备运行代码main.py了，数据库和LLM Api暂时还没配置，
你把数据全部mock，暂时不要改技术栈，数据能写死，先写死。先让我把项目能运行起来。你自己进行测试，跑通为止
```





## 第四步 Main\.py核心逻辑解析

生命周期管理



*yield之前的   运行执行*

yield之后的  服务器停掉运行

```Python
@asynccontextmanager
async def **lifespan**(*app*: FastAPI) -> AsyncGenerator[None, None]:
    """
    应用生命周期管理
    
    启动时：
    - 初始化数据库连接
    - 初始化 LangGraph Checkpointer（创建必要的表）
    
    关闭时：
    - 关闭数据库连接
    - 关闭 Checkpointer 连接池
    """
    *# 启动时执行*
    print(f"🚀 正在启动 {settings.app_name}...")
    
    *try*:
        *# 初始化 SQLAlchemy 数据库*
        print("📦 初始化数据库连接...")
        *await* init_db()
        
        *# 初始化 LangGraph Checkpointer*
        print("🔧 初始化 LangGraph Checkpointer...")
        *await* setup_checkpointer()
        print("✅ Checkpointer 表结构已创建/验证")
        
        print(f"✅ {settings.app_name} 启动成功!")
        print(f"📖 API 文档: http://localhost:8000/docs")
        
    *except* Exception *as* e:
        print(f"❌ 启动失败: {str(e)}")
        *raise*
    
    *yield*
    
    *# 关闭时执行*
    print(f"🛑 正在关闭 {settings.app_name}...")
    
    *try*:
        *await* close_checkpointer()
        *await* close_db()
        print("✅ 资源已释放")
    *except* Exception *as* e:
        print(f"⚠️ 关闭时出错: {str(e)}")

```



# 第四步 workflow入口注册

```Python
*# 注册路由*
app.include_router(workflow_router, *prefix*="/api/v1")

```

## graph流程设计

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=YzgyM2M1Zjg4ZGFhNmMxMjJlMDZkMGQ2NWVmZjdlNThfZjdmNmQ0ZWI0N2RjMjViMWEwNWRkMmZmZDFmYzU3NTdfSUQ6NzU5OTk4NjMxMzU1NDc1ODg2M18xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)





# 第五步  start   开始Agent接口，进入选题审核

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=YTY2NGQ1MDNiNjZiZjI4NjI3MDFhMDRkZGEyYmRkOGRfMWM0NjQ3YWRiZTNhMDA3YWVjMTY2NTUyMjdhZjg1ZTZfSUQ6NzYwMDA0ODg1MTU5NjM5Nzc2NV8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)



请求参数：
填写你要的大方向

```Python
{
  "topic_direction": "测试"
}
```

```JSON
{
  "thread_id": "247a8e83-e7af-4354-9253-9c800131182f",
  "status": "topics_generated",
  "generated_topics": [
    "LangGraph入门：构建你的第一个AI工作流 - 测试方向",
    "AI Agent实战：从零搭建智能助手 - 测试方向",
    "Python高并发编程：asyncio深度解析 - 测试方向",
    "RAG系统设计：让AI更懂你的业务",
    "Prompt Engineering最佳实践指南"
  ],
  "message": "工作流已启动，请选择一个选题继续",
  "interrupt_info": {
    "message": "请从以下选题中选择一个",
    "options": [
      "LangGraph入门：构建你的第一个AI工作流 - 测试方向",
      "AI Agent实战：从零搭建智能助手 - 测试方向",
      "Python高并发编程：asyncio深度解析 - 测试方向",
      "RAG系统设计：让AI更懂你的业务",
      "Prompt Engineering最佳实践指南"
    ],
    "action_required": "select_topic"
  }
}
```

thread\_id： 调用start接口，python服务端生成的随机字符串

status： graph\.invoke  在node节点中 return的数据改的

generated\_topics： 先是在node节点中LLM生成的，然后return改的

message：手动构造的

interrupt\_info： 在node节点human\_select\_topic，调用interrupt生成的





# 第六步  "/resume/\{thread\_id\}" 进入文章草稿审核流程



发起请求

```Python
{
  "action": "select_topic",
  "data": {
    "selected_topic": "LangGraph入门：构建你的第一个AI工作流 - 测试方向"
  }
}
```



响应

```JSON
{
  "thread_id": "247a8e83-e7af-4354-9253-9c800131182f",
  "status": "draft_generated",
  "message": "文章草稿已生成，请审核",
  "next_nodes": [
    "human_review"
  ],
  "is_completed": false,
  "result": null,
  "interrupt_info": {
    "message": "请审核以下文章内容",
    "article_preview": "# LangGraph入门：构建你的第一个AI工作流 - 测试方向\n\n## 引言\n\n在当今快速发展的技术领域，LangGraph入门：构建你的第一个AI工作流 - 测试方向 已经成为开发者必须掌握的核心技能之一。本文将深入探讨这一主题，帮助读者全面理解其核心概念和实践应用。\n\n## 核心概念\n\n### 什么是 LangGraph入门？\n\nLangGraph入门 是一种创新的技术范式，它改变了我们构建和部署智能应用的方式。通过合理运用这项技术，开发者可以显著提升开发效率和应用性能。\n\n### 关键特性\n\n1. **高效性**：通过优化的算法和架构设计，实现高性能处理\n2. **可扩展性**：支持横向和纵向扩展，适应不同规模的应用场景\n3. **易用性**：提供简洁的 API 和丰富的文档支持\n4. **可靠性**：内置错误处理和重试机制，确保系统稳定运行\n\n## 实战案例\n\n让我们通过一个具体的例子来理解如何在实际项目中应用这些概念：\n\n```python\n# 示例代码\nfrom example_lib import ExampleClass\n\ndef main():\n    insta...",
    "action_required": "review",
    "options": [
      "approve",
      "reject"
    ]
  }
}
```

next\_nodes： 中断的node节点，恢复后会再走一次

注意的点： graph\.invoke的返回值，是走到流程走不动为止决定的。





# 第七步： 流程结束

```SQL
{
  "thread_id": "247a8e83-e7af-4354-9253-9c800131182f",
  "status": "completed",
  "message": "工作流已完成",
  "next_nodes": [],
  "is_completed": true,
  "result": {
    "article_content": "# LangGraph入门：构建你的第一个AI工作流 - 测试方向\n\n## 引言\n\n在当今快速发展的技术领域，LangGraph入门：构建你的第一个AI工作流 - 测试方向 已经成为开发者必须掌握的核心技能之一。本文将深入探讨这一主题，帮助读者全面理解其核心概念和实践应用。\n\n## 核心概念\n\n### 什么是 LangGraph入门？\n\nLangGraph入门 是一种创新的技术范式，它改变了我们构建和部署智能应用的方式。通过合理运用这项技术，开发者可以显著提升开发效率和应用性能。\n\n### 关键特性\n\n1. **高效性**：通过优化的算法和架构设计，实现高性能处理\n2. **可扩展性**：支持横向和纵向扩展，适应不同规模的应用场景\n3. **易用性**：提供简洁的 API 和丰富的文档支持\n4. **可靠性**：内置错误处理和重试机制，确保系统稳定运行\n\n## 实战案例\n\n让我们通过一个具体的例子来理解如何在实际项目中应用这些概念：\n\n```python\n# 示例代码\nfrom example_lib import ExampleClass\n\ndef main():\n    instance = ExampleClass()\n    result = instance.process()\n    print(f\"处理结果: {result}\")\n\nif __name__ == \"__main__\":\n    main()\n```\n\n## 最佳实践\n\n在实际开发中，我们建议遵循以下最佳实践：\n\n- 始终进行充分的测试\n- 注重代码的可读性和可维护性\n- 合理使用设计模式\n- 持续学习和更新知识体系\n\n## 总结\n\n通过本文的学习，相信读者已经对 LangGraph入门：构建你的第一个AI工作流 - 测试方向 有了更深入的理解。技术的发展日新月异，保持学习的热情是每个开发者成长的关键。\n\n---\n\n*本文由 AI 内容助手生成，仅供参考学习使用。*\n",
    "visual_points": [
      "技术架构流程图：展示核心组件之间的交互关系",
      "代码示例截图：突出关键实现细节",
      "对比图表：新旧方案的性能对比",
      "思维导图：知识点总结和梳理",
      "封面图：吸引眼球的主题配图"
    ],
    "image_urls": [
      "https://via.placeholder.com/800x600/3498db/ffffff?text=Image_1_e3c1b003",
      "https://via.placeholder.com/1200x630/e74c3c/ffffff?text=Image_2_439ca2e8",
      "https://via.placeholder.com/600x400/2ecc71/ffffff?text=Image_3_23efd611",
      "https://via.placeholder.com/1080x1080/9b59b6/ffffff?text=Image_4_5076583d",
      "https://via.placeholder.com/750x500/f39c12/ffffff?text=Image_5_7e31f453"
    ]
  },
  "interrupt_info": null
}
```



# 第八步： 拒绝流程梳理

注意： 我们在human\_review\_node人工介入的，不管同意还是拒绝，human\_review\_node会再重新走一次！！！



当拒绝之后，流程会重新回到write\_draft\_node，带上修改意见，让LLM重新生成。

生成再看你是拒绝还是同意。

如果拒绝，就重复以上流程，改到满意为止。

```Python
workflow.add_node("plan_topics", plan_topics_node)
    workflow.add_node("human_select_topic", human_select_topic_node)
    workflow.add_node("write_draft", write_draft_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("extract_visuals", extract_visuals_node)
    workflow.add_node("generate_images", generate_images_node)
    
```

做Ai应用要点

1. 一定一定 是先写Ai的服务端逻辑，再写前端





# 项目学习、版本切换

这个版本是mock数据，完全状态

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MDYzMWJmNTZjNjhiN2YwNjY3NTBjODdlNTZhMTc0NGZfMjRkMGI3NDZmNDU1YWVjOTZkOGJiZDgyY2U0N2MxZDZfSUQ6NzYwMDA2NTExNTQ5NjUxNjgzMF8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)



如果你只是想查看某个版本的效果，并不打算修改代码，使用 `checkout` 或 `switch`。

```Python
git checkout <commit_id>
# 或者（Git 新版本推荐）
git switch --detach <commit_id>
```

如果看完想恢复到最新

```Python
git checkout main
# 或者
git switch main
```



# 第九步 把LLM接入  豆包1\.8

踩了个小坑，你在让Ai干活的时候，不要动代码。

4x模式的本质是Ai写多个 4个版本竞争，我感觉没必要。



提示词

```Python
请你帮我把项目中LLM部分接入Api。
暂时只接文字部分，图片部分逻辑先不动。
.env帮我预留填写key的位置
以下是火山引擎的LLM创建代码示意
llm = ChatOpenAI(
    model="doubao-seed-1-8-251228",
    temperature=0,
    api_key=api_key,
    base_url="https://ark.cn-beijing.volces.com/api/v3",
)
```



## 图片LLM 接入示意

Doubao\-Seedream\-4\.5文档

https://www\.volcengine\.com/docs/82379/1824121?lang=zh

```Python
import os
from openai import OpenAI
# 请确保您已将 API Key 存储在环境变量 ARK_API_KEY 中 
# 初始化Ark客户端，从环境变量中读取您的API Key 
client = OpenAI( 
    # 此为默认路径，您可根据业务所在地域进行配置 
    base_url="https://ark.cn-beijing.volces.com/api/v3", 
    # 从环境变量中获取您的 API Key。此为默认方式，您可根据需要进行修改 
    api_key=os.environ.get("ARK_API_KEY"), 
) 
 
imagesResponse = client.images.generate( 
    model="doubao-seedream-4-5-251128", 
    prompt="星际穿越，黑洞，黑洞里冲出一辆快支离破碎的复古列车，抢视觉冲击力，电影大片，末日既视感，动感，对比色，oc渲染，光线追踪，动态模糊，景深，超现实主义，深蓝，画面通过细腻的丰富的色彩层次塑造主体与场景，质感真实，暗黑风背景的光影效果营造出氛围，整体兼具艺术幻想感，夸张的广角透视效果，耀光，反射，极致的光影，强引力，吞噬",
    size="2K",
    response_format="url",
    extra_body={
        "watermark": True,
    },
) 
 
print(imagesResponse.data[0].url)
```



## 代码片段解读

相当于异步执行\_generate\_single\_image\_sync

```Python
url = *await* loop.run_in_executor(
            None,
            *self*._generate_single_image_sync,
            *prompt*,
            *size*,
        )
        *return* url
```



# 第 10步 前端界面

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ZWM0ZjRkZTgwYjhjNzUyMDA1ODhjNjU0NGRlMzdkODVfNjc0ODY4YTc3MjEwMTkwZTQ4NWEyMTY3MTk5MjY4YjZfSUQ6NzYwMDQwMjg0OTg4OTI3NTA5OF8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)

提示词

```Python
现在服务端的部分已经完全跑通了，我想帮你帮我写前端界面，
怎么给你提示词比较好，你有没有什么建议？
```



# 第11步 PostgreSQL同步Checkpointer数据

核心步骤

1. 使用langgraph官方提供的AsyncPostgresSaver创建连接池 ，返回值就是\_checkpointer

2. 将\_checkpointer和graph关联

3. graph运行自动写入checkpointer

4. 读取的，也是根据config从graph中查询graph\.aget\_state



提示词

```Python
我想使用PostgreSQL持久化Graph流程，让用户关闭页面再进来也可以保持上次的状态。
我先使用本地的PostgreSQL数据库跑通，请你帮我干活。还需要我提供哪些信息也可以问我
```



## 环境安装

安装数据库

https://www\.postgresql\.org/download/windows/

初始密码：123456

默认端口： 5432

这个可以不装

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=OGFmZjAxZmUwYzBiOTA3ZmUwZTc2MTkwNWU3ZGEwZGNfN2I5MzIzNDM2MWNjMjEwZDIxMjRjMzgwZTUxNWE4NTVfSUQ6NzYwMDQwOTU2ODY1MjY0MzU0MV8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)



## 进入pgAdmin4

初始密码：123456

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MTllMWY0ZjBkN2Y3OTU3NjJiNjNhYTdmNjk1YzAyNThfZmI3YTAxZDZlNjcyMDY5NDIzOWY5Y2IzZDUwYWFkNWRfSUQ6NzYwMDQxMzYyOTcwODA2MTYzM18xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)





创建数据库langgraph\_db

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ZjdiODZiMzA2ZDViY2QyYTdlODFhM2NkMzQ0ZmRhYjNfMzhmYjY3MDNlOWViOTFlZWUyOWIwMDc5OTMwYTMwZTJfSUQ6NzYwMDQxNzE4NjIyNTgwMjQzNF8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)



## 重启电脑之后数据库可能连不上，解决办法

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MzE3YWE4MWExOGJlYTIzZmM2NzVmMjRmMGNiZWRlYzlfNTBhMjc1ZjQ0OTkxZThiOTI3Yjc4Y2E3MzU4ZTExYmFfSUQ6NzYwMTM1NDkzNjkwMjk3ODc2N18xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)



## 逐行解读 PostGreSQL同步逻辑

## 一、Checkpointer 初始化逻辑 \(app/graph/utils\.py\)

这是数据持久化的核心模块，负责管理 LangGraph 的 Checkpointer（检查点保存器）。

### 1\. 导入和配置部分 \(第1\-29行\)

```Python
import psycopg
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.base import BaseCheckpointSaver
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.config import settings

# 是否使用 Mock 模式 (内存 Checkpointer)
# 通过环境变量 USE_MOCK_CHECKPOINTER 控制，默认为 False（使用 PostgreSQL）
USE_MOCK_CHECKPOINTER = os.getenv("USE_MOCK_CHECKPOINTER", "false").lower() == "true"

# 全局 Checkpointer 实例
_checkpointer: Union[MemorySaver, AsyncPostgresSaver, None] = None
# 全局连接池实例 (PostgreSQL 模式使用)
_connection_pool: AsyncConnectionPool | None = None
```

关键点解读：

- 第24行：通过环境变量 USE\_MOCK\_CHECKPOINTER 控制持久化模式

- true → 使用内存存储（MemorySaver），数据不持久化

- false（默认）→ 使用 PostgreSQL 持久化

- 第27\-29行：定义两个全局变量

- \_checkpointer：Checkpointer 单例实例

- \_connection\_pool：PostgreSQL 连接池（仅 PostgreSQL 模式使用）



```Python
from psycopg_pool import AsyncConnectionPool
```

## 什么是连接池？

`psycopg_pool` 是一个专门为 Python 异步程序（如 FastAPI、LangChain、LangGraph）设计的**数据库连接池**。

第三库，标准数据量连接池

### 为什么要用它？（核心痛点）

如果你每处理一个 AI 请求都去重新连接一次数据库，会非常慢且消耗资源：

- **传统方式：** “你好” \-\> 建立连接 \-\> 存入数据库 \-\> 断开连接。（每次都要握手，浪费时间）

- **使用 ConnectionPool：** 预先建立好一堆连接（比如 5 个）放在池子里。程序需要时直接拿，用完还回去，**不需要关闭**。



**Async \(异步\)**：它是非阻塞的。这意味着当你的 AI 正在等待数据库保存 Checkpoint 时，Python 引擎可以去处理其他任务，而不会卡死在那里。

**ConnectionPool \(连接池\)**：

- **管理连接数**：防止你的程序因为并发太高，瞬间开启几百个连接把数据库搞崩溃。

- **自动恢复**：如果某个连接断了，池子会自动帮你重连，保证你的 LangGraph 服务一直在线。

你在开发 LangGraph 的持久化（Persistence）功能时，通常会看到类似这样的初始化代码：

```Python
import asyncio
from psycopg_pool import AsyncConnectionPool

# 这里的字符串就是连接你刚才截图里那个 langgraph_db 的凭据
conninfo = "dbname=langgraph_db user=postgres password=你的密码 host=localhost"

async def main():
    # 创建一个连接池
    async with AsyncConnectionPool(conninfo) as pool:
        # LangGraph 会利用这个 pool 来自动存取数据
        # 比如：checkpointer = PostgresSaver(pool)
        print("连接池已就绪，AI 记忆功能正常工作")

asyncio.run(main())
```



预先建立好一堆连接（比如 5 个）放在池子里。程序需要时直接拿，用完还回去，不需要关闭。



**场景 A（低并发）：** 只有 1 个用户在和你的 AI 聊天。连接池会从 5 个空闲连接里借出 **1 个** 给这个请求。请求处理完（存好 Checkpoint），这个连接**立刻归还**到池子里变成空闲，等待下一个人。

**场景 B（高并发）：** 突然有 5 个人同时说话。连接池会把这 **5 个** 预建好的连接全部发出去。

**场景 C（超限）：** 第 6 个人来了怎么办？他会**排队（Wait）**。等前 5 个人里有一个人用完归还了，第 6 个人马上接手。



那连接池一般创建多少个连接呢？假设我有1000个用户同时在线呢？

这是一个非常经典的问题。初学者往往认为“1000个用户就得开1000个连接”，但实际上，**数据库连接是极其昂贵的资源**，如果真的开1000个连接，你的数据库服务器可能会直接因为内存耗尽而崩溃。



### 为什么 1000 个用户不需要 1000 个连接？

这是因为 **“用户在线”不等于 “数据库正在操作”**。

- **用户的行为是断续的：** 用户在阅读 AI 生成的内容、思考问题、或者打字时，是不占用数据库连接的。

- **数据库操作是极快的：** 存取一个 LangGraph 的 Checkpoint 可能只需要几毫秒到几十毫秒。

- **并发的真相：** 即使有 1000 人同时在线，在**同一毫秒**内真正发起数据库请求的可能只有几十个人。

对于大多数中小型 AI 应用（比如你的 AI 课程项目或 TikTok 运营工具），连接池的数量通常建议如下：

- **起始值：** 5 到 10 个。

### 核心初始化函数 setup\_checkpointer\(\)

```Python
async def setup_checkpointer() -> BaseCheckpointSaver:
    """
    设置并初始化 Checkpointer
    
    根据 USE_MOCK_CHECKPOINTER 环境变量决定使用哪种模式：
    - True: 使用 MemorySaver (内存存储)
    - False: 使用 AsyncPostgresSaver (PostgreSQL 持久化)
    
    Returns:
        配置好的 Checkpointer 实例
    """
    global _checkpointer, _connection_pool
    
    if _checkpointer is not None:
        return _checkpointer
    
    if USE_MOCK_CHECKPOINTER:
        # 使用内存版 Checkpointer (无需数据库)
        _checkpointer = MemorySaver()
        print("📝 使用 MemorySaver (内存模式) - 数据不会持久化")
    else:
        # 使用 PostgreSQL Checkpointer (数据持久化)
        print(f"📦 连接 PostgreSQL: {settings.postgres_uri.split('@')[-1]}")
        
        # 首先使用 autocommit 模式的连接来执行 setup()
        # 因为 CREATE INDEX CONCURRENTLY 不能在事务块中运行
        async with await psycopg.AsyncConnection.connect(
            settings.postgres_uri,
            autocommit=True
        ) as setup_conn:
            # 创建临时 checkpointer 用于 setup
            temp_checkpointer = AsyncPostgresSaver(setup_conn)
            await temp_checkpointer.setup()
            print("✅ Checkpointer 表结构已创建/验证")
        
        # 创建异步连接池用于正常操作
        _connection_pool = AsyncConnectionPool(
            conninfo=settings.postgres_uri,
            min_size=1,
            max_size=10,
            open=False,  # 稍后手动打开
        )
        
        # 打开连接池
        await _connection_pool.open()
        
        # 创建 PostgreSQL Checkpointer
        _checkpointer = AsyncPostgresSaver(_connection_pool)
        
        print("✅ PostgreSQL Checkpointer 初始化成功 - 数据将持久化到数据库")
    
    return _checkpointer
```

### 获取和关闭 Checkpointer \(第86\-119行\)

```Python
async def get_checkpointer() -> BaseCheckpointSaver:
    """
    获取已初始化的 Checkpointer 实例
    
    Returns:
        Checkpointer 实例 (MemorySaver 或 AsyncPostgresSaver)
        
    Raises:
        RuntimeError: 如果 Checkpointer 未初始化
    """
    global _checkpointer
    
    if _checkpointer is None:
        return await setup_checkpointer()
    
    return _checkpointer


async def close_checkpointer() -> None:
    """
    关闭 Checkpointer 和连接池
    
    PostgreSQL 模式需要关闭连接池释放资源
    """
    global _checkpointer, _connection_pool
    
    if _connection_pool is not None:
        # 关闭 PostgreSQL 连接池
        await _connection_pool.close()
        _connection_pool = None
        print("📦 PostgreSQL 连接池已关闭")
    
    _checkpointer = None
    print("📝 Checkpointer 已清理")
```

## 工作流与 Checkpointer 绑定 \(app/graph/workflow\.py\)

```Python
async def get_compiled_graph():
    """
    获取编译后的工作流图（带持久化）
    
    LangGraph 1.0+ 使用 interrupt() 函数实现中断，
    不再需要 interrupt_before 参数
    
    Returns:
        编译后的 CompiledStateGraph 实例
    """
    # 获取 Checkpointer
    checkpointer = await get_checkpointer()
    
    # 构建工作流图
    workflow = build_workflow_graph()
    
    # 编译图，配置持久化
    # LangGraph 1.0+ 中断由 interrupt() 函数控制，不需要 interrupt_before
    compiled_graph = workflow.compile(
        checkpointer=checkpointer,
    )
    
    return compiled_graph
```

## API 层如何利用持久化 \(app/api/v1/workflow\.py\)

```Python
# 生成唯一的线程 ID
        thread_id = str(uuid.uuid4())
        
        # 获取编译后的图
        graph = await get_graph()
        
        # 配置
        config = {"configurable": {"thread_id": thread_id}}
        
        # 初始输入
        initial_input = {
            **INITIAL_STATE,
            "topic_direction": request.topic_direction,
            "status": "started",
        }
        
        # 运行图直到第一个中断点
        # LangGraph 1.0+ 中 ainvoke 会在遇到 interrupt() 时暂停
        result = await graph.ainvoke(initial_input, config)
```

### 获取状态 \- 从持久化中读取 \(第152\-203行\)

```Python
# 获取编译后的图
        graph = await get_graph()
        
        # 配置
        config = {"configurable": {"thread_id": thread_id}}
        
        # 获取状态快照
        state_snapshot = await graph.aget_state(config)
```

### 恢复工作流 \- 从中断点继续 \(第206\-317行\)

```Python
# 使用 Command 恢复工作流
        # LangGraph 1.0+ 中，使用 ainvoke(Command(resume=value), config) 恢复
        resume_command = Command(resume=resume_value)
        
        # 恢复运行直到下一个中断点或结束
        result = await graph.ainvoke(resume_command, config)
```

### 获取历史记录 \- 查看所有状态变更 \(第320\-358行\)

```Python
# 获取历史状态
        history = []
        async for state in graph.aget_state_history(config):
            history.append({
                "config": state.config,
                "values": dict(state.values) if state.values else {},
                "next": list(state.next) if state.next else [],
                "created_at": state.created_at if hasattr(state, "created_at") else None,
            })
```

```Python
┌─────────────────────────────────────────────────────────────────┐
│                        启动时初始化                              │
├─────────────────────────────────────────────────────────────────┤
│  1. setup_checkpointer() 被调用                                 │
│  2. 根据环境变量选择 MemorySaver 或 AsyncPostgresSaver          │
│  3. PostgreSQL 模式：创建表结构 + 连接池                         │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                        编译工作流图                              │
├─────────────────────────────────────────────────────────────────┤
│  workflow.compile(checkpointer=checkpointer)                    │
│  → 将 Checkpointer 绑定到图，开启自动状态保存                    │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                        运行时持久化                              │
├─────────────────────────────────────────────────────────────────┤
│  每次 ainvoke(input, config) 时：                               │
│  - config 中的 thread_id 作为唯一标识                           │
│  - 每个节点执行后，状态自动保存到 PostgreSQL                     │
│  - 遇到 interrupt() 时暂停，状态已保存                           │
│  - 下次用相同 thread_id 调用 ainvoke(Command(...)) 可恢复        │
└─────────────────────────────────────────────────────────────────┘
```

AsyncPostgresSaver\.setup\(\) 会创建以下表（LangGraph 内置）：

每条记录通过 \(thread\_id, checkpoint\_id\) 唯一标识。

## LangGraph PostgreSQL Checkpointer 完整表结构

AsyncPostgresSaver\.setup\(\) 实际上会创建 4 个表：

## checkpoint\_blobs 表详解

这是最重要的数据表，存储了工作流的实际状态数据：

```Python
checkpoint_blobs 表结构（大致）:
┌─────────────┬──────────────────────────────────────────────────┐
│ 字段         │ 说明                                             │
├─────────────┼──────────────────────────────────────────────────┤
│ thread_id   │ 工作流线程ID（与 checkpoints 表关联）              │
│ checkpoint_ns│ 命名空间（用于区分不同的子图）                     │
│ channel     │ 通道名（如 "values", "messages" 等）              │
│ version     │ 版本号                                           │
│ type        │ 数据类型标识                                      │
│ blob        │ 序列化后的状态数据（bytea 类型，存储实际的状态值）   │
└─────────────┴──────────────────────────────────────────────────┘
```

### 为什么要分开存储？

LangGraph 采用分离存储的设计：

1. checkpoints 表：只存储轻量的元数据（时间戳、父子关系等）

2. checkpoint\_blobs 表：存储可能很大的状态数据

这样设计的好处：

- 查询效率：查询检查点列表时不需要加载大量数据

- 去重：相同的状态数据可以被多个检查点引用

- 灵活性：不同的 channel（如消息历史、状态值）分开存储

```SQL
工作流执行 → 状态变更
         ↓
    LangGraph 序列化状态
         ↓
┌────────────────────────────────────────┐
│          PostgreSQL 数据库             │
├────────────────────────────────────────┤
│  checkpoints 表                        │
│  ├─ thread_id: "abc-123"              │
│  ├─ checkpoint_id: "ckpt-001"         │
│  ├─ parent_checkpoint_id: null        │
│  └─ metadata: {...}                   │
│                                        │
│  checkpoint_blobs 表                   │
│  ├─ thread_id: "abc-123"              │
│  ├─ channel: "values"                 │
│  └─ blob: <序列化的 AgentState 数据>   │
│      {                                 │
│        "topic_direction": "AI技术",    │
│        "generated_topics": [...],      │
│        "article_content": "...",       │
│        "status": "draft_completed"     │
│      }                                 │
└────────────────────────────────────────┘
```



### 1\. checkpoints 表 \- 检查点索引

```SQL
CREATE TABLE checkpoints (
    thread_id       TEXT NOT NULL,           -- 工作流线程ID
    checkpoint_ns   TEXT NOT NULL DEFAULT '', -- 命名空间（子图用）
    checkpoint_id   TEXT NOT NULL,           -- 检查点唯一ID
    parent_checkpoint_id TEXT,               -- 父检查点ID（用于历史回溯）
    type            TEXT,                    -- 类型标识
    checkpoint      JSONB NOT NULL,          -- 检查点元数据（JSON格式）
    metadata        JSONB NOT NULL DEFAULT '{}', -- 额外元数据
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
```

checkpoint 字段示例内容：

```SQL
{
  "v": 4,
  "id": "1f0fc5a8-d77c-6654-bfff-868f6b38fcbb",
  "ts": "2026-01-28T15:03:49.917850+00:00",
  "versions_seen": {
    "__input__": {}
  },
  "channel_values": {},
  "channel_versions": {
    "__start__": "00000000000000000000000000000001.0.9769687785330453"
  },
  "updated_channels": [
    "__start__"
  ]
}
```

注意：这里只存了 blob\-id 的引用，不是实际数据！

**`v: 4`**** \(Version\)**

- **含义**：这是 LangGraph 存储序列化格式的版本号。

- **作用**：确保代码能正确解析存储的数据。如果未来 LangGraph 升级了存储格式，它会通过这个版本号来做兼容性处理。

**`id: "1f0fc5a8-..."`**** \(Checkpoint ID\)**

- **含义**：这是当前这个**特定瞬间**的唯一标识符。

- **作用**：每当 Agent 执行完一个步骤（Node），都会生成一个新的 ID。它能让你实现“时间旅行”（Time Travel）——即回溯到对话中的任何一个特定步骤。

**`ts: "2026-01-28T15:03:49..."`**** \(Timestamp\)**

- **含义**：存盘的时间戳。

- **作用**：记录这个状态是在什么时候产生的，方便调试和按时间顺序排序。

**`versions_seen`**

- **含义**：已读版本。

- **作用**：记录了各个 Channel（变量通道）被读取的状态。这里显示 `input: {}`，说明这是初始输入阶段，还没有复杂的中间状态。

**`channel_values`**

- **含义**：**最关键的部分（虽然在此片段中为空）**。

- **作用**：这里本应存储你定义的 `State` 里的所有变量值（比如 `messages` 列表、`user_info` 等）。因为这个 JSON 看起来处于初始状态（`start`），所以值还是空的。

**`channel_versions`**

- **含义**：通道的版本控制。

- **作用**：LangGraph 使用“多通道”机制。这里 `start` 对应的长字符串是内部的版本标识，用来追踪哪些数据被修改过，从而实现增量更新，避免重复存储没变的数据。

**`updated_channels: ["start"]`**

- **含义**：本次更新影响了哪些通道。

- **作用**：这里显示 `start`，意味着这是一个**新会话的起点**。





### checkpoint\_blobs 表 \- 实际状态数据存储

```SQL
CREATE TABLE checkpoint_blobs (
    thread_id       TEXT NOT NULL,           -- 工作流线程ID
    checkpoint_ns   TEXT NOT NULL DEFAULT '', -- 命名空间
    channel         TEXT NOT NULL,           -- 通道名（如 "values"）
    version         TEXT NOT NULL,           -- 版本号
    type            TEXT NOT NULL,           -- 序列化类型
    blob            BYTEA,                   -- ⭐ 实际数据（二进制格式）
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);
```

### checkpoint\_writes 表 \- 写入记录

```SQL
CREATE TABLE checkpoint_writes (
    thread_id       TEXT NOT NULL,
    checkpoint_ns   TEXT NOT NULL DEFAULT '',
    checkpoint_id   TEXT NOT NULL,
    task_id         TEXT NOT NULL,           -- 任务ID（节点名称）
    idx             INTEGER NOT NULL,        -- 写入序号
    channel         TEXT NOT NULL,           -- 通道名
    type            TEXT,                    -- 数据类型
    blob            BYTEA,                   -- 写入的数据（二进制）
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
```

### checkpoint\_migrations 表 \- Schema 版本

```Python
CREATE TABLE checkpoint_migrations (
    v INTEGER PRIMARY KEY  -- 版本号
);
```

## 为什么你看不到 topic list？

原因：数据是用 pickle 序列化后存成二进制的！当你直接查询 checkpoint\_blobs 表时：

```Python
SELECT thread_id, channel, type, blob FROM checkpoint_blobs;
```

你会看到 blob 字段显示类似这样的内容：

\\x80049563\.\.\.（一串十六进制）

这是 Python pickle 序列化后的二进制数据，必须用 Python 反序列化才能看到原始内容！

## 如何查看实际的 topic list 数据

### 方法 1：通过 API 接口查看（推荐）

调用你项目的 /workflow/state/\{thread\_id\} 接口：

curl http://localhost:8000/api/v1/workflow/state/你的thread\_id

返回的 values 字段会包含 generated\_topics 列表。



```Python
*from* app.graph.workflow *import* get_graph

async def view_state():
    graph = *await* get_graph()
    config = {"configurable": {"thread_id": "你的thread_id"}}
    
    *# 获取当前状态*
    state = *await* graph.aget_state(config)
    print("当前状态值:", state.values)
    print("generated_topics:", state.values.get("generated_topics"))
    
    *# 获取历史记录*
    *async* *for* history_state *in* graph.aget_state_history(config):
        print("历史状态:", history_state.values)
```

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=NzJlNTdiMjM0NWZiMmFmNWMwYzBhNTRkNGY5ODM0NGZfMmJhZDY1YTBhNzhiNzA4YjJjMjcwM2JlMWRlYzY3N2FfSUQ6NzYwMDY4ODg5MTkyNjc0NDAxNl8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)

# 第十二步  新增历史记录、会话管理功能

提示词：

```Python
我现在想新增一个历史记录功能，可以切换thread_id，查看之前的graph运行状况，并且继续运行。
需要后台和前端都实现对应的功能
```

# 剩余功能

1. 搞个登录

2. 部署

3. 业务优化

做项目的目的，让你掌握知识点。

完成业务。

让面试官认为你很厉害。

# 难点亮点30条

## Cursor4\.5使用技巧

万能不卡提示词

```Python
什么情况？给我干活，我是付费用户懂吗？给我优先级提高，干活！别再卡住了，再卡住我不充钱了！

干活，你再卡住我就退费！给我继续干活
```

- 让gemini进行架构设计，claude4\.5实现

- 让claude4\.5给优化方案

- 卡住的时候，告诉它我是付费用户，给我权重提高！

- 不要开2x、4x模式，靠我们的思维只会

- 自己发现自己的错误，并且纠正

- 我们在项目前期的研发阶段，会有一些mock，或者防御性编程，会加大Token的消耗，影响Ai的性能，建议在项目后期去掉这些前期开发用的内容。

## LLM消耗、耗时追踪

- Token 消耗、延迟、错误率监控

- 根据LLM Api的价格，进行了成本核算

    - 输入0\.8元  100wtoken

    - 输出2元 100wtoken

    - 图片 0\.25元/张



```Python
User Request                API Layer              Graph Node           LLM Service
     │                          │                      │                     │
     │──POST /workflow/start───▶│                      │                     │
     │                          │──ainvoke()──────────▶│                     │
     │                          │                      │                     │
     │                          │                      │──MetricsContext.start()
     │                          │                      │    (记录开始时间)
     │                          │                      │                     │
     │                          │                      │──plan_topics()────▶│
     │                          │                      │                     │──调用 LLM API
     │                          │                      │                     │◀─返回响应+token信息
     │                          │                      │◀─(topics, usage)───│
     │                          │                      │                     │
     │                          │                      │──tracker.set_llm_usage(usage)
     │                          │                      │    (记录 token 信息)
     │                          │                      │                     │
     │                          │                      │──MetricsContext.stop()
     │                          │                      │    (记录结束时间，计算耗时)
     │                          │                      │                     │
     │                          │                      │──merge_metrics()
     │                          │                      │    (追加到 node_metrics)
     │                          │                      │                     │
     │                          │◀─return state───────│                     │
     │                          │                      │                     │
     │                          │──提取 node_metrics   │                     │
     │◀───返回 Response──────────│                      │                     │
     │   (含 node_metrics)      │                      │                     │
```



妙不可言的设计

```Python
class MetricsContext:
    """
    指标上下文管理器
    
    使用方式：
    ```python
    async def my_node(state):
        with MetricsContext("my_node") as tracker:
            # 执行节点逻辑
            result, usage = await llm_service.call_with_metrics(...)
            tracker.set_llm_usage(usage)
        
        return {
            ...,
            "node_metrics": state.get("node_metrics", []) + [tracker.to_dict()]
        }
    ```
    """
    
    def **__init__**(*self*, *node_name*: str):
        *self*.tracker = NodeMetricsTracker(*node_name*)
    
    def **__enter__**(*self*) -> NodeMetricsTracker:
        *self*.tracker.start()
        *return* *self*.tracker
    
    def **__exit__**(*self*, *exc_type*, *exc_val*, *exc_tb*):
        *self*.tracker.stop()
        *return* False
```

## 在环境变量中引入mock开关

1. 实现llm\_mock、image\_mock、checkpointer\_mocker

2. 帮助项目开发，不完全依赖服务，保证业务顺利开发

## 使用PostgreSQL数据持久化

- 将graph的流程可以进行同步

## 通过数据持久化，支持Graph时间旅行

- 支持从任意历史节点回滚和重跑

- 支持部分节点重试（而非整个流程）

## 引入子图SubGraph模式

- 将选题、写作、配图拆分为独立子图

- 支持子图复用和组合编排

举例：

1. 选题Graph

    1. 先输入大方向

    2. rag 提供5个选题

    3. LLM  提供5个

    4. 运营专员选一个题

    5. 加入多人审核

        1. 组长审核

        2. 总监审核

    6. 确定题目





Checkpointer一般是主图统一管理，建议不要搞多个，中断恢复容易冲突。

## State（状态）

是同一个类型定义，但不是同一个实例对象。

# *子图 \- 使用 AgentState*

subgraph = StateGraph\(AgentState\)

# *主图 \- 也使用 AgentState*

workflow = StateGraph\(AgentState\)

LangGraph 的工作机制是：

1. 主图调用子图时，会把当前 state 传递给子图

2. 子图执行过程中对 state 的修改（通过 Command\(update=\{\.\.\.\}\)）会被收集

3. 子图结束后，更新后的 state 传回主图继续使用

所以状态是流转共享的，不是引用同一个内存对象。

## Checkpointer（检查点）

原理：

- 子图作为节点嵌入主图后，主图的 checkpointer 会负责管理整个工作流的状态持久化

- 包括子图内部的 interrupt\(\) 中断点，也会被主图的 checkpointer 正确记录

- 恢复执行时，checkpointer 知道工作流停在子图的哪个位置

## 总结

这就是为什么子图内的 interrupt\(\) 能正常工作 —— checkpointer 会记录完整的执行路径，包括"主图 → 子图 → 子图内某节点"这样的嵌套位置。



## 节点并行

- 多张图片生成可并行调用（当前是串行）

- 把图片生成同步改成异步模式





Doubao\-Seedream\-4\.5图片生成不支持异步调用。



相当于\_generate\_single\_image\_sync放到另一个线程去跑，跑完再回到主线程，模拟异步

```Python
loop = asyncio.get_running_loop()
url = *await* loop.run_in_executor(
    None,
    *self*._generate_single_image_sync,
    *prompt*,
    *size*,
)
*return* url
```

```Python
tasks = [
            *self*.generate_single_image(*prompt*=point, *size*=*size*)
            *for* point *in* *visual_points*
        ]
        image_urls = *await* asyncio.gather(*tasks)
```

## 超时与重试机制

- 为每个节点配置超时时间

- LLM 调用失败自动重试（指数退避）

    - 第一次间隔1s

    - 第二次间隔2s

    - 第三次间隔4s

    - 以此类推。。。。

## Prompt 工程化管理

- 将 Prompt 模板抽离到配置文件/数据库

## 流式输出

- 支持 SSE/WebSocket 流式返回 LLM 生成内容

- 用户实时看到文章生成过程

- 减少TTFT

- 流式输出Graph官网支持

- 流式输出和非流式输出不影响checkpointer存储的数据结构

- https://docs\.langchain\.com/oss/python/langgraph/streaming



1. 前端发起请求

```JavaScript
// 1. 前端调用入口
export function streamStartWorkflow(topicDirection, callbacks, streamMode = 'events') {
  return fetch('/api/v1/workflow/stream/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      topic_direction: topicDirection,
      stream_mode: streamMode  // 'events' 模式可获取 LLM token 级别流
    })
  }).then(response => handleSSEStream(response, callbacks))
}
```

2. 前端解析SSE流

```TypeScript
async function handleSSEStream(response, callbacks) {
  // 获取 ReadableStream 的 reader
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  
  while (true) {
    // 循环读取数据块
    const { done, value } = await reader.read()
    if (done) break
    
    // 解码二进制数据为字符串，stream: true 表示可能有不完整的字符
    buffer += decoder.decode(value, { stream: true })
    
    // 按换行符分割（SSE 格式每条消息以 \n\n 结尾）
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''  // 保留不完整的行
    
    for (const line of lines) {
      // SSE 数据格式: "data: {json}\n"
      if (line.startsWith('data: ')) {
        const event = JSON.parse(line.slice(6))  // 去掉 "data: " 前缀
        const { type, data } = event
        
        // 根据事件类型调用对应回调
        switch (type) {
          case 'init':
            callbacks.onInit?.(data)      // 初始化事件
            break
          case 'llm_token':
            callbacks.onLlmToken?.(data.content)  // LLM token 事件
            break
          case 'update':
            callbacks.onUpdate?.(data.node, data.output)  // 节点更新
            break
          case 'done':
            callbacks.onDone?.(data)      // 完成事件
            break
          // ... 其他事件
        }
      }
    }
  }
}
```



3. 服务端处理请求  @router\.post\("/stream/start"\)

```Python
@router.post("/stream/start")
async def stream_start_workflow(request: StreamStartWorkflowRequest):
    """流式启动工作流"""
    thread_id = str(uuid.uuid4())  # 生成唯一 ID
    
    # 定义异步生成器
    async def generate():
        try:
            graph = await get_graph()  # 获取 LangGraph 实例
            config = {"configurable": {"thread_id": thread_id}}
            
            # 初始输入状态
            initial_input = {
                **INITIAL_STATE,
                "topic_direction": request.topic_direction,
                "status": "started",
            }
            
            # 发送初始化事件
            yield format_sse_event("init", {"thread_id": thread_id})
            
            # 调用核心流式处理函数
            async for event in stream_graph_updates(
                graph, initial_input, config,
                stream_mode=request.stream_mode
            ):
                yield event  # 逐个 yield SSE 事件
                
        except Exception as e:
            yield format_sse_event("error", {"message": str(e)})
    
    # 返回流式响应
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",  # SSE MIME 类型
        headers={
            "Cache-Control": "no-cache",      # 禁用缓存
            "Connection": "keep-alive",        # 保持连接
            "X-Accel-Buffering": "no"         # 禁用 Nginx 缓冲
        }
    )
```



4. SSE数据格式化

```Python
def format_sse_event(event_type: str, data: Any) -> str:
    """将事件格式化为 SSE 标准格式"""
    payload = {
        "type": event_type,
        "data": data
    }
    # SSE 格式: "data: {json}\n\n"
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
```

5. 流式处理逻辑



**普通流 \(****`astream`****\)**：基于“状态更新”。只有当一个节点（Node）收工了，它才会告诉你结果。

**事件流 \(****`astream_events`****\)**：基于“生命周期事件”。它会监听每一个步骤的：

- `on_chain_start`（开始运行了）

- `on_chat_model_stream`（大模型正在吐字）

- `on_tool_start`（准备去调工具了）

- `on_chain_end`（运行结束）

```Python
if stream_mode == "events":
            # 这里的 astream_events 是 LangGraph 的高级 API，能监控内部所有细微动作
            async for event in graph.astream_events(input_data, config, version="v2"):
                event_kind = event.get("event", "")
                
                # 场景 A：一个节点（Node）开始运行了（比如“搜索节点”开始启动）
                if event_kind == "on_chain_start":
                    yield format_sse_event("node_start", {"node": event.get("name")})
                    
                # 场景 B：🔥 LLM 正在吐字（最重要的部分）
                elif event_kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk", {})
                    # 判断 chunk 里是否有文本内容
                    if hasattr(chunk, "content") and chunk.content:
                        # 实时把这一个 token（字符）发给前端
                        yield format_sse_event("llm_token", {"content": chunk.content})
                        
                # 场景 C：一个节点运行结束了
                elif event_kind == "on_chain_end":
                    yield format_sse_event("node_end", {"node": event.get("name")})
```



6. LLM调用非流式的

但 LangGraph 的 astream\_events\(\) 仍能捕获到 token 流，因为：

1. LangChain 的 ChatOpenAI 默认支持流式

2. astream\_events\(\) 会自动监听底层的流式事件

graph\.astream\_events会把LLM的底层调用变成astream模式，但是还是建议显性的把LLM的调用变成stream模式。方便项目维护，一目了然。

```Python
class LLMService:
    def __init__(self):
        # 使用 LangChain 的 ChatOpenAI 连接火山引擎
        self._llm = ChatOpenAI(
            model="doubao-seed-1-8-251228",
            api_key=os.getenv("LLM_API_KEY"),
            base_url="https://ark.cn-beijing.volces.com/api/v3",
        )
    
    async def plan_topics(self, topic_direction: str):
        """生成选题（非流式调用）"""
        messages = [
            SystemMessage(content="你是小红书内容策划专家..."),
            HumanMessage(content=f"主题方向：{topic_direction}")
        ]
        
        # 注意：这里使用的是 ainvoke（非流式）
        response = await self.llm.ainvoke(messages)
        
        return topics, usage_info
```

## 多模型路由策略

- 简单任务用小模型，复杂任务用大模型

- 根据内容类型、成本、延迟动态选择

- 简单任务用flash

- 复杂任务用旗舰版  1\.8

- 降本增效

## LLM 输出结构化校验

- 使用 Pydantic \+ LangChain 的 with\_structured\_output

- 强制 LLM 输出符合 Schema



需求：

1. 流式输出

2. 结构化输出

3. 还要统计token使用量

总结： 

1. 流式输出\+token统计

2. 结构化输出不能token统计的

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=Y2Q4MDM2NDE5NTkzYWIzNDBmYWZhZDI0MTcwYWMxMDlfNjY3ZmQwOGYyNTk2NzRjNDNkY2EwNWY5NDE1NjgxZTBfSUQ6NzYwMTM3NTEzMjYxMTIxODYzMl8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)

如果我们想结构化输出\+token统计，可以用

```Python
# 假设你已经定义好了 model 和 structured_llm
chain = llm.with_structured_output(YourSchema)

# 使用 with_raw 调用
response = chain.with_raw.invoke("你的输入内容")

# response 是一个字典，包含 'parsed' 和 'raw'
parsed_data = response['parsed']  # 这是你的结构化数据
raw_message = response['raw']     # 这是原始的 AIMessage

# 从 raw 中提取 token
token_usage = raw_message.usage_metadata # 或者 raw_message.response_metadata['token_usage']
print(f"输入: {token_usage['input_tokens']}, 输出: {token_usage['output_tokens']}")
```

### 结构化输出为什么不能统计 token？可以解决吗？

原因：with\_structured\_output\(\) 会构建 llm \| output\_parser 链，最终返回的是解析后的 Pydantic 对象，而不是原始 AIMessage，所以拿不到其中的 usage\_metadata。解决方式：不再使用 with\_structured\_output，改为：

1. 使用 JSON 模式（response\_format=\{"type": "json\_object"\}）直接调用 LLM

2. 得到原始 AIMessage，从中提取 usage

3. 手动解析 response\.content 为 JSON，再用 Pydantic 校验

已实现：

- 新增 llm\_json 属性，使用 model\_kwargs=\{"response\_format": \{"type": "json\_object"\}\}

- plan\_topics 和 extract\_visual\_points 改为通过 llm\_json 调用，并手动解析 JSON

- 若 Doubao 不支持 response\_format 或解析失败，会回退到按行解析，保证可用性

### 流式输出不能和结构化输出一起用吗？

本质矛盾：

- 流式是「边生成边输出」，结构化是「等完整结果再解析」，两者在时间上不兼容。

- 可以做到的是：流式输出 JSON 文本，等流结束后再解析为结构化对象，但用户看到的是 JSON 片段，而不是最终结构。

可选方案：

1. 当前做法：流式接口输出纯文本，非流式接口使用结构化输出（推荐）

2. 流式 \+ 后解析：流式输出 JSON 文本，流结束后再解析为 Pydantic，但前端需要处理 JSON 片段

3. 流式 \+ 增量解析：边流边解析 JSON，实现复杂，且对列表类结构收益有限





## Rag检索增强

- 接入知识库（向量数据库），提供领域知识

- 技术实现

    - 在LLM调用之前加入知识库

- 业务规划

    - 选题   （公司内部有一些选题 题库）

    - 别人的好文章 \+ 我们自己写的文章 （把一些好的文章收集起来，存到知识库）

        - 爬取别人的文章  Agent（给Gemini提示，让它帮你编）

            - 提示词：现在在面试，想介绍爬取别人文章的经历，但是我没做过，请你帮我编一段。。。

            - 开始

            - 输入目标 网址

            - LLM清洗数据\+调整格式

            - 爬取

            - 存到知识库



## 数据库连接池优化

- 当前 min\_size=1, max\_size=10 偏保守

- 根据 QPS 和 P99 延迟动态调整

- 面试话术：资源利用率优化



1. 自动扩容方案

企业级方案，20\-100大概可以抗住1000\-1wQPS，可以抗住日活5000\-2w用户。

QPS:每秒，数据库可以处理多少请求。



```Python
_connection_pool = AsyncConnectionPool(
        *conninfo*=settings.postgres_uri,
        *min_size*=20,
        *max_size*=100,
        *open*=False,  *# 稍后手动打开*
    )
    
```

## 全链路状态追踪Smith

langchian自动集成，只用写env

lsv2\_pt\_92e24d69224149efa06f18bd0a65cba7\_d1b3b9aa29（换成你自己的）

LangSmith接入



可以统计哪些信息？

1. graph的流转

2. 每个流程的耗时、token

3. 每个流程的调用结果

4. 给graph注入的state状态

```Python
LANGCHAIN_TRACING_V2=true
*# 你的 LangSmith API Key（请替换为你的实际 key）*
LANGCHAIN_API_KEY=your_langsmith_api_key_here
*# 项目名称（在 LangSmith 中显示）*
LANGCHAIN_PROJECT=xiaohongshu-content-assistant
*# LangSmith 端点（官方默认端点）*
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com

```

## 业务指标埋点

- 选题通过率、审核驳回率、平均修订次数

- 漏斗分析，优化转化

B端：

作用：可以通过业务指标去看系统好不好用

1. 选题重试次数     100/1000  = 10%  优化目标：降低重试率

2. 文章内容修改次数   300/1000 = 30%  优化目标：降低修改率

3. 图片的重新生成率  。。。   

技术实现（自己开发上报服务，适合数据很敏感的公司。但是神策也能私有化部署）：



C端的统计：

1. 接入数据统计平台  神策数据（统计一些通用的，跟业务不相干的）

一般是前端接入80%情况，20%后台也需要接入

https://www\.sensorsdata\.cn/

```Python
统计UV（有多少真实用户） PV（页面访问次数）
页面哪些按钮被点击了

原理：代理了浏览器的dom事件，获取你button的文本，post到神策的服务器
```

2. 神策也可以自定义业务统计



一般前端工程师，只需要接入神策SDK，可能就几行代码，不管了。

剩下的交给产品经理去干。



## 日志服务

- 使用 structlog/loguru

- 日志关联 thread\_id，便于排查

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=YjBlMmM4MmQyZjgyMTZmZDAwZDEzOThhNmQyMmFhZjdfZWNiYmQ5MzRiMWM3ZjJiYzY4ZjkwYjVjMTRkOWZhYzNfSUQ6NzYwMTQyNjUyMDI2NzY0MDAzMF8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)

1. api请求日志

```Python
# 记录内容
{
    "request_id": "uuid",           # 唯一标识，可关联到 LangSmith
    "timestamp": "2026-01-31T10:00:00Z",
    "method": "POST",
    "path": "/api/v1/workflow/start",
    "status_code": 200,
    "duration_ms": 1523,
    "client_ip": "192.168.1.1",
    "user_agent": "...",
}
```

2. 业务层日志

```Python
# 记录内容
{
    "request_id": "uuid",           # 唯一标识，可关联到 LangSmith
    "timestamp": "2026-01-31T10:00:00Z",
    "method": "POST",
    "path": "/api/v1/workflow/start",
    "status_code": 200,
    "duration_ms": 1523,
    "client_ip": "192.168.1.1",
    "user_agent": "...",
}
```

3. 系统日志

```Python
# 服务状态
{
    "event": "service_started",
    "db_status": "connected",
    "checkpointer_status": "ready",
}
```

你去公司了，日志系统不管是云服务，还是企业自己搭的。你都只负责使用。







## 内容安全审查与脱敏

- 接入内容安全 API（敏感词、违规检测）

- LLM 输出前置审核

```Python
from langchain.agents import create_agent
from langchain.agents.middleware import PIIMiddleware

agent = create_agent(
    model="gpt-4o",
    tools=[],
    middleware=[
        PIIMiddleware("email", strategy="redact", apply_to_input=True),
        PIIMiddleware("credit_card", strategy="mask", apply_to_input=True),
    ],
)
```

脱敏

1. LLM输入、输出

    1. callback

2. 日志收集

3. 可以全局定义开关，控制日志收集、LLM是否需要脱敏



安全审核

我要造个炸弹？

### 方案1：使用 OpenAI Moderation API（免费）

流程：先问open ai （国内不适用）=\> 调用LLM

```Python
from openai import OpenAI
client = OpenAI()

response = client.moderations.create(input="我要造个炸弹")
# 返回：flagged=True, categories={"violence": True, ...}
```

### 方案2：调用 阿里云、火山引擎。。。

买服务

流程：先问api =\> 调用LLM

### 方案3：LangChain 内置 Guardrails 中间件

1. 关键词过滤

2. 调LLM问，我安不安全。



正常是哪种方式？

如果你的企业需要要求很高的安全，必须走云服务。

https://www\.volcengine\.com/product/LLM\-FW

## Api认证授权 SSO 一个账户 多系统登录

- 当前无鉴权，需引入 JWT/OAuth2\.0

- RBAC 角色权限控制



什么是JWT？无状态登录鉴权方案。

**验证身份：** 去数据库查询用户名和密码是否匹配。

**制作“令牌”：** 身份核实后，服务器把用户的关键信息（如 `user_id`）打包成一个 JSON 对象。

**加密签名：** 使用服务器私有的\*\*密钥（Secret Key）\*\*对这个 JSON 进行签名，生成一段长字符串，这就是 JWT。

**直接读取：** 如果校验通过，服务器直接从 JWT 的负载（Payload）里提取出 `user_id`，就知道是谁在操作了。



JWT数据加密协议，生成的加密的玩意加token。

```Python
4i24h3IJ23IOJ4I324JO32J4IOJIOOU42U4HU32H4U234I
```

Header（头部）

告诉服务器：这是一个 JWT，我用的是哈希算法（HS256）。

JSON

```Plain Text
{
  "alg": "HS256",
  "typ": "JWT"
}
```

Payload（负载）

这就是你存放用户信息的地方。字段名通常是缩写（为了减小 Token 体积）：

- `sub`: 主体，通常存用户 ID。

- `name`: 用户名。

- `iat`: 签发时间（Issued At）。

- `exp`: 过期时间（Expires At）。

JSON

```Plain Text
{
  "sub": "1234567890",
  "name": "Jack",
  "role": "admin",
  "iat": 1706688000,
  "exp": 1706774400
}
```

## 

前端的请求会在Header中去携带，给到服务端。

JWT登录鉴权过程

1. 用户登录  用户名 \+密码

2. 服务器验证用户名\+密码对不对

3. 服务器对json加密   \{头部\} \{用户信息 id、用户名、权限等等\}   生成一个token，返回前端

4. 前端拿到这个token， 存在本地（localstorage），每次访问api，携带token，写入header中

5. 访问服务器api，  header就有token了

6. 服务端收到请求，验证token。解密，得到 用户信息\{用户信息 id、用户名、权限等等\}

7. api校验通过 返回数据

JWT的作用是用户，刷新页面不用再登录了。

传统的模式，后台加密一个token（加密字符串 非JWT），存到redis数据库的，有状态的。

传统的模型，python服务，token（加密字符串 非JWT）存到服务器内存。



弊端：不好横向扩展。

为什么现在流式JWT，可以支持无状态，服务端自解析。原生技术架构适配docker，方便扩容。





### Auth2\.0

解决的问题：SSO单点登录，一个账户，登录多个系统。

技术方案：Auth2\.0

通信协议使用：JWT

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ZTUxOWNhMzlmNmQzMjg1NGJlYWNkNGI0YmNkYzE4YmNfNzRjYjAyOThhOWE1MGE3NmFmMTk1NWVhNTZhOGMwZDdfSUQ6NzYwMTQ1NDM2ODk0MDEwMDU2M18xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)

如果我们想实现，一次登录，多系统使用

1. 用户访问a\.com

2. 到了业务服务器，你没登录，给我跳到认证中心

3. 输入手机号\+验证码

4. 认证中心帮你重定向 a\.com?code=xxxxx

5. 又访问业务服务器，拿到code去认证中心换token

6. 服务器把token写入浏览器的cookie中

7. 用户登录成功

8. 用户再次访问b\.com

9. 直接携带token，访问业务服务器

10. 业务服务器校验token

11. 你已经登录了，继续干活



以上我讲的内容是纯后台工作，java干的。

80%的java也没写过以上代码。

是为了写进简历，人家问你也顶得住。

## 配置中心抽象

我们的项目

1. 项目层面 Env

    1. Api key

    2. LLM的url

    3. LLM的模型类型

    4. Mock

    5. Debug

2. 业务层面

    1. 提示词

        1. 用户提示词

            1. 文章

            2. 图片

            3. 摘要

        2. 系统提示词



### 方案一：集中式模块管理（最简单）

```Python
app/
├── core/
│   ├── config.py        # 统一的环境变量配置
│   └── prompts.py       # 集中的提示词模板
```

### 方案二：存到数据库中（做成系统）

项目比较复杂之后，可以把提示词拿出来，做个系统，让产品经理或者运营去写。



配置管理网站

1. 提示词A版本

2. 提示词B版本



优点：

- 支持运行时修改

- 可以做 A/B 测试 ，灰度

    - 目的：是让不同的用户体验不同的版本。

    - 业务层写一个逻辑

        - 写一个判断如果是安卓用户  加载A

        - 如果是IOS用户  加载B

- 支持多版本管理

缺点：

- 复杂度高

- 增加数据库依赖

### 方案三 Nacos/Apollo

超级复杂，体量很大。



这玩意 一般是正经的java干的，而且还是中大厂，用户量很大

配置中心稳定。非常非常重要，极其要求稳定行。

分布式配置中心，主要解决微服务架构下的配置管理问题。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ZDk3ZTYwN2E3ODU5ODBlZDMxMTdjMDk4ZmYxMWJjMjdfYTQwZDU1N2U5ZTkyOTQzZjJiOWY2NWI5M2FhMTcxMGFfSUQ6NzYwMjI2MDI1NTgwNDEzMjI5N18xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)



## 工作流模板（业务上的扩展）

- 预设多种内容类型模板（种草、测评、教程）

- 用户快速选择启动

业务形态

1. 微信公众号的文章=\> 摘要 =\> 小红书的图片

2. 掘金的文章 =\> 摘要 =\> 抖音



系统做个模板

点击：

模板A： 微信公众号 \+ 小红书

模板B：掘金  \+ 抖音



## MCP服务拆分

- LLM MCP Server \(多模型路由、Prompt 管理\)

- Image MCP Server \(图片生成、风格控制\)

- RAG MCP Server \(知识库检索\)



MCP的目的。

我公司有多个系统，A、B、C。。。。

他们可能都有需求，要生成图片。

把图片做成MCP服务。

你传图片  提示词 \+ 参数

返回图片



理解为前端的组件库，发布成NPM包。





### 1\. 图片生成服务 \(app/services/image\_service\.py\)

推荐理由：

- ✅ 完全独立，零内部依赖

- ✅ 封装了火山引擎图片生成 API，功能明确

- ✅ 支持单张/批量生成，接口清晰

MCP 能力设计：

- generate\_image\(prompt, size, style\) → 生成单张图片

- generate\_images\_batch\(prompts, size, style\) → 批量生成图片

### 2\. LLM 服务 \(app/services/llm\_service\.py\)

推荐理由：

- ✅ 高复用性，封装了 Doubao API

- ✅ 支持结构化输出、流式输出、Token 统计

- ✅ 可适配多种 AI 场景

MCP 能力设计：

- chat\_completion\(messages, model, stream\) → 对话补全

- structured\_output\(messages, schema\) → 结构化输出（返回JSON）

- plan\_topics\(topic, style, count\) → 生成内容选题

- write\_article\(topic, outline, style\) → 生成文章



## 健康检查与优雅关闭

```Python
# 健康检查端点（已实现）
@app.get("/health")
async def health_check():
    return {"status": "healthy", "db": await check_db_connection()}

# 优雅关闭（可补充）
@app.on_event("shutdown")
async def shutdown():
    await connection_pool.close()  # 关闭连接池
    await checkpointer.close()     # 关闭checkpointer
```

真实项目中：

配合监控系统，你公司自己有。

写一个轮询，隔一会就问   访问api  /health  

挂了

1. 报警

2. 发邮件

3. 发短信



用于容器化部署，存活检测。

服务部署，python部署是在docker中，就是把服务封装成程序。

想学docker  node课有（自动化部署、看docker）。



docker需要K8S编排的，K8S（Pod）的作用是自动管理服务，弹性扩容、缩容

需要知道服务是不是挂了啊？探针  访问健康检查接口



## API版本控制

项目已采用 /api/v1/ 路由前缀，支持：

- 多版本并存（v1、v2）

- 平滑迁移，老版本不影响现有用户

### 场景一：破坏性变更 → 新增v2版本

当接口不兼容旧版本时，才新建版本：

```Bash
# 原有v1接口
POST /api/v1/workflow/start
请求体: { "topic_direction": "美食" }
响应: { "thread_id": "xxx", "status": "started" }

# 新需求：要加必填字段，会破坏老客户端
POST /api/v2/workflow/start  
请求体: { 
    "topic_direction": "美食",
    "content_type": "种草",      # 新增必填
    "target_platform": "xiaohongshu"  # 新增必填
}
响应: { 
    "thread_id": "xxx", 
    "workflow_id": "yyy",  # 字段名变了
    "status": "running"    # 状态值变了
}
```

```Python
app/api/
├── v1/
│   ├── workflow.py      # 保持不动，维护模式
│   └── image.py
├── v2/
│   ├── workflow.py      # 新版本，活跃开发
│   └── image.py
└── router.py

# router.py
app.include_router(v1_router, prefix="/api/v1")
app.include_router(v2_router, prefix="/api/v2")
```

### 场景二：非破坏性变更 → 直接改原接口

当变更向后兼容时，直接改v1：

```Bash
# 原接口
POST /api/v1/workflow/start
{ "topic_direction": "美食" }

# 新增可选字段，直接改v1（不需要v2）
POST /api/v1/workflow/start
{ 
    "topic_direction": "美食",
    "style": "轻松幽默"  # 新增，但是可选的，有默认值
}
```



数据库的字段变了怎么办？

一般数据库的字段是只增加不删除的。

会影响性能吗？会

但是 稳定性 \>性能





![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MmFkYmY3MzFiNTYwMTFjOWZjNGFjZjM3MTUyNjk4M2RfN2E4MGY4NjJmMjdlZDdjODFhMzUwNTk0YjYyNGM5NzlfSUQ6NzYwMjI4NjgyOTM3MDU3NTgwOV8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)



## Api限流与熔断

```Python
┌──────────────────────────────────────────────────────────┐
│                                                          │
│                    【限流】                               │
│                                                          │
│        用户 ──▶ 你的服务                                  │
│         │         │                                      │
│         │         │                                      │
│    请求太多      "我忙不过来，你少来点"                    │
│                                                          │
│    保护对象：自己                                          │
│    触发条件：请求量超过阈值                                │
│    目的：防止自己被压垮                                    │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                                                          │
│                    【熔断】                               │
│                                                          │
│        你的服务 ──▶ 下游服务（LLM/数据库/第三方API）       │
│            │            │                                │
│            │            │                                │
│         调用失败     "它挂了，我不等了"                    │
│                                                          │
│    保护对象：自己（不被下游拖死）                          │
│    触发条件：下游连续失败/超时                             │
│    目的：快速失败，不浪费资源等待                          │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ZDFkZDk5MzJjYzFlNzcxOWUwMTgwYjViNjAwMDQ2NjhfNjE0NWI4ODUyODNkZjU0N2EyYWJhYTBkNmI5ODMyM2FfSUQ6NzYwMjI5MzMwMzMxMjI1NTk2Nl8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)



```Python
from slowapi import Limiter
limiter = Limiter(key_func=get_remote_address)

@app.post("/workflow/start")
@limiter.limit("10/minute")  # 每分钟最多10次
async def start_workflow():
    pass
```

熔断器模式：

- 当LLM服务异常率超过阈值，自动熔断

- 熔断期间返回降级响应

- 半开状态探测恢复

```Python
熔断 ≠ 服务挂了
熔断 = 服务还在，但是走备用方案

就像：
高速公路封了 ≠ 你到不了目的地
高速公路封了 = 你走国道（慢一点，但能到）
```

```Python
class ContentService:
    
    @circuit_breaker(fail_max=5, reset_timeout=30)
    async def _call_llm(self, prompt: str):
        """真正的LLM调用，受熔断器保护"""
        return await self.llm.ainvoke(prompt)
    
    async def generate_article(self, topic: str):
        """对外暴露的方法，永远不会失败"""
        try:
            # 尝试调用LLM
            return await self._call_llm(topic)
        
        except CircuitBreakerOpen:
            # 熔断了，走降级
            logger.warning(f"LLM熔断中，返回降级结果")
            return self._get_fallback(topic)
    
    def _get_fallback(self, topic: str):
        """降级方案"""
        return {
            "title": f"关于{topic}的精彩内容",
            "content": "内容生成服务正在维护中，请稍后再试。",
            "is_degraded": True  # 标记这是降级结果
        }
```





真实企业方案：

### 网关层限流（最常见，推荐）



最终完整方案：

```Python
┌─────────────────────────────────────────────────────────┐
│                    多层防护体系                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│   第1层：CDN/WAF                                        │
│   └── DDoS防护、恶意IP封禁                               │
│                                                         │
│   第2层：API网关（Nginx/Kong/AWS）                       │
│   └── 全局限流（按IP、按用户、按接口）                    │
│                                                         │
│   第3层：应用层（代码）                                  │
│   └── 业务级限流（VIP用户配额更高）                      │
│   └── 熔断器（下游服务保护）                             │
│                                                         │
│   第4层：下游服务                                        │
│   └── LLM服务自己也有限流（火山引擎API限制）              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## 用户反馈闭环

```Python
用户反馈 → 数据收集 → 模型微调/Prompt优化 → 效果提升
    ↑                                          ↓
    ←─────────── A/B测试验证 ←────────────────←
```

业务优化方法论

提示词评测集

1. 流程跑完之后，我可以加一个功能

    1. 满意度调查 请你评价本次效果好不好

2. 收集数据（评测集、数据集）

    1. 提示词版本A

    2. 结果 A\_result

    3. 反馈： A\_用户评价

3. 有了样本之后，每次改动提示词，跑一次评测集（测试用例）。



可以怎么做，业务上设计

用户每次执行任务，数据库新建一张表专门维护数据集





## 错误边界与降级策略

```Python
请求1 ──▶ 尝试主服务 ──▶ 失败(等了10秒) ──▶ 走备用 ──▶ 失败计数=1
请求2 ──▶ 尝试主服务 ──▶ 失败(等了10秒) ──▶ 走备用 ──▶ 失败计数=2
请求3 ──▶ 尝试主服务 ──▶ 失败(等了10秒) ──▶ 走备用 ──▶ 失败计数=3 ──▶ 触发熔断！
────────────────────────────────────────────────────────────────
请求4 ──▶ 熔断器拦截 ──▶ 直接走备用（0秒）
请求5 ──▶ 熔断器拦截 ──▶ 直接走备用（0秒）
请求6 ──▶ 熔断器拦截 ──▶ 直接走备用（0秒）
...
30秒内都不尝试主服务
────────────────────────────────────────────────────────────────
30秒后 ──▶ 半开状态 ──▶ 放一个请求试试 ──▶ 成功了！──▶ 恢复正常
```

```Python
┌────────────────────────────────────────────────────────────────┐
│                                                                │
│   【简单降级】                                                  │
│                                                                │
│   请求 ──▶ 主服务(每次都试) ──▶ 失败 ──▶ 备用服务               │
│              │                                                 │
│              │ 超时10秒                                        │
│              ▼                                                 │
│         用户等了10秒才拿到结果                                  │
│                                                                │
│   问题：主服务挂了，每个用户都要等10秒                           │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│   【熔断降级】                                                  │
│                                                                │
│   请求 ──▶ 熔断器检查 ──▶ 开着 ──▶ 直接备用服务                 │
│              │                                                 │
│              │ 0秒                                             │
│              ▼                                                 │
│         用户秒拿到结果                                          │
│                                                                │
│   好处：快速失败，不浪费时间                                     │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

兜底方案

```Python
async def generate_content_with_fallback(topic: str):
    try:
        return await llm_primary.invoke(topic)  # 主模型
    except Exception:
        logger.warning("Primary LLM failed, fallback to secondary")
        return await llm_secondary.invoke(topic)  # 备用模型
    except Exception:
        return get_cached_template(topic)  # 兜底模板
```



## Api文档自动化

FastAPI自带Swagger文档，可增强：

```Python
@router.post("/workflow/start", 
    summary="启动内容生成工作流",
    description="根据主题方向生成小红书内容",
    response_model=WorkflowResponse,
    responses={
        200: {"description": "工作流启动成功"},
        429: {"description": "请求过于频繁"},
    }
)
```



## \_\_init\_\_\.py模块管理

```Python
backend/
├── app/                    ← 这是一个"包"
│   ├── __init__.py        ← 有这个文件，Python才认它是包
│   ├── main.py
│   └── core/              ← 这也是一个"包"
│       ├── __init__.py    ← 有这个文件，Python才认它是包
│       └── config.py
```

没有 init\.py 会怎样？

假设你在 main\.py 里想导入 config\.py：

```Python
from app.core import config  # ❌ 报错！
```

有了 init\.py 之后

```Python
from app.core import config  # ✅ 成功！
```

场景1：init\.py 是空的（或只有注释）

```Python
# 在其他文件中必须这样导入：
from app.core.config import settings
from app.core.logger import logger
```

场景2：init\.py 里写了导出代码

```Python
# app/core/__init__.py 内容：
from .config import settings
from .logger import logger
```

现在你可以更简洁地导入：

```Python
# 直接从 app.core 导入，不用写完整路径
from app.core import settings, logger
```

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=YTE5YWU4OGQzZmFhYWQzN2RjMjBhZWVlYWY1OGY4NzZfMjZkOTRiNGQzYmMyZjZjNjAwMDI5NDg2OWQzYzk5YWZfSUQ6NzYwMjQ5MDMyNTc1NTY2MTUzN18xNzgwODEyMTQ1OjE3ODA4OTg1NDVfVjM)



```Python
from .config import settings   
```

这句话啥意思，这不是从一个地方导入一个包进来吗？没有定义导出是啥啊？

Python 和 JavaScript 的关键区别

JavaScript 需要显式导出：



```Python
// config.js
const settings = { name: "app" };
export { settings };  // ← 必须写这个，别人才能导入
```

Python 不需要！

```Python
# config.py
settings = get_settings()  # ← 定义了就行，自动可以被导入
# 不需要写什么 export！
```

在 Python 里，只要你定义了，别人就能导入。不需要任何 export 声明。

```Python
*# __init__.py*
__all__ = ['module1', 'module2']
```

这个 只影响 当别人写：

```Python
*from* package *import* *  *# 星号导入*
```

这时候只会导入 module1 和 module2，其他的不会被星号导入。



\_\_init\_\_\.py 写了是空  和 不写有区别吗？

```Python
app/
├── __init__.py
├── main.py
└── graph/
    ├── __init__.py      ← 关键！
    └── workflow.py
```



```Python
# main.py
from app.graph import workflow  # ✅ 成功！
```

graph/init\.py 删掉

```Python
# main.py
from app.graph import workflow  # ⚠️ 可能出问题
```



## 图片包含敏感信息，生成失败

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=Nzk1MDU4MGQ1OTdmYTlkNTY5NjMwYTU0ODBjN2ZhYmRfOWY3MDBkOTZlOGE0ZDdkOWVkMDk2OTkwMzJkZjQzMTVfSUQ6NzYwMjU1NzgxNTg1NzE4Nzc3MV8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)



![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ZDIyNDQ3YjU2YzM5NDhmYmJhMmZlYzEyNGE5NDRjYTFfNzFiOTc4Yjk1MjMxYWI1Y2I1YTBiZGYwNzM2MTA2M2FfSUQ6NzYwMjU1NzYyMTIyOTAzMDYxNF8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)

1. 重试

2. 敏感词处理



处理的步骤

1. 提示词解决，告诉Ai 禁止输出敏感内容

2. LLM调用侧 PII检测的中间件

3. 图片LLM服务 安全设置





## 流程性能优化



没优化之前

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=NDI0Y2I3ZmM1MWVkMjNhNTM0N2E2NzQ0M2U3NzIzM2ZfZTY4NTk0N2Y1ZDY0MjBiZDZmYTk3YTVhYjk1OGMwYjNfSUQ6NzYwMjU2MTgwMzA3OTUwMzA0OF8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)



## LLM调用性能优化

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=YzlhMGUxNmEwMDMyNDkzY2NlZmI0M2FmNjNlMDJmZGJfMWE1NzRlNGYzYzkwOTUwM2FjODdiZDI2MDU5YTgwNDFfSUQ6NzYwMjU2MzY2MTYzMTcwNDI4N18xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)

生成选题调整 temperature为0合适吗？为什么

这是个好问题。选题生成用 temperature=0 其实不太合适。

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MzQyYmVlMGQ0ZjljMzg4ZWE0MWVkY2IxMjAzNjY1YTJfOTIzMTMxM2I2NDM4ZjJhNzhkNzkzNGYxZDVjY2UzMTNfSUQ6NzYwMjU2NDQzOTUwNjQwNjYxOF8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)

## 当前设置的问题

当前 LLM\_TEMPERATURE=0，意味着：

- 同一个主题方向，每次生成的选题几乎一样

- 缺乏多样性，用户重试也得不到新选题

- 对于创意类任务不理想

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=YWJiM2ExNmVkOTgxZmE2NmZlYTEwODExMTZiYzU4M2VfZGI5NDlmZGQxYTk2NTQ2MjFlOGY1ZmY1MWJjMDQ4NWVfSUQ6NzYwMjU2NDUwMzQxMDI2NTI4OV8xNzgwODEyMTQ1OjE3ODA4OTg1NDVfVjM)



## 最终效果

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ZGIxNWRiMTFkMTM0ZDJiNDkzZjdlNGM1NWEwZjBjYmJfNzg5NDlhNjgzOGU1ZjU5MzViMjQzZGQ1ZDAzNmJlMmRfSUQ6NzYwMjU2NzMwODA0OTkxMDk4Nl8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)

优化前

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=MTljNjFiNGUxZDkwN2Y0ZWY3OGQ3ZTBjNmRiYTMzZmFfMTNlNjc4MDhlZTUzMzljNzZmOGE5NjY2MGNmZDY2MGFfSUQ6NzYwMjU2NzE2NTU2NDU3MDgxNV8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)

优化后

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=Nzg4ODA1ODcxNjU5NGY4NDdmNTc4OWUyYTdlMmExNDJfMTFiMDhlMmFiMzBhZGMwMWI4MjRkN2Q3YzY2OTY5OTVfSUQ6NzYwMjU3OTQwMjAxNTE4MjAyMV8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=ZmRlOTM3NjU0N2ZjZDljNDQ4NWI1NWEyMzUzYjc5NGFfN2UxMWY4MzMwYzk1MTJhMTYyMmZjMWViYWZlYjVmMTZfSUQ6NzYwMjU4MjM5OTA2NzA5ODMxMF8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)

## 文章输出性能优化

最有效的优化手段。

1. 减少文章输出字数

2. 大模型本身快

## Nano\-banana

提示词

```Python
我现在想把图片生成改成nano banana模型。
我希望图片生成是小红书爆款图片，帮我优化提示词，输出图片比例统一3：4.

模型：gemini-3-pro-image-preview
api地址我用的国内加速：https://cn-beijing.yuannengai.com
key：your_api_key_here

这是文档给的调用示意：
import requests
import base64

def generate_image(prompt, api_key):
    url = "https://api.yuannengai.com/v1beta/models/gemini-3-pro-image-preview:generateContent"

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"]
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    response = requests.post(url, json=payload, headers=headers)
    result = response.json()

    # 提取图像数据
    for part in result["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            return part["inlineData"]["data"]

    return None

# 使用示例
image_base64 = generate_image("一只可爱的猫咪在阳光下睡觉", "your-api-key")

if image_base64:
    # 保存图像
    with open("cat.png", "wb") as f:
        f.write(base64.b64decode(image_base64))
    print("图像已生成并保存")
```

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=NGU2YWQ1MTcyNDM1ODEwMGQyMWU5YzQ4MDljY2IwNWZfZTJlOTdmZjdiOTU2NDIzMjM0NjFiMzU5N2M1ZTY0MzdfSUQ6NzYwMjU4Mjc1NzY2MzM3ODM5MV8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)





Api购买地址

~~https://www\.yuannengai\.com/console/token~~~~ ~~

https://api\.xunruijie\.com/



模型信息：

gemini\-3\-pro\-image\-preview

https://cn\-beijing\.yuannengai\.com

sk\-cLqcKKdysU6AhdT0nFF8GPvs57WqRmxSsYnr0ES7vhvdKIaf



```Python
import requests
import base64

def generate_image(prompt, api_key):
    url = "https://api.yuannengai.com/v1beta/models/gemini-3-pro-image-preview:generateContent"

    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"]
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    response = requests.post(url, json=payload, headers=headers)
    result = response.json()

    # 提取图像数据
    for part in result["candidates"][0]["content"]["parts"]:
        if "inlineData" in part:
            return part["inlineData"]["data"]

    return None

# 使用示例
image_base64 = generate_image("一只可爱的猫咪在阳光下睡觉", "your-api-key")

if image_base64:
    # 保存图像
    with open("cat.png", "wb") as f:
        f.write(base64.b64decode(image_base64))
    print("图像已生成并保存")
```



## 代码冗余设计优化

提示词

```Python
我帮我把服务端代码梳理下，
看有没有冗余代码设计，我希望代码能精简，流程清晰。不要过度防御性编程
```

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=OTJjNGExZTNkNDcxZThlY2U4NmJhOGQyMWE5NDE1ZGNfYThlNTI0YmMwNmY0MDY2MmI5NGRjMmI2ZjM0NGFjYWRfSUQ6NzYwMjU4ODQzMTI4NTUyMTYzNl8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)




## 项目架构设计

项目本身  Ai项目，Ai服务

![Image](https://internal-api-drive-stream.feishu.cn/space/api/box/stream/download/authcode/?code=YTFjNjhhMTAzMzljNDRkZmVmZGZhOWVhYTE2ZTgxNGJfNDZmMGVjMTJmMDdhZTNmYzQ5YzRiN2ZhYmY3YTVkOWFfSUQ6NzYwMjk4MjAzNTExMTg4OTg3Nl8xNzgwODEyMTQ2OjE3ODA4OTg1NDZfVjM)

## 系统架构设计

前端、后台、运维、Ai服务、数据库





# 项目登录流程设计

服务端

```SQL
POST /api/v1/auth/login  {"username": "john", "password": "123456"}
                              │
                              ▼
                 ┌────────────────────────┐
                 │  查询数据库找用户       │
                 │  SELECT * FROM users   │
                 │  WHERE username='john' │
                 └────────────────────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │  验证密码               │
                 │  verify_password(      │
                 │    "123456",           │
                 │    user.password_hash  │
                 │  )                     │
                 └────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
        验证失败                          验证成功
     返回 401 错误                             │
                                              ▼
                              ┌────────────────────────┐
                              │  生成 JWT Token        │
                              │  create_access_token(  │
                              │    {"sub": user.id}    │
                              │  )                     │
                              └────────────────────────┘
                                              │
                                              ▼
                              ┌────────────────────────┐
                              │  返回 Token            │
                              │  {                     │
                              │   "access_token":"eyJ.."│
                              │   "token_type":"bearer"│
                              │  }                     │
                              └────────────────────────┘
```

前端

```Python
┌─────────────────────────────────────────────────────────────┐
│  前端发起请求（任意需要认证的 API）                          │
│                                                             │
│  api.get('/auth/me')                                        │
│  api.post('/workflow/start', {...})                         │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  拦截器自动添加 Authorization 头                             │
│                                                             │
│  headers: {                                                 │
│    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIs..."        │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  后端收到请求                                                │
│                                                             │
│  Authorization: Bearer eyJhbGciOiJIUzI1NiIs...              │
│                        └────────────────────┘               │
│                              ↓                              │
│                    HTTPBearer 提取这部分                     │
│                              ↓                              │
│                    decode_access_token() 验证               │
└─────────────────────────────────────────────────────────────┘
```

## 登录流程梳理

注册

1. 前端输入用户名密码

2. 后台先查数据，是新用户

3. 注册，存入数据库

4. 返回token



登录

1. 前端输入用户名密码

2. 后台校验 你输入的 和数据库的加密字符串 比对

3. 通过，返回token



如何不同用户区分会话？

1. thread\_id = user\_id \+ 随机字符串

2. 查询的时候，根据user\_id的前缀查询



需要登录的接口怎么鉴权的？

```Python
async def **start_workflow**(
    *request*: StartWorkflowRequest,
    *current_user*: User = Depends(get_current_user)
) -> StartWorkflowResponse:
```



## 在真实的项目中，用户信息可能会存在redis中。

前提是，我的项目要非常高频的访问用户信息，和redis互动。

Redis特点：内存型数据库，适合数据少的高频读写

postgre：存硬盘



因为我们的项目是JWT，JWT的特点是自解析。

还有一种方案，把用户信息都用jwt加密

1. 用户名

2. 权限

3. 余额

不用依赖外部的redis。

而且可以保证我的服务器无状态，可以无限横向扩展。



用jwt方案（自解析）

用户登录

1. 查数据库（也可以是redis），返回用户的详细信息

2. 对详细信息加密，生成jwt的token

3. 用户再次访问api  服务器直接解密token

4. 服务器就直接操作

5. 返回数据给前端



传统的方案：（更加依赖redis）

1. 登录校验，查数据库   查到user id，也会对user\_id加密，返回token（不是jwt的）

2. 前端再次访问其他接口（查数据），携带token

3. 服务器解密token，拿到user id

4. 比如，你这个功能依赖用户的权限，刚好在用户这张表

5. 服务器查询用户表  拿用户的权限信息

6. 查业务数据库

7. 返回结果给前端



传统的方案会给数据库压力更大，比如说双11

并发流量来了。

用户的数据库，压力很大，也要跟着扩容。

我有1亿个用户，存redis  A。    扩展数据库  redisB

数据库的分布式

主从主备 读写分离

1. 主Redis（写入）

2. 从Redis（读）

每一个redis从，都要复制一份完整的数据。

1. 不仅要加业务服务器

2. 还要加用户数据库服务



JWT方案：双11

因为我已经登录，因为有已经有token了。

访问数据库，只需要带token，服务器就知道我的信息了。

面对压力的时候，只需要业务服务器扩容。

1. 只用加业务服务器



完美契合现在docker容器化架构（无状态）



# 关于项目面试的思考

Auth2\.0 SSO JWT我全部实现过，全部写过，干过，我在腾讯的时候全写过。

但是，今天在跟你们讲的时候，我全忘了，根本说不出来。

1. 这个活我一定能干

2. 说不出来

请问，面试能过吗？

肯定过不了。



1. 你没写过（Ai可以帮你写）

    1. gemini出方案

    2. claude干活

2. 但是你能说

请问面试能过不？

大概率可以

理解 \> 说 \> 能写

你要用最短的时间，达到最强的面试效果，一定是靠嘴！



# 项目源码解析与精华





## 日志记录

```Python
*# ============== Context Variables ==============*
*# 用于在请求生命周期内传递 request_id*
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", *default*=None)

```

这句话是整个日志系统的“灵魂”，它解决了在**高并发**环境下，如何准确追踪“哪条日志属于哪个请求”的问题。

简单来说，它定义了一个**线程/协程安全的全局变量**，专门用来存储当前请求的身份证号（`request_id`）。



在异步编程中，一个线程会并发地跑成百上千个协程。

- **如果用 ****`threading.local()`**：因为所有协程都运行在同一个线程里，协程 A 修改了数据，协程 B 就会看到修改后的值。日志里的 `request_id` 就会瞬间“张冠李戴”。

- **如果用 ****`ContextVar`**：即使多个协程在同一个线程里反复切换执行，Python 底层会确保每个协程只能读写属于自己的那份上下文数据。



`ContextVar`（上下文变量）是 Python 3\.7\+ 引入的特性，它的核心作用是：

- **隔离性**：它看起来像全局变量，但在不同的“执行上下文”（比如不同的协程或线程）中，它存的值是**互相隔离**的。

- **安全性**：在异步编程（`asyncio`）中，它能保证当一个协程挂起去执行另一个协程时，原本存储的 `request_id` 不会乱套。

**`request_id_var`**: 变量名。

**`ContextVar[Optional[str]]`**: 类型注解，表示这个容器里存的是“字符串”或者“None”。

**`"request_id"`**: 这个变量的标识符（内部名称）。

**`default=None`**: 初始默认值是 `None`。

想象一下这个过程：

1. **请求进入**：中间件（Middleware）接收到用户请求，生成一个 ID `a1b2c3`，通过 `request_id_var.set("a1b2c3")` 把 ID 塞进这个容器。

2. **业务逻辑**：代码执行到数据库操作、调用 AI 模型等。此时你只需调用 `logger.info``("Doing something")`，**不需要**手动把 ID 传给 logger。

3. **日志处理器**：代码中的 `add_request_id` 处理器会自动运行 `request_id_var.get()`，拿到 `a1b2c3` 并印在日志里。

4. **请求结束**：中间件调用 `clear_request_id()`，清空容器，迎接下一个请求。

1. 请求A   进来创建一个id   

    1. 记录 A ： id是xxx  开始处理用户请假

2. 请求A  去查询数据库 

    1. 记录A：id是xxx，开始查数据库

3. 请求A 去返回结果\(\)

    1. 记录A，id是xxx，返回结果是



1. 请求B   进来创建一个id   

    1. 记录 B ： id是xxx  开始处理用户请假

2. 请求B  去查询数据库 

    1. 记录B：id是xxx，开始查数据库

3. 请求B 去返回结果\(\)

    1. 记录B，id是xxx，返回结果是









没问题，我们直接看一个**高并发**（两个用户同时访问）的场景。

想象你在做一个“小红书助手”，两个用户同时点击了“生成文案”。



如果你图省事，用一个普通的变量来存 ID：

```Python
# 错误示范：普通的全局变量
current_request_id = None

async def handle_request(user_name, request_id):
    global current_request_id
    current_request_id = request_id  # 步骤 A：存入 ID
    
    await asyncio.sleep(1)           # 步骤 B：模拟耗时操作（比如调用 AI）
    
    print(f"用户 {user_name} 的日志 | ID: {current_request_id}")
```

**发生的惨剧：**

1. **用户甲** 进来了，ID 是 `AAA`。程序执行步骤 A，`current_request_id` 变成 `AAA`。

2. **用户甲** 执行到步骤 B，开始等 AI 响应。此时 **用户乙** 进来了！

3. **用户乙** ID 是 `BBB`。程序执行步骤 A，把全局变量改成了 `BBB`。

4. **用户甲** 的 AI 响应完了，继续跑。打印日志时，它读到的是被用户乙改掉的 `BBB`。

**结果：**

> 用户甲 的日志 \| ID: BBB  \<\-\- **写错了！** 用户乙 的日志 \| ID: BBB
> 
> 

### 使用 `request_id_var` \(ContextVar\)

现在我们换成你源码里的原生写法：

```Python
from contextvars import ContextVar
import asyncio

# 正确示范：原生上下文变量
request_id_var = ContextVar("request_id", default=None)

async def handle_request(user_name, request_id):
    # 步骤 A：存入 ID，这个 ID 只在当前这个“执行流”里有效
    request_id_var.set(request_id)
    
    await asyncio.sleep(1) # 步骤 B：即使这里切换去跑别的请求了，回来时 ID 还在
    
    # 步骤 C：取出 ID
    rid = request_id_var.get()
    print(f"用户 {user_name} 的日志 | ID: {rid}")

# 模拟并发运行
async def main():
    await asyncio.gather(
        handle_request("用户甲", "AAA"),
        handle_request("用户乙", "BBB")
    )

asyncio.run(main())
```











# 简历模板

## 自媒体智能内容运营系统（Graph RAG \+ LangGraph） 2025\.X \~ 至今

1. 基于 LangGraph 构建多阶段内容生成工作流，采用 SubGraph 子图模式将选题、写作、配图拆分为独立编排单元；通过 PostgreSQL Checkpointer 实现状态持久化，支持任意历史节点回滚与增量重试，将复杂流程的故障恢复粒度从整图级别细化至单节点级别。

2. 设计 MetricsContext 上下文管理器实现 LLM 全链路追踪，精准采集各节点 Token 消耗、推理延迟及错误率；结合火山引擎 API 定价模型完成成本核算，为模型选型与资源调优提供数据支撑。

3. 实现 SSE 流式输出与 LangGraph astream\_events 深度集成，通过监听 on\_chat\_model\_stream 事件捕获 Token 级别实时流，配合前端 ReadableStream 解析，将用户感知的首字延迟（TTFT）降低 60%；同时保证流式与非流式模式下 Checkpointer 数据结构一致性。

4. 针对图片批量生成场景实现异步并行优化，通过 asyncio\.gather 配合 run\_in\_executor 将同步 API 封装为协程，多张配图生成由串行改为并发执行；引入指数退避重试策略（1s→2s→4s），有效应对 LLM 服务抖动，整体生成耗时缩减 70%。

5. 构建多模型动态路由机制，简单任务分发至轻量 Flash 模型，复杂任务路由至旗舰模型（Doubao\-1\.8）；结合 with\_structured\_output 实现 Pydantic Schema 强约束输出，并通过 JSON Mode \+ 手动解析方案解决结构化输出与 Token 统计不兼容问题，在保证输出质量的同时降低 40% 推理成本。

6. 设计环境变量驱动的 Mock 开关体系（llm\_mock、image\_mock、checkpointer\_mock），实现开发阶段与外部服务解耦；配合 Swagger UI 可视化评测与 Ngrok 公网映射，将本地调试效率提升 3 倍，团队迭代周期从 2 天缩短至半天。

7. 接入 LangSmith 实现 Graph 全链路可观测性，自动采集节点流转路径、State 注入状态及各阶段耗时；配合 structlog 结构化日志与 request\_id 关联机制，实现问题定位从小时级压缩至分钟级。

8. 基于 SlowAPI 实现接口级限流（10 次/分钟），引入熔断器模式保护下游 LLM 服务，当连续失败超过阈值自动切换降级模板响应；结合健康检查端点（/health）与优雅关闭机制，确保容器化部署场景下服务的高可用性。



