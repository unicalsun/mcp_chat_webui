"""应用配置模块 - 从 .env 加载 LLM 配置"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
ENV_PATH = Path(__file__).parent.parent / ".env"
load_dotenv(ENV_PATH)


class Config:
    """应用配置"""

    # LLM 配置（只读，来自 .env）
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")

    # MCP Server 配置文件路径
    MCP_SERVERS_CONFIG: str = os.getenv("MCP_SERVERS_CONFIG", "servers.json")

    @property
    def mcp_servers_config_path(self) -> Path:
        """获取 MCP Server 配置文件的绝对路径"""
        return Path(__file__).parent.parent / self.MCP_SERVERS_CONFIG

    @property
    def has_llm(self) -> bool:
        """是否已配置 LLM"""
        return bool(self.LLM_PROVIDER and self.LLM_API_KEY)


config = Config()
