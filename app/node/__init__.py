from enum import Enum

from langgraph.prebuilt.chat_agent_executor import AgentStatePydantic


class NodeType(Enum):
    TRIAGE = "triage"
    SHELL = "shell"
    JAVA_DIAGNOSIS = "java_diagnosis"


class NodeState(AgentStatePydantic):
    current: str
