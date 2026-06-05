"""
Windows 启动脚本 - 使用 SelectorEventLoop 兼容 psycopg async
"""
import asyncio
import selectors
import platform

from uvicorn import Config, Server


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    config = Config(
        app="app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        loop="asyncio",
    )
    config.get_loop_factory = lambda: selector_loop_factory
    server = Server(config)
    server.run()
