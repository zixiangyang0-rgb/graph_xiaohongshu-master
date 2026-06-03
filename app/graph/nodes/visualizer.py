"""
视觉内容生成节点模块
=============================================================================
职责说明：
  定义工作流中的"视觉阶段"节点，包括：
  1. extract_visuals_node：从文章内容中提取配图要点
  2. generate_images_node：调用图片生成 API 生成配图

典型场景：
  用户审核通过文章 -> extract_visuals_node（提取 3 个配图描述）
  -> generate_images_node（调用 Gemini API 生成 3 张图片）
  -> 工作流完成，返回图片 URL 列表
=============================================================================
"""
from typing import Dict, Any
from app.graph.state import AgentState
from app.services import get_llm_service, get_image_service
from app.graph.metrics import MetricsContext, LLMUsage, merge_metrics


async def extract_visuals_node(state: AgentState) -> Dict[str, Any]:
    """
    提取视觉要点节点

    ==========================================================================
    工作流程：
      1. 读取 state 中的 article_content（文章内容）
      2. 调用 LLM 从文章中提取 3 个配图描述要点
      3. 返回 visual_points 列表

    为什么需要提取？
      直接用文章生成配图效果不好
      先让 AI 理解文章主题，提取适合配图的视觉描述
      这些描述作为图片生成的 prompt

    返回值说明：
      - visual_points：配图描述列表（3 条）
      - status：状态标记

    典型场景：
      article_content = "Python 入门 5 步法..."
      -> LLM 提取 -> ["温暖的学习场景，程序员深夜编程",
                      "简洁的代码编辑器界面",
                      "初学者困惑到顿悟的表情对比"]
    ==========================================================================
    """
    article_content = state.get("article_content", "")
    existing_metrics = state.get("node_metrics", [])

    # 文章为空时返回空列表（不阻塞工作流）
    if not article_content:
        return {
            "visual_points": [],
            "status": "error",
            "error": "文章内容为空，无法提取视觉要点",
        }

    # ---------- 调用 LLM 提取视觉要点 ----------
    with MetricsContext("extract_visuals") as tracker:
        try:
            llm_service = get_llm_service()
            visual_points, usage_info = await llm_service.extract_visual_points(article_content)

            # 记录 LLM 使用
            tracker.set_llm_usage(LLMUsage(
                input_tokens=usage_info.input_tokens,
                output_tokens=usage_info.output_tokens,
                total_tokens=usage_info.total_tokens,
                model=usage_info.model
            ))

            result = {
                "visual_points": visual_points,
                "status": "visuals_extracted",
                "error": "",
            }

        except Exception as e:
            result = {
                "visual_points": [],
                "status": "error",
                "error": f"提取视觉要点失败: {str(e)}",
            }

    # ---------- 记录指标 ----------
    result["node_metrics"] = merge_metrics(existing_metrics, tracker.to_dict())
    return result


async def generate_images_node(state: AgentState) -> Dict[str, Any]:
    """
    生成配图节点

    ==========================================================================
    工作流程：
      1. 读取 state 中的 visual_points（配图描述列表）
      2. 对每个描述调用图片生成 API（并行执行）
      3. 返回 image_urls 列表

    为什么并行？
      每个配图生成是独立的 API 调用
      asyncio.gather() 可以同时发起多个请求，大幅减少总耗时
      例如：3 张图片串行需要 3x10s=30s，并行只需要 ~10s

    错误容忍设计：
      即使部分图片生成失败，也不阻塞工作流
      成功的图片仍然返回给用户

    返回值说明：
      - image_urls：图片 URL 列表（可能少于 visual_points 的数量）
      - status：状态标记（即使部分失败也是 completed）

    典型场景：
      visual_points = ["温暖学习场景", "代码编辑器界面", "初学者表情对比"]
      -> 调用 Gemini API 生成 3 张图片
      -> 返回 ["/static/images/generated/xhs_xxx1.png",
               "/static/images/generated/xhs_xxx2.png",
               "/static/images/generated/xhs_xxx3.png"]
    ==========================================================================
    """
    visual_points = state.get("visual_points", [])
    existing_metrics = state.get("node_metrics", [])

    # 没有视觉要点时跳过（不阻塞工作流）
    if not visual_points:
        return {
            "image_urls": [],
            "status": "completed",
            "error": "视觉要点为空，跳过配图生成",
        }

    # ---------- 调用图片生成服务 ----------
    with MetricsContext("generate_images") as tracker:
        try:
            # 获取图片服务
            image_service = get_image_service()

            # 并行生成所有配图
            # asyncio.gather() 同时执行多个协程，返回结果列表
            image_urls = await image_service.generate_images(visual_points)

            # 记录部分失败的情况
            if len(image_urls) < len(visual_points):
                error_msg = f"部分配图生成失败 ({len(image_urls)}/{len(visual_points)} 成功)"
            else:
                error_msg = ""

            result = {
                "image_urls": image_urls,
                "status": "completed",
                "error": error_msg,
            }

        except Exception as e:
            # 即使全部失败，也标记为 completed（不阻塞工作流）
            result = {
                "image_urls": [],
                "status": "completed",
                "error": f"配图生成失败: {str(e)[:100]}",
            }

    # ---------- 记录指标 ----------
    result["node_metrics"] = merge_metrics(existing_metrics, tracker.to_dict())
    return result
