import json
from typing import Dict, Any, Optional

class SSEBuilder:
    @staticmethod
    def _build(event_type: str, data: Optional[Dict[str, Any]] = None, sub_agent: Optional[str] = None) -> str:
        payload = {"type": event_type}
        if data is not None:
            payload["data"] = data
        if sub_agent is not None:
            payload["sub_agent"] = sub_agent
        return f"data: {json.dumps(payload)}\n\n"

    @staticmethod
    def content(text: str, sub_agent: Optional[str] = None) -> str:
        return SSEBuilder._build("content", {"text": text}, sub_agent)

    @staticmethod
    def reasoning(text: str, sub_agent: Optional[str] = None) -> str:
        return SSEBuilder._build("reasoning", {"text": text}, sub_agent)

    @staticmethod
    def tool_start(name: str, args: Dict[str, Any], sub_agent: Optional[str] = None) -> str:
        return SSEBuilder._build("tool_start", {"name": name, "args": args}, sub_agent)

    @staticmethod
    def tool_end(name: str, result: str, sub_agent: Optional[str] = None) -> str:
        return SSEBuilder._build("tool_end", {"name": name, "result": result}, sub_agent)

    @staticmethod
    def sub_agent_start(name: str, task: str, sub_agent: Optional[str] = None) -> str:
        return SSEBuilder._build("sub_agent_start", {"name": name, "task": task}, sub_agent)

    @staticmethod
    def sub_agent_end(result: str, sub_agent: Optional[str] = None) -> str:
        return SSEBuilder._build("sub_agent_end", {"result": result}, sub_agent)

    @staticmethod
    def step_done() -> str:
        return SSEBuilder._build("step_done")

    @staticmethod
    def error(message: str) -> str:
        return SSEBuilder._build("error", {"message": message})
