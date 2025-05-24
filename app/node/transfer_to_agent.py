from langchain_core.tools import tool

from app.node import NodeType


@tool(description="A triage agent that can delegate a user's request to the appropriate agent.", return_direct=True)
def transfer_to_triage_agent() -> str:
    return NodeType.TRIAGE.value


@tool(description="A helpful agent that can execute shell on linux.", return_direct=True)
def transfer_to_shell_agent() -> str:
    return NodeType.SHELL.value


@tool(description="A helpful agent that can diagnosing Java application problems.", return_direct=True)
def transfer_to_java_diagnosis_agent() -> str:
    return NodeType.JAVA_DIAGNOSIS.value
