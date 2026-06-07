"""
选题规划节点 - 根据用户输入的主题方向，让 AI 生成候选选题列表

通俗理解：
  用户说"我想写 Python 相关的"，这里负责调用 AI 生成 5 个候选标题供用户选择。

核心功能：
  1. 调用 LLM 生成 5 个候选选题
  2. 使用结构化输出（JSON）确保结果格式正确
  3. 记录这次调用的耗时和 token 消耗
"""
from typing import Dict, Any
from langgraph.types import Command
from app.graph.state import AgentState
from app.services import get_llm_service
from app.graph.metrics import MetricsContext, LLMUsage, merge_metrics


async def plan_topics_node(state: AgentState) -> Command:
    """
    选题规划节点

    工作流程：
      1. 提取输入：拿到用户输入的主题方向（topic_direction）
      2. 计时 + 调用 AI：让 AI 根据主题生成 5 个候选选题
      3. 提取结果：从 AI 返回中拿出选题列表
      4. 记录指标：把这次调用的耗时和 token 消耗记下来
      5. 返回：把选题列表和指标存回状态

    为什么用结构化输出？
      传统方式：AI 输出纯文本 -> 手动解析 JSON
      结构化输出：AI 直接输出正确格式的 JSON -> 自动映射到 Pydantic 模型，更稳定
    """
    topic_direction = state.get("topic_direction", "")
    existing_metrics = state.get("node_metrics", [])

    # 计时 + 调用 AI
    with MetricsContext("plan_topics") as tracker:
        try:
            llm_service = get_llm_service()

            # 调用 AI 生成选题
            topics_response, usage_info = await llm_service.plan_topics(topic_direction)

            # 记录 token 消耗
            tracker.set_llm_usage(LLMUsage(
                input_tokens=usage_info.input_tokens,
                output_tokens=usage_info.output_tokens,
                total_tokens=usage_info.total_tokens,
                model=usage_info.model
            ))

            # 提取结果：从返回对象中拿出标题列表
            generated_topics = [topic.title for topic in topics_response.topics]

            print(f"[DEBUG plan_topics_node] 生成了 {len(generated_topics)} 个选题")

            # 记录指标
            node_metrics = merge_metrics(existing_metrics, tracker.to_dict())

            # 返回更新状态
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
            # AI 调用失败
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
