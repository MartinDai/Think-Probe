from pydantic import BaseModel, Field


class SubAgentInput(BaseModel):
    """Input schema for sub-agent delegation tools"""
    task: str = Field(description="委派给子代理的清晰任务描述")
