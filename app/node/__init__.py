from dataclasses import dataclass, field


@dataclass
class Agent:
    """
    Agent definition - inspired by OpenAI Agents SDK.

    An Agent encapsulates:
    - name: unique identifier
    - instructions: system prompt for the LLM
    - tools: list of tools the agent can use
    - sub_agents: list of sub-agents that this agent can delegate tasks to
    """
    name: str
    instructions: str
    tools: list = field(default_factory=list)
    sub_agents: list["Agent"] = field(default_factory=list)
