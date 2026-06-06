"""
选题规划调试脚本 - 测试 LLM 服务的选题生成功能

用途：
  直接运行这个脚本，不需要启动整个 FastAPI 服务，
  就能测试 LLM 选题生成是否正常工作。

用法：
  cd /path/to/project && python scripts/debug_plan_topics.py
"""
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.llm_service import LLMService
from langchain_core.messages import HumanMessage, SystemMessage


async def main() -> None:
    topic_direction = "AI技术"
    service = LLMService(enable_pii_anonymize=False)

    print(f"MODEL={service.model}")
    print(f"MODEL_FAST={service.model_fast}")

    messages = [
        SystemMessage(content=service.TOPIC_SYSTEM_PROMPT + '\n\n请直接输出5个标题，每行一个，不要解释。'),
        HumanMessage(content=f"主题：{topic_direction}"),
    ]

    print("\n=== raw ainvoke ===")
    raw_response = await service.llm.ainvoke(messages)
    print(ascii(raw_response.content))

    print("\n=== parsed from raw content ===")
    parsed = service._parse_topics_from_text(raw_response.content)
    print(json.dumps(parsed.model_dump(), ensure_ascii=True, indent=2))

    print("\n=== plan_topics result ===")
    topics_response, usage = await service.plan_topics(topic_direction)
    print(json.dumps(topics_response.model_dump(), ensure_ascii=True, indent=2))
    print(json.dumps(usage.__dict__, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
