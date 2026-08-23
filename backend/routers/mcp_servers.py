"""MCP Server 配置管理 API 路由"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from backend.mcp_client import MCPServerStore, MCPClientManager, MCPClient, _ensure_url_scheme

router = APIRouter(prefix="/api/mcp-servers", tags=["mcp-servers"])

# 这些会在 main.py 中注入
_store: Optional[MCPServerStore] = None
_manager: Optional[MCPClientManager] = None


def init(store: MCPServerStore, manager: MCPClientManager):
    global _store, _manager
    _store = store
    _manager = manager


@router.get("")
def list_servers(search: Optional[str] = Query(None)):
    return {"items": _store.list_all(search=search), "total": len(_store.list_all(search=search))}


@router.get("/{server_id}")
def get_server(server_id: str):
    server = _store.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")
    return {**server, "connected": _manager.is_connected(server_id)}


@router.post("")
def create_server(data: dict):
    if not data.get("name"):
        raise HTTPException(status_code=400, detail="name 不能为空")
    return _store.create(data)


@router.put("/{server_id}")
def update_server(server_id: str, data: dict):
    result = _store.update(server_id, data)
    if not result:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")
    return result


@router.delete("/{server_id}")
def delete_server(server_id: str):
    if not _store.delete(server_id):
        raise HTTPException(status_code=404, detail="MCP Server 不存在")
    return {"message": "删除成功"}


@router.post("/{server_id}/test")
async def test_server(server_id: str):
    """测试 MCP Server 连接（临时连接后断开）"""
    server = _store.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")

    import asyncio
    from backend.mcp_client import MCPClient

    async def _try_connect():
        client = MCPClient()
        try:
            st = server["server_type"]
            cfg = server["transport_config"]
            if st == "stdio":
                await client.connect_stdio(cfg.get("command", "python"), cfg.get("args", []), cfg.get("env"))
            elif st == "sse":
                await client.connect_sse(_ensure_url_scheme(cfg.get("url", "")), cfg.get("headers"))
            elif st == "streamable-http":
                await client.connect_streamable_http(_ensure_url_scheme(cfg.get("url", "")), cfg.get("headers"))
            else:
                raise ValueError(f"不支持的传输类型: {st}")

            tools = await client.list_tools()
            return {
                "status": "success",
                "message": f"成功连接到 MCP Server: {server['name']}",
                "tools_count": len(tools),
                "tools": [t["name"] for t in tools],
            }
        finally:
            await client.close()

    try:
        return await asyncio.wait_for(_try_connect(), timeout=15.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=500, detail="连接超时（15秒），请检查 MCP Server 是否运行中，地址是否正确")
    except BaseException as e:
        raise HTTPException(status_code=500, detail=f"连接失败: {type(e).__name__}: {str(e)}")
