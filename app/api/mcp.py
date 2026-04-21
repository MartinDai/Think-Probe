from fastapi import APIRouter, HTTPException, Request

from app.schemas.mcp import McpEnabledPayload, McpServerPayload, McpSyncRequest
from app.service.mcp_service import mcp_service

router = APIRouter(prefix="/api/mcp", tags=["MCP"])


@router.get("/servers")
async def list_mcp_servers():
    return {"servers": await mcp_service.list_servers(include_tools=True)}


@router.get("/servers/{server_id}")
async def get_mcp_server(server_id: int):
    server = await mcp_service.get_server(server_id, include_tools=True)
    if server is None:
        raise HTTPException(status_code=404, detail="MCP 服务不存在")
    return server


@router.post("/servers")
async def create_mcp_server(request: Request):
    payload = McpServerPayload(**(await request.json()))
    try:
        server = await mcp_service.create_server(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "server": server}


@router.put("/servers/{server_id}")
async def update_mcp_server(server_id: int, request: Request):
    payload = McpServerPayload(**(await request.json()))
    try:
        server = await mcp_service.update_server(server_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", "server": server}


@router.patch("/servers/{server_id}/enabled")
async def set_mcp_server_enabled(server_id: int, request: Request):
    payload = McpEnabledPayload(**(await request.json()))
    try:
        server = await mcp_service.set_enabled(server_id, payload.enabled)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "success", "server": server}


@router.delete("/servers/{server_id}")
async def delete_mcp_server(server_id: int):
    deleted = await mcp_service.delete_server(server_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="MCP 服务不存在")
    return {"status": "success"}


@router.post("/servers/{server_id}/sync")
async def sync_mcp_server(server_id: int):
    try:
        server = await mcp_service.sync_server(server_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"status": "success", "server": server}


@router.get("/servers/{server_id}/tools")
async def get_mcp_server_tools(server_id: int):
    server = await mcp_service.get_server(server_id, include_tools=True)
    if server is None:
        raise HTTPException(status_code=404, detail="MCP 服务不存在")
    return {"tools": server["tools"], "server": server}


@router.post("/servers/sync")
async def sync_enabled_mcp_servers(request: Request):
    payload = McpSyncRequest(**(await request.json() if request.headers.get("content-length") else {}))
    if payload.sync_enabled_only:
        summary = await mcp_service.sync_enabled_servers()
    else:
        servers = await mcp_service.list_servers()
        summary = {"total": len(servers), "success": 0, "failed": 0, "servers": []}
        for server in servers:
            synced = await mcp_service.sync_server(server["id"])
            summary["servers"].append(synced)
            if synced["last_error"]:
                summary["failed"] += 1
            else:
                summary["success"] += 1
    return {"status": "success", "summary": summary}
