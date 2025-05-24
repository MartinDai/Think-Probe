import uuid

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage

from app.node import NodeType


class ConversationContext:
    def __init__(self, conversation_id=None):
        self.current_node: str = NodeType.TRIAGE.value
        self.messages: list[BaseMessage] = []
        self.conversation_id: str = conversation_id if conversation_id else uuid.uuid4().hex[:16]

    def messages_to_dict_list(self) -> list[dict]:
        return [__message_to_dict__(message) for message in self.messages]

    def dict_list_to_message(self, msg_dict_list: list[dict]):
        self.messages = []
        for msg_dict in msg_dict_list:
            msg = __dict_to_message__(msg_dict)
            if msg is not None:
                self.messages.append(msg)


def __message_to_dict__(message: BaseMessage) -> dict:
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


def __dict_to_message__(data: dict) -> BaseMessage | None:
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
