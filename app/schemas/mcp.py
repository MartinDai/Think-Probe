from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


VALID_TRANSPORTS = {"stdio", "streamable_http"}


class McpServerPayload(BaseModel):
    name: str = Field(description="MCP 服务名称，需唯一。")
    description: str = Field(default="", description="后台展示用描述。")
    transport: str = Field(description="传输方式：stdio/streamable-http。")
    enabled: bool = Field(default=True, description="是否启用并参与 agent 自动加载。")
    command: str = Field(default="", description="stdio 模式下启动命令。")
    args: List[str] = Field(default_factory=list, description="stdio 模式下的参数列表。")
    url: str = Field(default="", description="streamable-http 模式下的目标地址。")
    env: Dict[str, str] = Field(default_factory=dict, description="stdio 模式下的环境变量。")
    headers: Dict[str, str] = Field(default_factory=dict, description="streamable-http 模式下的请求头。")
    cwd: str = Field(default="", description="stdio 模式下的工作目录。")
    session_kwargs: Dict[str, Any] = Field(default_factory=dict, description="客户端会话附加参数。")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("服务名称不能为空")
        return normalized

    @field_validator("transport")
    @classmethod
    def validate_transport(cls, value: str) -> str:
        normalized = value.strip().lower().replace("-", "_")
        if normalized == "http":
            normalized = "streamable_http"
        if normalized not in VALID_TRANSPORTS:
            raise ValueError("不支持的 transport")
        return normalized

    @field_validator("command", "url", "cwd")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class McpSyncRequest(BaseModel):
    sync_enabled_only: bool = Field(default=True, description="是否只同步启用的服务。")


class McpEnabledPayload(BaseModel):
    enabled: bool = Field(description="是否启用 MCP 服务。")


class McpToolRead(BaseModel):
    id: int
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    synced_at: Optional[str] = None


class McpServerRead(BaseModel):
    id: int
    name: str
    description: str = ""
    transport: str
    enabled: bool
    command: str = ""
    args: List[str] = Field(default_factory=list)
    url: str = ""
    env: Dict[str, str] = Field(default_factory=dict)
    headers: Dict[str, str] = Field(default_factory=dict)
    cwd: str = ""
    session_kwargs: Dict[str, Any] = Field(default_factory=dict)
    last_sync_at: Optional[str] = None
    last_error: str = ""
    tool_count: int = 0
    tools: List[McpToolRead] = Field(default_factory=list)
