from pydantic import BaseModel


class AgentContext(BaseModel):
    current: str | None = None
