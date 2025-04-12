from agents import Agent, handoff, HandoffInputData
from agents.extensions import handoff_filters
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

from app.agent.java_diagnosis_agent import JavaDiagnosisAgent
from app.agent.shell_agent import ShellAgent


def triage_handoff_message_filter(handoff_message_data: HandoffInputData) -> HandoffInputData:
    # 删除所有的工具调用
    handoff_message_data = handoff_filters.remove_all_tools(handoff_message_data)

    return HandoffInputData(
        input_history=handoff_message_data.input_history,
        pre_handoff_items=tuple(handoff_message_data.pre_handoff_items),
        new_items=tuple(handoff_message_data.new_items),
    )


TriageAgent = Agent(
    name="Triage Agent",
    handoff_description="A triage agent that can delegate a user's request to the appropriate agent.",
    instructions=(
        f"{RECOMMENDED_PROMPT_PREFIX} "
        "You are a helpful triaging agent. You can use your tools to delegate questions to other appropriate agents."
        "If there are no any appropriate agent to process user's problem, please inform the user directly"
    ),
    handoffs=[
        handoff(agent=JavaDiagnosisAgent),
        handoff(agent=ShellAgent),
    ],
)

JavaDiagnosisAgent.handoffs = [handoff(agent=TriageAgent, input_filter=triage_handoff_message_filter)]
ShellAgent.handoffs = [handoff(agent=TriageAgent)]
