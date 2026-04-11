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
    model_name: Optional[str] = None   # 允许不同 Agent 使用不同模型，None 表示使用默认模型
    temperature: float = 0              # 默认确定性输出

