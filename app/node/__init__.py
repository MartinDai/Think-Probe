from enum import Enum
from typing import Any

from langchain_core.messages import BaseMessage, ToolMessage, AIMessage
from langgraph.constants import END
from langgraph.prebuilt.chat_agent_executor import AgentStatePydantic


class NodeType(Enum):
    TRIAGE = "triage"
    SHELL = "shell"
    JAVA_DIAGNOSIS = "java_diagnosis"


class NodeState(AgentStatePydantic):
    current: str


def make_system_prompt(suffix: str) -> str:
    return (
        "# System context\n"
        "You are part of a multi-agent system, designed to make agent "
        "coordination and execution easy. Agents uses two primary abstraction: **Agents** and "
        "**Handoffs**. An agent encompasses instructions and tools and can hand off a "
        "conversation to another agent when appropriate. "
        "Handoffs are achieved by calling a handoff function, generally named "
        "`transfer_to_<agent_name>`. Transfers between agents are handled seamlessly in the background;"
        " do not mention or draw attention to these transfers in your conversation with the user."
        f"\n{suffix}"
    )


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
