from contextlib import asynccontextmanager

from fastapi import FastAPI
from langchain_core.tools import BaseTool

from app.mcp.linux_mcp_server import linux_mcp_client

linux_mcp_tools: list[BaseTool] = []


# 定义 lifespan 异步上下文管理器
@asynccontextmanager
async def mcp_lifespan(app: FastAPI):
    try:
        await init_linux_mcp_tools()
        yield  # 应用运行期间
    finally:
        pass


async def init_linux_mcp_tools() -> list[BaseTool]:
    global linux_mcp_tools
    linux_mcp_tools = await linux_mcp_client.get_tools()
    return linux_mcp_tools


async def get_linux_mcp_tools() -> list[BaseTool]:
    global linux_mcp_tools
    if linux_mcp_tools:
        return linux_mcp_tools
    linux_mcp_tools = await linux_mcp_client.get_tools()
    return linux_mcp_tools
