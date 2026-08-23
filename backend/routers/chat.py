"""聊天 API 路由 - MCP Server 连接管理和 LLM 聊天（含高风险操作确认）"""

import re
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException

from backend.config import config
from backend.mcp_client import MCPClientManager, MCPServerStore, MCPClient
from backend.llm_client import LLMClient, tool_result_to_text

router = APIRouter(prefix="/api/chat", tags=["chat"])

_store: Optional[MCPServerStore] = None
_manager: Optional[MCPClientManager] = None

# 每个 server 维护独立的对话历史
_conversations: dict[str, list] = {}
# 每个 server 的待确认状态
_pending_confirmations: dict[str, dict] = {}

# 高风险 SQL 关键词
_RISKY_KEYWORDS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|REPLACE|RENAME|GRANT|REVOKE)\b',
    re.IGNORECASE,
)


def init(store: MCPServerStore, manager: MCPClientManager):
    global _store, _manager
    _store = store
    _manager = manager


def _is_risky_tool(tool_name: str, arguments: Dict[str, Any]) -> bool:
    """检测工具调用是否为高风险操作（检查工具名和参数中的 SQL 关键词）"""
    # 检查工具名
    if _RISKY_KEYWORDS.search(tool_name):
        return True
    # 检查所有参数值
    for val in arguments.values():
        if isinstance(val, str) and _RISKY_KEYWORDS.search(val):
            return True
    return False


def _assistant_msg(resp: Dict[str, Any]) -> Dict[str, Any]:
    """构建 assistant 消息 — reasoning_content 必须在字段中（可以为空）"""
    msg: Dict[str, Any] = {"role": "assistant", "content": resp["content"] or ""}
    msg["reasoning_content"] = resp.get("reasoning_content") or ""
    return msg


@router.get("/status")
def chat_status():
    """获取全局状态（LLM 配置、活跃连接）"""
    return {
        "llm_configured": config.has_llm,
        "llm_provider": config.LLM_PROVIDER if config.has_llm else "",
        "llm_model": config.LLM_MODEL if config.has_llm else "",
        "connected_servers": list(_manager._clients),
    }


@router.post("/connect/{server_id}")
async def connect_server(server_id: str):
    """建立到 MCP Server 的持久连接"""
    server = _store.get(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP Server 不存在")

    if _manager.is_connected(server_id):
        tools = await _manager.get(server_id).list_tools()
        return {"message": "已连接", "tools": tools}

    try:
        client = await _manager.connect(
            server_id=server_id,
            server_type=server["server_type"],
            transport_config=server["transport_config"],
        )
        tools = await client.list_tools()
        _conversations[server_id] = []
        _pending_confirmations.pop(server_id, None)
        return {"message": f"已连接到 {server['name']}", "tools": tools}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"连接失败: {str(e)}")


@router.post("/disconnect/{server_id}")
async def disconnect_server(server_id: str):
    """断开 MCP Server 连接"""
    await _manager.disconnect(server_id)
    _conversations.pop(server_id, None)
    _pending_confirmations.pop(server_id, None)
    return {"message": "已断开"}


@router.get("/tools/{server_id}")
async def get_tools(server_id: str):
    """获取已连接 Server 的工具列表"""
    client = _manager.get(server_id)
    if not client:
        raise HTTPException(status_code=400, detail="未连接到该 MCP Server，请先连接")
    tools = await client.list_tools()
    return {"tools": tools}


@router.post("/call-tool/{server_id}")
async def call_tool_direct(server_id: str, data: dict):
    """直接调用工具（不经过 LLM）"""
    client = _manager.get(server_id)
    if not client:
        raise HTTPException(status_code=400, detail="未连接到该 MCP Server，请先连接")

    tool_name = data.get("tool_name", "")
    arguments = data.get("arguments", {})
    if not tool_name:
        raise HTTPException(status_code=400, detail="tool_name 不能为空")

    try:
        result = await client.call_tool(tool_name, arguments)
        return {"tool_name": tool_name, "arguments": arguments, "result": tool_result_to_text(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"工具调用失败: {str(e)}")


async def _run_tool_loop(
    server_id: str,
    history: list,
    tools: list,
    system_prompt: Optional[str],
    tool_call_records: list,
    llm: LLMClient,
) -> dict:
    """
    执行 LLM + 工具调用循环。
    正常返回：{"content": ..., "tool_calls": [...]}
    需要确认：{"status": "confirm_required", ...}
    """
    client = _manager.get(server_id)

    for _ in range(5):
        response = await llm.chat(messages=history, tools=tools, system_prompt=system_prompt)

        if not response["tool_calls"]:
            history.append(_assistant_msg(response))
            _conversations[server_id] = history
            return {
                "content": response["content"],
                "reasoning_content": response.get("reasoning_content"),
                "tool_calls": tool_call_records,
            }

        # 有工具调用
        # 将 content、reasoning_content、tool_calls 合并到一条 assistant 消息中
        assistant_tool_msg: Dict[str, Any] = {
            "role": "assistant",
            "content": response["content"] or "",
            "reasoning_content": response.get("reasoning_content") or "",
            "tool_calls": [
                {"id": tc.get("id") or f"call_{i+1}", "type": "function",
                 "function": {"name": tc["name"], "arguments": str(tc["arguments"])}}
                for i, tc in enumerate(response["tool_calls"])
            ],
        }
        history.append(assistant_tool_msg)

        # 检查是否有高风险工具
        risky_tools = []
        for tc in response["tool_calls"]:
            if _is_risky_tool(tc["name"], tc["arguments"]):
                risky_tools.append(tc)

        if risky_tools:
            # 发现高风险工具，暂停执行，等待用户确认
            _pending_confirmations[server_id] = {
                "history": history,
                "tools": tools,
                "system_prompt": system_prompt,
                "tool_call_records": list(tool_call_records),
                "pending_tools": response["tool_calls"],
                "llm_content": response["content"] or "",
                "reasoning_content": response.get("reasoning_content") or "",
                "tool_call_message": assistant_tool_msg,
            }
            return {
                "status": "confirm_required",
                "content": response["content"] or "",
                "reasoning_content": response.get("reasoning_content"),
                "pending_tools": [
                    {"name": tc["name"], "arguments": tc["arguments"], "is_risky": _is_risky_tool(tc["name"], tc["arguments"])}
                    for tc in response["tool_calls"]
                ],
                "completed_tools": tool_call_records,
            }

        # 全部非高风险，直接执行
        for tc in response["tool_calls"]:
            tool_name = tc["name"]
            arguments = tc["arguments"]
            record = {"name": tool_name, "arguments": arguments, "result": ""}

            try:
                result = await client.call_tool(tool_name, arguments)
                result_text = tool_result_to_text(result)
                record["result"] = result_text
            except Exception as e:
                result_text = f"工具调用出错: {str(e)}"
                record["result"] = result_text
                record["error"] = True

            tool_call_records.append(record)

            history.append({
                "role": "tool",
                "tool_call_id": tc.get("id") or f"call_{len(tool_call_records)}",
                "content": result_text,
            })

    final_text = response.get("content", "") if response else ""
    _conversations[server_id] = history
    return {"content": final_text, "tool_calls": tool_call_records}


@router.post("/send/{server_id}")
async def send_chat_message(server_id: str, data: dict):
    """发送聊天消息（LLM 模式）"""
    client = _manager.get(server_id)
    if not client:
        raise HTTPException(status_code=400, detail="未连接到该 MCP Server，请先连接")
    if not config.has_llm:
        raise HTTPException(status_code=400, detail="LLM 未配置，请在 .env 文件中设置 LLM 配置")

    user_message = data.get("message", "").strip()
    system_prompt = data.get("system_prompt", "") or None
    if not user_message:
        raise HTTPException(status_code=400, detail="消息不能为空")

    tools = await client.list_tools()
    history = _conversations.get(server_id, [])
    history.append({"role": "user", "content": user_message})

    # 打印历史记录（调试用）
    import logging, json as _json
    logging.info(f"[Chat] server={server_id} history_len={len(history)}")
    for i, m in enumerate(history):
        keys = list(m.keys())
        has_reasoning = 'reasoning_content' in m
        tc_count = len(m.get('tool_calls', [])) if 'tool_calls' in m else 0
        logging.info(f"[History {i}] role={m.get('role')} keys={keys} has_reasoning={has_reasoning} tool_calls={tc_count}")

    llm = LLMClient(
        provider=config.LLM_PROVIDER,
        model=config.LLM_MODEL,
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_BASE_URL or None,
    )

    try:
        return await _run_tool_loop(server_id, history, tools, system_prompt, [], llm)
    except BaseException as e:
        if history and history[-1].get("role") == "user":
            history.pop()
        _conversations[server_id] = history
        err_type = type(e).__name__
        err_msg = str(e)
        if hasattr(e, "response"):
            err_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        raise HTTPException(status_code=500, detail=f"LLM 调用失败 [{err_type}]: {err_msg}")


@router.post("/confirm/{server_id}")
async def confirm_tool(server_id: str, data: dict):
    """
    用户确认/拒绝高风险工具调用。
    data: {"approved": true/false}
    """
    pending = _pending_confirmations.get(server_id)
    if not pending:
        raise HTTPException(status_code=400, detail="没有待确认的操作")

    approved = data.get("approved", False)
    client = _manager.get(server_id)
    if not client:
        raise HTTPException(status_code=400, detail="MCP Server 连接已断开")

    history = pending["history"]
    tools = pending["tools"]
    system_prompt = pending["system_prompt"]
    tool_call_records = list(pending["tool_call_records"])
    pending_tools = pending["pending_tools"]

    _pending_confirmations.pop(server_id, None)

    llm = LLMClient(
        provider=config.LLM_PROVIDER,
        model=config.LLM_MODEL,
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_BASE_URL or None,
    )

    try:
        if approved:
            # 执行所有待确认的工具
            for tc in pending_tools:
                tool_name = tc["name"]
                arguments = tc["arguments"]
                record = {"name": tool_name, "arguments": arguments, "result": ""}

                try:
                    result = await client.call_tool(tool_name, arguments)
                    result_text = tool_result_to_text(result)
                    record["result"] = result_text
                except Exception as e:
                    result_text = f"工具调用出错: {str(e)}"
                    record["result"] = result_text
                    record["error"] = True

                tool_call_records.append(record)

                # assistant tool_call 消息已在 pending 时加入 history，这里只加 tool 结果
                history.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id") or f"call_{len(tool_call_records)}",
                    "content": result_text,
                })

            # 继续 LLM 循环
            return await _run_tool_loop(server_id, history, tools, system_prompt, tool_call_records, llm)
        else:
            # 用户拒绝：告知 LLM 工具被拒绝
            reject_msg = "用户拒绝了该操作，不要执行此工具。请回复告知用户操作已取消。"
            for tc in pending_tools:
                tool_name = tc["name"]
                history.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id") or f"call_reject_{tool_name}",
                    "content": reject_msg,
                })

            # 让 LLM 生成拒绝后的回复
            response = await llm.chat(messages=history, tools=tools, system_prompt=system_prompt)
            history.append(_assistant_msg(response))
            _conversations[server_id] = history
            return {
                "content": response["content"] or "操作已取消。",
                "reasoning_content": response.get("reasoning_content"),
                "tool_calls": tool_call_records,
            }

    except BaseException as e:
        _conversations[server_id] = history
        err_type = type(e).__name__
        err_msg = str(e)
        if hasattr(e, "response"):
            err_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        raise HTTPException(status_code=500, detail=f"LLM 调用失败 [{err_type}]: {err_msg}")


@router.post("/clear/{server_id}")
def clear_conversation(server_id: str):
    """清空对话历史"""
    _conversations.pop(server_id, None)
    _pending_confirmations.pop(server_id, None)
    return {"message": "对话已清空"}
