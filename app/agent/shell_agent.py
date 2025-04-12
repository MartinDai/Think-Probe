from agents import Agent
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX

from app.mcp.linux_mcp_server import linux_mcp_server

ShellAgent = Agent(
    name="Shell Agent",
    handoff_description="A helpful agent that can execute shell on linux",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
    You are a shell agent. You can only execute shell on linux.
    If the user asks a question that is out of your scope, transfer back to the triage agent. 
    """,
    mcp_servers=[linux_mcp_server],
)
