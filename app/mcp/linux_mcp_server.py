from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import SSEConnection

linux_mcp_client = MultiServerMCPClient(
    connections={
        "linux": SSEConnection(
            url="http://localhost:3001/sse",
            transport="sse",
            headers=None,
            timeout=5000,
            sse_read_timeout=5000,
            session_kwargs=None,
        )
    }
)
