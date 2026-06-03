"""
LangGraph 工作流定义模块
=============================================================================
职责说明：
  组装完整的 AI 内容运营工作流，定义所有节点和它们之间的流转关系。

核心概念：
  - StateGraph：LangGraph 的核心类，代表一个有向图
  - Node（节点）：工作流中的一个处理步骤（Python 函数）
  - Edge（边）：节点之间的连接，代表执行顺序
  - Subgraph（子图）：把一组节点封装成子工作流
  - interrupt()：LangGraph 1.0+ 的人工中断机制
  - Command：LangGraph 1.0+ 的恢复指令

工作流完整路径：
  Start
    -> topic_selection [子图]
        -> plan_topics（AI 生成选题）
        -> interrupt（等待用户选择）
    -> write_draft（AI 生成文章）
    -> human_review（人工审核）
        -> approve: extract_visuals -> generate_images -> End
        -> reject: 回到 write_draft

为什么用 interrupt？
  AI 内容生成需要人工把关（选题选择、文章审核）
  interrupt() 让 AI 执行到关键节点时暂停，等待人工输入后再继续

典型场景：
  1. graph.ainvoke(initial_input, config) 开始执行
  2. 走到 topic_selection 子图，plan_topics 生成选题
  3. 遇到 interrupt，暂停并返回选题列表
  4. 用户调用 graph.ainvoke(Command(resume={"selected_topic": "xxx"}), config) 恢复
  5. 工作流继续执行 write_draft（生成文章）
  6. 遇到 human_review 的 interrupt，暂停并返回文章
  7. 用户 approve -> 继续 extract_visuals + generate_images -> 完成
=============================================================================
"""
from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

from app.graph.state import AgentState
from app.graph.nodes import (
    write_draft_node,
    extract_visuals_node,
    generate_images_node,
)
from app.graph.utils import get_checkpointer
from app.graph.subgraphs.topic_selection import get_compiled_topic_selection_subgraph


# =============================================================================
# 第 1 步：人工审稿节点
# =============================================================================

async def human_review_node(state: AgentState) -> Command[Literal["extract_visuals", "write_draft"]]:
    """
    人工审稿节点（使用 LangGraph 1.0+ interrupt 模式）

    ==========================================================================
    工作流程：
      1. 读取 state 中的 article_content（AI 生成的文章草稿）
      2. 调用 interrupt() 暂停工作流，等待人工审核
      3. 用户通过 API 传入审核结果（approve 或 reject）
      4. 根据用户选择，返回不同的路由指令

    interrupt() 机制说明：
      interrupt() 是 LangGraph 1.0+ 的人工中断机制
      它会暂停图执行，等待外部输入（通过 Command）恢复
      传入的字典会被作为 user_input 传递给 interrupt() 之后的代码

    参数说明：
      - state["article_content"]：AI 生成的文章草稿
        用于显示给审核人员

    返回值说明：
      Command 对象告诉 LangGraph 两件事：
      1. update={}：恢复后要更新哪些状态字段
      2. goto="xxx"：下一步要去哪个节点

    典型场景：
      # 用户 approve
      return Command(update={"review_status": "approved", ...}, goto="extract_visuals")
      -> 触发 extract_visuals 节点（生成配图）

      # 用户 reject
      return Command(update={"review_status": "rejected", "review_feedback": feedback, ...}, goto="write_draft")
      -> 触发 write_draft 节点（根据反馈重写文章）
    """
    article_content = state.get("article_content", "")

    # ---------- 中断：等待人工审核 ----------
    # interrupt() 的参数会传给恢复时的 user_input
    # 这里传入审核所需的信息：文章内容、操作选项
    user_input = interrupt({
        "message": "请审核以下文章内容",
        "article_preview": article_content[:500] + "..." if len(article_content) > 500 else article_content,
        "action_required": "review",
        "options": ["approve", "reject"]
    })

    # ---------- 解析用户审核结果 ----------
    # user_input 是 API 通过 Command(resume={...}) 传入的字典
    if isinstance(user_input, dict):
        action = user_input.get("action", "reject")
        feedback = user_input.get("feedback", "")
    else:
        action = "reject"
        feedback = ""

    # ---------- 根据审核结果决定下一步 ----------
    if action == "approve":
        # 审核通过：进入配图生成阶段
        return Command(
            update={
                "review_status": "approved",
                "review_feedback": "",
                "status": "review_approved",
            },
            goto="extract_visuals"
        )
    else:
        # 审核驳回：回到文章写作阶段（带反馈重写）
        return Command(
            update={
                "review_status": "rejected",
                "review_feedback": feedback,
                "status": "review_rejected",
            },
            goto="write_draft"
        )


# =============================================================================
# 第 2 步：构建工作流图
# =============================================================================

def build_workflow_graph() -> StateGraph:
    """
    构建工作流图（LangGraph 1.0+ 语法）

    ==========================================================================
    工作流程图：
      ┌──────────────┐
      │    START     │
      └──────┬───────┘
             │
             v
      ┌──────────────────┐
      │ topic_selection  │  (子图)
      │  ├─ plan_topics │
      │  └─ interrupt() │  (等待选题)
      └──────┬───────────┘
             │
             v
      ┌──────────────────┐
      │   write_draft    │  (AI 生成文章)
      └──────┬───────────┘
             │
             v
      ┌──────────────────┐
      │  human_review   │  (人工审核)
      │  └─ interrupt() │  (等待审核)
      └──┬───────────┬──┘
         │           │
    approve      reject
         │           │
         v           v
   extract_visuals  write_draft
         │
         v
   generate_images
         │
         v
         END

    节点详解：
      1. topic_selection（子图）：
         - plan_topics：调用 LLM 生成 5 个候选选题
         - human_select_topic：interrupt 等待用户选择
      2. write_draft：调用 LLM 根据选题生成文章草稿
      3. human_review：interrupt 等待用户审核（通过/驳回）
      4. extract_visuals：调用 LLM 从文章中提取配图要点
      5. generate_images：调用图片生成 API 生成配图

    返回值：
      StateGraph 实例（未编译），需要调用 .compile() 才可执行
    """
    # ---------- 创建状态图 ----------
    workflow = StateGraph(AgentState)

    # ---------- 获取编译好的选题子图 ----------
    topic_selection_subgraph = get_compiled_topic_selection_subgraph()

    # ---------- 添加节点（5 个） ----------
    # 节点 1：选题子图（封装了选题相关的所有逻辑）
    workflow.add_node("topic_selection", topic_selection_subgraph)

    # 节点 2：文章写作节点
    workflow.add_node("write_draft", write_draft_node)

    # 节点 3：人工审稿节点
    workflow.add_node("human_review", human_review_node)

    # 节点 4：提取配图要点节点
    workflow.add_node("extract_visuals", extract_visuals_node)

    # 节点 5：生成配图节点
    workflow.add_node("generate_images", generate_images_node)

    # ---------- 添加边（连接） ----------
    # 边 1：Start -> topic_selection（开始工作流）
    workflow.add_edge(START, "topic_selection")

    # 边 2：topic_selection -> write_draft（选题完成后进入写作）
    workflow.add_edge("topic_selection", "write_draft")

    # 边 3：write_draft -> human_review（文章生成后等待审核）
    workflow.add_edge("write_draft", "human_review")

    # 边 4：human_review 是条件路由（在 human_review_node 中用 Command 指定）
    #           approve -> extract_visuals -> generate_images -> END
    #           reject -> write_draft（重写）

    # 边 5：extract_visuals -> generate_images（要点提取后生成配图）
    workflow.add_edge("extract_visuals", "generate_images")

    # 边 6：generate_images -> END（配图生成后工作流完成）
    workflow.add_edge("generate_images", END)

    return workflow


# =============================================================================
# 第 3 步：编译工作流图
# =============================================================================

async def get_compiled_graph():
    """
    获取编译后的工作流图（带持久化 Checkpointer）

    ==========================================================================
    为什么需要编译？
      StateGraph 只是定义了节点和边的结构
      compile() 会：
      1. 验证图的完整性（所有边的端点都存在）
      2. 创建可执行的图对象
      3. 绑定 Checkpointer（用于持久化状态）

    Checkpointer 说明：
      每个工作流执行后，状态会被持久化到 PostgreSQL
      下次调用时传入相同的 thread_id，可以从上次中断的地方继续
      这就是"断点恢复"功能

    LangGraph 1.0+ 中断机制：
      1.0 以前用 interrupt_before/interrupt_after 参数指定中断节点
      1.0+ 直接在节点函数中调用 interrupt()，更灵活
      不需要显式指定中断节点，interrupt() 在哪就在哪中断

    返回值：
      CompiledStateGraph 实例，可以调用 .invoke() / .ainvoke()
    """
    # ---------- 获取 Checkpointer ----------
    checkpointer = await get_checkpointer()

    # ---------- 构建工作流图 ----------
    workflow = build_workflow_graph()

    # ---------- 编译图（绑定持久化） ----------
    compiled_graph = workflow.compile(
        checkpointer=checkpointer,
    )

    return compiled_graph


# =============================================================================
# 第 4 步：获取图实例（单例）
# =============================================================================

_compiled_graph = None


async def get_graph():
    """
    获取或创建编译后的图实例（单例模式）

    ==========================================================================
    为什么用单例？
      编译图是一个相对重的操作（验证、绑定）
      工作流在服务生命周期内不会变化
      只需要编译一次，之后直接复用

    _compiled_graph：
      全局变量存储编译后的图实例
      首次调用时编译并缓存
      后续调用直接返回缓存

    为什么需要 async？
      get_checkpointer() 内部可能需要初始化连接池
      这是异步操作，所以 get_graph 也是 async
    """
    global _compiled_graph

    if _compiled_graph is None:
        _compiled_graph = await get_compiled_graph()

    return _compiled_graph


# =============================================================================
# 第 5 步：重置图实例
# =============================================================================

async def reset_graph():
    """
    重置图实例（用于重新初始化）

    ==========================================================================
    为什么需要这个？
      某些测试场景需要重新编译图
      或者 Checkpointer 连接断开后需要重建

    注意：
      重置后 _compiled_graph 为 None
      下次 get_graph() 调用时会重新编译
    """
    global _compiled_graph
    _compiled_graph = None
