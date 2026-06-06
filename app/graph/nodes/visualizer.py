"""
文章写完后，这里负责先提配图要点，再去生成图片。
"""
from typing import Dict, Any
from app.graph.state import AgentState
from app.services import get_llm_service, get_image_service
from app.graph.metrics import MetricsContext, LLMUsage, merge_metrics


async def extract_visuals_node(state: AgentState) -> Dict[str, Any]:
    """让 AI 从文章里提取适合配图的视觉描述。"""
    article_content = state.get("article_content", "")
    existing_metrics = state.get("node_metrics", [])

    if not article_content:
        return {
            "visual_points": [],
            "status": "error",
            "error": "文章内容为空，无法提取视觉要点",
        }

    with MetricsContext("extract_visuals") as tracker:
        try:
            llm_service = get_llm_service()
            visual_points, usage_info = await llm_service.extract_visual_points(article_content)

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

    result["node_metrics"] = merge_metrics(existing_metrics, tracker.to_dict())
    return result


async def generate_images_node(state: AgentState) -> Dict[str, Any]:
    """
    把视觉描述转成图片，并行调画图 API。
    部分失败不阻塞——成功的图片仍返回。
    """
    visual_points = state.get("visual_points", [])
    existing_metrics = state.get("node_metrics", [])

    if not visual_points:
        return {
            "image_urls": [],
            "status": "completed",
            "error": "视觉要点为空，跳过配图生成",
        }

    with MetricsContext("generate_images") as tracker:
        try:
            image_service = get_image_service()
            image_urls = await image_service.generate_images(visual_points)

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
            result = {
                "image_urls": [],
                "status": "completed",
                "error": f"配图生成失败: {str(e)[:100]}",
            }

    result["node_metrics"] = merge_metrics(existing_metrics, tracker.to_dict())
    return result
