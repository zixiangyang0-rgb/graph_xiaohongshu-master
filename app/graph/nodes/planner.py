"""
根据用户给的主题方向出一批候选选题。
"""
from typing import Dict, Any
from langgraph.types import Command
from app.graph.state import AgentState
from app.services import get_llm_service
from app.graph.metrics import MetricsContext, LLMUsage, merge_metrics


async def plan_topics_node(state: AgentState) -> Command:
    """让 AI 根据主题方向生成一组选题。"""
    topic_direction = state.get("topic_direction", "")
    existing_metrics = state.get("node_metrics", [])

    with MetricsContext("plan_topics") as tracker:
        try:
            llm_service = get_llm_service()
            topics_response, usage_info = await llm_service.plan_topics(topic_direction)

            tracker.set_llm_usage(LLMUsage(
                input_tokens=usage_info.input_tokens,
                output_tokens=usage_info.output_tokens,
                total_tokens=usage_info.total_tokens,
                model=usage_info.model
            ))

            generated_topics = [topic.title for topic in topics_response.topics]
            print(f"[DEBUG plan_topics_node] 生成了 {len(generated_topics)} 个选题")

            node_metrics = merge_metrics(existing_metrics, tracker.to_dict())

            return Command(
                update={
                    "generated_topics": generated_topics,
                    "status": "topics_generated",
                    "error": "",
                    "node_metrics": node_metrics,
                },
                goto="__end__"
            )

        except Exception as e:
            node_metrics = merge_metrics(existing_metrics, tracker.to_dict())
            return Command(
                update={
                    "generated_topics": [],
                    "status": "error",
                    "error": f"生成选题失败: {str(e)}",
                    "node_metrics": node_metrics,
                },
                goto="__end__"
            )
