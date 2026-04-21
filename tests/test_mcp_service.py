import unittest
from unittest.mock import AsyncMock, patch

from pydantic import BaseModel

from app.schemas.mcp import McpServerPayload
from app.service.mcp_service import McpService
from app.store.database import McpServer


class _DummyToolSchema(BaseModel):
    path: str


class _DummyTool:
    name = "filesystem_read"
    description = "Read a file from MCP filesystem server."

    @staticmethod
    def get_input_schema():
        return _DummyToolSchema


class McpServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = McpService()

    def test_payload_normalizes_transport(self):
        payload = McpServerPayload(
            name="demo",
            transport="streamable-http",
        )
        self.assertEqual(payload.transport, "streamable_http")

    def test_payload_rejects_unsupported_transport(self):
        with self.assertRaises(ValueError):
            McpServerPayload(
                name="demo",
                transport="websocket",
            )

    def test_build_connection_for_stdio(self):
        server = McpServer(
            name="fs",
            transport="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "."],
            env={"ROOT": "/tmp"},
            cwd="/tmp",
            session_kwargs={"read_timeout_seconds": 20},
            enabled=True,
        )

        connection = self.service._build_connection(server)

        self.assertEqual(connection["transport"], "stdio")
        self.assertEqual(connection["command"], "npx")
        self.assertEqual(connection["args"][1], "@modelcontextprotocol/server-filesystem")
        self.assertEqual(connection["env"]["ROOT"], "/tmp")
        self.assertEqual(connection["cwd"], "/tmp")
        self.assertEqual(connection["session_kwargs"]["read_timeout_seconds"], 20)

    def test_tool_snapshot_contains_schema(self):
        snapshot = self.service._tool_to_snapshot(_DummyTool())

        self.assertEqual(snapshot["name"], "filesystem_read")
        self.assertIn("path", snapshot["input_schema"]["properties"])

    def test_serialize_server_does_not_require_lazy_loaded_tools(self):
        server = McpServer(
            id=1,
            name="linux-mcp",
            transport="streamable_http",
            url="http://127.0.0.1:3001/mcp",
            enabled=True,
        )

        serialized = self.service._serialize_server(server, include_tools=True)

        self.assertEqual(serialized["tool_count"], 0)
        self.assertEqual(serialized["tools"], [])

    async def test_set_enabled_raises_for_missing_server(self):
        with self.assertRaises(KeyError):
            await self.service.set_enabled(999999, True)

    async def test_load_server_tools_returns_empty_on_error(self):
        server = McpServer(name="broken", transport="http", url="http://localhost:9999", enabled=True)

        with patch("app.service.mcp_service.MultiServerMCPClient") as mock_client:
            instance = mock_client.return_value
            instance.get_tools = AsyncMock(side_effect=RuntimeError("boom"))

            result = await self.service._load_server_tools(server)

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
