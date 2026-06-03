"""
LangGraph 节点模块
=============================================================================
职责说明：
  定义工作流中所有 AI 节点的实现。

节点列表：
  - plan_topics_node：选题规划（AI 生成选题）
  - write_draft_node：文章写作（AI 生成文章）
  - extract_visuals_node：视觉提取（AI 提取配图要点）
  - generate_images_node：图片生成（调用 Gemini API）

注意事项：
  human_select_topic_node 和 human_review_node
  已移至 workflow.py 中，使用 LangGraph 1.0+ 的 interrupt() 和 Command 模式
=============================================================================
"""
from app.graph.nodes.planner import plan_topics_node
from app.graph.nodes.writer import write_draft_node
from app.graph.nodes.visualizer import extract_visuals_node, generate_images_node

__all__ = [
    "plan_topics_node",
    "write_draft_node",
    "extract_visuals_node",
    "generate_images_node",
]
