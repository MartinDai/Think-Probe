import uuid

from langchain_core.messages import BaseMessage


class ConversationContext:
    def __init__(self, conversation_id=None):
        self.conversation_id: str = conversation_id if conversation_id else uuid.uuid4().hex[:16]
        self.messages: list[BaseMessage] = []
