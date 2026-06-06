"""
工作流定义模块 - 把所有"节点"串成一个完整的 AI 工作流

通俗理解：
  这个文件就是"包工头"，负责把所有小工位（节点）按顺序串起来。

核心概念：
  - StateGraph：LangGraph 的核心类，代表一个有向图
  - Node（节点）：工作流中的一个处理步骤
  - Edge（边）：节点之间的连接，代表执行顺序
  - interrupt()：暂停工作流，等人工输入后再继续
  - Command：恢复中断的工作流

工作流完整路径：
  Start -> topic_selection（AI 生成选题 + 等你选） -> write_draft（写文章）
  -> human_review（等你审核） -> 审核通过？ -> extract_visuals -> generate_images -> 完成
  -> 审核驳回？ -> 回到 write_draft 重写
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
# 人工审稿节点
# =============================================================================

async def human_review_node(state: AgentState) -> Command[Literal["extract_visuals", "write_draft"]]:
    """
    人工审稿节点（等用户点"通过"或"驳回"）

    工作流程：
      1. 读取 state 中的 article_content（AI 生成的文章草稿）
      2. 调用 interrupt() 暂停工作流，等人工审核
      3. 用户通过 API 传入审核结果（approve 或 reject）
      4. 根据用户选择，决定下一步是"生成配图"还是"重写文章"

    interrupt() 是什么？
      就像游戏里的暂停点——工作流跑到这里就停了，
      等你通过 API 告诉我审核结果再继续。

    返回值说明：
      Command 告诉 LangGraph 两件事：
      1. update={}：要更新哪些状态字段
      2. goto="xxx"：下一步要去哪个节点
        - "extract_visuals" = 用户点了通过 → 生成配图
        - "write_draft" = 用户点了驳回 → 重写文章
    """
    article_content = state.get("article_content", "")

    # 暂停：等用户审核
    user_input = interrupt({
        "message": "请审核以下文章内容",
        "article_preview": article_content[:500] + "..." if len(article_content) > 500 else article_content,
        "action_required": "review",
        "options": ["approve", "reject"]
    })

    # 解析用户审核结果
    if isinstance(user_input, dict):
        action = user_input.get("action", "reject")
        feedback = user_input.get("feedback", "")
    else:
        action = "reject"
        feedback = ""

    # 根据审核结果决定下一步
    if action == "approve":
        # 审核通过 → 进入配图生成阶段
        return Command(
            update={
                "review_status": "approved",
                "review_feedback": "",
                "status": "review_approved",
            },
            goto="extract_visuals"
        )
    else:
        # 审核驳回 → 回到文章写作阶段（带反馈重写）
        return Command(
            update={
                "review_status": "rejected",
                "review_feedback": feedback,
                "status": "review_rejected",
            },
            goto="write_draft"
        )


# =============================================================================
# 构建工作流图
# =============================================================================

def build_workflow_graph() -> StateGraph:
    """
    把所有节点串成一条流水线

    工作流图：
      ┌──────────────┐
      │    START     │
      └──────┬───────┘
             │
             v
      ┌──────────────────┐
      │ topic_selection  │  (子图：AI 出题 + 等你选)
      └──────┬───────────┘
             │
             v
      ┌──────────────────┐
      │   write_draft    │  (AI 写文章)
      └──────┬───────────┘
             │
             v
      ┌──────────────────┐
      │  human_review    │  (等用户审核)
      └──┬───────────┬──┘
         │           │
    通过 │        驳回 │
         │           │
         v           v
   extract_visuals  write_draft
         │
         v
   generate_images
         │
         v
         END
    """
    workflow = StateGraph(AgentState)

    # 获取编译好的选题子图
    topic_selection_subgraph = get_compiled_topic_selection_subgraph()

    # 添加节点（5 个）
    workflow.add_node("topic_selection", topic_selection_subgraph)  # 选题子图
    workflow.add_node("write_draft", write_draft_node)  # 写文章
    workflow.add_node("human_review", human_review_node)  # 人工审稿
    workflow.add_node("extract_visuals", extract_visuals_node)  # 提取配图要点
    workflow.add_node("generate_images", generate_images_node)  # 生成配图

    # 添加边（连接）
    workflow.add_edge(START, "topic_selection")  # 开始 -> 选题
    workflow.add_edge("topic_selection", "write_draft")  # 选题完 -> 写文章
    workflow.add_edge("write_draft", "human_review")  # 文章写完 -> 等审核
    # human_review 用 Command(goto=...) 决定下一步（在函数内部）
    workflow.add_edge("extract_visuals", "generate_images")  # 提取完 -> 生成配图
    workflow.add_edge("generate_images", END)  # 生成完 -> 结束

    return workflow


# =============================================================================
# 编译工作流图
# =============================================================================

async def get_compiled_graph():
    """
    编译工作流图，让它可以被执行

    为什么需要编译？
      StateGraph 只是定义了"有哪些节点"和"节点之间怎么连"
      compile() 会验证图的完整性，然后生成一个可以实际运行的图

    Checkpointer 是干嘛的？
      每个工作流执行后，状态会被存到 PostgreSQL
      下次传入相同的 thread_id，可以从上次中断的地方继续
      就像游戏存档一样
    """
    checkpointer = await get_checkpointer()
    workflow = build_workflow_graph()

    compiled_graph = workflow.compile(
        checkpointer=checkpointer,
    )

    return compiled_graph


# =============================================================================
# 获取图实例（单例）
# =============================================================================

_compiled_graph = None


async def get_graph():
    """
    获取编译后的图实例（单例模式）

    为什么用单例？
      编译图比较慢，但工作流在服务运行时不会变
      所以只编译一次，之后直接复用
    """
    global _compiled_graph

    if _compiled_graph is None:
        _compiled_graph = await get_compiled_graph()

    return _compiled_graph


# =============================================================================
# 重置图实例
# =============================================================================

async def reset_graph():
    """
    重置图实例（测试用，或者 Checkpointer 连接断开时重建）
    """
    global _compiled_graph
    _compiled_graph = None
