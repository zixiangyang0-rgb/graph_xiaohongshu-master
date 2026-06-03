"""
选题规划节点模块
=============================================================================
职责说明：
  定义工作流中的"选题规划"节点，负责调用 LLM 生成候选选题列表。

核心功能：
  1. 根据用户输入的主题方向，调用 LLM 生成 5 个候选选题
  2. 使用结构化输出（JSON）确保结果格式正确
  3. 记录 LLM 调用的性能指标（耗时、token 消耗）

典型场景：
  用户输入"Python 开发" -> plan_topics_node() -> 返回 ["Python 入门 5 步法", "10 个 Python 技巧", ...]
=============================================================================
"""
from typing import Dict, Any
from app.graph.state import AgentState
from app.services import get_llm_service
from app.graph.metrics import MetricsContext, LLMUsage, merge_metrics


async def plan_topics_node(state: AgentState) -> Dict[str, Any]:
    """
    选题规划节点（结构化输出 + 非流式）

    ==========================================================================
    工作流程（每一步都有明确目的）：

    ---------- 第 1 步：提取输入 ----------
    从 state 中获取用户输入的主题方向（topic_direction）
    从 state 中获取已有的 node_metrics（追加新的指标）

    ---------- 第 2 步：计时和记录 LLM 使用 ----------
    MetricsContext 是一个上下文管理器：
    - __enter__：记录开始时间
    - __exit__：记录结束时间，计算耗时
    set_llm_usage() 记录这次 LLM 调用的 token 消耗

    ---------- 第 3 步：调用 LLM ----------
    llm_service.plan_topics(topic_direction)
    使用结构化输出（Pydantic 模型）确保返回格式正确
    如果结构化输出失败，fallback 到手动解析 JSON

    ---------- 第 4 步：提取结果 ----------
    topics_response.topics：选题列表
    提取每个 topic.title 组成字符串列表

    ---------- 第 5 步：记录指标 ----------
    将这次节点的执行数据追加到 state.node_metrics

    返回值说明：
      - generated_topics：选题标题列表
      - status：状态标记
      - node_metrics：追加新指标后的完整列表

    为什么用结构化输出？
      传统的 text completion 需要手动解析 JSON
      structured output 让 LLM 直接输出正确格式的 JSON
      更稳定，解析失败率更低
    ==========================================================================
    """
    # ---------- 第 1 步：提取输入 ----------
    topic_direction = state.get("topic_direction", "")
    existing_metrics = state.get("node_metrics", [])

    # ---------- 第 2 步：计时 + 调用 LLM ----------
    with MetricsContext("plan_topics") as tracker:
        try:
            # 获取 LLM 服务（单例）
            llm_service = get_llm_service()

            # 调用 LLM 生成选题（结构化输出）
            topics_response, usage_info = await llm_service.plan_topics(topic_direction)

            # 记录 LLM 使用信息
            tracker.set_llm_usage(LLMUsage(
                input_tokens=usage_info.input_tokens,
                output_tokens=usage_info.output_tokens,
                total_tokens=usage_info.total_tokens,
                model=usage_info.model
            ))

            # ---------- 第 3 步：提取结果 ----------
            generated_topics = [topic.title for topic in topics_response.topics]

            result = {
                "generated_topics": generated_topics,
                "status": "topics_generated",
                "error": "",
            }

        except Exception as e:
            # LLM 调用失败
            result = {
                "generated_topics": [],
                "status": "error",
                "error": f"生成选题失败: {str(e)}",
            }

    # ---------- 第 4 步：记录指标 ----------
    # 在 with 块结束后（tracker.stop() 已被调用）再获取指标
    result["node_metrics"] = merge_metrics(existing_metrics, tracker.to_dict())
    return result
