// ==================== 全局状态 ====================

let currentTopicId = null;
let pendingImages = [];
let topics = [];
let messages = {};
let agents = [];
let selectedAgent = null;
let eventSource = null;
let apiBaseUrl = localStorage.getItem('apiBaseUrl') || window.location.origin;

// ==================== 初始化 ====================

document.addEventListener('DOMContentLoaded', async () => {
    initializeServerConnection();
    loadFromStorage();
    if (topics.length === 0) {
        createNewTopic('默认对话');
    } else {
        selectTopic(topics[0].id);
    }
    renderTopicsList();
    renderMessages();
    
    // 加载 agents
    await loadAgents();
    
    // 启动 SSE 监听
    startSSE();
});

function normalizeBaseUrl(value) {
    if (!value || !value.trim()) return window.location.origin;
    return value.trim().replace(/\/+$/, '');
}

function buildApiUrl(path) {
    const normalizedPath = path.startsWith('/') ? path : `/${path}`;
    return `${apiBaseUrl}${normalizedPath}`;
}

async function apiFetch(path, options) {
    return fetch(buildApiUrl(path), options);
}

function initializeServerConnection() {
    apiBaseUrl = normalizeBaseUrl(localStorage.getItem('apiBaseUrl') || window.location.origin);
    const input = document.getElementById('serverUrlInput');
    if (input) {
        input.value = apiBaseUrl;
    }
    updateServerStatus('未连接', '');
}

function updateServerStatus(text, type = '') {
    const status = document.getElementById('serverStatus');
    if (!status) return;
    status.textContent = text;
    status.className = `server-status ${type}`.trim();
}

async function connectServer() {
    const input = document.getElementById('serverUrlInput');
    if (!input) return;
    
    apiBaseUrl = normalizeBaseUrl(input.value);
    localStorage.setItem('apiBaseUrl', apiBaseUrl);
    updateServerStatus('连接中...', '');
    
    try {
        const response = await apiFetch('/api/agents');
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        updateServerStatus('已连接', 'connected');
        await loadAgents();
        startSSE();
    } catch (error) {
        console.error('连接服务器失败:', error);
        updateServerStatus('连接失败', 'error');
        alert(`连接失败，请检查服务地址或服务是否启动。\n当前地址: ${apiBaseUrl}`);
    }
}

// ==================== Agent 管理 ====================

async function loadAgents() {
    try {
        const response = await apiFetch('/api/agents');
        const data = await response.json();
        agents = data.agents || [];
        renderAgentsList();
        updateServerStatus('已连接', 'connected');
        
        // 如果有选中的 agent，更新详情面板
        if (selectedAgent) {
            const updatedAgent = agents.find(a => a.id === selectedAgent.id);
            if (updatedAgent) {
                await showAgentDetail(updatedAgent.id);
            }
        }
    } catch (error) {
        console.error('加载 agents 失败:', error);
        updateServerStatus('连接失败', 'error');
    }
}

function renderAgentsList() {
    const agentsList = document.getElementById('agentsList');
    if (!agentsList) return;

    if (agents.length === 0) {
        agentsList.innerHTML = '<div class="empty-state"><p>暂无 Agent</p></div>';
        return;
    }

    agentsList.innerHTML = agents.map(agent => `
        <div class="agent-item ${selectedAgent && selectedAgent.id === agent.id ? 'active' : ''}" 
             onclick="showAgentDetail('${agent.id}')">
            <div class="agent-status-dot ${agent.status}"></div>
            <div class="agent-info">
                <div class="agent-name">${escapeHtml(agent.name)}</div>
                <div class="agent-status-text">${getStatusText(agent.status)}</div>
            </div>
        </div>
    `).join('');
}

function getStatusText(status) {
    const statusMap = {
        'idle': '空闲',
        'running': '运行中',
        'completed': '已完成',
        'error': '错误'
    };
    return statusMap[status] || status;
}

async function showAgentDetail(agentId) {
    try {
        const response = await apiFetch(`/api/agents/${agentId}`);
        const agent = await response.json();
        
        selectedAgent = agent;
        renderAgentsList(); // 更新选中状态
        
        // 显示详情面板
        const panel = document.getElementById('agentDetailPanel');
        panel.classList.add('visible');
        
        // 更新详情
        document.getElementById('agentDetailName').textContent = agent.name;
        
        const statusBadge = document.getElementById('agentDetailStatus');
        statusBadge.textContent = getStatusText(agent.status);
        statusBadge.className = `status-badge ${agent.status}`;
        
        document.getElementById('agentDetailTask').textContent = agent.current_task || '--';
        
        // 渲染日志
        const logsContainer = document.getElementById('agentLogs');
        if (agent.logs && agent.logs.length > 0) {
            logsContainer.innerHTML = agent.logs.map(log => `
                <div class="log-entry">
                    <span class="log-time">${log.time}</span>
                    <span class="log-message">${escapeHtml(log.message)}</span>
                </div>
            `).join('');
            logsContainer.scrollTop = logsContainer.scrollHeight;
        } else {
            logsContainer.innerHTML = '<div class="log-entry"><span class="log-message" style="color: #666;">暂无日志</span></div>';
        }
        
        // 更新按钮状态
        const btnRun = document.getElementById('btnRunAgent');
        const btnStop = document.getElementById('btnStopAgent');
        
        if (agent.status === 'running') {
            btnRun.disabled = true;
            btnStop.disabled = false;
        } else {
            btnRun.disabled = false;
            btnStop.disabled = true;
        }
        
    } catch (error) {
        console.error('获取 agent 详情失败:', error);
    }
}

function closeAgentDetail() {
    const panel = document.getElementById('agentDetailPanel');
    panel.classList.remove('visible');
    selectedAgent = null;
    renderAgentsList();
}

function showRunAgentDialog() {
    if (!selectedAgent || selectedAgent.status === 'running') return;
    
    const dialog = document.getElementById('runTaskDialog');
    dialog.style.display = 'flex';
    document.getElementById('taskInput').focus();
}

async function runAgentWithTask() {
    if (!selectedAgent) return;
    
    const taskInput = document.getElementById('taskInput');
    const task = taskInput.value.trim();
    
    if (!task) {
        alert('请输入任务描述');
        return;
    }
    
    try {
        const response = await apiFetch(`/api/agents/${selectedAgent.id}/run`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ task })
        });
        
        if (response.ok) {
            // 隐藏对话框
            document.getElementById('runTaskDialog').style.display = 'none';
            taskInput.value = '';
            
            // 刷新详情
            await showAgentDetail(selectedAgent.id);
            await loadAgents();
        }
    } catch (error) {
        console.error('启动 agent 失败:', error);
        alert('启动失败，请重试');
    }
}

async function stopCurrentAgent() {
    if (!selectedAgent || selectedAgent.status !== 'running') return;
    
    try {
        const response = await apiFetch(`/api/agents/${selectedAgent.id}/stop`, {
            method: 'POST'
        });
        
        if (response.ok) {
            // 刷新详情
            await showAgentDetail(selectedAgent.id);
            await loadAgents();
        }
    } catch (error) {
        console.error('停止 agent 失败:', error);
    }
}

// ==================== SSE 实时更新 ====================

function startSSE() {
    if (eventSource) {
        eventSource.close();
    }
    
    eventSource = new EventSource(buildApiUrl('/api/events'));
    
    eventSource.onmessage = async (event) => {
        try {
            const data = JSON.parse(event.data);
            
            // 更新 agents 列表
            if (data.agents) {
                agents = data.agents;
                renderAgentsList();
                
                // 如果有选中的 agent，更新详情
                if (selectedAgent) {
                    const updatedAgent = agents.find(a => a.id === selectedAgent.id);
                    if (updatedAgent) {
                        await showAgentDetail(selectedAgent.id);
                    } else {
                        closeAgentDetail();
                    }
                }
            }
        } catch (error) {
            console.error('处理 SSE 事件失败:', error);
        }
    };
    
    eventSource.onerror = () => {
        updateServerStatus('连接中断', 'error');
        console.log('SSE 连接断开，尝试重连...');
        setTimeout(() => {
            if (!eventSource || eventSource.readyState === EventSource.CLOSED) {
                startSSE();
            }
        }, 5000);
    };
}

// ==================== 话题管理 ====================

function createNewTopic(title = '新对话') {
    const topic = {
        id: Date.now().toString(),
        title: title,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
    };
    topics.unshift(topic);
    messages[topic.id] = [];
    currentTopicId = topic.id;
    saveToStorage();
    renderTopicsList();
    renderMessages();
    return topic.id;
}

function addNewTopic() {
    const title = prompt('请输入话题名称：', '新对话');
    if (title) {
        createNewTopic(title);
    }
}

function selectTopic(topicId) {
    currentTopicId = topicId;
    const topic = topics.find(t => t.id === topicId);
    if (topic) {
        topic.updatedAt = new Date().toISOString();
        const index = topics.findIndex(t => t.id === topicId);
        if (index > 0) {
            topics.splice(index, 1);
            topics.unshift(topic);
        }
    }
    saveToStorage();
    renderTopicsList();
    renderMessages();
    
    // 从服务器加载话题消息
    loadChatFromServer(topicId);
}

async function loadChatFromServer(topicId) {
    try {
        const response = await apiFetch(`/api/chat/${topicId}`);
        const data = await response.json();
        
        if (data.messages && data.messages.length > 0) {
            messages[topicId] = data.messages;
            renderMessages();
        }
    } catch (error) {
        console.log('加载历史消息失败，使用本地存储');
    }
}

function deleteTopic(topicId, event) {
    event.stopPropagation();
    if (topics.length <= 1) {
        alert('至少保留一个对话');
        return;
    }
    if (confirm('确定删除这个对话吗？')) {
        topics = topics.filter(t => t.id !== topicId);
        delete messages[topicId];
        if (currentTopicId === topicId) {
            currentTopicId = topics[0]?.id;
        }
        saveToStorage();
        renderTopicsList();
        renderMessages();
    }
}

function editTopic(topicId, event) {
    event.stopPropagation();
    const topic = topics.find(t => t.id === topicId);
    if (topic) {
        const newTitle = prompt('请输入新标题：', topic.title);
        if (newTitle && newTitle.trim()) {
            topic.title = newTitle.trim();
            saveToStorage();
            renderTopicsList();
        }
    }
}

function renderTopicsList() {
    const topicsList = document.getElementById('topicsList');
    if (!topicsList) return;

    if (topics.length === 0) {
        topicsList.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📁</div><p>暂无对话</p></div>';
        return;
    }

    topicsList.innerHTML = topics.map(topic => {
        const topicMessages = messages[topic.id] || [];
        const lastMessage = topicMessages[topicMessages.length - 1];
        const preview = lastMessage ? (lastMessage.text ? lastMessage.text.substring(0, 30) : '[图片]') : '暂无消息';
        const time = formatTime(topic.updatedAt);
        
        return `
            <div class="topic-item ${topic.id === currentTopicId ? 'active' : ''}" 
                 onclick="selectTopic('${topic.id}')">
                <div class="topic-title">${escapeHtml(topic.title)}</div>
                <div class="topic-preview">${escapeHtml(preview)}${preview.length >= 30 ? '...' : ''}</div>
                <div class="topic-time">${time}</div>
                <div class="topic-actions">
                    <button onclick="editTopic('${topic.id}', event)">编辑</button>
                    <button onclick="deleteTopic('${topic.id}', event)">删除</button>
                </div>
            </div>
        `;
    }).join('');
}

// ==================== 消息处理 ====================

async function sendMessage() {
    const input = document.getElementById('messageInput');
    const text = input.value.trim();
    
    if (!text && pendingImages.length === 0) {
        return;
    }

    if (!currentTopicId) {
        createNewTopic();
    }

    // 禁用发送按钮
    const sendBtn = document.getElementById('sendBtn');
    sendBtn.disabled = true;
    sendBtn.textContent = '发送中...';

    // 构建消息数据
    const messageData = {
        topic_id: currentTopicId,
        text: text,
        images: pendingImages
    };

    try {
        const response = await apiFetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(messageData)
        });

        if (response.ok) {
            const data = await response.json();
            
            // 添加用户消息
            addMessage(data.user_message);
            
            // 添加 AI 消息
            addMessage(data.ai_message);

            // 更新话题时间
            const topic = topics.find(t => t.id === currentTopicId);
            if (topic) {
                topic.updatedAt = new Date().toISOString();
                renderTopicsList();
            }
        } else {
            alert('发送失败，请重试');
        }
    } catch (error) {
        console.error('发送消息失败:', error);
        alert('发送失败: ' + error.message);
    } finally {
        // 清空输入和图片
        input.value = '';
        pendingImages = [];
        renderImagePreviews();
        
        // 重新启用发送按钮
        sendBtn.disabled = false;
        sendBtn.textContent = '发送';
    }
}

function addMessage(message) {
    if (!messages[currentTopicId]) {
        messages[currentTopicId] = [];
    }
    messages[currentTopicId].push(message);
    saveToStorage();
    renderMessages();
    scrollToBottom();
}

function renderMessages() {
    const chatMessages = document.getElementById('chatMessages');
    if (!chatMessages) return;

    const topicMessages = messages[currentTopicId] || [];

    if (topicMessages.length === 0) {
        chatMessages.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">💬</div>
                <h3>开始对话</h3>
                <p>发送消息开始聊天</p>
            </div>
        `;
        return;
    }

    chatMessages.innerHTML = topicMessages.map(msg => {
        const imagesHtml = msg.images && msg.images.length > 0 
            ? `<div class="message-images">${msg.images.map(img => `<img src="${img}" onclick="previewImage('${img}')">`).join('')}</div>`
            : '';
        
        const textHtml = msg.text ? `<div class="message-text">${escapeHtml(msg.text).replace(/\n/g, '<br>')}</div>` : '';
        
        return `
            <div class="message ${msg.type}">
                ${imagesHtml}
                ${textHtml}
                <div class="message-time">${formatTime(msg.timestamp || msg.time)}</div>
            </div>
        `;
    }).join('');

    scrollToBottom();
}

function scrollToBottom() {
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages) {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

// ==================== 图片处理 ====================

function handleImageUpload(event) {
    const files = event.target.files;
    if (!files) return;

    for (const file of files) {
        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = (e) => {
                pendingImages.push(e.target.result);
                renderImagePreviews();
            };
            reader.readAsDataURL(file);
        }
    }
    event.target.value = '';
}

function renderImagePreviews() {
    const previewArea = document.getElementById('imagePreviewArea');
    if (!previewArea) return;

    if (pendingImages.length === 0) {
        previewArea.style.display = 'none';
        previewArea.innerHTML = '';
        return;
    }

    previewArea.style.display = 'flex';
    previewArea.innerHTML = pendingImages.map((img, index) => `
        <div class="preview-item">
            <img src="${img}" alt="preview">
            <button class="remove-btn" onclick="removeImage(${index})">×</button>
        </div>
    `).join('');
}

function removeImage(index) {
    pendingImages.splice(index, 1);
    renderImagePreviews();
}

function previewImage(src) {
    window.open(src, '_blank');
}

// ==================== 输入处理 ====================

function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function newChat() {
    const title = prompt('请输入对话名称：', '新对话');
    const topicId = createNewTopic(title || '新对话');
    renderTopicsList();
    renderMessages();
}

// ==================== 工具函数 ====================

function formatTime(isoString) {
    if (!isoString) return '';
    
    const date = new Date(isoString);
    const now = new Date();
    const diff = now - date;

    if (diff < 60000) {
        return '刚刚';
    }
    if (diff < 3600000) {
        return Math.floor(diff / 60000) + '分钟前';
    }
    if (diff < 86400000) {
        return Math.floor(diff / 3600000) + '小时前';
    }
    if (diff < 604800000) {
        return Math.floor(diff / 86400000) + '天前';
    }

    return date.toLocaleDateString('zh-CN', { 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==================== 本地存储 ====================

function saveToStorage() {
    localStorage.setItem('chatTopics', JSON.stringify(topics));
    localStorage.setItem('chatMessages', JSON.stringify(messages));
    localStorage.setItem('currentTopicId', currentTopicId || '');
}

function loadFromStorage() {
    try {
        const storedTopics = localStorage.getItem('chatTopics');
        const storedMessages = localStorage.getItem('chatMessages');
        const storedCurrentId = localStorage.getItem('currentTopicId');

        if (storedTopics) {
            topics = JSON.parse(storedTopics);
        }
        if (storedMessages) {
            messages = JSON.parse(storedMessages);
        }
        if (storedCurrentId) {
            currentTopicId = storedCurrentId;
        }
    } catch (e) {
        console.error('加载数据失败:', e);
    }
}

// 页面卸载时关闭 SSE
window.addEventListener('beforeunload', () => {
    if (eventSource) {
        eventSource.close();
    }
});
