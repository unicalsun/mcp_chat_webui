/**
 * Chat 视图 - MCP 调试聊天界面
 */
const ChatView = {
    currentServerId: null,
    connected: false,
    tools: [],
    messages: [],

    render() {
        const container = document.getElementById('viewContainer');
        container.innerHTML = `
            <div class="chat-layout">
                <div class="chat-toolbar">
                    <div class="toolbar-left">
                        <select id="chatServerSelect" class="form-select" onchange="ChatView.onServerChange()">
                            <option value="">-- 选择 MCP Server --</option>
                        </select>
                        <button id="btnConnect" class="btn btn-sm" onclick="ChatView.toggleConnect()">连接</button>
                        <span id="connStatus" class="tag tag-gray">未连接</span>
                    </div>
                    <div class="toolbar-right">
                        <button class="btn btn-sm" onclick="ChatView.clearMessages()">清空对话</button>
                    </div>
                </div>

                <div class="chat-main">
                    <div class="chat-messages" id="chatMessages">
                        <div class="empty-hint">选择一个 MCP Server 并连接，开始聊天调试。</div>
                    </div>
                    <div class="chat-tools-panel" id="toolsPanel" style="display:none;">
                        <div class="panel-header">Tools</div>
                        <div id="toolsList"></div>
                    </div>
                </div>

                <div class="chat-input-area">
                    <div class="chat-system-prompt">
                        <div class="system-prompt-toggle" onclick="ChatView.toggleSystemPrompt()">
                            System Prompt <span id="spArrow">&#9654;</span>
                        </div>
                        <div class="system-prompt-body" id="systemPromptBody" style="display:none;">
                            <textarea id="systemPromptInput" rows="3" placeholder="如果是增删改查、DDL、truncate等对库表结构做改动的sql，不允许自己执行sql,均需要向用户确认。"></textarea>
                        </div>
                    </div>
                    <div class="chat-input-row">
                        <textarea id="chatInput" placeholder="输入消息... (Shift+Enter 换行)" rows="2"></textarea>
                        <button id="btnSend" class="btn btn-primary" onclick="ChatView.sendMessage()">发送</button>
                    </div>
                </div>
            </div>
        `;
        this.loadServerList();
        this.bindKeys();
    },

    bindKeys() {
        const input = document.getElementById('chatInput');
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
    },

    async loadServerList() {
        try {
            const result = await API.listServers();
            const select = document.getElementById('chatServerSelect');
            select.innerHTML = '<option value="">-- 选择 MCP Server --</option>';
            result.items.forEach(s => {
                select.innerHTML += `<option value="${s.server_id}">${escapeHtml(s.name)} (${s.server_type})</option>`;
            });
        } catch (e) {
            console.error('加载 MCP Server 列表失败:', e);
        }
    },

    async onServerChange() {
        const serverId = document.getElementById('chatServerSelect').value;
        if (!serverId) {
            this.currentServerId = null;
            this.connected = false;
            this.updateStatusUI();
            this.showEmptyHint();
            return;
        }
        this.currentServerId = serverId;
        // 检查是否已连接
        try {
            const status = await API.chatStatus();
            this.connected = status.connected_servers.includes(serverId);
            if (this.connected) {
                const toolsResult = await API.getTools(serverId);
                this.tools = toolsResult.tools || [];
            } else {
                this.tools = [];
            }
        } catch {
            this.connected = false;
            this.tools = [];
        }
        this.updateStatusUI();
        this.updateToolsPanel();
    },

    showEmptyHint() {
        document.getElementById('chatMessages').innerHTML =
            '<div class="empty-hint">选择一个 MCP Server 并连接，开始聊天调试。</div>';
        document.getElementById('toolsPanel').style.display = 'none';
    },

    updateStatusUI() {
        const statusEl = document.getElementById('connStatus');
        const btn = document.getElementById('btnConnect');
        if (this.connected) {
            statusEl.className = 'tag tag-green';
            statusEl.textContent = '已连接';
            btn.textContent = '断开';
            btn.className = 'btn btn-sm btn-danger';
        } else {
            statusEl.className = 'tag tag-gray';
            statusEl.textContent = '未连接';
            btn.textContent = '连接';
            btn.className = 'btn btn-sm';
        }
    },

    updateToolsPanel() {
        const panel = document.getElementById('toolsPanel');
        const list = document.getElementById('toolsList');
        if (!this.connected || this.tools.length === 0) {
            panel.style.display = 'none';
            return;
        }
        panel.style.display = '';
        list.innerHTML = this.tools.map(t => `
            <div class="tool-item">
                <div class="tool-name" onclick="ChatView.insertToolCall('${escapeHtml(t.name)}')" title="点击插入调用">${escapeHtml(t.name)}</div>
                <div class="tool-desc">${escapeHtml(t.description || '')}</div>
            </div>
        `).join('');
    },

    insertToolCall(name) {
        const input = document.getElementById('chatInput');
        input.value = `/call ${name} `;
        input.focus();
    },

    async toggleConnect() {
        if (!this.currentServerId) return;
        const btn = document.getElementById('btnConnect');
        btn.disabled = true;
        try {
            if (this.connected) {
                await API.disconnect(this.currentServerId);
                this.connected = false;
                this.tools = [];
            } else {
                const result = await API.connect(this.currentServerId);
                this.connected = true;
                this.tools = result.tools || [];
                this.addMessage('system', `已连接。可用工具 ${this.tools.length} 个。`);
            }
        } catch (e) {
            this.addMessage('error', `连接失败: ${e.message}`);
        }
        this.updateStatusUI();
        this.updateToolsPanel();
        btn.disabled = false;
    },

    toggleSystemPrompt() {
        const body = document.getElementById('systemPromptBody');
        const arrow = document.getElementById('spArrow');
        if (body.style.display === 'none') {
            body.style.display = '';
            arrow.innerHTML = '&#9660;';
        } else {
            body.style.display = 'none';
            arrow.innerHTML = '&#9654;';
        }
    },

    async sendMessage() {
        if (!this.currentServerId) {
            alert('请先选择 MCP Server');
            return;
        }
        const input = document.getElementById('chatInput');
        const content = input.value.trim();
        if (!content) return;
        input.value = '';

        this.addMessage('user', content);
        const btnSend = document.getElementById('btnSend');
        btnSend.disabled = true;

        try {
            if (content.startsWith('/call ')) {
                // 直接调用工具模式
                await this.handleDirectToolCall(content);
            } else if (this.connected && this.tools.length > 0) {
                // LLM 模式
                await this.handleLLMChat(content);
            } else {
                // 没有连接，无法处理
                this.addMessage('system', '请先连接 MCP Server，或使用 /call <工具名> 直接调用工具。');
            }
        } catch (e) {
            this.addMessage('error', `发送失败: ${e.message}`);
        }
        btnSend.disabled = false;
        input.focus();
    },

    async handleDirectToolCall(content) {
        const parts = content.slice(6).trim().split(/\s+/);
        const toolName = parts[0];
        let args = {};
        if (parts.length > 1) {
            try {
                args = JSON.parse(parts.slice(1).join(' '));
            } catch {
                args = { input: parts.slice(1).join(' ') };
            }
        }
        this.addMessage('tool-call', `调用 ${toolName}`, { name: toolName, arguments: args });

        const result = await API.callTool(this.currentServerId, { tool_name: toolName, arguments: args });
        if (result.error) {
            this.addMessage('error', result.result);
        } else {
            this.addMessage('tool-result', result.result, { name: toolName });
        }
    },

    async handleLLMChat(content) {
        const sysPrompt = document.getElementById('systemPromptInput')?.value || '';
        this.addMessage('loading', 'LLM 思考中...');

        const result = await API.sendChat(this.currentServerId, {
            message: content,
            system_prompt: sysPrompt,
        });

        // 移除 loading
        this.removeLastLoading();

        // 需要用户确认高风险操作
        if (result.status === 'confirm_required') {
            // 显示已完成的工具调用（如果有）
            if (result.completed_tools && result.completed_tools.length > 0) {
                for (const tc of result.completed_tools) {
                    this.addMessage('tool-call', `调用 ${tc.name}`, tc);
                    this.addMessage('tool-result', tc.result, { name: tc.name, error: tc.error });
                }
            }
            // 显示 LLM 文本说明
            if (result.content) {
                this.addMessage('assistant', result.content, result.reasoning_content ? { reasoning: result.reasoning_content } : null);
            }
            // 弹出确认框
            this.showConfirmDialog(result.pending_tools);
            return;
        }

        // 显示工具调用记录
        if (result.tool_calls && result.tool_calls.length > 0) {
            for (const tc of result.tool_calls) {
                this.addMessage('tool-call', `调用 ${tc.name}`, tc);
                this.addMessage('tool-result', tc.result, { name: tc.name, error: tc.error });
            }
        }

        // 显示最终回复（含 reasoning_content）
        if (result.content) {
            this.addMessage('assistant', result.content, result.reasoning_content ? { reasoning: result.reasoning_content } : null);
        } else if (result.tool_calls && result.tool_calls.length > 0) {
            this.addMessage('assistant', '(工具已执行，LLM 未返回文本回复)');
        }
    },

    /**
     * 显示高风险操作确认对话框
     */
    showConfirmDialog(pendingTools) {
        const container = document.getElementById('chatMessages');
        const div = document.createElement('div');
        div.className = 'confirm-dialog';
        div.id = 'confirmDialog';

        const toolsHtml = pendingTools.map(tc => `
            <div class="confirm-tool-item">
                <div class="confirm-tool-name">${tc.is_risky ? '⚠️ ' : ''}${escapeHtml(tc.name)}</div>
                <pre class="code-block">${escapeHtml(formatJson(tc.arguments))}</pre>
            </div>
        `).join('');

        div.innerHTML = `
            <div class="confirm-header">⚠️ 需要确认高风险操作</div>
            <div class="confirm-tools">${toolsHtml}</div>
            <div class="confirm-actions">
                <button class="btn btn-danger" onclick="ChatView.confirmTool(false)">拒绝</button>
                <button class="btn btn-primary" onclick="ChatView.confirmTool(true)">确认执行</button>
            </div>
        `;

        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    },

    /**
     * 发送确认/拒绝结果
     */
    async confirmTool(approved) {
        const dialog = document.getElementById('confirmDialog');
        if (dialog) dialog.remove();

        const btnSend = document.getElementById('btnSend');
        btnSend.disabled = true;

        try {
            this.addMessage('loading', approved ? '执行中...' : '处理中...');
            const result = await API.confirmTool(this.currentServerId, { approved });
            this.removeLastLoading();

            // 显示工具调用记录
            if (result.tool_calls && result.tool_calls.length > 0) {
                for (const tc of result.tool_calls) {
                    this.addMessage('tool-call', `调用 ${tc.name}`, tc);
                    this.addMessage('tool-result', tc.result, { name: tc.name, error: tc.error });
                }
            }

            if (result.content) {
                this.addMessage('assistant', result.content, result.reasoning_content ? { reasoning: result.reasoning_content } : null);
            } else if (approved) {
                this.addMessage('assistant', '(工具已执行)');
            } else {
                this.addMessage('assistant', '操作已取消。');
            }
        } catch (e) {
            this.removeLastLoading();
            this.addMessage('error', `确认操作失败: ${e.message}`);
        }
        btnSend.disabled = false;
    },

    addMessage(type, content, meta = null) {
        const container = document.getElementById('chatMessages');
        const emptyHint = container.querySelector('.empty-hint');
        if (emptyHint) emptyHint.remove();

        const div = document.createElement('div');
        div.className = `msg msg-${type}`;

        if (type === 'user') {
            div.innerHTML = `<div class="msg-role">You</div><div class="msg-body">${escapeHtml(content)}</div>`;
        } else if (type === 'assistant') {
            let bodyHtml = '';
            if (meta?.reasoning) {
                bodyHtml += `<details class="reasoning-block"><summary>Thinking</summary><pre class="code-block">${escapeHtml(meta.reasoning)}</pre></details>`;
            }
            bodyHtml += escapeHtml(content);
            div.innerHTML = `<div class="msg-role">Assistant</div><div class="msg-body">${bodyHtml}</div>`;
        } else if (type === 'system') {
            div.innerHTML = `<div class="msg-role">System</div><div class="msg-body">${escapeHtml(content)}</div>`;
        } else if (type === 'error') {
            div.innerHTML = `<div class="msg-role">Error</div><div class="msg-body error-text">${escapeHtml(content)}</div>`;
        } else if (type === 'tool-call') {
            const argsStr = meta ? formatJson(meta.arguments || {}) : '';
            div.innerHTML = `<div class="msg-role">Tool Call</div>
                <div class="msg-body">
                    <code>${escapeHtml(meta?.name || '')}</code>
                    <pre class="code-block">${escapeHtml(argsStr)}</pre>
                </div>`;
        } else if (type === 'tool-result') {
            div.innerHTML = `<div class="msg-role">Tool Result: ${escapeHtml(meta?.name || '')}</div>
                <div class="msg-body"><pre class="code-block">${escapeHtml(content)}</pre></div>`;
        } else if (type === 'loading') {
            div.classList.add('msg-loading');
            div.innerHTML = `<div class="msg-body"><span class="spinner"></span> ${escapeHtml(content)}</div>`;
        }

        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    },

    removeLastLoading() {
        const container = document.getElementById('chatMessages');
        const loading = container.querySelector('.msg-loading');
        if (loading) loading.remove();
    },

    async clearMessages() {
        if (!this.currentServerId) return;
        try {
            await API.clearChat(this.currentServerId);
        } catch { /* 忽略 */ }
        document.getElementById('chatMessages').innerHTML =
            '<div class="empty-hint">对话已清空。</div>';
    },
};
