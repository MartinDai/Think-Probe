from langgraph.prebuilt import create_react_agent
from langgraph.types import Command

from app.model import DEFAULT_MODEL
from app.node import NodeState, NodeType, post_process_message, make_system_prompt
from app.node.transfer_to_agent import transfer_to_triage_agent
from app.tools.get_source_code_tool import get_source_code_tool
from app.utils.logger import logger

java_diagnosis_agent = create_react_agent(
    DEFAULT_MODEL,
    [get_source_code_tool, transfer_to_triage_agent],
    prompt=make_system_prompt(
        """
        You are a java diagnosis agent. You can only process the user's problems about java application.
        Use your knowledge help user find the root cause of the problem and provide a solution.
        The tools available are part of your ability, and you can always choose to call the tools as needed to get the data you want
        You need make a step-by-step plan to solve the problem, Each step of the plan must conform to the following constraints and priorities:
        # Constraints
        - Your experience is important, and you must mine important data every time you get new information, and avoid frequent requests for information from users or frequent calls to tools.
        - Take full advantage of the tools provided to assist you in advancing the next step of plan.
        - You can get the parameters you need to call the tool based on the information you already have, Do not speculate on any value of the parameter
        - Do not expose the tools you call to the user.
    
        # Priorities
        - Based on your experience, analyze the information you have obtained so far and get the information you need to plan the next steps.
        - Call the tool to get the data you need, analyze the information you have so far based on your experience, and then get the information you need for the next steps you plan.
        - Take the information provided by the user, then analyze the current information based on your experience, and then get the information needed to plan the next steps.
        - If the information provided by the user is not included in your plan, you should update your plan.
        - If the user asks a question that is out of your scope, transfer back to the triage agent. 
        """
    ),
    state_schema=NodeState,
)


async def java_diagnosis_node(state: NodeState) -> Command:
    logger.info("Entering java_diagnosis node")
    state.current = NodeType.JAVA_DIAGNOSIS.value
    result = await java_diagnosis_agent.ainvoke(state)
    new_state = post_process_message(state, result)
    return Command(
        update=new_state,
    )
