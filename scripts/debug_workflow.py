"""
工作流调试脚本 - 查询和恢复已中断的工作流

用法：
    # 1. 查询某个 thread_id 的当前状态
    python scripts/debug_workflow.py query <thread_id>

    # 2. 恢复工作流（选择选题继续）
    python scripts/debug_workflow.py resume-topic <thread_id> "<选题内容>"

    # 3. 恢复工作流（审核通过）
    python scripts/debug_workflow.py approve <thread_id>

    # 4. 恢复工作流（审核驳回，附带反馈）
    python scripts/debug_workflow.py reject <thread_id> "<驳回原因>"

    # 5. 查看工作流完整历史
    python scripts/debug_workflow.py history <thread_id>

    # 6. 列出当前用户所有工作流线程
    python scripts/debug_workflow.py list

    # 7. 删除指定工作流
    python scripts/debug_workflow.py delete <thread_id>

示例：
    python scripts/debug_workflow.py query a6305e96-da84-4c59-8a3f-9eabecd16073_f98378ba-ac1c-4581-859c-4cbb06f3bcfd
    python scripts/debug_workflow.py resume-topic a6305e96-da84-4c59-8a3f-9eabecd16073_f98378ba-ac1c-4581-859c-4cbb06f3bcfd "AI如何提升程序员效率"
    python scripts/debug_workflow.py approve a6305e96-da84-4c59-8a3f-9eabecd16073_f98378ba-ac1c-4581-859c-4cbb06f3bcfd
    python scripts/debug_workflow.py history a6305e96-da84-4c59-8a3f-9eabecd16073_f98378ba-ac1c-4581-859c-4cbb06f3bcfd
"""
import sys
import asyncio
import argparse
from pathlib import Path

# 保证 app 导入路径正确
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from langgraph.types import Command
import psycopg

from app.graph.workflow import get_graph
from app.core.config import settings


# =============================================================================
# 辅助函数
# =============================================================================

def extract_interrupt_info(state_snapshot):
    """从状态快照中提取中断信息"""
    if not state_snapshot or not hasattr(state_snapshot, 'tasks'):
        return None
    for task in state_snapshot.tasks:
        if hasattr(task, 'interrupts') and task.interrupts:
            for interrupt_obj in task.interrupts:
                if hasattr(interrupt_obj, 'value'):
                    return interrupt_obj.value
    return None


def print_divider(title: str = ""):
    width = 80
    if title:
        print(f"\n{'=' * width}")
        print(f"  {title}")
        print('=' * width)
    else:
        print('-' * width)


def print_state_snapshot(state_snapshot, thread_id: str):
    """格式化打印状态快照"""
    print_divider(f"Thread: {thread_id}")

    status = state_snapshot.values.get("status", "unknown")
    print(f"  状态 (status):     {status}")

    interrupt_info = extract_interrupt_info(state_snapshot)
    if interrupt_info:
        print(f"  中断信息:")
        for k, v in interrupt_info.items():
            if k == "article_preview":
                v = str(v)[:200] + "..."
            print(f"    - {k}: {v}")
    else:
        print(f"  中断信息:           无（工作流已完成或未中断）")

    next_nodes = list(state_snapshot.next) if state_snapshot.next else []
    print(f"  下一个节点 (next):  {next_nodes if next_nodes else '无'}")

    print_divider()

    # 打印关键状态字段
    print(f"  主题方向:           {state_snapshot.values.get('topic_direction', '(未设置)')}")
    print(f"  选中选题:           {state_snapshot.values.get('selected_topic', '(未选择)')}")
    print(f"  审核状态:           {state_snapshot.values.get('review_status', '(未审核)')}")

    article = state_snapshot.values.get("article_content", "")
    if article:
        print(f"  文章内容长度:       {len(article)} 字符")
        print(f"  文章预览:           {article[:150]}...")
    else:
        print(f"  文章内容:           (暂无)")

    visual_points = state_snapshot.values.get("visual_points", [])
    print(f"  配图要点数量:       {len(visual_points)}")

    image_urls = state_snapshot.values.get("image_urls", [])
    print(f"  生成图片数量:        {len(image_urls)}")
    if image_urls:
        for url in image_urls:
            print(f"    - {url}")

    node_metrics = state_snapshot.values.get("node_metrics", [])
    if node_metrics:
        print_divider("节点执行指标")
        for m in node_metrics:
            print(f"  [{m.get('node_name', '?')}]")
            print(f"    耗时: {m.get('duration_ms', 0):.0f}ms")
            print(f"    Token: {m.get('input_tokens', 0)} in / {m.get('output_tokens', 0)} out")
            print(f"    模型: {m.get('model', '?')}")

    print_divider()


# =============================================================================
# 数据库直接查询（不需要认证）
# =============================================================================

async def query_from_db(thread_id: str):
    """直接从数据库查询 checkpoints 表（不需要通过 API）"""
    print_divider(f"数据库查询 - {thread_id}")

    async with await psycopg.AsyncConnection.connect(
        settings.postgres_uri,
        autocommit=True
    ) as conn:
        async with conn.cursor() as cur:
            # 查询所有相关 checkpoints
            await cur.execute("""
                SELECT checkpoint_id, checkpoint_ns, created_at,
                       LENGTH(serialized_checkpoint) as checkpoint_size
                FROM checkpoints
                WHERE thread_id = %s
                ORDER BY created_at DESC
            """, (thread_id,))
            rows = await cur.fetchall()

            if not rows:
                print(f"  未找到任何 checkpoints，thread_id 可能不存在或已被删除")
                return

            print(f"  找到 {len(rows)} 个检查点:")
            for row in rows:
                print(f"    checkpoint_id: {row[0]}")
                print(f"    命名空间:       {row[1]}")
                print(f"    创建时间:      {row[2]}")
                print(f"    数据大小:      {row[3]} bytes")
                print()

            # 查询 checkpoint_writes
            await cur.execute("""
                SELECT checkpoint_id, channel, LEFT(val, 200) as val_preview,
                       LENGTH(val) as val_size, created_at
                FROM checkpoint_writes
                WHERE thread_id = %s
                ORDER BY created_at DESC
            """, (thread_id,))
            writes = await cur.fetchall()

            if writes:
                print(f"  最近的写入记录 ({len(writes)} 条):")
                for w in writes[:10]:
                    preview = w[2] + "..." if len(w[2]) >= 200 else w[2]
                    print(f"    [{w[0]}] {w[1]}: {preview} ({w[3]} bytes)")


# =============================================================================
# 通过 API 认证方式查询（需要认证）
# =============================================================================

async def query_workflow_state(thread_id: str):
    """通过工作流 API 查询当前状态"""
    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    state_snapshot = await graph.aget_state(config)

    if state_snapshot is None or state_snapshot.values is None:
        print(f"未找到工作流: {thread_id}")
        return

    print_state_snapshot(state_snapshot, thread_id)


async def get_workflow_history(thread_id: str):
    """查看完整历史"""
    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    history = []
    async for state in graph.aget_state_history(config):
        history.append(state)

    print_divider(f"工作流历史 - {thread_id}")
    print(f"  总共 {len(history)} 个检查点（按时间倒序）")

    for i, state in enumerate(history):
        print_divider(f"检查点 #{i + 1}")
        print(f"  checkpoint_id: {state.config.get('configurable', {}).get('checkpoint_id', '?')}")
        print(f"  created_at:   {state.created_at}")
        print(f"  next nodes:   {list(state.next) if state.next else '无'}")
        print(f"  status:       {state.values.get('status', 'unknown')}")
        print(f"  字段摘要:")
        for key in ["topic_direction", "selected_topic", "review_status", "article_content"]:
            val = state.values.get(key, "(未设置)")
            if isinstance(val, str) and len(val) > 80:
                val = val[:80] + "..."
            print(f"    {key}: {val}")


async def resume_workflow(thread_id: str, action: str, data: dict = None):
    """恢复工作流"""
    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    # 先查看当前状态
    current_state = await graph.aget_state(config)
    if current_state is None or current_state.values is None:
        print(f"未找到工作流: {thread_id}")
        return

    print(f"当前状态: {current_state.values.get('status', 'unknown')}")
    print(f"操作: {action}")
    print()

    resume_value = {}
    if action == "select_topic":
        resume_value = {"selected_topic": data.get("selected_topic")}
        print(f">> 选中选题: {data.get('selected_topic')}")
    elif action == "approve":
        resume_value = {"action": "approve"}
        print(">> 审核通过")
    elif action == "reject":
        resume_value = {"action": "reject", "feedback": data.get("feedback", "")}
        print(f">> 审核驳回: {data.get('feedback', '')}")

    # 恢复执行
    print("正在恢复工作流...")
    resume_command = Command(resume=resume_value)
    result = await graph.ainvoke(resume_command, config)

    # 查看恢复后的状态
    updated_state = await graph.aget_state(config)
    print()
    print(f"恢复后状态: {updated_state.values.get('status', 'unknown')}")
    interrupt_info = extract_interrupt_info(updated_state)
    if interrupt_info:
        print(f"中断信息: {interrupt_info}")
    else:
        next_nodes = list(updated_state.next) if updated_state.next else []
        if not next_nodes:
            print(">> 工作流已完成！")
        else:
            print(f">> 下一个节点: {next_nodes}")


async def list_all_threads():
    """列出所有工作流线程"""
    print_divider("所有工作流线程")

    async with await psycopg.AsyncConnection.connect(
        settings.postgres_uri,
        autocommit=True
    ) as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                SELECT thread_id, COUNT(*) as checkpoint_count, MAX(created_at) as last_update
                FROM checkpoints
                GROUP BY thread_id
                ORDER BY last_update DESC
                LIMIT 50
            """)
            rows = await cur.fetchall()

    if not rows:
        print("  没有找到任何工作流记录")
        return

    print(f"  找到 {len(rows)} 个工作流线程:")
    for row in rows:
        print(f"    thread_id:   {row[0]}")
        print(f"    检查点数:    {row[1]}")
        print(f"    最后更新:   {row[2]}")
        print()


async def delete_workflow(thread_id: str):
    """删除指定工作流"""
    print_divider(f"删除工作流 - {thread_id}")
    confirm = input(f"确认删除 {thread_id}？此操作不可恢复！(yes/no): ")
    if confirm.lower() != "yes":
        print("取消删除")
        return

    async with await psycopg.AsyncConnection.connect(
        settings.postgres_uri,
        autocommit=True
    ) as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (thread_id,))
            await cur.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (thread_id,))
            await cur.execute("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,))
            print(f"已删除: {thread_id}")


# =============================================================================
# 主入口
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(
        description="工作流调试脚本 - 查询和恢复已中断的工作流",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # query - 查询状态
    subparsers.add_parser("query", help="查询工作流当前状态").add_argument("thread_id", help="线程ID")

    # db-query - 数据库直接查询
    subparsers.add_parser("db-query", help="直接从数据库查询（无需API认证）").add_argument("thread_id", help="线程ID")

    # history - 查看历史
    subparsers.add_parser("history", help="查看工作流完整历史").add_argument("thread_id", help="线程ID")

    # resume-topic - 恢复（选择选题）
    p_resume_topic = subparsers.add_parser("resume-topic", help="恢复工作流 - 选择选题")
    p_resume_topic.add_argument("thread_id", help="线程ID")
    p_resume_topic.add_argument("topic", help="选中的选题内容")

    # approve - 审核通过
    subparsers.add_parser("approve", help="恢复工作流 - 审核通过").add_argument("thread_id", help="线程ID")

    # reject - 审核驳回
    p_reject = subparsers.add_parser("reject", help="恢复工作流 - 审核驳回")
    p_reject.add_argument("thread_id", help="线程ID")
    p_reject.add_argument("feedback", nargs="?", default="", help="驳回原因（可选）")

    # list - 列出所有
    subparsers.add_parser("list", help="列出所有工作流线程")

    # delete - 删除
    subparsers.add_parser("delete", help="删除指定工作流").add_argument("thread_id", help="线程ID")

    args = parser.parse_args()

    if args.command == "query":
        await query_workflow_state(args.thread_id)
    elif args.command == "db-query":
        await query_from_db(args.thread_id)
    elif args.command == "history":
        await get_workflow_history(args.thread_id)
    elif args.command == "resume-topic":
        await resume_workflow(args.thread_id, "select_topic", {"selected_topic": args.topic})
    elif args.command == "approve":
        await resume_workflow(args.thread_id, "approve")
    elif args.command == "reject":
        await resume_workflow(args.thread_id, "reject", {"feedback": args.feedback})
    elif args.command == "list":
        await list_all_threads()
    elif args.command == "delete":
        await delete_workflow(args.thread_id)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
