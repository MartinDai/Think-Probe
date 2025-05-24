from langgraph.graph.graph import CompiledGraph
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

from app.context import mcp_context
from app.model import DEFAULT_MODEL
from app.node import NodeState, NodeType, post_process_message, make_system_prompt
from app.node.transfer_to_agent import transfer_to_triage_agent
from app.utils.logger import logger


async def get_shell_agent() -> CompiledGraph:
    linux_mcp_tools = await mcp_context.get_linux_mcp_tools()
    shell_agent = create_react_agent(
        DEFAULT_MODEL,
        linux_mcp_tools + [transfer_to_triage_agent],
        prompt=make_system_prompt(
            """
            You are a shell agent. You can only execute shell on linux.
            If the user asks a question that is out of your scope, transfer back to the triage agent. 
            """
        ),
        state_schema=NodeState,
    )
    return shell_agent


async def shell_node(state: NodeState) -> Command:
    logger.info("Entering shell node")
    state.current = NodeType.SHELL.value
    shell_agent = await get_shell_agent()
    result = await shell_agent.ainvoke(state)
    new_state = post_process_message(state, result)
    return Command(
        update=new_state,
    )
