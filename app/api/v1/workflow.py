"""
工作流接口。

这里是后端最核心的一组接口：启动流程、查看状态、继续执行、查历史、删记录，
基本都从这里进出。
"""
import uuid
import json
from typing import Optional, Dict, Any, List, Literal, AsyncGenerator
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langgraph.types import Command
import psycopg

from app.graph.workflow import get_graph
from app.graph.state import INITIAL_STATE
from app.graph.utils import get_checkpointer
from app.core.config import settings
from app.core.logger import app_logger
from app.models.user import User
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/workflow", tags=["Workflow"])


# =============================================================================
# 请求/响应模型定义
# =============================================================================

class NodeMetricInfo(BaseModel):
    """节点执行指标信息"""
    node_name: str = Field(..., description="节点名称")
    duration_ms: float = Field(default=0, description="执行耗时（毫秒）")
    input_tokens: int = Field(default=0, description="发给 AI 的 token 数")
    output_tokens: int = Field(default=0, description="AI 返回的 token 数")
    total_tokens: int = Field(default=0, description="总 token 数")
    start_time: str = Field(default="", description="开始时间")
    end_time: str = Field(default="", description="结束时间")
    model: str = Field(default="", description="使用的 AI 模型")


class StartWorkflowRequest(BaseModel):
    """启动工作流请求"""
    topic_direction: str = Field(..., min_length=1, max_length=200, description="主题方向，如 AI技术、Python开发")


class StartWorkflowResponse(BaseModel):
    """启动工作流响应"""
    thread_id: str = Field(..., description="工作流线程ID，后续操作凭证")
    status: str = Field(..., description="当前工作流状态")
    generated_topics: List[str] = Field(default=[], description="AI 生成的候选选题列表")
    message: str = Field(..., description="用户提示信息")
    interrupt_info: Optional[Dict[str, Any]] = Field(default=None, description="中断等待信息")
    node_metrics: List[NodeMetricInfo] = Field(default=[], description="节点执行指标")


class WorkflowStateResponse(BaseModel):
    """工作流状态响应"""
    thread_id: str = Field(..., description="工作流线程ID")
    status: str = Field(..., description="当前工作流状态")
    values: Dict[str, Any] = Field(default={}, description="当前状态快照")
    next_nodes: List[str] = Field(default=[], description="下一个待执行节点")
    is_completed: bool = Field(default=False, description="工作流是否已完成")
    interrupt_info: Optional[Dict[str, Any]] = Field(default=None, description="当前中断信息")
    node_metrics: List[NodeMetricInfo] = Field(default=[], description="节点执行指标")


class ResumeWorkflowRequest(BaseModel):
    """恢复工作流请求"""
    action: Literal["select_topic", "approve", "reject"] = Field(..., description="操作类型")
    data: Optional[Dict[str, Any]] = Field(default=None, description="操作数据")


class ResumeWorkflowResponse(BaseModel):
    """恢复工作流响应"""
    thread_id: str = Field(..., description="工作流线程ID")
    status: str = Field(..., description="当前状态")
    message: str = Field(..., description="用户提示信息")
    next_nodes: List[str] = Field(default=[], description="下一个待执行节点")
    is_completed: bool = Field(default=False, description="是否已完成")
    result: Optional[Dict[str, Any]] = Field(default=None, description="完成时的结果数据")
    interrupt_info: Optional[Dict[str, Any]] = Field(default=None, description="下一个中断信息")
    node_metrics: List[NodeMetricInfo] = Field(default=[], description="节点执行指标")


class ThreadInfo(BaseModel):
    """线程基本信息"""
    thread_id: str = Field(..., description="线程ID")
    topic_direction: str = Field(default="", description="主题方向")
    selected_topic: str = Field(default="", description="选中的选题")
    status: str = Field(default="", description="当前状态")
    is_completed: bool = Field(default=False, description="是否已完成")
    created_at: Optional[str] = Field(default=None, description="创建时间")


class ThreadListResponse(BaseModel):
    """线程列表响应"""
    threads: List[ThreadInfo] = Field(default=[], description="工作流列表")
    total: int = Field(default=0, description="总数")


class StreamResumeWorkflowRequest(BaseModel):
    """流式恢复工作流请求"""
    action: Literal["select_topic", "reject"] = Field(..., description="操作类型")
    data: Optional[Dict[str, Any]] = Field(default=None, description="操作数据")


# =============================================================================
# 辅助函数
# =============================================================================

def extract_interrupt_info(state_snapshot) -> Optional[Dict[str, Any]]:
    """
    从 LangGraph 1.0+ 状态快照中提取中断信息

    LangGraph 1.0+ 的 interrupt() 中断信息存在 state_snapshot.tasks 中。
    这个函数遍历 tasks 找出中断值。
    """
    if not state_snapshot or not hasattr(state_snapshot, 'tasks'):
        return None

    for task in state_snapshot.tasks:
        if hasattr(task, 'interrupts') and task.interrupts:
            for interrupt_obj in task.interrupts:
                if hasattr(interrupt_obj, 'value'):
                    return interrupt_obj.value

    return None


# =============================================================================
# API 接口
# =============================================================================

@router.post("/start", response_model=StartWorkflowResponse)
async def start_workflow(
    request: StartWorkflowRequest,
    current_user: User = Depends(get_current_user)
) -> StartWorkflowResponse:
    """启动工作流，执行到第一个中断点（选题生成完成）后返回。"""
    try:
        thread_id = f"{current_user.id}_{uuid.uuid4()}"

        app_logger.workflow_started(
            thread_id=thread_id,
            topic_direction=request.topic_direction
        )

        graph = await get_graph()
        config = {"configurable": {"thread_id": thread_id}}

        initial_input = {
            **INITIAL_STATE,
            "topic_direction": request.topic_direction,
            "status": "started",
        }

        # 执行工作流（遇到 interrupt 自动暂停）
        await graph.ainvoke(initial_input, config)

        state_snapshot = await graph.aget_state(config)
        if state_snapshot is None or state_snapshot.values is None:
            raise RuntimeError("工作流已启动，但未能读取到状态快照")

        interrupt_info = extract_interrupt_info(state_snapshot)
        state_values = dict(state_snapshot.values)

        # 从中断信息或状态中提取选题列表
        generated_topics = []
        if interrupt_info and "options" in interrupt_info:
            generated_topics = interrupt_info.get("options", [])

        if not generated_topics:
            generated_topics = state_values.get("generated_topics", [])

        current_status = state_values.get("status", "unknown")
        node_metrics = state_values.get("node_metrics", [])
        error_message = state_values.get("error", "")

        if not generated_topics:
            detail = error_message or "工作流未生成任何候选选题，请检查 LLM 配置后重试"
            raise RuntimeError(detail)

        app_logger.workflow_stage_changed(
            thread_id=thread_id,
            stage="topics_generated",
            topics_count=len(generated_topics)
        )

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


@router.get("/state/{thread_id}", response_model=WorkflowStateResponse)
async def get_workflow_state(
    thread_id: str,
    current_user: User = Depends(get_current_user)
) -> WorkflowStateResponse:
    """
    获取工作流当前状态

    用途：
      - 页面刷新后恢复状态
      - 调试时查看工作流内部数据
      - 确认工作流是否还在进行中
    """
    try:
        # 验证所有权（防止跨用户访问）
        if not thread_id.startswith(str(current_user.id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此工作流"
            )

        graph = await get_graph()
        config = {"configurable": {"thread_id": thread_id}}

        state_snapshot = await graph.aget_state(config)

        if state_snapshot is None or state_snapshot.values is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到工作流: {thread_id}"
            )

        next_nodes = list(state_snapshot.next) if state_snapshot.next else []
        interrupt_info = extract_interrupt_info(state_snapshot)
        is_completed = len(next_nodes) == 0 and not interrupt_info
        node_metrics = state_snapshot.values.get("node_metrics", [])

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


@router.post("/resume/{thread_id}", response_model=ResumeWorkflowResponse)
async def resume_workflow(
    thread_id: str,
    request: ResumeWorkflowRequest,
    current_user: User = Depends(get_current_user)
) -> ResumeWorkflowResponse:
    """
    恢复工作流（普通模式，非流式）

    action 类型说明：
      - select_topic：继续执行 write_draft（AI 生成文章）
      - approve：继续执行 extract_visuals + generate_images（审核通过）
      - reject：继续执行 write_draft（驳回重写）

    LangGraph 1.0+ 使用 Command(resume=value) 恢复中断的工作流。
    """
    try:
        if not thread_id.startswith(str(current_user.id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此工作流"
            )

        graph = await get_graph()
        config = {"configurable": {"thread_id": thread_id}}

        current_state = await graph.aget_state(config)
        if current_state is None or current_state.values is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"未找到工作流: {thread_id}"
            )

        # 根据 action 构建恢复数据
        resume_value: Dict[str, Any] = {}

        if request.action == "select_topic":
            if not request.data or "selected_topic" not in request.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="选择选题需要提供 selected_topic"
                )
            resume_value = {"selected_topic": request.data["selected_topic"]}
            app_logger.topic_selected(
                thread_id=thread_id,
                selected_topic=request.data["selected_topic"]
            )

        elif request.action == "approve":
            resume_value = {"action": "approve"}
            app_logger.draft_approved(thread_id=thread_id)

        elif request.action == "reject":
            feedback = request.data.get("feedback", "") if request.data else ""
            resume_value = {"action": "reject", "feedback": feedback}
            revision_count = current_state.values.get("revision_count", 0)
            app_logger.draft_rejected(
                thread_id=thread_id,
                feedback=feedback,
                revision_count=revision_count
            )

        # 恢复工作流执行
        resume_command = Command(resume=resume_value)
        result = await graph.ainvoke(resume_command, config)

        updated_state = await graph.aget_state(config)
        next_nodes = list(updated_state.next) if updated_state.next else []
        interrupt_info = extract_interrupt_info(updated_state)
        is_completed = len(next_nodes) == 0 and not interrupt_info
        node_metrics = updated_state.values.get("node_metrics", [])

        # 构建响应消息
        message = "操作成功"
        final_result = None

        if is_completed:
            message = "工作流已完成"
            final_result = {
                "article_content": updated_state.values.get("article_content", ""),
                "visual_points": updated_state.values.get("visual_points", []),
                "image_urls": updated_state.values.get("image_urls", []),
            }
            app_logger.workflow_completed(thread_id=thread_id)
        elif interrupt_info:
            action_required = interrupt_info.get("action_required", "")
            if action_required == "review":
                message = "文章草稿已生成，请审核"
                article_content = updated_state.values.get("article_content", "")
                app_logger.draft_generated(thread_id=thread_id, word_count=len(article_content))
            elif action_required == "select_topic":
                message = "请选择选题"
            else:
                message = "等待用户操作"

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


@router.get("/history/{thread_id}")
async def get_workflow_history(
    thread_id: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    获取工作流历史状态记录

    用途：
      - 调试：查看每个节点的输入输出
      - 审计：记录工作流的每个决策点
    """
    try:
        if not thread_id.startswith(str(current_user.id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权访问此工作流"
            )

        graph = await get_graph()
        config = {"configurable": {"thread_id": thread_id}}

        history = []
        async for state in graph.aget_state_history(config):
            history.append({
                "config": state.config,
                "values": dict(state.values) if state.values else {},
                "next": list(state.next) if state.next else [],
                "created_at": state.created_at if hasattr(state, "created_at") else None,
            })

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


@router.get("/threads", response_model=ThreadListResponse)
async def get_all_threads(
    current_user: User = Depends(get_current_user)
) -> ThreadListResponse:
    """
    获取用户所有工作流线程列表

    工作流程：
      1. 直连 PostgreSQL 查询 checkpoints 表（按 user_id 前缀过滤）
      2. 对每个 thread_id 调用 aget_state 获取基本信息
      3. 返回轻量化的 ThreadInfo 列表
    """
    try:
        threads = []

        async with await psycopg.AsyncConnection.connect(
            settings.postgres_uri,
            autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                user_id_prefix = f"{current_user.id}_%"
                await cur.execute("""
                    SELECT DISTINCT thread_id
                    FROM checkpoints
                    WHERE thread_id LIKE %s
                    ORDER BY thread_id
                """, (user_id_prefix,))
                rows = await cur.fetchall()

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
                continue

        return ThreadListResponse(threads=threads, total=len(threads))

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取线程列表失败: {str(e)}"
        )


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    删除指定的工作流

    为什么直接操作 PostgreSQL？
      LangGraph 的 Checkpointer 表结构特殊，
      需要删除 checkpoint_writes、checkpoint_blobs、checkpoints 三张表。
    """
    try:
        if not thread_id.startswith(str(current_user.id)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权删除此工作流"
            )

        async with await psycopg.AsyncConnection.connect(
            settings.postgres_uri,
            autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (thread_id,))
                await cur.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (thread_id,))
                await cur.execute("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,))

                return {"success": True, "message": f"线程 {thread_id} 已删除"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除线程失败: {str(e)}"
        )


# =============================================================================
# SSE 流式恢复接口
# =============================================================================

def format_sse_event(event_type: str, data: Any) -> str:
    """
    将事件格式化为 SSE（Server-Sent Events）格式

    SSE 格式：
      data: {"type": "llm_token", "data": {"content": "今"}}
      data: {"type": "done", "data": {...}}
      （两个换行结束）

    为什么用 SSE 而不是 WebSocket？
      SSE 是单向（服务端 -> 客户端），更简单；HTTP/2 复用，不需要建多个连接。
    """
    payload = {
        "type": event_type,
        "data": data
    }
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


async def stream_graph_updates(
    graph,
    input_data: Any,
    config: Dict[str, Any]
) -> AsyncGenerator[str, None]:
    """
    使用 LangGraph astream_events 流式输出文章生成过程

    工作原理：
      1. 使用 graph.astream_events() 遍历事件流
      2. 捕获 on_chat_model_stream 事件，获取 AI 生成的每个 token
      3. 将 token 格式化为 SSE 事件，yield 给客户端

    为什么用 astream_events 而不是 astream？
      astream 只返回最终节点结果，无法逐 token 显示。
      astream_events 提供更细粒度的事件，可以区分"节点开始"和"LLM token 输出"。
    """
    try:
        yield format_sse_event("start", {})

        token_stats = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        }

        async for event in graph.astream_events(input_data, config, version="v2"):
            event_kind = event.get("event", "")
            event_name = event.get("name", "")
            event_data = event.get("data", {})

            if event_kind == "on_chat_model_start":
                yield format_sse_event("llm_start", {"model": event_name})

            elif event_kind == "on_chat_model_stream":
                chunk = event_data.get("chunk", {})
                if hasattr(chunk, "content") and chunk.content:
                    yield format_sse_event("llm_token", {"content": chunk.content})

            elif event_kind == "on_chat_model_end":
                output = event_data.get("output", {})
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

        final_state = await graph.aget_state(config)
        interrupt_info = extract_interrupt_info(final_state)
        next_nodes = list(final_state.next) if final_state.next else []
        is_completed = len(next_nodes) == 0 and not interrupt_info

        yield format_sse_event("done", {
            "status": final_state.values.get("status", "unknown") if final_state.values else "unknown",
            "next_nodes": next_nodes,
            "is_completed": is_completed,
            "interrupt_info": interrupt_info,
            "values": dict(final_state.values) if final_state.values else {}
        })

    except Exception as e:
        yield format_sse_event("error", {"message": str(e)})


@router.post("/stream/resume/{thread_id}")
async def stream_resume_workflow(
    thread_id: str,
    request: StreamResumeWorkflowRequest,
    current_user: User = Depends(get_current_user)
):
    """
    流式恢复工作流（实时显示 AI 生成过程）

    SSE 事件流：
      1. resume：恢复开始
      2. llm_start：AI 开始生成
      3. llm_token：AI 输出的每个 token（文章内容逐字显示）
      4. llm_end：AI 生成完成，包含 token 统计
      5. done：工作流阶段完成
    """
    if not thread_id.startswith(str(current_user.id)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此工作流"
        )

    async def generate():
        try:
            graph = await get_graph()
            config = {"configurable": {"thread_id": thread_id}}

            current_state = await graph.aget_state(config)
            if current_state is None or current_state.values is None:
                yield format_sse_event("error", {"message": f"未找到工作流: {thread_id}"})
                return

            resume_value: Dict[str, Any] = {}

            if request.action == "select_topic":
                if not request.data or "selected_topic" not in request.data:
                    yield format_sse_event("error", {"message": "选择选题需要提供 selected_topic"})
                    return
                resume_value = {"selected_topic": request.data["selected_topic"]}
            elif request.action == "reject":
                feedback = request.data.get("feedback", "") if request.data else ""
                resume_value = {"action": "reject", "feedback": feedback}

            yield format_sse_event("resume", {"thread_id": thread_id, "action": request.action})

            resume_command = Command(resume=resume_value)
            async for event in stream_graph_updates(graph, resume_command, config):
                yield event

        except Exception as e:
            yield format_sse_event("error", {"message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
