# readme.md

## 项目概述

MCP Debug WebUI - 用于调试 MCP Server 的聊天界面工具，支持自然语言对话调用 MCP 工具（NL2SQL），带高风险操作二次确认。

## 技术栈

- **后端**: Python FastAPI + mcp SDK（mcp 1.28.1）
- **前端**: 原生 HTML + JavaScript + CSS（无框架依赖）
- **ORM**: 无数据库，使用 JSON 文件存储 MCP 配置
- **LLM 支持**: OpenAI / DeepSeek / Anthropic（在 .env 配置）

```commandline

python3 -m pip install fastapi mcp dotenv httpx --break-system-packages --ignore-installed


```

## 架构

### 目录结构
```
backend/
├── config.py           # 应用配置（从 .env 加载）
├── mcp_client.py       # MCP 客户端管理 + servers.json 持久化
├── llm_client.py       # LLM 客户端封装 + 安全 JSON 解析
├── main.py             # FastAPI 入口，路由注册，lifespan 清理
└── routers/
    ├── mcp_servers.py  # MCP Server CRUD + 连接测试 API
    └── chat.py         # 聊天 + 工具调用 + 高风险确认 API
frontend/
├── index.html          # 主页面（SPA）
├── css/style.css       # 深色主题样式
└── js/
    ├── api.js          # AJAX 封装层
    ├── utils.js        # 工具函数
    ├── app.js          # 视图切换入口
    └── views/
        ├── chat.js     # 聊天界面（含确认对话框）
        └── mcp-servers.js  # MCP Server 管理界面
.env                   # LLM 配置（敏感信息，gitignore）
servers.json           # MCP Server 配置（JSON 持久化）
```

### 关键设计决策

1. **无持久化会话**：会话状态仅在内存中保持（`_conversations` 字典），重启即清空
2. **MCP 配置文件**：`servers.json` 存储 MCP Server 配置，通过 UI 管理
3. **LLM 配置**：仅通过 `.env` 文件，不在 UI 中暴露
4. **高风险操作确认**：后端检测 SQL DML/DDL 关键词，返回 `confirm_required` 状态，前端弹出确认框，用户确认后继续执行

## 核心 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/chat/connect/{id}` | 连接 MCP Server |
| POST | `/api/chat/send/{id}` | 发送聊天消息（可能返回 `confirm_required`）|
| POST | `/api/chat/confirm/{id}` | 确认/拒绝高风险工具执行 |
| POST | `/api/chat/call-tool/{id}` | 直接调用工具（不经过 LLM）|
| GET | `/api/mcp-servers` | 列出 MCP Server 配置 |
| POST | `/api/mcp-servers` | 添加 MCP Server |
| POST | `/api/mcp-servers/{id}/test` | 测试 MCP Server 连接（15秒超时）|

## DeepSeek Thinking 模式兼容要点

与 DeepSeek thinking 模式（`deepseek-v4-flash` 等）交互时的关键约束：

1. **`reasoning_content` 字段**：API 返回的 assistant 消息可能包含此字段，下一次请求时历史 assistant 消息**必须**保留该字段（可以为空字符串），否则返回400
2. **单条 assistant 消息**：当响应同时包含 `content`、`reasoning_content`、`tool_calls` 时，三者必须在**同一条 assistant 消息**中，不可拆分
3. **`tool_call_id` 一致性**：tool 结果消息的 `tool_call_id` 必须与 assistant 消息中 `tool_calls` 的 `id` 精确匹配
4. **`content` 不可为 null**：assistant 消息的 `content` 字段使用空字符串 `""`，不要用 `None`

## 注意事项

- `BaseException` 捕获：DeepSeek 异步操作中 `CancelledError` 继承自 `BaseException`，用 `except Exception` 捕获不到会导致 uvicorn 崩溃
- MCP URL 格式：用户配置的 URL 可能缺少 `http://` 前缀，连接前自动补全
- 工具参数解析：LLM 返回的 arguments 可能不是标准 JSON，需多策略容错解析
