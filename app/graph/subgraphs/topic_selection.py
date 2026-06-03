"""
选题子图模块
=============================================================================
职责说明：
  将选题相关的逻辑封装为独立的子图，包含：
  1. plan_topics_node：调用 LLM 生成候选选题
  2. human_select_topic_node：interrupt 等待用户选择

核心概念：
  - Subgraph（子图）：在主图中使用另一个图作为节点
  - 状态共享：子图和主图使用相同的 AgentState 类型
  - interrupt()：人工中断点

子图工作流：
  START -> plan_topics -> human_select_topic -> END
                              |
                         interrupt()

典型场景：
  主图 START -> topic_selection(子图) -> write_draft -> ...
  子图内部：
    plan_topics_node：AI 生成 5 个选题
    human_select_topic_node：interrupt 等待用户选择
      -> 用户调用 API 选择选题
      -> interrupt 恢复，选题写入 state
      -> 子图结束，返回主图
=============================================================================
"""
from typing import Literal, Dict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

from app.graph.state import AgentState
from app.graph.nodes import plan_topics_node


async def human_select_topic_node(state: AgentState) -> Command[Literal["__end__"]]:
    """
    人工选题节点（使用 LangGraph 1.0+ interrupt）

    ==========================================================================
    工作流程：
      1. 读取 state 中的 generated_topics（AI 生成的选题列表）
      2. 调用 interrupt() 暂停，等待用户选择
      3. 用户通过 API 传入 selected_topic
      4. 将 selected_topic 写入 state，结束子图，返回主图

    interrupt() 参数说明：
      - message：显示给用户的消息
      - options：可选的选题列表（前端可以渲染成按钮）
      - action_required：当前需要用户执行的动作

    返回值说明：
      - update：恢复后要更新的状态字段
        selected_topic：用户选择的选题
        status：状态标记
      - goto：下一步去哪（END = 结束子图，返回主图）

    典型场景：
      generated_topics = ["Python 5步法", "10个技巧", ...]
      -> interrupt({"options": [...], ...})
      -> 用户选择 "Python 5步法"
      -> Command(update={selected_topic: "Python 5步法", status: "topic_selected"}, goto=END)
      -> 子图结束，主图继续执行 write_draft
    """
    generated_topics = state.get("generated_topics", [])

    # ---------- 中断：等待用户选择 ----------
    user_input = interrupt({
        "message": "请从以下选题中选择一个",
        "options": generated_topics,
        "action_required": "select_topic"
    })

    # ---------- 解析用户选择 ----------
    # user_input 是 API 通过 Command(resume={...}) 传入的字典
    selected_topic = user_input.get("selected_topic", "") if isinstance(user_input, dict) else ""

    # ---------- 返回更新并结束子图 ----------
    return Command(
        update={
            "selected_topic": selected_topic,
            "status": "topic_selected",
        },
        goto=END  # 结束子图，控制权返回主图
    )


def build_topic_selection_subgraph() -> StateGraph:
    """
    构建选题子图

    ==========================================================================
    子图结构：
      ┌──────────────┐
      │    START     │
      └──────┬───────┘
             │
             v
      ┌──────────────────┐
      │  plan_topics     │  (AI 生成选题)
      └──────┬───────────┘
             │
             v
      ┌──────────────────────────┐
      │ human_select_topic       │  (interrupt 等待)
      │  └─ interrupt()          │
      └──────────┬───────────────┘
                 │
                 v
                END

    为什么用子图？
      1. 模块化：选题逻辑独立于主工作流
      2. 可复用：同样的选题子图可以在其他工作流中使用
      3. 清晰：主图更简洁，细节封装在子图中

    返回值：
      StateGraph 实例（未编译）
    """
    # 创建子图，使用与主图相同的 AgentState
    subgraph = StateGraph(AgentState)

    # ---------- 添加节点 ----------
    subgraph.add_node("plan_topics", plan_topics_node)
    subgraph.add_node("human_select_topic", human_select_topic_node)

    # ---------- 添加边 ----------
    subgraph.add_edge(START, "plan_topics")
    subgraph.add_edge("plan_topics", "human_select_topic")
    # human_select_topic 用 Command(goto=END) 结束子图

    return subgraph


def get_compiled_topic_selection_subgraph():
    """
    获取编译后的选题子图

    ==========================================================================
    为什么不需要 Checkpointer？
      子图复用主图的 Checkpointer
      所有状态（包括子图的状态）都存在主图 Checkpointer 中
      thread_id 是全局唯一的

    为什么不需要 interrupt_before？
      1.0+ 风格直接在节点函数中调用 interrupt()
      不需要声明式指定中断节点

    返回值：
      CompiledStateGraph 实例
    """
    subgraph = build_topic_selection_subgraph()
    return subgraph.compile()
