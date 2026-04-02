from app.node import Agent

triage_agent = Agent(
    name="triage",
    instructions=(
        "You are a helpful triaging agent. You help users by answering their questions directly. "
        "If the user asks about shell commands or Java application diagnosis, "
        "let them know you can help with those topics."
    ),
    tools=[],
)
