from app.context import mcp_context
from app.node import Agent


async def get_shell_agent() -> Agent:
    """
    Create shell agent with MCP tools.
    Async factory because MCP tools require async initialization.
    """
    mcp_tools = await mcp_context.get_linux_mcp_tools()
    return Agent(
        name="shell",
        instructions=(
            "You are a shell agent. You can execute shell commands on linux. "
            "Use the tools provided to help users with their shell-related tasks. "
            "Be careful with destructive commands and always explain what you're doing."
        ),
        tools=mcp_tools,
    )
