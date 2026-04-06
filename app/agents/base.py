from dataclasses import dataclass, field
from typing import List, Optional, Any


@dataclass
class Agent:
    """
    Agent definition - encapsulates name, instructions, tools, and sub-agents.
    """
    name: str
    instructions: str
    tools: List[Any] = field(default_factory=list)
    sub_agents: List["Agent"] = field(default_factory=list)
