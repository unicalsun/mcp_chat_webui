/**
 * API 封装层
 */
const API = {
    async request(url, options = {}) {
        const resp = await fetch(url, {
            headers: { 'Content-Type': 'application/json', ...options.headers },
            ...options,
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `请求失败: ${resp.status}`);
        }
        return resp.json();
    },

    // MCP Server
    listServers: (search) => API.request(`/api/mcp-servers${search ? '?search=' + encodeURIComponent(search) : ''}`),
    getServer: (id) => API.request(`/api/mcp-servers/${id}`),
    createServer: (data) => API.request('/api/mcp-servers', { method: 'POST', body: JSON.stringify(data) }),
    updateServer: (id, data) => API.request(`/api/mcp-servers/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteServer: (id) => API.request(`/api/mcp-servers/${id}`, { method: 'DELETE' }),
    testServer: (id) => API.request(`/api/mcp-servers/${id}/test`, { method: 'POST' }),

    // Chat
    chatStatus: () => API.request('/api/chat/status'),
    connect: (serverId) => API.request(`/api/chat/connect/${serverId}`, { method: 'POST' }),
    disconnect: (serverId) => API.request(`/api/chat/disconnect/${serverId}`, { method: 'POST' }),
    getTools: (serverId) => API.request(`/api/chat/tools/${serverId}`),
    callTool: (serverId, data) => API.request(`/api/chat/call-tool/${serverId}`, { method: 'POST', body: JSON.stringify(data) }),
    sendChat: (serverId, data) => API.request(`/api/chat/send/${serverId}`, { method: 'POST', body: JSON.stringify(data) }),
    confirmTool: (serverId, data) => API.request(`/api/chat/confirm/${serverId}`, { method: 'POST', body: JSON.stringify(data) }),
    clearChat: (serverId) => API.request(`/api/chat/clear/${serverId}`, { method: 'POST' }),
};
