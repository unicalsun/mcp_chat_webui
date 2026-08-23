/**
 * 主应用入口 - 视图切换和初始化
 */
const App = {
    currentView: null,

    async init() {
        await this.loadStatus();
        this.showView('chat');
    },

    async loadStatus() {
        const el = document.getElementById('globalStatus');
        try {
            const status = await API.chatStatus();
            const parts = [];
            if (status.llm_configured) {
                parts.push(`LLM: ${status.llm_provider}/${status.llm_model}`);
            } else {
                parts.push('LLM: 未配置');
            }
            parts.push(`连接: ${status.connected_servers.length}`);
            el.innerHTML = parts.join('<br>');
        } catch {
            el.innerHTML = '<span class="error-text">无法获取状态</span>';
        }
    },

    showView(name) {
        // 更新导航高亮
        document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
        const navItems = document.querySelectorAll('.nav-item');
        navItems.forEach(el => {
            if ((name === 'chat' && el.textContent.includes('Chat')) ||
                (name === 'mcp-servers' && el.textContent.includes('MCP'))) {
                el.classList.add('active');
            }
        });

        // 渲染视图
        switch (name) {
            case 'chat': ChatView.render(); break;
            case 'mcp-servers': MCPServersView.render(); break;
        }
        this.currentView = name;
        this.loadStatus();
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());
