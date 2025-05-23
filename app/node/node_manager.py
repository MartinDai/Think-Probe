from typing import Any

from langchain_core.messages import BaseMessage, ToolMessage, AIMessage
from langgraph.constants import END
from langgraph.types import Command

from app.agent.agent_manager import triage_agent, java_diagnosis_agent, get_shell_agent
from app.node import NodeType, NodeState
from app.utils.logger import logger


def get_next_node(last_message: BaseMessage):
    # Check if the last message is a ToolMessage from a transfer_to tool
    if isinstance(last_message, ToolMessage):
        if last_message.name.startswith("transfer_to"):
            return last_message.content  # Extract node name from ToolMessage content

    return END


def filter_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    filtered_messages = []
    for message in messages:
        if isinstance(message, ToolMessage):
            if not message.name.startswith("transfer_to"):
                filtered_messages.append(message)
        elif isinstance(message, AIMessage):
            if message.tool_calls and message.tool_calls[0]["name"].startswith("transfer_to"):
                pass
            else:
                filtered_messages.append(message)
        else:
            filtered_messages.append(message)
    return filtered_messages


def post_process_message(state: NodeState, result: dict[str, Any]) -> NodeState:
    messages = result["messages"]
    filtered_messages = filter_messages(messages)
    goto = get_next_node(messages[-1])
    state.messages = filtered_messages
    state.current = goto
    return state


async def triage_node(state: NodeState) -> Command:
    logger.info("Entering triage node")
    state.current = NodeType.TRIAGE.value
    result = await triage_agent.ainvoke(state)
    new_state = post_process_message(state, result)
    return Command(
        update=new_state,
    )


async def shell_node(state: NodeState) -> Command:
    logger.info("Entering shell node")
    state.current = NodeType.SHELL.value
    shell_agent = await get_shell_agent()
    result = await shell_agent.ainvoke(state)
    new_state = post_process_message(state, result)
    return Command(
        update=new_state,
    )


async def java_diagnosis_node(state: NodeState) -> Command:
    logger.info("Entering java_diagnosis node")
    state.current = NodeType.JAVA_DIAGNOSIS.value
    result = await java_diagnosis_agent.ainvoke(state)
    new_state = post_process_message(state, result)
    return Command(
        update=new_state,
    )
