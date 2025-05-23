import json
from io import TextIOWrapper
from pathlib import Path

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage

from app.context.conversation_context import ConversationContext
from app.node import NodeType

CONVERSATIONS_DIR = "conversations"

RUNTIME_DIR = Path.cwd()


def message_to_dict(message: BaseMessage) -> dict:
    """将 BaseMessage 转换为可序列化的字典"""

    if isinstance(message, HumanMessage):
        return {
            "type": "human",
            "content": message.content,
        }
    elif isinstance(message, AIMessage):
        return {
            "type": "ai",
            "content": message.content,
            "tool_calls": message.tool_calls,
        }
    elif isinstance(message, ToolMessage):
        return {
            "type": "tool",
            "name": message.name,
            "content": message.content,
            "tool_call_id": message.tool_call_id,
        }
    else:
        return {}


def dict_to_message(data: dict) -> BaseMessage | None:
    """将字典反序列化为对应的 BaseMessage 子类"""
    message_type = data.get("type")
    content = data.get("content", "")

    if message_type == "human":
        return HumanMessage(content=content)
    elif message_type == "ai":
        tool_calls = data.get("tool_calls", [])
        return AIMessage(content=content, tool_calls=tool_calls)
    elif message_type == "tool":
        name = data.get("name", "")
        tool_call_id = data.get("tool_call_id", "")
        return ToolMessage(content=content, name=name, tool_call_id=tool_call_id)
    else:
        return None


def save_conversation(context: ConversationContext):
    """
    保存会话
    文件名格式为: conversation_id.json
    如果文件已存在，将被覆盖
    """
    save_dir = RUNTIME_DIR / CONVERSATIONS_DIR
    save_dir.mkdir(parents=True, exist_ok=True)  # 创建目录，如果不存在
    filename = save_dir / f"{context.conversation_id}.json"

    message_dict = [message_to_dict(message) for message in context.messages]

    data = {
        'conversation_id': context.conversation_id,
        'messages': message_dict,
        'current_node': context.current_node
    }

    # 写入JSON文件
    with open(filename, 'w', encoding='utf-8') as f:  # type: TextIOWrapper
        json.dump(data, f, ensure_ascii=False, indent=4)


def get_conversation_context(conversation_id: str) -> ConversationContext | None:
    filename = RUNTIME_DIR / CONVERSATIONS_DIR / f"{conversation_id}.json"
    if not filename.exists():
        return None
    with open(filename, 'r', encoding='utf-8') as f:  # type: TextIOWrapper
        data = json.load(f)
        context = ConversationContext(conversation_id=data['conversation_id'])
        context.messages = [dict_to_message(msg_dict) for msg_dict in data['messages']]
        current_node = data['current_node']
        if current_node == NodeType.JAVA_DIAGNOSIS.value:
            context.current_node = NodeType.JAVA_DIAGNOSIS.value
        elif current_node == NodeType.SHELL.value:
            context.current_node = NodeType.SHELL.value
        else:
            context.current_node = NodeType.TRIAGE.value
        return context
