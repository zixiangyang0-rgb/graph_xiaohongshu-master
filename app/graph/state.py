"""
LangGraph 状态定义模块
=============================================================================
职责说明：
  定义工作流中流转的数据结构，即工作流的"状态"（State）。

核心概念：
  - State：工作流在执行过程中的数据快照，包含所有需要流转的信息
  - TypedDict：Python 字典的类型注解，定义状态有哪些字段
  - AgentState：整个应用的完整状态定义
  - NodeMetric：单个节点执行时的性能指标

为什么用 TypedDict 而不是 dataclass？
  LangGraph 推荐使用 TypedDict 定义状态，state.graph.add() 的节点接收 state 参数
  TypedDict 更接近"字典+类型"的概念，和 LangGraph 的状态管理更契合

状态生命周期：
  1. 初始化：所有字段为空/默认值
  2. 选题阶段：topic_direction + generated_topics
  3. 写作阶段：selected_topic + article_content
  4. 审核阶段：review_status + review_feedback
  5. 配图阶段：visual_points + image_urls
  6. 完成：所有数据就绪

典型场景：
  用户输入"Python 开发" -> state = {topic_direction: "Python 开发"}
  AI 生成选题 -> state = {generated_topics: ["Python 5步法", ...]}
  用户选择"Python 5步法" -> state = {selected_topic: "Python 5步法"}
  AI 生成文章 -> state = {article_content: "..."}
  审核通过 -> state = {review_status: "approved"}
  AI 生成配图 -> state = {image_urls: ["...", "..."]}
=============================================================================
"""
from typing import TypedDict, List, Literal, Annotated, Dict, Any
from langgraph.graph.message import add_messages


class NodeMetric(TypedDict, total=False):
    """
    单个节点执行时的性能指标
    ==========================================================================
    用于监控和计费，每个 AI 节点执行后都会记录这些数据。

    字段详解：
      - node_name：节点唯一标识，用于区分不同节点
        典型值："plan_topics"、"write_draft"、"extract_visuals"
      - duration_ms：执行耗时（毫秒）
        典型值：1523.45 表示这次执行用了 1.5 秒
      - input_tokens：发送给 AI 的 token 数量
        用于计算 LLM API 调用费用
      - output_tokens：AI 返回的 token 数量
        输出越长，费用越高
      - total_tokens：总 token 数
        input_tokens + output_tokens = total_tokens
      - start_time / end_time：执行时间范围
        ISO 8601 格式，如 "2024-01-01T10:00:00.000Z"
      - model：使用的 AI 模型名称
        如 "doubao-seed-1-6-flash-250828"

    典型场景：
      {"node_name": "write_draft", "duration_ms": 5234.5, "input_tokens": 450,
       "output_tokens": 1200, "total_tokens": 1650, "model": "doubao-seed-1-8-251228"}
    """
    node_name: str
    duration_ms: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    start_time: str
    end_time: str
    model: str


class AgentState(TypedDict, total=False):
    """
    AI 内容运营助手的工作流状态定义
    ==========================================================================
    定义工作流在执行过程中所有需要流转的数据。

    状态分段说明：

    【选题阶段】
    - topic_direction：用户输入的主题方向
      典型值："Python 开发"、"AI 技术趋势"
      来源：用户通过 POST /workflow/start 传入
    - generated_topics：AI 根据主题生成的候选选题列表
      典型值：["Python 入门 5 步法", "10 个 Python 技巧", ...]
      生成：plan_topics 节点调用 LLM 生成

    【写作阶段】
    - selected_topic：用户从候选中选中的选题
      典型值："Python 入门 5 步法"
      来源：用户通过 POST /workflow/resume 传入
    - article_content：AI 生成的文章内容
      典型值："# Python 入门 5 步法\n\n..."（Markdown 格式）
      生成：write_draft 节点调用 LLM 生成
    - review_feedback：用户审核时的修改意见
      典型值："文章太长了，缩短到 600 字"
      来源：用户在驳回时提供
    - review_status：审核状态
      典型值："pending"（待审核）、"approved"（通过）、"rejected"（驳回）
      流转：pending -> approved（通过）或 pending -> rejected（驳回）
    - revision_count：修订次数
      典型值：0（初稿）、1（第一次驳回重写）、2（第二次）
      每次驳回重写后 +1

    【配图阶段】
    - visual_points：AI 从文章中提取的配图描述要点
      典型值：["温暖的学习场景，程序员深夜编程", ...]
      生成：extract_visuals 节点调用 LLM 提取
    - image_urls：生成的配图 URL 列表
      典型值：["/static/images/generated/xhs_xxx.png", ...]
      生成：generate_images 节点调用图片生成 API

    【工作流元数据】
    - status：当前工作流状态描述
      典型值："initialized"、"topics_generated"、"draft_generated"、"completed"
    - error：错误信息（如果有）
      典型值：""（无错误）
    - node_metrics：各节点执行指标列表
      存储所有节点的性能数据

    为什么所有字段都标记为 total=False？
      TypedDict 默认所有字段必填
      total=False 表示所有字段都是可选的（相当于都标注了 ?）
      初始化时不需要填所有字段，未填字段值为 None
    """
    # ---------- 选题阶段 ----------
    # 用户输入的主题方向，如 "Python 开发"
    topic_direction: str
    # AI 生成的候选选题标题列表（5个）
    generated_topics: List[str]
    # 用户最终选定的选题标题
    selected_topic: str

    # ---------- 写作阶段 ----------
    # AI 生成的文章内容（Markdown 格式）
    article_content: str
    # 用户驳回时提供的修改意见
    review_feedback: str
    # 审核状态：pending（待审核）/ approved（通过）/ rejected（驳回）
    review_status: Literal["pending", "approved", "rejected"]
    # 修订次数，每次驳回重写后 +1
    revision_count: int

    # ---------- 视觉阶段 ----------
    # 从文章提取的配图描述要点（3条）
    visual_points: List[str]
    # 生成的配图 URL 列表
    image_urls: List[str]

    # ---------- 工作流元数据 ----------
    # 当前状态描述
    status: str
    # 错误信息（无错误时空字符串）
    error: str

    # ---------- 节点执行指标 ----------
    # 存储每个 AI 节点的执行数据（耗时、token 消耗等）
    node_metrics: List[NodeMetric]


# =============================================================================
# 状态初始值
# =============================================================================

# 所有新工作流都从这里开始
# 作为 POST /workflow/start 时的初始状态模板
INITIAL_STATE: AgentState = {
    # 选题阶段默认值
    "topic_direction": "",         # 用户还没输入主题方向
    "generated_topics": [],       # AI 还没生成选题
    "selected_topic": "",         # 用户还没选择

    # 写作阶段默认值
    "article_content": "",        # AI 还没生成文章
    "review_feedback": "",        # 用户还没反馈
    "review_status": "pending",  # 默认待审核
    "revision_count": 0,          # 还没修订过

    # 视觉阶段默认值
    "visual_points": [],         # AI 还没提取要点
    "image_urls": [],             # AI 还没生成配图

    # 元数据默认值
    "status": "initialized",     # 刚初始化的状态
    "error": "",                  # 无错误

    # 指标默认值
    "node_metrics": [],           # 还没执行任何节点
}
