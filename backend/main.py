"""FastAPI 主应用入口"""

import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import config
from backend.mcp_client import MCPClientManager, MCPServerStore
from backend.routers import mcp_servers, chat

# 初始化存储和连接管理器
server_store = MCPServerStore(config.mcp_servers_config_path)
client_manager = MCPClientManager()

# 注入依赖到路由模块
mcp_servers.init(server_store, client_manager)
chat.init(server_store, client_manager)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await client_manager.disconnect_all()


app = FastAPI(
    title="MCP Debug WebUI",
    description="MCP Server 调试工具 - 聊天界面",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(mcp_servers.router)
app.include_router(chat.router)


@app.get("/")
def root():
    return FileResponse(str(PROJECT_ROOT / "index.html"))


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 挂载静态文件
app.mount("/css", StaticFiles(directory=str(PROJECT_ROOT / "css")), name="css")
app.mount("/js", StaticFiles(directory=str(PROJECT_ROOT / "js")), name="js")


if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="MCP Debug WebUI Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    print(f"Starting server at http://{args.host}:{args.port}")
    print(f"API docs at http://{args.host}:{args.port}/docs")
    uvicorn.run(app, host=args.host, port=args.port)
