import uuid

from agents import TResponseInputItem, Agent

from app.agent.triage_agent import TriageAgent
from app.context.agent_context import AgentContext


class ConversationContext:
    def __init__(self, conversation_id=None):
        self.context = AgentContext()
        self.current_agent: Agent = TriageAgent
        self.input_items: list[TResponseInputItem] = []
        self.conversation_id: str = conversation_id if conversation_id else uuid.uuid4().hex[:16]
