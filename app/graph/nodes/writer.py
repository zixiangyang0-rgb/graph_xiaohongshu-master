"""
文章写作节点模块
=============================================================================
职责说明：
  定义工作流中的"文章写作"节点，负责根据选题生成文章草稿。

核心功能：
  1. 根据用户选定的选题，调用 LLM 生成完整文章
  2. 支持根据修改意见重写（驳回重写场景）
  3. 记录 LLM 调用性能指标

典型场景：
  1. 用户选择一个选题 -> plan_topics_node 生成选题 -> write_draft_node 生成文章
  2. 用户驳回文章 -> write_draft_node 再次执行 -> 根据反馈重写
     （第二次会传入 review_feedback 和 revision_count）
=============================================================================
"""
from typing import Dict, Any
from app.graph.state import AgentState
from app.services import get_llm_service
from app.graph.metrics import MetricsContext, LLMUsage, merge_metrics


async def write_draft_node(state: AgentState) -> Dict[str, Any]:
    """
    文章写作节点（流式输出 + 非结构化）

    ==========================================================================
    工作流程（每一步都有明确目的）：

    ---------- 第 1 步：提取输入 ----------
    - selected_topic：用户选定的选题（必需）
    - review_feedback：用户的修改意见（驳回重写时才有值）
    - revision_count：修订次数（每次驳回重写 +1）
    - existing_metrics：已有的节点指标

    ---------- 第 2 步：验证选题 ----------
    如果 selected_topic 为空，说明还没选题，返回错误
    （防止在没有选题的情况下调用写作）

    ---------- 第 3 步：处理修订计数 ----------
    如果有 review_feedback（用户有修改意见），revision_count += 1
    这样可以告诉 LLM 是第几次修订

    ---------- 第 4 步：调用 LLM ----------
    使用流式方法 stream_write_draft_with_usage()
    - 流式方法让 AI 的输出可以逐 token 传回前端显示
    - with_usage 版本同时返回 token 统计

    ---------- 第 5 步：返回结果 ----------
    返回更新的状态字段：
    - article_content：生成的文章内容
    - revision_count：修订次数
    - review_status：重置为 pending（等待下次审核）
    - node_metrics：追加新指标

    为什么需要 revision_count？
      LLM 的 prompt 会根据修订次数显示"第 N 次修订"
      帮助 AI 理解上下文，调整输出策略（重写 vs 微调）

    典型场景：
      # 初稿生成
      write_draft_node({selected_topic: "Python 5步法", ...})
      -> 返回 article_content（完整文章）

      # 驳回重写
      write_draft_node({selected_topic: "Python 5步法", review_feedback: "太长了", revision_count: 1, ...})
      -> 返回 article_content（短版本的文章）
    ==========================================================================
    """
    # ---------- 第 1 步：提取输入 ----------
    selected_topic = state.get("selected_topic", "")
    review_feedback = state.get("review_feedback", "")
    revision_count = state.get("revision_count", 0)
    existing_metrics = state.get("node_metrics", [])

    # ---------- 第 2 步：验证选题 ----------
    if not selected_topic:
        return {
            "article_content": "",
            "status": "error",
            "error": "未选择选题，无法生成文章",
        }

    # ---------- 第 3 步：计时 + 调用 LLM ----------
    with MetricsContext("write_draft") as tracker:
        try:
            # 如果有修改意见，增加修订计数
            if review_feedback:
                revision_count += 1

            # 获取 LLM 服务
            llm_service = get_llm_service()

            # 使用流式方法生成文章（同时获取 token 统计）
            stream_result = await llm_service.stream_write_draft_with_usage(
                topic=selected_topic,
                feedback=review_feedback,
                revision_count=revision_count
            )

            article_content = stream_result.content
            usage_info = stream_result.usage

            # 记录 LLM 使用信息
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

    # ---------- 第 4 步：记录指标 ----------
    result["node_metrics"] = merge_metrics(existing_metrics, tracker.to_dict())
    return result
