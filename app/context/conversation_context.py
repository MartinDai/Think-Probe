import uuid

from langchain_core.messages import BaseMessage

from app.node import NodeType


class ConversationContext:
    def __init__(self, conversation_id=None):
        self.current_node: str = NodeType.TRIAGE.value
        self.messages: list[BaseMessage] = []
        self.conversation_id: str = conversation_id if conversation_id else uuid.uuid4().hex[:16]
