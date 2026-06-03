"""
Subgraphs 子图模块
=============================================================================
职责说明：
  定义可复用的子图（Subgraph）。

子图定义：
  - topic_selection.py：选题子图（AI 生成选题 + 人工选择）

子图特点：
  - 可以像节点一样在主图中使用
  - 内部包含自己的节点和边
  - 与主图共享状态（AgentState）
=============================================================================
"""
from app.graph.subgraphs.topic_selection import build_topic_selection_subgraph

__all__ = [
    "build_topic_selection_subgraph",
]
