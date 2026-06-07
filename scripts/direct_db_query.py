"""
直接查数据库，解码 checkpoints 内容来了解工作流状态
用法: python scripts/direct_db_query.py [thread_id]
"""
import asyncio
import json
import sys
import psycopg

POSTGRES_URI = "postgresql://postgres:''''@localhost:5432/graph_xiaohongshu"


async def main(thread_id: str):
    async with await psycopg.AsyncConnection.connect(
        POSTGRES_URI, autocommit=True
    ) as conn:
        async with conn.cursor() as cur:
            # 看 checkpoint_writes 表结构
            await cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'checkpoint_writes'
                ORDER BY ordinal_position
            """)
            write_cols = await cur.fetchall()
            print("checkpoint_writes 表结构:")
            for col in write_cols:
                print(f"  {col[0]} ({col[1]})")
            print()

            # 查 checkpoints
            await cur.execute("""
                SELECT checkpoint_id, checkpoint_ns, type, parent_checkpoint_id,
                       checkpoint, metadata
                FROM checkpoints
                WHERE thread_id = %s
                ORDER BY checkpoint_id
            """, (thread_id,))
            checkpoints = await cur.fetchall()

            if not checkpoints:
                print(f"未找到 thread_id: {thread_id}")
                return

            print(f"{'=' * 80}")
            print(f"Thread: {thread_id}")
            print(f"共 {len(checkpoints)} 个检查点")
            print(f"{'=' * 80}")

            for i, row in enumerate(checkpoints):
                cp_id, ns, typ, parent_cp, cp_jsonb, meta_jsonb = row
                print(f"\n{'─' * 80}")
                print(f"检查点 #{i + 1}  |  ID: {cp_id}  |  ns: '{ns}'  |  step: {meta_jsonb.get('step') if meta_jsonb else '?'}")
                print(f"{'─' * 80}")

                if cp_jsonb:
                    cv = cp_jsonb.get("channel_values", {})
                    if cv:
                        print(f"  状态快照 channel_values:")
                        for key, val in cv.items():
                            if key == "node_metrics":
                                print(f"    {key}: (共 {len(val) if val else 0} 条)")
                                if val:
                                    for m in val:
                                        print(f"      - {m.get('node_name', '?')} | {m.get('duration_ms', 0):.0f}ms | {m.get('total_tokens', 0)} tokens")
                            elif isinstance(val, str) and len(val) > 300:
                                print(f"    {key}: {val[:300]}...")
                            elif val is not None and val != "":
                                print(f"    {key}: {val}")

            # checkpoint_writes
            print(f"\n{'=' * 80}")
            print("增量写入记录 (checkpoint_writes)")
            print(f"{'=' * 80}")

            await cur.execute("""
                SELECT checkpoint_id, checkpoint_ns, channel, idx, type
                FROM checkpoint_writes
                WHERE thread_id = %s
                ORDER BY checkpoint_id, idx
            """, (thread_id,))
            writes = await cur.fetchall()

            if not writes:
                print("  无写入记录")
            else:
                print(f"  共 {len(writes)} 条写入:")
                cur_cp = None
                for row in writes:
                    cp_id, cp_ns, channel, idx, typ = row
                    if cp_id != cur_cp:
                        print(f"\n  [{cp_id}] (ns={cp_ns})")
                        cur_cp = cp_id
                    print(f"    [{idx}] {channel} ({typ})")


if __name__ == "__main__":
    tid = sys.argv[1] if len(sys.argv) > 1 else "a6305e96-da84-4c59-8a3f-9eabecd16073_f98378ba-ac1c-4581-859c-4cbb06f3bcfd"
    asyncio.run(main(tid))
