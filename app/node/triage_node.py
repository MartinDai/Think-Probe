from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

from app.model import DEFAULT_MODEL
from app.node import NodeState, NodeType, post_process_message, make_system_prompt
from app.node.transfer_to_agent import transfer_to_shell_agent, transfer_to_java_diagnosis_agent
from app.utils.logger import logger

triage_agent = create_react_agent(
    DEFAULT_MODEL,
    tools=[transfer_to_shell_agent, transfer_to_java_diagnosis_agent],
    prompt=make_system_prompt(
        "You are a helpful triaging agent. You can use your tools to delegate questions to other appropriate agents."
        "If there are no any appropriate agent to process user's problem, please inform the user directly"
    ),
    state_schema=NodeState,
)


async def triage_node(state: NodeState) -> Command:
    logger.info("Entering triage node")
    state.current = NodeType.TRIAGE.value
    result = await triage_agent.ainvoke(state)
    new_state = post_process_message(state, result)
    return Command(
        update=new_state,
    )
