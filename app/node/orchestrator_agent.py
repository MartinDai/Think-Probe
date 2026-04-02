from app.node import Agent

orchestrator_agent = Agent(
    name="orchestrator",
    instructions=(
        "You are a helpful orchestrator agent. You are responsible for understanding the user's request "
        "and delegating tasks to the appropriate sub-agent when needed. "
        "Use the transfer tools to delegate tasks to specialized agents. "
        "After receiving results from sub-agents, synthesize the information and respond to the user. "
        "If no sub-agent is appropriate, answer the user's question directly."
    ),
    tools=[],
    sub_agents=[],  # Sub-agents are wired in workflow_service
)
