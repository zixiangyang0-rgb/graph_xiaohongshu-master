"""
工作流 API 模块
=============================================================================
职责说明：
  提供工作流管理的核心 HTTP 接口，是整个 AI 内容运营助手的后端核心。

核心接口：
  1. POST /workflow/start：启动新工作流（输入主题，AI 生成选题）
  2. GET /workflow/state/{thread_id}：获取工作流当前状态
  3. POST /workflow/resume/{thread_id}：恢复工作流（选择选题/审核通过/驳回重写）
  4. GET /workflow/history/{thread_id}：获取工作流历史记录
  5. GET /workflow/threads：获取用户所有工作流列表
  6. DELETE /workflow/threads/{thread_id}：删除工作流
  7. POST /workflow/stream/resume/{thread_id}：流式恢复（实时返回 AI 生成内容）

典型场景：
  1. 用户输入"Python 开发" -> POST /start
     -> AI 生成 5 个选题 -> 返回选题列表
  2. 用户选择一个选题 -> POST /stream/resume/{thread_id}?action=select_topic
     -> AI 流式生成文章 -> 实时返回每个 token
  3. 用户看完文章 -> POST /resume/{thread_id}?action=approve
     -> AI 生成配图 -> 工作流完成

LangGraph 1.0+ 设计：
  - 使用 interrupt() 实现人工中断点（选题、审核）
  - 使用 Command(resume=value) 恢复中断的工作流
  - 使用 PostgreSQL Checkpointer 持久化状态（服务重启不丢失）

用户数据隔离：
  - 每个用户的 thread_id 以 user_id 为前缀
  - 验证请求时检查 thread_id 前缀，防止跨用户访问
=============================================================================
"""
import uuid
import json
from typing import Optional, Dict, Any, List, Literal, AsyncGenerator
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langgraph.types import Command
import psycopg

# 导入工作流核心组件
from app.graph.workflow import get_graph
from app.graph.state import INITIAL_STATE
from app.graph.utils import get_checkpointer

# 导入配置
from app.core.config import settings

# 导入日志
from app.core.logger import app_logger

# 导入用户模型
from app.models.user import User

# 导入认证依赖
from app.dependencies.auth import get_current_user

# 创建路由实例
router = APIRouter(prefix="/workflow", tags=["Workflow"])


# =============================================================================
# 第 1 步：定义请求/响应模型
# =============================================================================

class NodeMetricInfo(BaseModel):
    """
    节点执行指标信息
    ==========================================================================
    记录工作流中每个 AI 节点的性能数据，用于监控和计费。

    字段详解：
      - node_name：节点名称，如 "plan_topics"（选题规划）
      - duration_ms：执行耗时（毫秒），如 1523.45ms
      - input_tokens：发送给 AI 的 token 数（输入）
      - output_tokens：AI 返回的 token 数（输出）
      - total_tokens：总 token 数（input + output）
      - start_time / end_time：执行时间范围（ISO 格式）
      - model：使用的 AI 模型名称

    典型场景：
      {"node_name": "write_draft", "duration_ms": 5234.5, "input_tokens": 450, "output_tokens": 1200, "total_tokens": 1650}
    """
    node_name: str = Field(..., description="节点名称，如 plan_topics、write_draft")
    duration_ms: float = Field(default=0, description="执行耗时，单位毫秒（ms）")
    input_tokens: int = Field(default=0, description="输入 token 数量（给 AI 的提示词 token 数）")
    output_tokens: int = Field(default=0, description="输出 token 数量（AI 生成的内容 token 数）")
    total_tokens: int = Field(default=0, description="总 token 数量（input + output）")
    start_time: str = Field(default="", description="开始时间，ISO 8601 格式")
    end_time: str = Field(default="", description="结束时间，ISO 8601 格式")
    model: str = Field(default="", description="使用的 AI 模型名称")


class StartWorkflowRequest(BaseModel):
    """
    启动工作流请求
    ==========================================================================
    用户输入一个主题方向，AI 会生成多个候选选题供选择。

    字段详解：
      - topic_direction：主题方向（最多 200 字符）
        典型值："Python 开发"、"AI 技术趋势"、"职场沟通技巧"

    典型场景：
      前端表单输入 -> POST /workflow/start {"topic_direction": "Python 开发"}
    """
    topic_direction: str = Field(
        ...,
        description="主题方向，例如：AI技术、Python开发、职场技能",
        min_length=1,
        max_length=200
    )


class StartWorkflowResponse(BaseModel):
    """
    启动工作流响应
    ==========================================================================
    返回生成的选题列表和后续操作指引。

    字段详解：
      - thread_id：工作流线程 ID，后续操作都需要这个 ID
      - status：当前状态，如 "topics_generated"
      - generated_topics：AI 生成的选题列表（如 ["Python 入门 5 步法", ...]）
      - message：用户友好的提示信息
      - interrupt_info：中断信息，描述当前等待用户做什么
      - node_metrics：执行指标（AI 节点耗时、token 消耗）
    """
    thread_id: str = Field(..., description="工作流线程ID，后续操作凭证")
    status: str = Field(..., description="当前工作流状态")
    generated_topics: List[str] = Field(default=[], description="AI 生成的候选选题列表")
    message: str = Field(..., description="用户提示信息")
    interrupt_info: Optional[Dict[str, Any]] = Field(default=None, description="中断等待信息，描述当前需要用户做什么")
    node_metrics: List[NodeMetricInfo] = Field(default=[], description="节点执行指标（耗时、token 消耗）")


class WorkflowStateResponse(BaseModel):
    """
    工作流状态响应
    ==========================================================================
    随时查询工作流的当前状态快照。

    字段详解：
      - thread_id：工作流线程 ID
      - status：当前状态（如 "topics_generated"、"draft_generated"）
      - values：完整的状态快照，包含所有字段
      - next_nodes：下一个待执行节点列表（空表示已结束或有中断）
      - is_completed：工作流是否已完成
      - interrupt_info：当前中断信息（如果有）
      - node_metrics：执行指标
    """
    thread_id: str = Field(..., description="工作流线程ID")
    status: str = Field(..., description="当前工作流状态")
    values: Dict[str, Any] = Field(default={}, description="当前状态快照（所有字段）")
    next_nodes: List[str] = Field(default=[], description="下一个待执行节点列表")
    is_completed: bool = Field(default=False, description="工作流是否已完成")
    interrupt_info: Optional[Dict[str, Any]] = Field(default=None, description="当前中断信息")
    node_metrics: List[NodeMetricInfo] = Field(default=[], description="节点执行指标")


class ResumeWorkflowRequest(BaseModel):
    """
    恢复工作流请求
    ==========================================================================
    用户在人工中断点做出选择后，调用此接口继续工作流。

    action 类型详解：
      - select_topic：用户从 AI 生成的选题中选择了一个
        需要提供 data.selected_topic
      - approve：用户审核通过文章草稿
        无需额外数据
      - reject：用户驳回文章草稿，要求重写
        需要提供 data.feedback（修改意见）

    典型场景：
      # 用户选择了第 3 个选题
      {"action": "select_topic", "data": {"selected_topic": "Python 入门 5 步法"}}
      # 用户审核通过
      {"action": "approve"}
      # 用户驳回并给出修改意见
      {"action": "reject", "data": {"feedback": "文章太长了，缩短到 600 字"}}
    """
    action: Literal["select_topic", "approve", "reject"] = Field(
        ...,
        description="操作类型：select_topic(选择选题)、approve(通过审核)、reject(驳回)"
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="操作数据，选择选题时需要 selected_topic，驳回时需要 feedback"
    )


class ResumeWorkflowResponse(BaseModel):
    """
    恢复工作流响应
    ==========================================================================
    返回恢复后的工作流状态和结果。

    字段详解：
      - thread_id：工作流线程 ID
      - status：当前状态
      - message：用户提示信息
      - next_nodes：下一个待执行节点
      - is_completed：是否已完成（完成后有 result）
      - result：完成时的结果（文章内容、配图 URL 列表等）
      - interrupt_info：下一个中断信息（如果还没完成）
      - node_metrics：执行指标
    """
    thread_id: str = Field(..., description="工作流线程ID")
    status: str = Field(..., description="当前状态")
    message: str = Field(..., description="用户提示信息")
    next_nodes: List[str] = Field(default=[], description="下一个待执行节点")
    is_completed: bool = Field(default=False, description="是否已完成")
    result: Optional[Dict[str, Any]] = Field(default=None, description="完成时的结果数据")
    interrupt_info: Optional[Dict[str, Any]] = Field(default=None, description="下一个中断等待信息")
    node_metrics: List[NodeMetricInfo] = Field(default=[], description="节点执行指标")


class ThreadInfo(BaseModel):
    """
    线程基本信息
    ==========================================================================
    列表展示时使用的轻量信息。

    字段详解：
      - thread_id：线程 ID
      - topic_direction：用户输入的主题方向
      - selected_topic：用户选择的选题（如果选了就显示）
      - status：当前状态
      - is_completed：是否已完成
      - created_at：创建时间
    """
    thread_id: str = Field(..., description="线程ID")
    topic_direction: str = Field(default="", description="用户输入的主题方向")
    selected_topic: str = Field(default="", description="用户选择的选题标题")
    status: str = Field(default="", description="当前状态")
    is_completed: bool = Field(default=False, description="是否已完成")
    created_at: Optional[str] = Field(default=None, description="创建时间")


class ThreadListResponse(BaseModel):
    """
    线程列表响应
    ==========================================================================
    返回用户的所有工作流历史记录。
    """
    threads: List[ThreadInfo] = Field(default=[], description="工作流列表")
    total: int = Field(default=0, description="总数")


# =============================================================================
# 第 2 步：辅助函数
# =============================================================================

def extract_interrupt_info(state_snapshot) -> Optional[Dict[str, Any]]:
    """
    从 LangGraph 1.0+ 状态快照中提取中断信息

    ==========================================================================
    LangGraph 1.0+ 的中断机制：
      工作流执行到 interrupt() 时会暂停，中断信息存储在 state_snapshot.tasks 中
      interrupt() 传入的字典（包含 message、action_required 等）会作为中断值

    为什么需要这个函数？
      状态快照中不一定有 interrupt_info 字段，中断信息存在 task.interrupts 中
      这个函数遍历 tasks 找出中断值

    返回值：
      中断信息字典，如 {"message": "请审核文章", "action_required": "review", ...}
      如果没有中断，返回 None
    """
    # 防御性检查：确保 state_snapshot 有 tasks 属性
    if not state_snapshot or not hasattr(state_snapshot, 'tasks'):
        return None

    # 遍历所有任务（通常只有一个）
    for task in state_snapshot.tasks:
        # 检查任务是否有中断信息
        if hasattr(task, 'interrupts') and task.interrupts:
            for interrupt_obj in task.interrupts:
                # interrupt_obj.value 就是 interrupt() 传入的字典
                if hasattr(interrupt_obj, 'value'):
                    return interrupt_obj.value

    return None


# =============================================================================
# 第 3 步：启动工作流
# =============================================================================

@router.post("/start", response_model=StartWorkflowResponse)
async def start_workflow(
    request: StartWorkflowRequest,
    current_user: User = Depends(get_current_user)
) -> StartWorkflowResponse:
    """
    启动新工作流

    ==========================================================================
    请求：POST /workflow/start
    参数：StartWorkflowRequest（topic_direction）
    认证：需要登录

    工作流程（每一步都有明确目的）：

    ---------- 第 1 步：生成 thread_id ----------
    thread_id = f"{user_id}_{uuid.uuid4()}"
    格式：用户 UUID + 随机字符串
    作用：区分不同用户的工作流，防止跨用户访问

    ---------- 第 2 步：配置 LangGraph ----------
    config = {"configurable": {"thread_id": thread_id}}
    thread_id 是 Checkpointer 的键，用来持久化和恢复状态

    ---------- 第 3 步：准备初始输入 ----------
    initial_input = {**INITIAL_STATE, "topic_direction": request.topic_direction, ...}
    INITIAL_STATE 定义了所有字段的默认值
    这里覆盖 topic_direction 和 status

    ---------- 第 4 步：执行工作流 ----------
    result = await graph.ainvoke(initial_input, config)
    工作流执行路径：Start -> topic_selection 子图
    topic_selection 子图：plan_topics（AI 生成选题）-> interrupt（等待选题）
    invoke 会在 interrupt 处暂停，返回当前状态

    ---------- 第 5 步：提取结果 ----------
    generated_topics：从 result 中取出选题列表
    interrupt_info：从 state_snapshot.tasks 中提取中断信息
    node_metrics：从 result 中取出执行指标

    ---------- 第 6 步：返回响应 ----------
    前端收到选题列表后，显示给用户选择

    典型场景：
      POST {"topic_direction": "Python 开发"}
      -> AI 生成 5 个选题
      -> 返回 {"generated_topics": [...], "interrupt_info": {...}}
      -> 前端显示选题列表，用户点击选择
    ==========================================================================
    """
    try:
        # ---------- 第 1 步：生成带用户前缀的 thread_id ----------
        # 格式：user_id_uuid
        # 前缀作用：确保不同用户的 thread_id 不会冲突
        # 也方便后续按用户 ID 过滤查询
        thread_id = f"{current_user.id}_{uuid.uuid4()}"

        # 记录日志
        app_logger.workflow_started(
            thread_id=thread_id,
            topic_direction=request.topic_direction
        )

        # ---------- 第 2 步：获取编译后的工作流图 ----------
        # get_graph() 返回编译好的 LangGraph（单例）
        graph = await get_graph()

        # ---------- 第 3 步：配置 Checkpointer ----------
        # configurable.thread_id 是 Checkpointer 的唯一键
        # 相同 thread_id 会复用之前的状态（支持断点恢复）
        config = {"configurable": {"thread_id": thread_id}}

        # ---------- 第 4 步：准备初始状态 ----------
        initial_input = {
            **INITIAL_STATE,
            "topic_direction": request.topic_direction,
            "status": "started",
        }

        # ---------- 第 5 步：执行工作流（直到第一个中断点） ----------
        # ainvoke() 是异步版本
        # LangGraph 1.0+ 在遇到 interrupt() 时自动暂停
        await graph.ainvoke(initial_input, config)

        # ---------- 第 6 步：获取状态快照（包含中断信息） ----------
        state_snapshot = await graph.aget_state(config)
        if state_snapshot is None or state_snapshot.values is None:
            raise RuntimeError("工作流已启动，但未能读取到状态快照")

        interrupt_info = extract_interrupt_info(state_snapshot)
        state_values = dict(state_snapshot.values)

        # ---------- 第 7 步：从持久化状态中提取结果 ----------
        # 对于包含子图 + interrupt 的流程，真实状态以快照为准
        generated_topics = state_values.get("generated_topics", [])
        current_status = state_values.get("status", "unknown")
        node_metrics = state_values.get("node_metrics", [])
        error_message = state_values.get("error", "")

        if not generated_topics:
            detail = error_message or "工作流未生成任何候选选题，请检查 LLM 配置后重试"
            raise RuntimeError(detail)

        # 记录阶段变化日志
        app_logger.workflow_stage_changed(
            thread_id=thread_id,
            stage="topics_generated",
            topics_count=len(generated_topics)
        )

        # ---------- 第 8 步：返回响应 ----------
        return StartWorkflowResponse(
            thread_id=thread_id,
            status=current_status,
            generated_topics=generated_topics,
            message="工作流已启动，请选择一个选题继续",
            interrupt_info=interrupt_info,
            node_metrics=node_metrics
        )

    except Exception as e:
        app_logger.workflow_error(
            thread_id=thread_id if 'thread_id' in dir() else "unknown",
            error=str(e),
            stage="start"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"启动工作流失败: {str(e)}"
        )


# =============================================================================
# 第 4 步：获取工作流状态
# =============================================================================

@router.get("/state/{thread_id}", response_model=WorkflowStateResponse)
async def get_workflow_state(
    thread_id: str,
    current_user: User = Depends(get_current_user)
) -> WorkflowStateResponse:
    """
    获取工作流当前状态

    ==========================================================================
    请求：GET /workflow/state/{thread_id}
    用途：随时查询工作流进展，获取最新数据

    工作流程：
      1. 验证 thread_id 属于当前用户（防止跨用户访问）
      2. 调用 aget_state(config) 获取状态快照
      3. 提取中断信息
      4. 判断是否已完成（无 next_nodes + 无中断）
      5. 返回完整状态

    典型场景：
      - 页面刷新后恢复状态
      - 调试时查看工作流内部数据
      - 确认工作流是否还在进行中
    """
    try:
        # ---------- 第 1 步：验证所有权 ----------
        # thread_id 格式：user_id_uuid
        # 只有前缀匹配的用户才能访问
        if not thread_id.startswith(str(current_user.id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此工作流"
            )

        # ---------- 第 2 步：获取工作流图 ----------
        graph = await get_graph()

        # ---------- 第 3 步：配置 ----------
        config = {"configurable": {"thread_id": thread_id}}

        # ---------- 第 4 步：获取状态快照 ----------
        state_snapshot = await graph.aget_state(config)

        # ---------- 第 5 步：检查状态是否存在 ----------
        if state_snapshot is None or state_snapshot.values is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到工作流: {thread_id}"
            )

        # ---------- 第 6 步：提取信息 ----------
        next_nodes = list(state_snapshot.next) if state_snapshot.next else []
        interrupt_info = extract_interrupt_info(state_snapshot)

        # ---------- 第 7 步：判断是否完成 ----------
        # 完成条件：无待执行节点 + 无中断信息
        is_completed = len(next_nodes) == 0 and not interrupt_info

        # ---------- 第 8 步：提取节点指标 ----------
        node_metrics = state_snapshot.values.get("node_metrics", [])

        # ---------- 第 9 步：返回响应 ----------
        return WorkflowStateResponse(
            thread_id=thread_id,
            status=state_snapshot.values.get("status", "unknown"),
            values=dict(state_snapshot.values),
            next_nodes=next_nodes,
            is_completed=is_completed,
            interrupt_info=interrupt_info,
            node_metrics=node_metrics
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取工作流状态失败: {str(e)}"
        )


# =============================================================================
# 第 5 步：恢复工作流（普通模式）
# =============================================================================

@router.post("/resume/{thread_id}", response_model=ResumeWorkflowResponse)
async def resume_workflow(
    thread_id: str,
    request: ResumeWorkflowRequest,
    current_user: User = Depends(get_current_user)
) -> ResumeWorkflowResponse:
    """
    恢复工作流（普通模式，非流式）

    ==========================================================================
    请求：POST /workflow/resume/{thread_id}
    用途：在人工中断点继续执行工作流

    action 类型说明：
      - select_topic：继续执行 write_draft（AI 生成文章）
      - approve：继续执行 extract_visuals + generate_images（审核通过）
      - reject：继续执行 write_draft（驳回重写）

    LangGraph 1.0+ Command 模式：
      使用 Command(resume=value) 恢复中断的工作流
      value 中包含用户的选择（如选中的选题、是否通过）

    典型场景：
      # 选择选题
      POST {action: "select_topic", data: {selected_topic: "Python 5步法"}}
      -> 触发 write_draft 节点 -> AI 生成文章 -> 遇到 interrupt（等待审核）暂停
      -> 返回 "文章草稿已生成，请审核"

      # 审核通过
      POST {action: "approve"}
      -> 触发 extract_visuals -> generate_images -> END
      -> 返回 result（文章内容、配图 URL）

      # 审核驳回
      POST {action: "reject", data: {feedback: "太长了"}}
      -> 触发 write_draft（带修改意见）-> AI 重写 -> 遇到 interrupt
      -> 返回 "文章已重写，请重新审核"
    """
    try:
        # ---------- 第 1 步：验证所有权 ----------
        if not thread_id.startswith(str(current_user.id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此工作流"
            )

        # ---------- 第 2 步：获取工作流图 ----------
        graph = await get_graph()
        config = {"configurable": {"thread_id": thread_id}}

        # ---------- 第 3 步：验证状态存在 ----------
        current_state = await graph.aget_state(config)
        if current_state is None or current_state.values is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到工作流: {thread_id}"
            )

        # ---------- 第 4 步：根据 action 构建恢复数据 ----------
        resume_value: Dict[str, Any] = {}

        if request.action == "select_topic":
            # 选择选题：把用户选中的选题传给工作流
            if not request.data or "selected_topic" not in request.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="选择选题需要提供 selected_topic"
                )
            resume_value = {
                "selected_topic": request.data["selected_topic"],
            }
            app_logger.topic_selected(
                thread_id=thread_id,
                selected_topic=request.data["selected_topic"]
            )

        elif request.action == "approve":
            # 审核通过：告诉工作流用户同意
            resume_value = {
                "action": "approve",
            }
            app_logger.draft_approved(thread_id=thread_id)

        elif request.action == "reject":
            # 审核驳回：把修改意见传给工作流
            feedback = request.data.get("feedback", "") if request.data else ""
            resume_value = {
                "action": "reject",
                "feedback": feedback,
            }
            revision_count = current_state.values.get("revision_count", 0)
            app_logger.draft_rejected(
                thread_id=thread_id,
                feedback=feedback,
                revision_count=revision_count
            )

        # ---------- 第 5 步：恢复工作流执行 ----------
        # Command(resume=resume_value) 是 LangGraph 1.0+ 的恢复机制
        # interrupt() 处读取 resume_value 中的数据，继续执行
        resume_command = Command(resume=resume_value)
        result = await graph.ainvoke(resume_command, config)

        # ---------- 第 6 步：获取更新后的状态 ----------
        updated_state = await graph.aget_state(config)
        next_nodes = list(updated_state.next) if updated_state.next else []
        interrupt_info = extract_interrupt_info(updated_state)
        is_completed = len(next_nodes) == 0 and not interrupt_info
        node_metrics = updated_state.values.get("node_metrics", [])

        # ---------- 第 7 步：构建响应消息 ----------
        message = "操作成功"
        final_result = None

        if is_completed:
            # 工作流完成：包含文章内容和配图
            message = "工作流已完成"
            final_result = {
                "article_content": updated_state.values.get("article_content", ""),
                "visual_points": updated_state.values.get("visual_points", []),
                "image_urls": updated_state.values.get("image_urls", []),
            }
            app_logger.workflow_completed(thread_id=thread_id)
        elif interrupt_info:
            # 还有中断：可能是等待审核或选题
            action_required = interrupt_info.get("action_required", "")
            if action_required == "review":
                message = "文章草稿已生成，请审核"
                article_content = updated_state.values.get("article_content", "")
                app_logger.draft_generated(
                    thread_id=thread_id,
                    word_count=len(article_content)
                )
            elif action_required == "select_topic":
                message = "请选择选题"
            else:
                message = "等待用户操作"

        # ---------- 第 8 步：返回响应 ----------
        return ResumeWorkflowResponse(
            thread_id=thread_id,
            status=updated_state.values.get("status", "unknown"),
            message=message,
            next_nodes=next_nodes,
            is_completed=is_completed,
            result=final_result,
            interrupt_info=interrupt_info,
            node_metrics=node_metrics
        )

    except HTTPException:
        raise
    except Exception as e:
        app_logger.workflow_error(
            thread_id=thread_id,
            error=str(e),
            stage="resume"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"恢复工作流失败: {str(e)}"
        )


# =============================================================================
# 第 6 步：获取工作流历史
# =============================================================================

@router.get("/history/{thread_id}")
async def get_workflow_history(
    thread_id: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取工作流历史状态记录

    ==========================================================================
    请求：GET /workflow/history/{thread_id}
    用途：查看工作流每个节点执行的历史快照

    工作流程：
      1. 验证所有权
      2. 调用 aget_state_history(config) 获取历史列表
      3. 返回最近 20 条记录

    典型场景：
      - 调试：查看每个节点的输入输出
      - 审计：记录工作流的每个决策点
      - 恢复：重新播放历史状态
    """
    try:
        # ---------- 第 1 步：验证所有权 ----------
        if not thread_id.startswith(str(current_user.id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此工作流"
            )

        # ---------- 第 2 步：获取工作流图 ----------
        graph = await get_graph()
        config = {"configurable": {"thread_id": thread_id}}

        # ---------- 第 3 步：获取历史 ----------
        history = []
        async for state in graph.aget_state_history(config):
            history.append({
                "config": state.config,
                "values": dict(state.values) if state.values else {},
                "next": list(state.next) if state.next else [],
                "created_at": state.created_at if hasattr(state, "created_at") else None,
            })

        # ---------- 第 4 步：返回响应 ----------
        return {
            "thread_id": thread_id,
            "history": history[:20],  # 限制返回最近 20 条
            "total": len(history)
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取工作流历史失败: {str(e)}"
        )


# =============================================================================
# 第 7 步：获取所有工作流列表
# =============================================================================

@router.get("/threads", response_model=ThreadListResponse)
async def get_all_threads(
    current_user: User = Depends(get_current_user)
) -> ThreadListResponse:
    """
    获取用户所有工作流线程列表

    ==========================================================================
    请求：GET /workflow/threads
    用途：前端显示历史记录侧边栏

    工作流程：
      1. 用 psycopg 直连 PostgreSQL 查询 checkpoints 表
      2. 按 user_id 前缀过滤属于当前用户的工作流
      3. 对每个 thread_id 调用 aget_state 获取基本信息
      4. 返回轻量化的 ThreadInfo 列表

    为什么不用 SQLAlchemy？
      checkpoints 表是 LangGraph Checkpointer 管理的
      直接用 psycopg 查询更方便（轻量级，不需要 ORM 模型）

    典型场景：
      用户登录后，前端调用此接口获取所有历史工作流
      显示在侧边栏列表中，用户可以点击切换
    """
    try:
        threads = []

        # ---------- 第 1 步：查询用户的所有 thread_id ----------
        # 直接连接 PostgreSQL（不走 SQLAlchemy）
        async with await psycopg.AsyncConnection.connect(
            settings.postgres_uri,
            autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # 查询 checkpoints 表获取该用户的所有工作流
                # thread_id 格式：user_id_uuid，所以用 LIKE 匹配前缀
                user_id_prefix = f"{current_user.id}_%"
                await cur.execute("""
                    SELECT DISTINCT thread_id
                    FROM checkpoints
                    WHERE thread_id LIKE %s
                    ORDER BY thread_id
                """, (user_id_prefix,))
                rows = await cur.fetchall()

        # ---------- 第 2 步：对每个 thread_id 获取详细信息 ----------
        graph = await get_graph()

        for row in rows:
            thread_id = row[0]
            config = {"configurable": {"thread_id": thread_id}}
            try:
                state_snapshot = await graph.aget_state(config)
                if state_snapshot and state_snapshot.values:
                    values = state_snapshot.values
                    next_nodes = list(state_snapshot.next) if state_snapshot.next else []
                    interrupt_info = extract_interrupt_info(state_snapshot)
                    is_completed = len(next_nodes) == 0 and not interrupt_info
                    created_at = None
                    if hasattr(state_snapshot, 'created_at') and state_snapshot.created_at:
                        created_at = state_snapshot.created_at

                    threads.append(ThreadInfo(
                        thread_id=thread_id,
                        topic_direction=values.get("topic_direction", ""),
                        selected_topic=values.get("selected_topic", ""),
                        status=values.get("status", "unknown"),
                        is_completed=is_completed,
                        created_at=created_at
                    ))
            except Exception:
                # 单个线程查询失败不影响其他线程
                continue

        # ---------- 第 3 步：返回列表 ----------
        return ThreadListResponse(
            threads=threads,
            total=len(threads)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取线程列表失败: {str(e)}"
        )


# =============================================================================
# 第 8 步：删除工作流
# =============================================================================

@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    删除指定的工作流

    ==========================================================================
    请求：DELETE /workflow/threads/{thread_id}
    用途：清理不需要的工作流历史

    工作流程：
      1. 验证所有权
      2. 直接操作 PostgreSQL 删除 checkpoints 相关记录

    为什么直接操作 PostgreSQL？
      LangGraph 的 Checkpointer 表结构特殊
      需要删除 checkpoint_writes、checkpoint_blobs、checkpoints 三张表

    典型场景：
      用户在历史记录列表点击删除按钮
      -> DELETE /workflow/threads/xxx
      -> 从侧边栏移除
    """
    try:
        # ---------- 第 1 步：验证所有权 ----------
        if not thread_id.startswith(str(current_user.id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权删除此工作流"
            )

        # ---------- 第 2 步：删除 Checkpointer 相关表 ----------
        async with await psycopg.AsyncConnection.connect(
            settings.postgres_uri,
            autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # 按顺序删除（可能有外键约束）
                await cur.execute(
                    "DELETE FROM checkpoint_writes WHERE thread_id = %s",
                    (thread_id,)
                )
                await cur.execute(
                    "DELETE FROM checkpoint_blobs WHERE thread_id = %s",
                    (thread_id,)
                )
                await cur.execute(
                    "DELETE FROM checkpoints WHERE thread_id = %s",
                    (thread_id,)
                )

                return {"success": True, "message": f"线程 {thread_id} 已删除"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除线程失败: {str(e)}"
        )


# =============================================================================
# 第 9 步：SSE 流式恢复接口
# =============================================================================

class StreamResumeWorkflowRequest(BaseModel):
    """
    流式恢复工作流请求

    ==========================================================================
    仅用于需要实时显示 AI 生成内容的场景：
      - select_topic：选择选题后流式生成文章
      - reject：驳回后流式重新生成文章

    为什么不用于所有场景？
      - 选题阶段：结构化输出（JSON），不需要流式
      - 审核通过：不需要 LLM 调用，不需要流式
      - 只有关键的"文章生成"阶段才需要逐字显示

    事件类型说明：
      - llm_token：AI 生成的每个 token（文章逐字输出）
      - 其他事件：llm_start、llm_end、done、error
    """
    action: Literal["select_topic", "reject"] = Field(
        ...,
        description="操作类型：select_topic(选择选题后生成文章)、reject(驳回后重新生成文章)"
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="操作数据，选择选题时需要 selected_topic，驳回时可提供 feedback"
    )


# =============================================================================
# 第 10 步：SSE 事件格式化
# =============================================================================

def format_sse_event(event_type: str, data: Any) -> str:
    """
    将事件格式化为 SSE（Server-Sent Events）格式

    ==========================================================================
    SSE 格式：
      data: {"type": "llm_token", "data": {"content": "今"}}
      data: {"type": "llm_token", "data": {"content": "天"}}
      data: {"type": "done", "data": {...}}
      \n\n

    为什么用 SSE 而不是 WebSocket？
      - SSE 是单向（服务端 -> 客户端），更简单
      - HTTP/2 复用，不需要建多个连接
      - 自动重连，断线自动恢复

    典型场景：
      前端用 EventSource 或 fetch + ReadableStream 接收
    """
    payload = {
        "type": event_type,
        "data": data
    }
    # SSE 格式：每条消息以 "data: " 开头，以两个换行结束
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


# =============================================================================
# 第 11 步：流式图更新生成器
# =============================================================================

async def stream_graph_updates(
    graph,
    input_data: Any,
    config: Dict[str, Any]
) -> AsyncGenerator[str, None]:
    """
    使用 LangGraph astream_events 流式输出文章生成过程

    ==========================================================================
    工作原理：
      1. 使用 graph.astream_events() 遍历事件流
      2. 捕获 on_chat_model_stream 事件，获取 AI 生成的每个 token
      3. 将 token 格式化为 SSE 事件，yield 给客户端

    事件类型：
      - on_chat_model_start：LLM 开始调用
      - on_chat_model_stream：LLM 输出 token（逐个）
      - on_chat_model_end：LLM 调用结束
      - 其他：节点开始/结束等

    为什么用 astream_events 而不是 astream？
      astream_events 提供更细粒度的事件
      可以区分"节点开始"和"LLM token 输出"
      astream 只返回最终节点结果，无法逐 token 显示
    """
    try:
        # ---------- 发送开始事件 ----------
        yield format_sse_event("start", {})

        # ---------- 初始化 token 统计 ----------
        token_stats = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }

        # ---------- 遍历 LangGraph 事件流 ----------
        # astream_events 是异步生成器，每次产出事件
        async for event in graph.astream_events(input_data, config, version="v2"):
            event_kind = event.get("event", "")
            event_name = event.get("name", "")
            event_data = event.get("data", {})

            # ---------- LLM 开始 ----------
            if event_kind == "on_chat_model_start":
                yield format_sse_event("llm_start", {
                    "model": event_name
                })

            # ---------- LLM 输出 token（核心） ----------
            elif event_kind == "on_chat_model_stream":
                chunk = event_data.get("chunk", {})
                if hasattr(chunk, "content") and chunk.content:
                    yield format_sse_event("llm_token", {
                        "content": chunk.content
                    })

            # ---------- LLM 结束 ----------
            elif event_kind == "on_chat_model_end":
                output = event_data.get("output", {})
                # 提取 token 使用信息（从不同的响应格式中）
                usage_info = {}
                if hasattr(output, "usage_metadata") and output.usage_metadata:
                    usage_info = {
                        "input_tokens": output.usage_metadata.get("input_tokens", 0),
                        "output_tokens": output.usage_metadata.get("output_tokens", 0),
                        "total_tokens": output.usage_metadata.get("total_tokens", 0)
                    }
                    token_stats.update(usage_info)
                elif hasattr(output, "response_metadata") and output.response_metadata:
                    token_usage = output.response_metadata.get("token_usage", {})
                    if token_usage:
                        usage_info = {
                            "input_tokens": token_usage.get("prompt_tokens", 0),
                            "output_tokens": token_usage.get("completion_tokens", 0),
                            "total_tokens": token_usage.get("total_tokens", 0)
                        }
                        token_stats.update(usage_info)

                yield format_sse_event("llm_end", {
                    "model": event_name,
                    "usage": usage_info if usage_info else token_stats
                })

        # ---------- 获取最终状态 ----------
        final_state = await graph.aget_state(config)
        interrupt_info = extract_interrupt_info(final_state)
        next_nodes = list(final_state.next) if final_state.next else []
        is_completed = len(next_nodes) == 0 and not interrupt_info

        # ---------- 发送完成事件 ----------
        yield format_sse_event("done", {
            "status": final_state.values.get("status", "unknown") if final_state.values else "unknown",
            "next_nodes": next_nodes,
            "is_completed": is_completed,
            "interrupt_info": interrupt_info,
            "values": dict(final_state.values) if final_state.values else {}
        })

    except Exception as e:
        # ---------- 发送错误事件 ----------
        yield format_sse_event("error", {"message": str(e)})


# =============================================================================
# 第 12 步：流式恢复接口
# =============================================================================

@router.post("/stream/resume/{thread_id}")
async def stream_resume_workflow(
    thread_id: str,
    request: StreamResumeWorkflowRequest,
    current_user: User = Depends(get_current_user)
):
    """
    流式恢复工作流（实时显示 AI 生成过程）

    ==========================================================================
    请求：POST /workflow/stream/resume/{thread_id}
    用途：实时显示 AI 生成文章的每个 token

    SSE 事件流：
      1. resume：恢复开始
      2. llm_start：AI 开始生成
      3. llm_token：AI 输出的每个 token（文章内容逐字显示）
      4. llm_end：AI 生成完成，包含 token 统计
      5. done：工作流阶段完成

    前端处理：
      ```javascript
      const eventSource = new EventSource(url)
      eventSource.addEventListener('llm_token', (e) => {
        const content = JSON.parse(e.data).content
        articleText += content
      })
      ```
    """
    # ---------- 验证所有权 ----------
    if not thread_id.startswith(str(current_user.id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此工作流"
        )

    async def generate():
        try:
            # ---------- 获取工作流图 ----------
            graph = await get_graph()
            config = {"configurable": {"thread_id": thread_id}}

            # ---------- 验证状态 ----------
            current_state = await graph.aget_state(config)
            if current_state is None or current_state.values is None:
                yield format_sse_event("error", {"message": f"未找到工作流: {thread_id}"})
                return

            # ---------- 构建恢复数据 ----------
            resume_value: Dict[str, Any] = {}

            if request.action == "select_topic":
                if not request.data or "selected_topic" not in request.data:
                    yield format_sse_event("error", {"message": "选择选题需要提供 selected_topic"})
                    return
                resume_value = {
                    "selected_topic": request.data["selected_topic"],
                }
            elif request.action == "reject":
                feedback = request.data.get("feedback", "") if request.data else ""
                resume_value = {
                    "action": "reject",
                    "feedback": feedback,
                }

            # ---------- 发送恢复事件 ----------
            resume_command = Command(resume=resume_value)
            yield format_sse_event("resume", {
                "thread_id": thread_id,
                "action": request.action
            })

            # ---------- 流式输出 ----------
            async for event in stream_graph_updates(graph, resume_command, config):
                yield event

        except Exception as e:
            yield format_sse_event("error", {"message": str(e)})

    # ---------- 返回 SSE 响应 ----------
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # 禁用 Nginx 缓冲，确保实时
        }
    )
