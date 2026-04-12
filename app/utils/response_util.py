import json
from typing import Dict, Any, Optional

class SSEBuilder:
    @staticmethod
    def _build(event_type: str, data: Optional[Dict[str, Any]] = None, sub_thread_id: Optional[str] = None) -> str:
        payload = {"type": event_type}
        if data is not None:
            payload["data"] = data
        if sub_thread_id is not None:
            payload["sub_thread_id"] = sub_thread_id
        return f"data: {json.dumps(payload)}\n\n"

    @staticmethod
    def content(text: str, sub_thread_id: Optional[str] = None) -> str:
        return SSEBuilder._build("content", {"text": text}, sub_thread_id)

    @staticmethod
    def reasoning(text: str, sub_thread_id: Optional[str] = None) -> str:
        return SSEBuilder._build("reasoning", {"text": text}, sub_thread_id)

    @staticmethod
    def tool_start(name: str, args: Dict[str, Any], sub_thread_id: Optional[str] = None) -> str:
        return SSEBuilder._build("tool_start", {"name": name, "args": args}, sub_thread_id)

    @staticmethod
    def tool_end(name: str, result: str, sub_thread_id: Optional[str] = None) -> str:
        return SSEBuilder._build("tool_end", {"name": name, "result": result}, sub_thread_id)

    @staticmethod
    def sub_agent_start(
        task: str,
        sub_thread_id: Optional[str] = None,
        parent_sub_thread_id: Optional[str] = None
    ) -> str:
        payload = {"task": task}
        if parent_sub_thread_id is not None:
            payload["parent_sub_thread_id"] = parent_sub_thread_id
        return SSEBuilder._build("sub_agent_start", payload, sub_thread_id)

    @staticmethod
    def sub_agent_end(result: str, sub_thread_id: Optional[str] = None) -> str:
        return SSEBuilder._build("sub_agent_end", {"result": result}, sub_thread_id)

    @staticmethod
    def step_done() -> str:
        return SSEBuilder._build("step_done")

    @staticmethod
    def error(message: str) -> str:
        return SSEBuilder._build("error", {"message": message})
