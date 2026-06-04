# 小红书 AI 内容运营助手 — 零基础学习路线

> 本项目是一个基于 **LangGraph** + **FastAPI** + **Vue 3** 构建的 AI 内容生成工作流。下面的路线从完全零基础开始，分阶段逐步掌握所有核心技术。每个阶段都有明确的**学习目标**、**推荐资源**和**实操任务**。

---

## 学习阶段总览

```
第一阶段：编程基础（Python）      → 预计 2~3 周
第二阶段：前端入门（HTML/CSS/JS）  → 预计 1~2 周
第三阶段：Vue 3 渐进式框架        → 预计 1~2 周
第四阶段：Python Web 开发（FastAPI）→ 预计 2~3 周
第五阶段：数据库与 SQL             → 预计 1~2 周
第六阶段：AI 与 LLM 概念           → 预计 1~2 周
第七阶段：LangGraph 工作流编排      → 预计 2~3 周
第八阶段：项目实战 & 部署           → 预计 1~2 周
─────────────────────────────────────────────
总计：约 11~19 周
```

---

## 第一阶段：Python 编程基础

**目标**：能独立写脚本、处理数据、调用 API

### 1.1 环境安装

1. 安装 **Python 3.10+**（推荐 3.11）
   - 官网：https://www.python.org/downloads/
   - 安装时勾选 "Add Python to PATH"
   - 验证：命令行运行 `python --version`

2. 安装代码编辑器 **VS Code**
   - 官网：https://code.visualstudio.com/
   - 安装 Python 插件：`Ctrl+Shift+X` → 搜索 "Python" → 安装微软官方插件

3. 使用 **venv** 创建虚拟环境（项目隔离）

```bash
# 进入项目目录
cd d:\graph_xiaohongshu-master-main\graph_xiaohongshu-master-main

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境（Windows PowerShell）
.\venv\Scripts\Activate.ps1
# 或 CMD：
# venv\Scripts\activate.bat

# 安装依赖
pip install -r requirements.txt
```

### 1.2 Python 核心语法（第一周）

| 知识点 | 目标 | 练习任务 |
|--------|------|----------|
| 变量与数据类型 | 理解 int, str, float, bool | 写一个计算器脚本 |
| 条件判断 if/else | 能写分支逻辑 | 成绩评级程序 |
| 循环 for/while | 能遍历数据 | 打印九九乘法表 |
| 函数 def | 能封装复用代码 | 写一个天气查询函数 |
| 列表/字典 | 能存储和操作数据 | 通讯录增删改查 |
| 文件读写 | 能读写文本文件 | 日志文件读写 |
| 异常处理 try/except | 能处理运行时错误 | 改进上面的程序 |

**推荐资源**：
- B站：Python 入门 — 小甲鱼 / 莫烦 Python
- 书籍：《Python 编程：从入门到实践》（艾里克）
- 在线：https://docs.python.org/zh-cn/3/tutorial/（官方教程中文版）

### 1.3 Python 进阶（第二周）

| 知识点 | 目标 | 练习任务 |
|--------|------|----------|
| 面向对象（class） | 理解类与对象 | 写一个 User 类 |
| 模块与包 import | 会组织代码结构 | 重构上面的程序 |
| 列表推导式 | 能写简洁的数据处理 | 筛选过滤数据 |
| lambda 与 map/filter | 理解函数式编程 | 数据转换管道 |
| json 处理 | 能读写 JSON 数据 | 读取配置文件 |
| requests 库 | 能发送 HTTP 请求 | 调用天气 API |
| 虚拟环境 pip | 能管理项目依赖 | 独立创建一个小项目 |

**实操任务**：写一个命令行工具，调用公开 API（如天气、新闻），输出格式化结果。

### 1.4 第一阶段检验

```
[  ] 能独立创建虚拟环境并安装依赖
[  ] 能写一个 100 行以内的 Python 脚本
[  ] 能读写 JSON 文件
[  ] 能用 requests 调用一个外部 API
```

---

## 第二阶段：前端基础（HTML/CSS/JavaScript）

**目标**：理解网页是如何工作的，能看懂和修改前端代码

### 2.1 HTML — 网页骨架

| 知识点 | 目标 | 练习任务 |
|--------|------|----------|
| 标签与元素 | 理解 `<div>`, `<p>`, `<button>` 等 | 写一个自我介绍页面 |
| 属性与链接 | 会写 href, src, class | 添加图片和超链接 |
| 表单元素 | 理解 input, select, button | 写一个登录表单 |
| 语义化标签 | 会用 `<header>`, `<main>`, `<footer>` | 重构自我介绍页面 |

**推荐资源**：
- B站：Web 入门全套（pink 老师）
- 交互式：https://flexboxfroggy.com/（CSS Flexbox 游戏）
- 交互式：https://cssgridgarden.com/（CSS Grid 游戏）

### 2.2 CSS — 网页样式

| 知识点 | 目标 | 练习任务 |
|--------|------|----------|
| 选择器 | 会用 class、id、标签选择器 | 给 HTML 页面加样式 |
| 盒模型 | 理解 margin/border/padding/content | 布局卡片组件 |
| Flexbox | 能用弹性盒子布局 | 导航栏 + 内容区布局 |
| CSS 变量 | 会定义主题色 | 做一个简易 UI 组件库 |
| 响应式 media query | 能适配手机屏幕 | 移动端适配 |

**实操任务**：把第一阶段的自我介绍页面美化，要求有头部、主体内容、底部，使用 Flexbox 布局。

### 2.3 JavaScript — 网页交互

| 知识点 | 目标 | 练习任务 |
|--------|------|----------|
| 变量与数据类型 | 理解 let/const | 变量操作练习 |
| 函数与作用域 | 能定义和调用函数 | 计算器逻辑 |
| DOM 操作 | 能获取和修改页面元素 | 点击按钮修改文字颜色 |
| 事件监听 | 能响应用户点击/输入 | 表单验证 |
| 数组与对象 | 能处理 JSON 数据 | 数据列表渲染 |
| Fetch API | 能发送网络请求 | 调用后端接口 |
| ES6 模块 | 会用 import/export | 代码模块化拆分 |

**实操任务**：用纯 HTML/CSS/JS 写一个 Todo 列表，支持添加、删除、完成待办。

**推荐资源**：
- B站：JavaScript 入门（李南江 / 尚硅谷）
- 书籍：《你不知道的 JavaScript》上卷
- 练习：https://www.frontendmentor.io/（前端挑战题）

---

## 第三阶段：Vue 3 渐进式框架

**目标**：能用 Vue 3 开发组件，理解响应式原理

### 3.1 Vue 3 核心概念

| 知识点 | 目标 | 项目对应代码 |
|--------|------|-------------|
| 模板语法 | 理解 `{{ }}` 和 `v-bind` | `frontend/src/App.vue` |
| 响应式 ref/reactive | 理解数据驱动视图 | 文章列表状态管理 |
| 条件渲染 v-if/v-show | 显示/隐藏元素 | 加载状态切换 |
| 列表渲染 v-for | 循环渲染列表 | 文章卡片列表 |
| 事件处理 v-on | 响应用户操作 | 按钮点击事件 |
| 表单绑定 v-model | 双向数据绑定 | 登录表单 |
| 组件基础 | 会拆分和使用组件 | `App.vue` 中的各个区域 |

**学习建议**：
1. 先通读 Vue 官方文档（中文）：https://cn.vuejs.org/guide/
2. 跟着官方教程做一个小 demo
3. 再看项目的 `App.vue` 文件，理解真实项目结构

### 3.2 理解项目前端代码

```14:51:frontend/src/App.vue
export default {
  data() { ... },
  computed: { ... },
  methods: { ... }
}
```

重点看本项目的 `App.vue`：
- 它用 Vue 3 Options API 定义了哪些数据和方法
- 它调用了 `api.js` 中的哪些接口
- 流式输出（SSE）是如何处理的

### 3.3 组件化与 API 调用

| 知识点 | 目标 |
|--------|------|
| 组件拆分 | 能把大组件拆成小组件 |
| Props 与 Emit | 父子组件通信 |
| Axios | 能调用 FastAPI 后端接口 |
| Vue Router（可选） | 多页面导航 |
| Pinia（可选） | 状态管理 |

**实操任务**：在项目中添加一个新功能（比如显示当前时间），然后提交代码。

---

## 第四阶段：Python Web 开发（FastAPI）

**目标**：能理解 REST API 概念，看懂并扩展本项目的后端接口

### 4.1 API 基础概念

**什么是 API？** — 想象餐厅的菜单，厨房（后端）把能做菜的清单（接口列表）写在菜单上，顾客（前端）按菜单点菜（发送请求），厨房做好后上菜（返回数据）。

| 概念 | 类比 | 本项目示例 |
|------|------|-----------|
| URL | 菜品名称 | `/api/v1/auth/login` |
| HTTP 方法 | 点菜方式 | GET（查）、POST（增） |
| Request | 顾客点的菜和口味 | 登录名 + 密码 |
| Response | 厨房端上来的菜 | JWT token |
| JSON | 标准化菜品描述格式 | `{"access_token": "xxx"}` |

### 4.2 FastAPI 入门

```python
# 最简单的 FastAPI 示例
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.post("/items/")
def create_item(name: str, price: float):
    return {"name": name, "price": price}
```

**运行方式**：

```bash
# 安装 uvicorn（ASGI 服务器）
pip install uvicorn

# 启动服务（热重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**自动文档**：FastAPI 自带交互式 API 文档
- Swagger UI：http://127.0.0.1:8000/docs
- ReDoc：http://127.0.0.1:8000/redoc

### 4.3 Pydantic 数据模型

| 概念 | 说明 | 本项目示例 |
|------|------|-----------|
| BaseModel | 定义数据结构 | `LoginRequest`, `TokenResponse` |
| Field | 字段验证 | `@Field(..., min_length=1)` |
| validator | 自定义验证 | 密码复杂度检查 |

### 4.4 本项目后端结构

```
app/
├── main.py              # FastAPI 应用入口，注册路由
├── api/
│   └── v1/
│       ├── auth.py      # 认证接口（登录/注册）
│       ├── workflow.py  # 工作流接口（启动/状态/人工操作）
│       └── image.py     # 图像相关接口
├── core/
│   ├── config.py        # 环境变量配置
│   ├── security.py      # JWT + 密码哈希
│   ├── db.py           # 数据库连接
│   └── middleware.py    # 中间件（日志、PII 脱敏）
├── graph/
│   ├── workflow.py      # LangGraph 工作流主定义
│   ├── state.py        # 工作流状态定义
│   ├── nodes/          # 工作流节点（planner/writer/visualizer）
│   └── subgraphs/      # 子图（如 topic_selection）
├── models/             # SQLAlchemy 数据库模型
└── services/           # 业务逻辑服务（llm_service, image_service）
```

### 4.5 理解核心接口

| 文件 | 接口路径 | 功能 |
|------|---------|------|
| `auth.py` | POST `/api/v1/auth/login` | 用户登录，返回 JWT token |
| `auth.py` | POST `/api/v1/auth/register` | 用户注册 |
| `workflow.py` | POST `/api/v1/workflow/start` | 启动工作流（输入主题） |
| `workflow.py` | GET `/api/v1/workflow/{run_id}/state` | 查询工作流状态 |
| `workflow.py` | POST `/api/v1/workflow/{run_id}/resume` | 人工操作后恢复工作流 |
| `image.py` | GET `/api/v1/images/{filename}` | 获取生成的图片 |

**实操任务**：阅读 `app/api/v1/auth.py` 代码，理解登录流程（从请求到 JWT 返回），然后尝试添加一个新接口。

---

## 第五阶段：数据库基础（PostgreSQL + SQLAlchemy）

**目标**：理解关系型数据库概念，能读写数据

### 5.1 数据库基础

| 概念 | 说明 |
|------|------|
| 表（Table） | 就像 Excel 表格，有行有列 |
| 列（Column） | 字段，如 id, username, created_at |
| 行（Row） | 一条记录，如一个用户的信息 |
| 主键（Primary Key） | 唯一标识一行，如用户 ID |
| 外键（Foreign Key） | 表之间的关联，如 user_id |

**SQL 基础命令**：

```sql
-- 创建表
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 插入数据
INSERT INTO users (username, password_hash) VALUES ('alice', 'xxx');

-- 查询数据
SELECT * FROM users WHERE username = 'alice';

-- 更新数据
UPDATE users SET username = 'bob' WHERE id = 1;

-- 删除数据
DELETE FROM users WHERE id = 1;
```

### 5.2 SQLAlchemy 异步 ORM

| 概念 | 说明 | 本项目示例 |
|------|------|-----------|
| Engine | 数据库连接引擎 | `create_async_engine` |
| Session | 数据库会话 | `AsyncSession` |
| Model | 数据模型类 | `app/models/user.py` |
| CRUD | 增删改查操作 | 登录时的用户查询 |

**本项目的数据库模型**：

```python
# app/models/user.py（简化版）
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

### 5.3 PostgreSQL 安装与使用

**Windows 安装**：
1. 下载：https://www.postgresql.org/download/windows/
2. 安装时记住超级用户密码
3. 安装 pgAdmin（图形化管理工具）

**连接数据库**：

```bash
# 命令行连接
psql -U postgres -d 数据库名

# pgAdmin：浏览器打开 http://127.0.0.1:5050
```

**实操任务**：
1. 安装 PostgreSQL
2. 创建一个数据库 `ai_content_db`
3. 导入 `scripts/init_db.sql` 初始化表结构
4. 用 pgAdmin 查看创建的表结构

---

## 第六阶段：AI 与 LLM 概念入门

**目标**：理解大语言模型是什么，能调用 AI 接口

### 6.1 大语言模型（LLM）基础

| 概念 | 通俗解释 |
|------|---------|
| LLM | 训练过海量文本的 AI，能理解和生成文字 |
| Prompt | 给 LLM 的指令（提示词） |
| Token | 文本处理的最小单位（1 个中文 ≈ 1-2 个 token） |
| Temperature | 控制输出的随机性（0=确定，1=创意） |
| System Prompt | 给 LLM 设定角色和行为规则 |
| Context Window | LLM 一次能处理的文本上限 |

### 6.2 LangChain 快速入门

LangChain 是调用 LLM 的封装框架，让 AI 应用开发更简单。

```python
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
from langchain.prompts import PromptTemplate

# 初始化模型（本项目用的是火山引擎 Doubao，兼容 OpenAI 接口）
llm = ChatOpenAI(
    model="doubao-pro-32k",
    openai_api_key="your-api-key",
    openai_api_base="https://ark.cn-beijing.volces.com/api/v3/"
)

# 简单调用
response = llm.invoke([HumanMessage(content="用一句话解释量子计算")])
print(response.content)

# 使用 PromptTemplate
template = PromptTemplate.from_template("请用{style}风格写一篇关于{topic}的文章")
chain = template | llm
result = chain.invoke({"style": "轻松", "topic": "人工智能"})
print(result.content)
```

### 6.3 本项目的 AI 调用

| 文件 | 作用 |
|------|------|
| `app/services/llm_service.py` | 调用 Doubao LLM 的统一封装 |
| `app/graph/nodes/planner.py` | 用 LLM 生成选题 |
| `app/graph/nodes/writer.py` | 用 LLM 撰写文章 |
| `app/graph/nodes/visualizer.py` | 用 LLM 提取配图描述 |

**重点理解** `llm_service.py`：
1. 如何初始化 ChatOpenAI 客户端
2. 如何构造 Prompt（系统提示词 + 用户输入）
3. 如何处理响应（parse JSON / stream 输出）

### 6.4 AI 应用开发关键概念

| 概念 | 本项目中的应用 |
|------|--------------|
| 结构化输出（JSON Mode） | 选题以 JSON 格式返回，保证格式一致 |
| 流式输出（SSE） | 文章一个字一个字地显示，打字机效果 |
| Prompt Engineering | 不同节点用不同的 system prompt |
| RAG（检索增强） | 将来可扩展：先检索素材再生成 |
| Human-in-the-loop | AI 生成 → 人工审核 → AI 继续 |

---

## 第七阶段：LangGraph 工作流编排

**目标**：理解 LangGraph 的核心概念，能看懂和修改工作流

### 7.1 什么是 LangGraph？

LangGraph = **有状态的 LLM 应用**。

| 普通 LLM 调用 | LangGraph 工作流 |
|-------------|----------------|
| 一次调用，一次响应 | 多步骤、可中断、可恢复 |
| 无状态 | 有状态（保留上下文） |
| 无法人工介入 | 支持人工决策点（interrupt） |
| 线性流程 | 支持条件分支、并行、循环 |

### 7.2 LangGraph 四大核心概念

```
┌─────────────────────────────────────────────────────────┐
│                      STATE（状态）                        │
│  整个工作流共享的数据字典，记录当前进展和中间结果             │
│  例如: { topics: [...], selected_topic: null, draft: "" }│
└─────────────────────────────────────────────────────────┘
          │                           ▲
          ▼                           │
┌─────────────────────────────────────────────────────────┐
│                    NODES（节点）                          │
│  工作流中的一个个处理步骤，类似流水线上的工位                │
│  例如: planner（生成选题）→ writer（写文章）→ visualizer（生成图）│
└─────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────┐
│                     EDGES（边）                          │
│  连接节点的线，定义"谁处理完之后去哪"                       │
│  简单边：planner → writer（无条件）                        │
│  条件边：planner → [writer / 重新选题]（根据结果判断）       │
└─────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────┐
│              CHECKPOINTER（检查点）                        │
│  每个节点处理完后，把状态自动保存到数据库                    │
│  断电重启？恢复！人工介入？暂停！                           │
└─────────────────────────────────────────────────────────┘
```

### 7.3 本项目工作流详解

**完整流程图**：

```
用户输入主题 "AI技术"
       │
       ▼
┌──────────────────┐
│  interrupt()     │  ← 暂停，等用户选择选题
│  选题生成节点     │
└──────────────────┘
       │
       ▼
  用户选择 [3] 号选题
       │
       ▼
┌──────────────────┐
│  interrupt()     │  ← 暂停，等用户审核
│  文章撰写节点     │
└──────────────────┘
       │
       ▼
  用户点"通过"
       │
       ▼
┌──────────────────┐
│  配图生成节点     │
│  (并行生成 5 张)   │
└──────────────────┘
       │
       ▼
    工作流完成
```

### 7.4 核心代码解读

**state.py — 定义工作流状态**：

```python
# app/graph/state.py
class WorkflowState(TypedDict):
    # 输入
    topic: str                          # 用户输入的主题
    # 选题阶段
    topics: Annotated[list, operator.add]  # 生成的选题列表
    selected_topic: str | None          # 用户选择的选题
    # 写作阶段
    article_draft: str                  # 文章草稿
    # 审核结果
    review_result: str | None           # 通过/修改/重新选题
    # 配图阶段
    image_prompts: list[str]            # 图片描述词
    generated_images: list[str]         # 生成的图片路径
    # 元数据
    run_id: str | None
    user_id: str | None
```

**workflow.py — 定义工作流**：

```python
# app/graph/workflow.py
from langgraph.graph import StateGraph, END, START

# 创建图
graph = StateGraph(WorkflowState)

# 添加节点
graph.add_node("planner", plan_node)        # 选题
graph.add_node("writer", write_node)        # 写作
graph.add_node("visualizer", visualize_node) # 配图

# 添加边
graph.add_edge(START, "planner")            # 开始 → 选题
graph.add_edge("planner", END)             # 选题后中断（interrupt）
graph.add_edge("writer", END)              # 写作后中断（interrupt）
graph.add_edge("visualizer", END)          # 配图后结束

# 编译
compiled_graph = graph.compile(
    checkpointer=PostgresSaver(...)        # 持久化到数据库
)
```

**nodes/planner.py — 选题节点**：

```python
async def plan_node(state: WorkflowState) -> dict:
    # 1. 构建 prompt（系统提示词 + 用户主题）
    prompt = build_planner_prompt(state["topic"])

    # 2. 调用 LLM（JSON Mode，返回结构化选题）
    response = await llm_service.invoke(prompt, json_mode=True)

    # 3. 解析选题列表
    topics = parse_topics(response)

    # 4. 更新状态（注意这里用 return，不是直接修改）
    return {"topics": topics}
```

### 7.5 interrupt（人工介入）原理

```python
# 关键：当节点返回 {"topics": [...]} 后
# LangGraph 检测到 graph.add_edge("planner", END)
# → 但 END 前遇到了 interrupt()
# → 状态自动保存到 PostgreSQL
# → 工作流暂停，等待外部恢复

# 前端调用 resume 接口恢复：
# POST /api/v1/workflow/{run_id}/resume
# body: {"action": "select_topic", "topic_index": 2}
```

### 7.6 第二阶段检验

```
[  ] 能画出本项目 LangGraph 工作流的完整流程图
[  ] 能解释 State 中每个字段的含义和作用
[  ] 能解释为什么需要 interrupt，它在哪两个节点出现
[  ] 能修改节点 prompt，观察输出的变化
[  ] 能在 writer 节点添加一个新字段（如"文章摘要"）
```

---

## 第八阶段：项目实战与部署

### 8.1 本地运行完整项目

**前置条件**：
- [ ] Python 3.10+ 已安装
- [ ] PostgreSQL 已安装并运行
- [ ] 火山引擎 API Key 已申请（https://console.volcengine.com/ark）
- [ ] Gemini API Key 已申请（可选，用于配图）

**启动步骤**：

```bash
# 1. 克隆项目（如果还没克隆）
git clone <项目地址>
cd graph_xiaohongshu-master-main

# 2. 创建虚拟环境
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. 安装后端依赖
pip install -r requirements.txt

# 4. 配置环境变量
# 复制 .env.example 为 .env，填入你的 API Key
# cp .env.example .env

# 5. 初始化数据库
psql -U postgres -c "CREATE DATABASE ai_content_db;"
psql -U postgres -d ai_content_db -f scripts/init_db.sql

# 6. 启动后端
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 7. 新开终端，启动前端
cd frontend
npm install
npm run dev
```

### 8.2 功能验证清单

```
[  ] 前端页面能打开（http://localhost:5173）
[  ] 能注册新账号并登录
[  ] 输入主题"AI技术"，能看到选题生成
[  ] 能选择一个选题
[  ] 能看到文章流式生成
[  ] 能审核文章并通过
[  ] 能看到配图生成
[  ] 数据库中能看到 LangGraph 的 checkpoint 数据
```

### 8.3 调试技巧

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
  -d '{"topic": "Python 编程"}'
```

### 8.4 扩展建议

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
psql -U postgres -d ai_content_db
# 或用 pgAdmin 图形界面
```

### B. 推荐工具

| 工具 | 用途 |
|------|------|
| VS Code | 代码编辑器（主力开发工具） |
| pgAdmin | PostgreSQL 图形化管理 |
| Postman / Insomnia | API 调试工具 |
| DBeaver | 数据库客户端 |
| Vue DevTools | Vue 浏览器调试插件 |
| ChatGPT / Kimi | AI 辅助学习与代码生成 |

### C. 遇到问题怎么办

1. **看报错信息**：错误信息本身就是答案
2. **搜索引擎**：CSDN、知乎、Stack Overflow
3. **AI 助手**：用 Kimi/ChatGPT 解释代码和报错
4. **官方文档**：FastAPI、LangGraph、Vue 都有中文文档
5. **项目 README**：本项目的 README.md 有详细说明
6. **问人**：技术社区提问要附上完整的报错信息和代码片段
