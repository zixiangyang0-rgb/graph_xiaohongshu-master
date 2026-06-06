"""
工作流状态定义 - 这个文件定义了 AI 工作流中数据是怎么传递的

通俗理解：
  工作流就像一条流水线，state（状态）就是这条流水线上的"数据箱子"。
  每个节点（工位）从这个箱子里拿数据，处理完后把结果放回去。
  这里定义的，就是箱子里装的是什么。

数据变化过程（从开始到结束）：
  1. 开始：所有字段都是空的
  2. 选题：填入"主题方向"和"AI 生成的 5 个候选标题"
  3. 写作：填入"用户选的标题"和"AI 生成的文章"
  4. 审核：填入"审核结果"和"修改意见"
  5. 配图：填入"配图描述"和"生成的图片地址"
  6. 完成：所有数据都有了
"""
from typing import TypedDict, List, Literal, Annotated, Dict, Any
from langgraph.graph.message import add_messages


class NodeMetric(TypedDict, total=False):
    """
    记录每个节点跑了多久、花了多少 token

    每次 AI 干完活，都记一笔：花了多久、用多少 token、用什么模型。
    这些数据用来算钱（API 按 token 收费）和排查哪里慢。

    各字段含义：
      - node_name：节点名字，比如 "write_draft"（写文章）、"plan_topics"（生成选题）
      - duration_ms：这次执行花了多少毫秒，比如 1523.45 就是跑了 1.5 秒
      - input_tokens：发给 AI 的"字数"（专业叫 token），越多收费越高
      - output_tokens：AI 返回来的"字数"，越长收费也越高
      - total_tokens：input + output，总共用了多少
      - start_time / end_time：开始和结束时间
      - model：用的哪个 AI 模型
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
    AI 小红书内容运营助手的状态箱子

    整个文章生成流程中，所有需要流转的数据都在这儿。

    【第一步：选题】
    - topic_direction：用户输入的主题方向，比如"Python 开发"
    - generated_topics：AI 根据主题生成的 5 个候选标题
    - selected_topic：用户最后选了哪个标题

    【第二步：写作】
    - article_content：AI 写出来的文章（Markdown 格式）
    - review_feedback：用户看完觉得哪里要改，比如"太长了，缩短到 600 字"
    - review_status：审核状态，三个值：pending（等着审）/ approved（通过了）/ rejected（打回改）
    - revision_count：被打回重写了几次（0 = 第一次写，1 = 第一次打回重写）

    【第三步：配图】
    - visual_points：AI 从文章里挖出来的配图描述，3 条
    - image_urls：生成的配图存在哪里

    【其他信息】
    - status：工作流现在走到哪一步了
    - error：如果出错了存这儿，没出错就是空字符串
    - node_metrics：记账本，存着每个节点的耗时和 token 消耗

    为什么字段都是 total=False？
      因为 Python TypedDict 默认要求每个字段都必须填。
      加上 total=False 后，所有字段都变成可选的了——初始化时不用全部填满，
      用到哪个填哪个就行。
    """
    # ---------- 选题阶段 ----------
    topic_direction: str  # 用户想写什么方向，比如"Python 开发"
    generated_topics: List[str]  # AI 生成的 5 个候选标题
    selected_topic: str  # 用户最后选了哪个标题

    # ---------- 写作阶段 ----------
    article_content: str  # AI 写出来的文章（Markdown 格式）
    review_feedback: str  # 用户打回时的修改意见，比如"太长了"
    review_status: Literal["pending", "approved", "rejected"]  # pending=待审 / approved=通过 / rejected=打回
    revision_count: int  # 被打回重写了几次

    # ---------- 视觉阶段 ----------
    visual_points: List[str]  # 从文章里挖出来的 3 条配图描述
    image_urls: List[str]  # 生成的配图文件的路径

    # ---------- 工作流元数据 ----------
    status: str  # 现在工作流走到哪了
    error: str  # 出错信息，没错就是空字符串
    node_metrics: List[NodeMetric]  # 每个 AI 节点跑完的"记账本"


# =============================================================================
# 初始状态（新建工作流时的默认值）
# =============================================================================

INITIAL_STATE: AgentState = {
    # 选题阶段
    "topic_direction": "",
    "generated_topics": [],
    "selected_topic": "",

    # 写作阶段
    "article_content": "",
    "review_feedback": "",
    "review_status": "pending",
    "revision_count": 0,

    # 配图阶段
    "visual_points": [],
    "image_urls": [],

    # 元数据
    "status": "initialized",
    "error": "",

    # 记账本
    "node_metrics": [],
}
