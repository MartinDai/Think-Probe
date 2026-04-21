from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List

from langchain_mcp_adapters.client import MultiServerMCPClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.schemas.mcp import McpServerPayload
from app.store.database import McpServer, McpTool, get_session

logger = logging.getLogger(__name__)


class McpService:
    def _get_loaded_tools(self, server: McpServer) -> List[McpTool]:
        tools = server.__dict__.get("tools")
        if tools is None:
            return []
        return list(tools)

    def _normalize_transport(self, transport: str) -> str:
        normalized = transport.strip().lower().replace("-", "_")
        if normalized == "http":
            return "streamable_http"
        return normalized

    def _build_connection(self, server: McpServer) -> Dict[str, Any]:
        transport = self._normalize_transport(server.transport)
        connection: Dict[str, Any] = {"transport": transport}

        if transport == "stdio":
            connection["command"] = server.command or ""
            connection["args"] = list(server.args or [])
            if server.env:
                connection["env"] = dict(server.env)
            if server.cwd:
                connection["cwd"] = server.cwd
        else:
            connection["url"] = server.url or ""
            if server.headers:
                connection["headers"] = dict(server.headers)

        if server.session_kwargs:
            connection["session_kwargs"] = dict(server.session_kwargs)

        return connection

    def _serialize_tool(self, tool: McpTool) -> Dict[str, Any]:
        return {
            "id": tool.id,
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.input_schema or {},
            "synced_at": tool.synced_at.isoformat() if tool.synced_at else None,
        }

    def _serialize_server(self, server: McpServer, *, include_tools: bool = False) -> Dict[str, Any]:
        loaded_tools = self._get_loaded_tools(server)
        tools = sorted(loaded_tools, key=lambda item: item.name.lower()) if include_tools else []
        return {
            "id": server.id,
            "name": server.name,
            "description": server.description or "",
            "transport": server.transport,
            "enabled": server.enabled,
            "command": server.command or "",
            "args": list(server.args or []),
            "url": server.url or "",
            "env": dict(server.env or {}),
            "headers": dict(server.headers or {}),
            "cwd": server.cwd or "",
            "session_kwargs": dict(server.session_kwargs or {}),
            "last_sync_at": server.last_sync_at.isoformat() if server.last_sync_at else None,
            "last_error": server.last_error or "",
            "tool_count": len(loaded_tools),
            "tools": [self._serialize_tool(tool) for tool in tools],
        }

    async def _get_server(self, server_id: int, *, include_tools: bool = True) -> McpServer | None:
        async with get_session() as session:
            stmt = select(McpServer).where(McpServer.id == server_id)
            if include_tools:
                stmt = stmt.options(selectinload(McpServer.tools))
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_servers(self, *, include_tools: bool = False) -> List[Dict[str, Any]]:
        async with get_session() as session:
            stmt = select(McpServer).order_by(McpServer.updated_at.desc(), McpServer.id.desc())
            if include_tools:
                stmt = stmt.options(selectinload(McpServer.tools))
            result = await session.execute(stmt)
            servers = result.scalars().unique().all()
            return [self._serialize_server(server, include_tools=include_tools) for server in servers]

    async def get_server(self, server_id: int, *, include_tools: bool = True) -> Dict[str, Any] | None:
        server = await self._get_server(server_id, include_tools=include_tools)
        if server is None:
            return None
        return self._serialize_server(server, include_tools=include_tools)

    async def create_server(self, payload: McpServerPayload) -> Dict[str, Any]:
        async with get_session() as session:
            exists_stmt = select(McpServer).where(McpServer.name == payload.name)
            exists = await session.execute(exists_stmt)
            if exists.scalar_one_or_none():
                raise ValueError(f"MCP 服务 `{payload.name}` 已存在")

            server = McpServer(
                name=payload.name,
                description=payload.description,
                transport=payload.transport,
                enabled=payload.enabled,
                command=payload.command or None,
                args=payload.args or [],
                url=payload.url or None,
                env=payload.env or {},
                headers=payload.headers or {},
                cwd=payload.cwd or None,
                session_kwargs=payload.session_kwargs or {},
                updated_at=datetime.utcnow(),
            )
            session.add(server)
            await session.flush()
            await session.refresh(server)
            return self._serialize_server(server, include_tools=True)

    async def update_server(self, server_id: int, payload: McpServerPayload) -> Dict[str, Any]:
        async with get_session() as session:
            stmt = (
                select(McpServer)
                .where(McpServer.id == server_id)
                .options(selectinload(McpServer.tools))
            )
            result = await session.execute(stmt)
            server = result.scalar_one_or_none()
            if server is None:
                raise KeyError("MCP 服务不存在")

            duplicate_stmt = select(McpServer).where(McpServer.name == payload.name, McpServer.id != server_id)
            duplicate = await session.execute(duplicate_stmt)
            if duplicate.scalar_one_or_none():
                raise ValueError(f"MCP 服务 `{payload.name}` 已存在")

            server.name = payload.name
            server.description = payload.description or None
            server.transport = payload.transport
            server.enabled = payload.enabled
            server.command = payload.command or None
            server.args = payload.args or []
            server.url = payload.url or None
            server.env = payload.env or {}
            server.headers = payload.headers or {}
            server.cwd = payload.cwd or None
            server.session_kwargs = payload.session_kwargs or {}
            server.updated_at = datetime.utcnow()

            return self._serialize_server(server, include_tools=True)

    async def set_enabled(self, server_id: int, enabled: bool) -> Dict[str, Any]:
        async with get_session() as session:
            stmt = (
                select(McpServer)
                .where(McpServer.id == server_id)
                .options(selectinload(McpServer.tools))
            )
            result = await session.execute(stmt)
            server = result.scalar_one_or_none()
            if server is None:
                raise KeyError("MCP 服务不存在")

            server.enabled = enabled
            server.updated_at = datetime.utcnow()
            return self._serialize_server(server, include_tools=True)

    async def delete_server(self, server_id: int) -> bool:
        async with get_session() as session:
            stmt = (
                select(McpServer)
                .where(McpServer.id == server_id)
                .options(selectinload(McpServer.tools))
            )
            result = await session.execute(stmt)
            server = result.scalar_one_or_none()
            if server is None:
                return False
            await session.delete(server)
            return True

    async def _replace_tools(self, server: McpServer, tool_snapshots: List[Dict[str, Any]]) -> None:
        now = datetime.utcnow()
        server.tools.clear()
        for item in tool_snapshots:
            server.tools.append(
                McpTool(
                    name=item["name"],
                    description=item.get("description") or "",
                    input_schema=item.get("input_schema") or {},
                    synced_at=now,
                )
            )
        server.last_sync_at = now
        server.last_error = None
        server.updated_at = now

    def _tool_to_snapshot(self, tool: Any) -> Dict[str, Any]:
        schema = {}
        try:
            tool_input_schema = tool.get_input_schema()
            if hasattr(tool_input_schema, "model_json_schema"):
                schema = tool_input_schema.model_json_schema()
        except Exception:
            schema = {}

        return {
            "name": getattr(tool, "name", "unknown"),
            "description": getattr(tool, "description", "") or "",
            "input_schema": schema,
        }

    async def sync_server(self, server_id: int) -> Dict[str, Any]:
        async with get_session() as session:
            stmt = (
                select(McpServer)
                .where(McpServer.id == server_id)
                .options(selectinload(McpServer.tools))
            )
            result = await session.execute(stmt)
            server = result.scalar_one_or_none()
            if server is None:
                raise KeyError("MCP 服务不存在")

            client = MultiServerMCPClient(
                {server.name: self._build_connection(server)},
                tool_name_prefix=True,
            )
            try:
                tools = await client.get_tools(server_name=server.name)
                snapshots = [self._tool_to_snapshot(tool) for tool in tools]
                await self._replace_tools(server, snapshots)
            except Exception as exc:
                server.last_error = str(exc)
                server.updated_at = datetime.utcnow()
                logger.warning("Failed to sync MCP server %s: %s", server.name, exc)
            return self._serialize_server(server, include_tools=True)

    async def sync_enabled_servers(self) -> Dict[str, Any]:
        async with get_session() as session:
            stmt = (
                select(McpServer)
                .where(McpServer.enabled.is_(True))
                .options(selectinload(McpServer.tools))
            )
            result = await session.execute(stmt)
            servers = result.scalars().unique().all()

            summary = {"total": len(servers), "success": 0, "failed": 0, "servers": []}
            for server in servers:
                client = MultiServerMCPClient(
                    {server.name: self._build_connection(server)},
                    tool_name_prefix=True,
                )
                try:
                    tools = await client.get_tools(server_name=server.name)
                    snapshots = [self._tool_to_snapshot(tool) for tool in tools]
                    await self._replace_tools(server, snapshots)
                    summary["success"] += 1
                except Exception as exc:
                    server.last_error = str(exc)
                    server.updated_at = datetime.utcnow()
                    summary["failed"] += 1
                    logger.warning("Failed to sync MCP server %s: %s", server.name, exc)

                summary["servers"].append(self._serialize_server(server, include_tools=True))

            return summary

    async def load_enabled_tools(self) -> List[Any]:
        async with get_session() as session:
            stmt = select(McpServer).where(McpServer.enabled.is_(True)).order_by(McpServer.id.asc())
            result = await session.execute(stmt)
            servers = result.scalars().all()

        tasks = [self._load_server_tools(server) for server in servers]
        tool_groups = await asyncio.gather(*tasks)
        tools: List[Any] = []
        for group in tool_groups:
            tools.extend(group)
        return tools

    async def _load_server_tools(self, server: McpServer) -> List[Any]:
        client = MultiServerMCPClient(
            {server.name: self._build_connection(server)},
            tool_name_prefix=True,
        )
        try:
            return await client.get_tools(server_name=server.name)
        except Exception as exc:
            logger.warning("Skipping MCP server %s during runtime tool load: %s", server.name, exc)
            return []


mcp_service = McpService()
