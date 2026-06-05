"""
Windows 启动脚本 - patch asyncio 默认事件循环确保 psycopg3 使用 SelectorEventLoop
必须在导入 app.main 之前执行
"""
import asyncio
import selectors
import platform

if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    _orig_new_event_loop = asyncio.new_event_loop

    def _patched_new_event_loop():
        return asyncio.SelectorEventLoop(selectors.SelectSelector())

    asyncio.new_event_loop = _patched_new_event_loop

# 启动 uvicorn
import sys
sys.exit(__import__("uvicorn").main())
