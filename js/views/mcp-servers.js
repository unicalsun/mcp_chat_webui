/**
 * MCP Server 管理视图
 */
const MCPServersView = {
    render() {
        const container = document.getElementById('viewContainer');
        container.innerHTML = `
            <div class="view-header">
                <h2>MCP Server 管理</h2>
                <button class="btn btn-primary" onclick="MCPServersView.showAddDialog()">+ 添加 Server</button>
            </div>
            <div id="serversList" class="servers-list">
                <div class="empty-hint">加载中...</div>
            </div>
        `;
        this.loadServers();
    },

    async loadServers() {
        const el = document.getElementById('serversList');
        try {
            const result = await API.listServers();
            if (result.items.length === 0) {
                el.innerHTML = `<div class="empty-hint">暂无 MCP Server 配置。点击右上角添加。</div>`;
                return;
            }
            el.innerHTML = result.items.map(s => `
                <div class="server-card">
                    <div class="server-card-row">
                        <div>
                            <span class="server-name">${escapeHtml(s.name)}</span>
                            <span class="tag">${s.server_type}</span>
                        </div>
                        <div class="server-actions">
                            <button class="btn btn-sm" onclick="MCPServersView.testServer('${s.server_id}')">测试</button>
                            <button class="btn btn-sm" onclick="MCPServersView.showEditDialog('${s.server_id}')">编辑</button>
                            <button class="btn btn-sm btn-danger" onclick="MCPServersView.deleteServer('${s.server_id}')">删除</button>
                        </div>
                    </div>
                    <div class="server-desc">${escapeHtml(s.description || '无描述')}</div>
                    <div class="server-config"><pre>${escapeHtml(formatJson(s.transport_config))}</pre></div>
                </div>
            `).join('');
        } catch (e) {
            el.innerHTML = `<div class="error-text">加载失败: ${escapeHtml(e.message)}</div>`;
        }
    },

    showAddDialog() {
        this._showDialog('添加 MCP Server', null, async (data) => {
            await API.createServer(data);
        });
    },

    async showEditDialog(serverId) {
        const server = await API.getServer(serverId);
        this._showDialog('编辑 MCP Server', server, async (data) => {
            await API.updateServer(serverId, data);
        });
    },

    _showDialog(title, existing, onSubmit) {
        const isEdit = !!existing;
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h3>${title}</h3>
                    <button class="btn" onclick="this.closest('.modal-overlay').remove()">X</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>名称</label>
                        <input type="text" id="dlgName" class="form-input" value="${escapeHtml(existing?.name || '')}" placeholder="MCP Server 名称">
                    </div>
                    <div class="form-group">
                        <label>描述</label>
                        <input type="text" id="dlgDesc" class="form-input" value="${escapeHtml(existing?.description || '')}" placeholder="可选">
                    </div>
                    <div class="form-group">
                        <label>传输类型</label>
                        <select id="dlgType" class="form-select" onchange="MCPServersView._updateTemplate()">
                            <option value="stdio" ${existing?.server_type === 'stdio' ? 'selected' : ''}>stdio</option>
                            <option value="sse" ${existing?.server_type === 'sse' ? 'selected' : ''}>SSE</option>
                            <option value="streamable-http" ${existing?.server_type === 'streamable-http' ? 'selected' : ''}>Streamable HTTP</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>传输配置 (JSON)</label>
                        <textarea id="dlgConfig" class="form-input code-input" rows="8">${escapeHtml(existing ? formatJson(existing.transport_config) : '')}</textarea>
                    </div>
                    <div class="help-text" id="dlgHelp"></div>
                </div>
                <div class="modal-footer">
                    <button class="btn" onclick="this.closest('.modal-overlay').remove()">取消</button>
                    <button class="btn btn-primary" id="dlgSubmit">${isEdit ? '保存' : '添加'}</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        // 填充默认模板（如果没有 existing）
        if (!isEdit) this._updateTemplate();

        overlay.querySelector('#dlgSubmit').onclick = async () => {
            const name = overlay.querySelector('#dlgName').value.trim();
            const description = overlay.querySelector('#dlgDesc').value.trim();
            const serverType = overlay.querySelector('#dlgType').value;
            const configStr = overlay.querySelector('#dlgConfig').value.trim();

            if (!name) { alert('请输入名称'); return; }
            let transportConfig;
            try {
                transportConfig = JSON.parse(configStr);
            } catch (e) {
                alert('JSON 格式错误: ' + e.message);
                return;
            }
            try {
                await onSubmit({ name, description, server_type: serverType, transport_config: transportConfig });
                overlay.remove();
                this.loadServers();
            } catch (e) {
                alert('操作失败: ' + e.message);
            }
        };
    },

    _updateTemplate() {
        const type = document.getElementById('dlgType').value;
        const configEl = document.getElementById('dlgConfig');
        const helpEl = document.getElementById('dlgHelp');
        const templates = {
            'stdio': { command: 'python', args: ['-m', 'my_mcp_server'], env: {} },
            'sse': { url: 'http://localhost:8000/sse', headers: {} },
            'streamable-http': { url: 'http://localhost:8000/mcp', headers: {} },
        };
        // 自动填充对应类型的模板
        configEl.value = formatJson(templates[type]);
        const helps = {
            'stdio': 'command: 可执行文件路径；args: 命令行参数；env: 环境变量',
            'sse': 'url: SSE 端点地址；headers: 自定义请求头',
            'streamable-http': 'url: HTTP 端点地址；headers: 自定义请求头',
        };
        helpEl.textContent = helps[type] || '';
    },

    async deleteServer(serverId) {
        if (!confirm('确定删除？')) return;
        try {
            await API.deleteServer(serverId);
            this.loadServers();
        } catch (e) {
            alert('删除失败: ' + e.message);
        }
    },

    async testServer(serverId) {
        try {
            const result = await API.testServer(serverId);
            alert(`连接成功！工具数: ${result.tools_count}\n工具列表: ${result.tools.join(', ')}`);
        } catch (e) {
            alert('连接测试失败: ' + e.message);
        }
    },
};
