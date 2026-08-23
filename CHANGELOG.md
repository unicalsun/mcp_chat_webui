# CHANGELOG

## [1.2.0] - 2026-08-23

### 修复
- DeepSeek thinking 模式兼容：assistant 消息必须包含 `reasoning_content` 字段（空字符串也可），否则 API 返回400
- assistant 消息格式修复：tool_calls 响应中 content/reasoning_content/tool_calls 必须合并在一条消息，不可拆分
- tool_call_id 保留 LLM 返回的原始 ID，避免 assistant 消息与 tool 消息 ID 不匹配导致400
- tool_call arguments JSON 解析容错：支持单引号、Python 字面量等非标准格式
- MCP Server 连接测试：URL 自动补全 http:// 前缀；取消 exit_stack 清理异常掩盖原始错误；增加15秒超时
- `BaseException` 替代 `Exception` 捕获，防止 `CancelledError` 逃逸导致 uvicorn 崩溃

### 新增
- 高风险操作二次确认功能（SQL DML/DDL 自动检测）
- 确认对话框：显示待执行工具名和参数，用户确认/拒绝
- 聊天区域滚动：flex 布局 `min-height: 0` + `scroll-behavior: smooth`
- 自定义深色主题滚动条

## [1.1.0] - 2026-08-23

### 新增
- 高风险操作二次确认功能（SQL DML/DDL 自动检测）
- 确认对话框：显示待执行工具名和参数，支持确认/拒绝
- DeepSeek thinking 模式 `reasoning_content` 兼容

### 修复
- 聊天区域滚动问题（flex 布局 min-height: 0）
- MCP Server 连接测试超时和错误处理
- LLM API 调用错误的友好提示

## [1.0.0] - 2026-08-23

### 新增
- MCP Server 配置管理（JSON 文件持久化，支持 stdio / SSE / Streamable HTTP）
- MCP Server 连接测试功能
- 聊天调试界面，支持直接调用 `/call <工具名> <JSON参数>`
- LLM 聊天模式，自动调用 MCP 工具（需在 .env 配置 LLM）
- System Prompt 可折叠编辑
- 工具列表面板，点击工具名可快速插入调用命令
- 支持 OpenAI / DeepSeek / Anthropic 三种 LLM 提供商
- 深色主题 UI
- AJAX 视图切换，无页面刷新

### 架构
- MVC 分层架构，职责分离
- 后端：FastAPI + MCP Client SDK
- 前端：原生 HTML + JS，无框架依赖
- LLM 配置：仅通过 .env 文件，不在 UI 中暴露
- MCP Server 配置：JSON 文件，可在 UI 中管理
- 无数据库依赖，会话状态仅在内存中保持
