from agents import Agent, handoff
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

from app.agent.java_diagnosis_agent import JavaDiagnosisAgent
from app.agent.shell_agent import ShellAgent

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

JavaDiagnosisAgent.handoffs = [handoff(agent=TriageAgent)]
ShellAgent.handoffs = [handoff(agent=TriageAgent)]
