"""
把“生成选题 + 等用户选择”这段单独拆成一个子图。

这样主流程会更清楚，选题这段逻辑也更容易单独维护。
"""
from typing import Literal, Dict, Any
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command

from app.graph.state import AgentState
from app.graph.nodes import plan_topics_node


async def human_select_topic_node(state: AgentState) -> Command[Literal["__end__"]]:
    """
    等你选一个选题

    执行逻辑：
      1. 拿到 AI 生成的选题列表
      2. 暂停，等你来选一个
      3. 你选了之后，把你的选择存到状态里，然后子图结束

    interrupt() 是什么？
      和审稿节点一样，是暂停点。
      这里 AI 出完题就停住，等你通过 API 告诉我你选了哪个。
    """
    generated_topics = state.get("generated_topics", [])

    if not generated_topics:
        return Command(
            update={
                "status": "error",
                "error": "未生成任何可选选题，请检查 LLM 配置或稍后重试",
            },
            goto=END
        )

    # 暂停：等用户选择
    user_input = interrupt({
        "message": "请从以下选题中选择一个",
        "options": generated_topics,
        "action_required": "select_topic"
    })

    # 解析用户选择
    selected_topic = user_input.get("selected_topic", "") if isinstance(user_input, dict) else ""

    # 返回更新并结束子图
    return Command(
        update={
            "generated_topics": generated_topics,
            "selected_topic": selected_topic,
            "status": "topic_selected",
        },
        goto=END
    )


def build_topic_selection_subgraph() -> StateGraph:
    """
    把"AI 出题"和"等你选择"两个步骤串成子图

    子图流程：
      START -> plan_topics（AI 生成选题） -> human_select_topic（等你选） -> END
    """
    subgraph = StateGraph(AgentState)
    subgraph.add_node("plan_topics", plan_topics_node)
    subgraph.add_node("human_select_topic", human_select_topic_node)
    subgraph.add_edge(START, "plan_topics")
    subgraph.add_edge("plan_topics", "human_select_topic")
    return subgraph


def get_compiled_topic_selection_subgraph():
    """获取编译好的选题子图"""
    subgraph = build_topic_selection_subgraph()
    return subgraph.compile()
