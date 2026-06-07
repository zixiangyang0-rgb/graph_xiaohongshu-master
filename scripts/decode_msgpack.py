"""
解码 checkpoint_writes 中的 msgpack 二进制数据
"""
import asyncio
import json
import sys
import psycopg
import msgpack

POSTGRES_URI = "postgresql://postgres:''''@localhost:5432/graph_xiaohongshu"


async def main(thread_id: str):
    async with await psycopg.AsyncConnection.connect(
        POSTGRES_URI, autocommit=True
    ) as conn:
        async with conn.cursor() as cur:
            # 查所有写入记录及其 blob 数据
            await cur.execute("""
                SELECT checkpoint_id, checkpoint_ns, channel, idx, type, blob
                FROM checkpoint_writes
                WHERE thread_id = %s
                ORDER BY checkpoint_id, idx
            """, (thread_id,))
            writes = await cur.fetchall()

            print(f"{'=' * 80}")
            print(f"解码后的写入内容 - Thread: {thread_id}")
            print(f"{'=' * 80}")

            for row in writes:
                cp_id, cp_ns, channel, idx, typ, blob_data = row
                if blob_data is None:
                    continue

                try:
                    decoded = msgpack.unpackb(bytes(blob_data), raw=False)
                    val_str = json.dumps(decoded, ensure_ascii=False, indent=2)
                    if len(val_str) > 500:
                        val_str = val_str[:500] + "\n    ... (truncated)"
                    print(f"\n  [{cp_id[:12]}...] {channel}:")
                    print(f"    {val_str}")
                except Exception as e:
                    print(f"\n  [{cp_id[:12]}...] {channel}: <无法解码: {e}>")


if __name__ == "__main__":
    tid = sys.argv[1] if len(sys.argv) > 1 else "a6305e96-da84-4c59-8a3f-9eabecd16073_f98378ba-ac1c-4581-859c-4cbb06f3bcfd"
    asyncio.run(main(tid))
