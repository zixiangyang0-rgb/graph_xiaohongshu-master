"""
文章写作节点 - 根据用户选定的选题，调用 AI 生成文章草稿

通俗理解：
  用户选好了标题，这里负责让 AI 把文章写出来。

核心功能：
  1. 根据选题生成完整文章
  2. 支持根据修改意见重写（用户说"太长了"就重写个短的）
  3. 记录这次调用的耗时和 token 消耗

典型场景：
  - 第一次生成：用户选标题 -> AI 写文章
  - 驳回重写：用户说"太长了" -> AI 根据反馈重写
"""
from typing import Dict, Any
from app.graph.state import AgentState
from app.services import get_llm_service
from app.graph.metrics import MetricsContext, LLMUsage, merge_metrics


async def write_draft_node(state: AgentState) -> Dict[str, Any]:
    """
    文章写作节点

    工作流程：
      1. 提取输入：拿到选题标题、修改意见（如果有的话）、修订次数
      2. 验证：确保选题不为空
      3. 处理修订：如果有修改意见，revision_count += 1
      4. 调用 AI：用流式方式生成文章，同时记录 token 消耗
      5. 返回：把文章内容和指标存回状态

    为什么 revision_count 重要？
      告诉 AI 是第几次修订了，它会根据上下文调整输出策略。
      第一次写 vs 第三次重写，AI 的心态是不一样的。

    返回：
      - article_content：生成的文章
      - revision_count：修订次数
      - review_status：重置为 pending，等下次审核
    """
    selected_topic = state.get("selected_topic", "")
    review_feedback = state.get("review_feedback", "")
    revision_count = state.get("revision_count", 0)
    existing_metrics = state.get("node_metrics", [])

    if not selected_topic:
        return {
            "article_content": "",
            "status": "error",
            "error": "未选择选题，无法生成文章",
        }

    # 计时 + 调用 AI
    with MetricsContext("write_draft") as tracker:
        try:
            # 如果有修改意见，增加修订计数
            if review_feedback:
                revision_count += 1

            llm_service = get_llm_service()

            # 流式生成文章（同时获取 token 统计）
            stream_result = await llm_service.stream_write_draft_with_usage(
                topic=selected_topic,
                feedback=review_feedback,
                revision_count=revision_count
            )

            article_content = stream_result.content
            usage_info = stream_result.usage

            # 记录 token 消耗
            tracker.set_llm_usage(LLMUsage(
                input_tokens=usage_info.input_tokens,
                output_tokens=usage_info.output_tokens,
                total_tokens=usage_info.total_tokens,
                model=usage_info.model
            ))

            result = {
                "article_content": article_content,
                "revision_count": revision_count,
                "review_status": "pending",
                "status": "draft_generated",
                "error": "",
            }

        except Exception as e:
            result = {
                "article_content": "",
                "status": "error",
                "error": f"生成文章失败: {str(e)}",
            }

    # 记录指标
    result["node_metrics"] = merge_metrics(existing_metrics, tracker.to_dict())
    return result
