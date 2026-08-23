"""LLM 客户端模块 - 支持 OpenAI 兼容 API 和 Anthropic API，带工具调用支持"""

import json
import re
import httpx
from typing import Optional, Dict, Any, List


def _safe_parse_arguments(args_str: str) -> Dict[str, Any]:
    """安全解析工具参数，兼容单引号、多余逗号等非标准 JSON"""
    if not args_str:
        return {}
    args_str = args_str.strip()
    # 标准 JSON
    try:
        return json.loads(args_str)
    except json.JSONDecodeError:
        pass
    # 把单引号包裹的键/值转成双引号（简单场景）
    try:
        fixed = re.sub(r"(?<!\\)'", '"', args_str)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    # Python 字面量
    try:
        import ast
        result = ast.literal_eval(args_str)
        if isinstance(result, dict):
            return result
    except Exception:
        pass
    # 实在解析不了，返回原始字符串
    return {"input": args_str}


class LLMClient:
    """LLM 客户端封装"""

    def __init__(self, provider: str, model: str, api_key: str, base_url: Optional[str] = None):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        发送消息并获取响应。

        Returns:
            {
                "content": "文本响应（如果有）",
                "tool_calls": [{"name": "...", "arguments": {...}}]  # 如果有工具调用
            }
        """
        if self.provider in ("openai", "deepseek"):
            return await self._chat_openai(messages, tools, system_prompt)
        elif self.provider == "anthropic":
            return await self._chat_anthropic(messages, tools, system_prompt)
        else:
            raise ValueError(f"不支持的 LLM 提供商: {self.provider}")

    # ---------- OpenAI / DeepSeek / 兼容 API ----------

    def _build_url(self, base_url: str, default: str, endpoint: str) -> str:
        """构建 API URL，兼容各种 base_url 格式"""
        base = (base_url or default).rstrip("/")
        # 如果 base_url 已包含完整端点路径，直接返回
        if endpoint in base:
            return base
        return f"{base}/{endpoint.lstrip('/')}"

    async def _chat_openai(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]],
        system_prompt: Optional[str],
    ) -> Dict[str, Any]:
        url = self._build_url(self.base_url, "https://api.openai.com/v1", "/chat/completions")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        data: Dict[str, Any] = {"model": self.model, "messages": full_messages}
        if tools:
            data["tools"] = self._format_tools_openai(tools)
            data["tool_choice"] = "auto"

        # 打印完整请求（调试用）
        import logging, json as _json
        logging.info(f"[LLM Request] model={self.model} msgs={len(full_messages)} tools={len(tools) if tools else 0}")
        # 打印每条消息的完整内容（截断长文本）
        for i, m in enumerate(full_messages):
            m_copy = {k: v for k, v in m.items()}
            if 'content' in m_copy and isinstance(m_copy['content'], str) and len(m_copy['content']) > 200:
                m_copy['content'] = m_copy['content'][:200] + '...'
            logging.info(f"[MSG {i}] {_json.dumps(m_copy, ensure_ascii=False, default=str)}")
        # 打印完整 data（不含大段 content）
        log_data = _json.dumps(data, ensure_ascii=False, default=str)
        if len(log_data) > 2000:
            log_data = log_data[:2000] + '...[truncated]'
        logging.info(f"[LLM Full Request] {log_data}")

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=data, timeout=120.0)
            if resp.status_code != 200:
                logging.error(f"[LLM Error] status={resp.status_code} body={resp.text[:500]}")
            resp.raise_for_status()
            result = resp.json()

        msg = result["choices"][0]["message"]
        response: Dict[str, Any] = {
            "content": msg.get("content") or "",
            "reasoning_content": msg.get("reasoning_content") or "",
            "tool_calls": [],
        }

        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                fn = tc["function"]
                response["tool_calls"].append({
                    "id": tc.get("id", ""),
                    "name": fn["name"],
                    "arguments": _safe_parse_arguments(fn.get("arguments", "")),
                })

        return response

    # ---------- Anthropic API ----------

    async def _chat_anthropic(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]],
        system_prompt: Optional[str],
    ) -> Dict[str, Any]:
        url = self._build_url(self.base_url, "https://api.anthropic.com/v1", "/messages")
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        data: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": 8192,
            "messages": messages,
        }
        if system_prompt:
            data["system"] = system_prompt
        if tools:
            data["tools"] = self._format_tools_anthropic(tools)

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json=data, timeout=120.0)
            resp.raise_for_status()
            result = resp.json()

        content = ""
        tool_calls = []

        for block in result.get("content", []):
            if block["type"] == "text":
                content += block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append({"name": block["name"], "arguments": block["input"]})

        return {"content": content, "tool_calls": tool_calls}

    # ---------- 工具格式化 ----------

    @staticmethod
    def _format_tools_openai(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {}),
                },
            }
            for t in tools
        ]

    @staticmethod
    def _format_tools_anthropic(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("input_schema", {}),
            }
            for t in tools
        ]


def tool_result_to_text(result: Any) -> str:
    """将 MCP tool call 结果转为文本"""
    if hasattr(result, "content") and result.content:
        parts = []
        for block in result.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts)
    return str(result)
