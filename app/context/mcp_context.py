from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.mcp.linux_mcp_server import linux_mcp_server


# 定义 lifespan 异步上下文管理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动逻辑：在 yield 之前调用 connect
    await linux_mcp_server.connect()
    try:
        yield  # 应用运行期间
    finally:
        # 关闭逻辑：在 yield 之后调用 cleanup
        await linux_mcp_server.cleanup()
