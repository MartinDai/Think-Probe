import json
from datetime import datetime
from pathlib import Path

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage

from app.utils.logger import logger

CONVERSATIONS_DIR = "conversations"
RUNTIME_DIR = Path.cwd()


def _message_to_dict(message: BaseMessage) -> dict:
    """Convert a BaseMessage to a serializable dict"""
    if isinstance(message, HumanMessage):
        return {"role": "human", "content": message.content}
    elif isinstance(message, AIMessage):
        result = {"role": "ai", "content": message.content}
        if message.tool_calls:
            result["tool_calls"] = message.tool_calls
        if "reasoning_content" in message.additional_kwargs:
            result["reasoning_content"] = message.additional_kwargs["reasoning_content"]
        return result
    elif isinstance(message, ToolMessage):
        return {
            "role": "tool",
            "name": message.name,
            "content": message.content,
            "tool_call_id": message.tool_call_id,
        }
    return {}


def _dict_to_message(data: dict) -> BaseMessage | None:
    """Convert a dict back to a BaseMessage"""
    role = data.get("role")
    content = data.get("content", "")

    if role == "human":
        return HumanMessage(content=content)
    elif role == "ai":
        tool_calls = data.get("tool_calls", [])
        additional_kwargs = {}
        if "reasoning_content" in data:
            additional_kwargs["reasoning_content"] = data["reasoning_content"]
        return AIMessage(content=content, tool_calls=tool_calls, additional_kwargs=additional_kwargs)
    elif role == "tool":
        return ToolMessage(
            content=content,
            name=data.get("name", ""),
            tool_call_id=data.get("tool_call_id", ""),
        )
    return None


def append_message(conversation_id: str, agent_name: str, message: BaseMessage, extra: dict = None):
    """
    Append a single message to the agent's JSONL file.
    Extra metadata (e.g. sub_agent_file reference) is merged into the JSONL line.

    File structure:
        conversations/{conversation_id}/{agent_name}.jsonl
    """
    dir_path = RUNTIME_DIR / CONVERSATIONS_DIR / conversation_id
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{agent_name}.jsonl"

    msg_dict = _message_to_dict(message)
    msg_dict["timestamp"] = datetime.now().isoformat()
    if extra:
        msg_dict.update(extra)

    with open(file_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(msg_dict, ensure_ascii=False) + '\n')

    logger.info(f"Persisted {msg_dict.get('role')} message to {agent_name}.jsonl")


def get_messages(conversation_id: str, agent_name: str) -> list[BaseMessage]:
    """Read all messages for an agent from its JSONL file (as BaseMessage objects)"""
    file_path = RUNTIME_DIR / CONVERSATIONS_DIR / conversation_id / f"{agent_name}.jsonl"
    if not file_path.exists():
        return []

    messages = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    msg_dict = json.loads(line)
                    msg = _dict_to_message(msg_dict)
                    if msg is not None:
                        messages.append(msg)
                except json.JSONDecodeError:
                    logger.warning(f"Skipping invalid JSONL line in {file_path}")
    return messages


def _read_jsonl_dicts(conversation_id: str, agent_name: str) -> list[dict]:
    """Read all JSONL lines as raw dicts (preserving extra fields like sub_agent_file)"""
    file_path = RUNTIME_DIR / CONVERSATIONS_DIR / conversation_id / f"{agent_name}.jsonl"
    if not file_path.exists():
        return []

    records = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(f"Skipping invalid JSONL line in {file_path}")
    return records


def get_conversation_timeline(conversation_id: str) -> dict | None:
    """
    Build the full conversation timeline from the orchestrator's perspective.

    Returns a structured dict where each message in the orchestrator's timeline
    is preserved. For messages that reference a sub-agent (via sub_agent_file),
    the sub-agent's messages are embedded as a nested list.

    Example output:
    {
        "conversation_id": "abc123",
        "messages": [
            {"role": "human", "content": "查看/tmp下的文件", "timestamp": "..."},
            {"role": "ai", "content": "", "tool_calls": [...], "timestamp": "..."},
            {
                "role": "tool",
                "name": "transfer_to_shell",
                "content": "file1.txt",
                "sub_agent_file": "shell_20260402_211407",
                "sub_agent_messages": [
                    {"role": "human", "content": "列出/tmp下的文件", "timestamp": "..."},
                    {"role": "ai", "content": "", "tool_calls": [...], "timestamp": "..."},
                    {"role": "tool", "name": "exec_command", "content": "...", "timestamp": "..."},
                    {"role": "ai", "content": "file1.txt", "timestamp": "..."}
                ],
                "timestamp": "..."
            },
            {"role": "ai", "content": "在/tmp目录下有以下文件...", "timestamp": "..."}
        ]
    }
    """
    if not conversation_exists(conversation_id):
        return None

    orchestrator_records = _read_jsonl_dicts(conversation_id, "orchestrator")

    # For each record that has a sub_agent_file reference, load and embed sub-agent messages
    for record in orchestrator_records:
        sub_agent_file = record.get("sub_agent_file")
        if sub_agent_file:
            sub_records = _read_jsonl_dicts(conversation_id, sub_agent_file)
            record["sub_agent_messages"] = sub_records

    return {
        "conversation_id": conversation_id,
        "messages": orchestrator_records,
    }


def conversation_exists(conversation_id: str) -> bool:
    """Check if a conversation directory exists with orchestrator messages"""
    dir_path = RUNTIME_DIR / CONVERSATIONS_DIR / conversation_id
    return dir_path.exists() and (dir_path / "orchestrator.jsonl").exists()
