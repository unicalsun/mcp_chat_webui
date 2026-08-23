"""MCP 客户端管理模块 - 管理 MCP Server 连接和工具调用"""

import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client


def _ensure_url_scheme(url: str) -> str:
    """确保 URL 有 http/https 前缀"""
    if url and not url.startswith(("http://", "https://")):
        return f"http://{url}"
    return url


class MCPClient:
    """单个 MCP Server 连接"""

    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack: Optional[AsyncExitStack] = None
        self._tools: Optional[List[Dict[str, Any]]] = None

    async def connect_stdio(self, command: str, args: List[str], env: Optional[Dict[str, str]] = None):
        self.exit_stack = AsyncExitStack()
        server_params = StdioServerParameters(command=command, args=args, env=env)
        read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

    async def connect_sse(self, url: str, headers: Optional[Dict[str, str]] = None):
        self.exit_stack = AsyncExitStack()
        result = await self.exit_stack.enter_async_context(sse_client(url, headers=headers))
        if isinstance(result, tuple) and len(result) == 2:
            read, write = result
        else:
            raise ValueError(f"SSE client returned unexpected result: {type(result)}")
        self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

    async def connect_streamable_http(self, url: str, headers: Optional[Dict[str, str]] = None):
        self.exit_stack = AsyncExitStack()
        try:
            from mcp.client.streamable_http import streamablehttp_client
            result = await self.exit_stack.enter_async_context(streamablehttp_client(url, headers=headers))
            if isinstance(result, tuple) and len(result) >= 2:
                read, write = result[0], result[1]
            else:
                raise ValueError(f"Streamable HTTP client returned unexpected result: {type(result)}")
            self.session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await self.session.initialize()
        except ImportError:
            await self.connect_sse(url, headers)

    async def list_tools(self) -> List[Dict[str, Any]]:
        if self._tools is not None:
            return self._tools
        if not self.session:
            raise Exception("未连接到 MCP Server")
        result = await self.session.list_tools()
        self._tools = [
            {"name": t.name, "description": t.description, "input_schema": t.inputSchema}
            for t in result.tools
        ]
        return self._tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if not self.session:
            raise Exception("未连接到 MCP Server")
        return await self.session.call_tool(tool_name, arguments)

    async def close(self):
        self.session = None
        if self.exit_stack:
            try:
                await self.exit_stack.aclose()
            except BaseException:
                pass  # 忽略清理时的任何错误（CancelledError 等）
            self.exit_stack = None
            self._tools = None


class MCPClientManager:
    """管理所有活跃的 MCP Server 连接"""

    def __init__(self):
        self._clients: Dict[str, MCPClient] = {}

    async def connect(self, server_id: str, server_type: str, transport_config: Dict[str, Any]) -> MCPClient:
        if server_id in self._clients:
            return self._clients[server_id]

        client = MCPClient()
        try:
            if server_type == "stdio":
                await client.connect_stdio(
                    command=transport_config.get("command", "python"),
                    args=transport_config.get("args", []),
                    env=transport_config.get("env"),
                )
            elif server_type == "sse":
                await client.connect_sse(
                    url=_ensure_url_scheme(transport_config.get("url", "")),
                    headers=transport_config.get("headers"),
                )
            elif server_type == "streamable-http":
                await client.connect_streamable_http(
                    url=_ensure_url_scheme(transport_config.get("url", "")),
                    headers=transport_config.get("headers"),
                )
            else:
                raise ValueError(f"不支持的传输类型: {server_type}")

            self._clients[server_id] = client
            return client
        except BaseException:
            await client.close()
            raise

    def get(self, server_id: str) -> Optional[MCPClient]:
        return self._clients.get(server_id)

    async def disconnect(self, server_id: str):
        if server_id in self._clients:
            await self._clients[server_id].close()
            del self._clients[server_id]

    async def disconnect_all(self):
        for sid in list(self._clients.keys()):
            await self.disconnect(sid)

    def is_connected(self, server_id: str) -> bool:
        return server_id in self._clients


# ---------- MCP Server 配置持久化 ----------

class MCPServerStore:
    """MCP Server 配置文件存储（JSON）"""

    def __init__(self, config_path: Path):
        self._path = config_path
        self._servers: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._servers = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._servers = []
        else:
            self._servers = []

    def _save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._servers, f, ensure_ascii=False, indent=2)

    def list_all(self, search: Optional[str] = None) -> List[Dict[str, Any]]:
        if search:
            s = search.lower()
            return [sv for sv in self._servers if s in sv.get("name", "").lower() or s in sv.get("server_id", "").lower()]
        return list(self._servers)

    def get(self, server_id: str) -> Optional[Dict[str, Any]]:
        for sv in self._servers:
            if sv["server_id"] == server_id:
                return sv
        return None

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        server_id = f"mcp_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        server = {
            "server_id": server_id,
            "name": data["name"],
            "description": data.get("description", ""),
            "server_type": data.get("server_type", "stdio"),
            "transport_config": data["transport_config"],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._servers.append(server)
        self._save()
        return server

    def update(self, server_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        server = self.get(server_id)
        if not server:
            return None
        for key in ("name", "description", "server_type", "transport_config"):
            if key in data:
                server[key] = data[key]
        server["updated_at"] = datetime.utcnow().isoformat()
        self._save()
        return server

    def delete(self, server_id: str) -> bool:
        before = len(self._servers)
        self._servers = [sv for sv in self._servers if sv["server_id"] != server_id]
        if len(self._servers) < before:
            self._save()
            return True
        return False
