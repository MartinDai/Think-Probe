import asyncio

from agents.mcp import MCPServerSse

linux_mcp_server = MCPServerSse(
    name="Linux MCP Server",
    params={
        "url": "http://localhost:3001/sse",
    },
)

asyncio.run(linux_mcp_server.connect())
