import json
import shutil
from datetime import datetime
from pathlib import Path

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage

from app.utils.logger import logger

CONVERSATIONS_DIR = "conversations"
RUNTIME_DIR = Path.cwd()


def _message_to_dict(message: BaseMessage) -> dict:
    """Convert a BaseMessage to a serializable dict for the UI"""
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
        result = {
            "role": "tool",
            "name": message.name,
            "content": message.content,
            "tool_call_id": message.tool_call_id,
        }
        # Include sub_thread_id if present for nested UI
        if "sub_thread_id" in message.additional_kwargs:
            result["sub_thread_id"] = message.additional_kwargs["sub_thread_id"]
        return result
    return {}


async def get_messages(conversation_id: str, thread_id: str = None) -> list[BaseMessage]:
    """
    Read messages for a specific LangGraph thread.
    If thread_id is None, use conversation_id as the main thread.
    """
    from app.core.graph import workflow, DB_PATH
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    
    t_id = thread_id if thread_id else conversation_id
    config = {"configurable": {"thread_id": t_id}}
    
    async with AsyncSqliteSaver.from_conn_string(DB_PATH) as saver:
        graph = workflow.compile(checkpointer=saver)
        state = await graph.aget_state(config)
        if state and "messages" in state.values:
            return state.values["messages"]
    return []


async def get_conversation_timeline(conversation_id: str) -> dict | None:
    """
    Build the full conversation timeline from the main LangGraph thread.
    Recursively embeds sub-agent messages by following sub_thread_id references.
    """
    if not conversation_exists(conversation_id):
        return None

    main_messages = await get_messages(conversation_id)
    if not main_messages:
        return {"conversation_id": conversation_id, "messages": []}

    records = []
    for msg in main_messages:
        msg_dict = _message_to_dict(msg)
        
        # If it's a tool message with a sub_thread_id, recursively fetch sub-messages
        sub_thread_id = msg_dict.get("sub_thread_id")
        if sub_thread_id:
            sub_messages = await get_messages(conversation_id, thread_id=sub_thread_id)
            msg_dict["sub_agent_messages"] = [_message_to_dict(m) for m in sub_messages]
            
        records.append(msg_dict)

    return {
        "conversation_id": conversation_id,
        "messages": records,
    }


def get_metadata(conversation_id: str) -> dict:
    """Get conversation metadata from meta.json"""
    file_path = RUNTIME_DIR / CONVERSATIONS_DIR / conversation_id / "meta.json"
    if file_path.exists():
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def update_metadata(conversation_id: str, metadata: dict):
    """Update conversation metadata in meta.json"""
    dir_path = RUNTIME_DIR / CONVERSATIONS_DIR / conversation_id
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / "meta.json"

    current = get_metadata(conversation_id)
    current.update(metadata)
    current["updated_at"] = datetime.now().isoformat()
    if "created_at" not in current:
        current["created_at"] = datetime.now().isoformat()

    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(current, f, ensure_ascii=False, indent=2)


def list_conversations() -> list[dict]:
    """List all available conversations with their metadata"""
    base_path = RUNTIME_DIR / CONVERSATIONS_DIR
    if not base_path.exists():
        return []

    results = []
    for conv_dir in base_path.iterdir():
        if conv_dir.is_dir() and (conv_dir / "meta.json").exists():
            conv_id = conv_dir.name
            meta = get_metadata(conv_id)
            if meta:
                meta["id"] = conv_id
                results.append(meta)

    # Sort by updated_at descending
    results.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return results


def conversation_exists(conversation_id: str) -> bool:
    """Check if a conversation directory exists"""
    dir_path = RUNTIME_DIR / CONVERSATIONS_DIR / conversation_id
    return dir_path.exists()


def delete_conversation(conversation_id: str) -> bool:
    """Delete the conversation directory and all its contents"""
    dir_path = RUNTIME_DIR / CONVERSATIONS_DIR / conversation_id
    if dir_path.exists():
        try:
            shutil.rmtree(dir_path)
            # Note: LangGraph SQLite data is not deleted here as it's shared in checkpoints.db
            # We could optionally delete from SQLite but it's more complex.
            logger.info(f"Deleted conversation directory: {dir_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete conversation directory {dir_path}: {e}")
            return False
    return False

# Deprecated in favor of LangGraph automatic persistence
def append_message(*args, **kwargs):
    pass
