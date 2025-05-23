from langchain_core.tools import tool
from langgraph.graph.graph import CompiledGraph
from langgraph.prebuilt import create_react_agent

from app.context import mcp_context
from app.model.default_model_provider import DEFAULT_MODEL
from app.node import NodeState
from app.tools.get_source_code_tool import get_source_code_tool


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


@tool(description="A triage agent that can delegate a user's request to the appropriate agent.", return_direct=True)
def transfer_to_triage_agent() -> str:
    return "triage"


@tool(description="A helpful agent that can execute shell on linux.", return_direct=True)
def transfer_to_shell_agent() -> str:
    return "shell"


@tool(description="A helpful agent that can diagnosing Java application problems.", return_direct=True)
def transfer_to_java_diagnosis_agent() -> str:
    return "java_diagnosis"


triage_agent = create_react_agent(
    DEFAULT_MODEL,
    tools=[transfer_to_shell_agent, transfer_to_java_diagnosis_agent],
    prompt=make_system_prompt(
        "You are a helpful triaging agent. You can use your tools to delegate questions to other appropriate agents."
        "If there are no any appropriate agent to process user's problem, please inform the user directly"
    ),
    state_schema=NodeState,
)


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


java_diagnosis_agent = create_react_agent(
    DEFAULT_MODEL,
    [get_source_code_tool, transfer_to_triage_agent],
    prompt=make_system_prompt(
        """
        You are a shell agent. You can only execute shell on linux.
        If the user asks a question that is out of your scope, transfer back to the triage agent. 
        """
    ),
    state_schema=NodeState,
)
