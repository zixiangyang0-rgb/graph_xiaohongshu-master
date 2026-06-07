"""
视觉内容生成节点 - 从文章里提取配图描述 + 调用 AI 生成图片

通俗理解：
  文章写好了，这里负责给文章配图。
  分两步走：1）让 AI 看看文章说了什么，提取适合配图的视觉描述；2）把描述喂给画图 AI 生成图片。

核心功能：
  1. extract_visuals_node：从文章内容中提取 3 个配图描述
  2. generate_images_node：调用画图 API 生成配图
"""
from typing import Dict, Any
from app.graph.state import AgentState
from app.services import get_llm_service, get_image_service
from app.graph.metrics import MetricsContext, LLMUsage, merge_metrics


async def extract_visuals_node(state: AgentState) -> Dict[str, Any]:
    """
    提取视觉要点节点

    工作流程：
      1. 读取文章内容
      2. 让 AI 看看文章说了什么，提取 3 个适合配图的视觉描述
      3. 返回配图描述列表

    为什么需要这一步？
      直接让 AI 根据文章生成配图效果不好。
      先让它"读"一遍文章，理解主题，然后提取适合画图的视觉描述，
      这些描述再作为画图 prompt，效果更好。

    返回：
      - visual_points：配图描述列表（3 条）
      - status：状态标记
    """
    article_content = state.get("article_content", "")
    existing_metrics = state.get("node_metrics", [])

    if not article_content:
        return {
            "visual_points": [],
            "status": "error",
            "error": "文章内容为空，无法提取视觉要点",
        }

    # 调用 AI 提取视觉要点
    with MetricsContext("extract_visuals") as tracker:
        try:
            llm_service = get_llm_service()
            visual_points, usage_info = await llm_service.extract_visual_points(article_content)

            # 记录 token 消耗
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

    # 记录指标
    result["node_metrics"] = merge_metrics(existing_metrics, tracker.to_dict())
    return result


async def generate_images_node(state: AgentState) -> Dict[str, Any]:
    """
    生成配图节点

    工作流程：
      1. 读取配图描述列表（visual_points）
      2. 对每条描述调用画图 API（并行执行）
      3. 返回生成的图片 URL 列表

    为什么并行？
      每张图是独立的 API 调用，可以同时发起。
      串行：3 张图 x 10 秒 = 30 秒
      并行：3 张图同时跑 ≈ 10 秒

    错误容忍设计：
      即使部分图片生成失败，也不阻塞工作流——成功的图片仍然返回给用户。

    返回：
      - image_urls：图片 URL 列表（可能少于 3 张）
      - status：即使部分失败也标记为 completed
    """
    visual_points = state.get("visual_points", [])
    existing_metrics = state.get("node_metrics", [])

    if not visual_points:
        return {
            "image_urls": [],
            "status": "completed",
            "error": "视觉要点为空，跳过配图生成",
        }

    # 调用画图服务
    with MetricsContext("generate_images") as tracker:
        try:
            image_service = get_image_service()

            # 并行生成所有配图
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
            # 即使全部失败，也标记为 completed，不阻塞工作流
            result = {
                "image_urls": [],
                "status": "completed",
                "error": f"配图生成失败: {str(e)[:100]}",
            }

    # 记录指标
    result["node_metrics"] = merge_metrics(existing_metrics, tracker.to_dict())
    return result
