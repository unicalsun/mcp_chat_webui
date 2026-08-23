
# 项目已创建完成，所有文件通过导入测试。

---

# 项目结构
```
webui_no_store/
├── .env                       # LLM 配置（修改此处）
├── index.html                 # 主页面
├── css/style.css              # 样式（深色
├── js/
│   ├── api.js                 # API 封装层
│   ├── utils.js               # 工具函数
│   ├── app.js                 # 入口，视图切换
│   └── views/
│       ├── chat.js            # 聊天调试视图
│       └── mcp-servers.js     # MCP Server 管理视图
├── backend/
│   ├── config.py              # 从 .env 加
│   ├── mcp_client.py          # MCP 连接管理 + JSON 持久化
│   ├── llm_client.py          # LLM 客户端（支持 tool_call）
│   ├── main.py                # FastAPI 入
│   └── routers/
│       ├── mcp_servers.py     # MCP Server CRUD
│       └── chat.py            # 聊天 + 工具调用 API
├── CHANGELOG.md
└── AGENTS.md
```

# 启动方式

```
cd C:\oc_workspace\deepagents\webui_no_store
python -m backend.main --port 9000

访问 http://localhost:9000
```
# 使用前必改

## 编辑 .env，填入真实 LLM 配置：
- LLM_API_KEY - 替换为真实 key
- LLM_PROVIDER / LLM_MODEL / LLM_BASE_URL - 按需调整

## 聊天模式

- LLM 模式：连接 MCP Server 后直接发送自然语
- 直接调用：输入 /call 工具名 {"参数": "值"} 直接调用 MCP 工具（无需 LLM）


