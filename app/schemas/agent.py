from pydantic import BaseModel, Field


class SubAgentInput(BaseModel):
    """Input schema for sub-agent delegation tools"""
    task: str = Field(description="委派给子代理的具体目标与核心任务描述")
    context: str = Field(default="", description="前置上下文或前提条件，帮助子代理避免重复提问")
