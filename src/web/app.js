const form = document.getElementById('chat-form');
const input = document.getElementById('chat-input');
const messages = document.getElementById('messages');
const subagentList = document.getElementById('subagent-list');
const streamState = document.getElementById('stream-state');

function addMessage(role, text) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.innerHTML = `<strong>${role === 'user' ? '你' : 'Claw'}：</strong>${text}`;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function renderSubagents(items = []) {
  subagentList.innerHTML = '';
  items.forEach((item) => {
    const li = document.createElement('li');
    li.className = 'agent';
    li.innerHTML = `
      <div class="top">
        <strong>${item.name}</strong>
        <span>${item.status}</span>
      </div>
      <div class="muted">${item.task}</div>
      <div class="progress"><span style="width:${item.progress}%"></span></div>
    `;
    subagentList.appendChild(li);
  });
}

async function bootstrap() {
  const resp = await fetch('/api/subagents');
  const data = await resp.json();
  renderSubagents(data.subagents || []);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  addMessage('user', text);

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    const payload = await resp.json();
    if (!resp.ok) {
      addMessage('assistant', `请求失败：${payload.error || '未知错误'}`);
      return;
    }
    addMessage('assistant', payload.assistant);
    renderSubagents(payload.subagents || []);
  } catch (error) {
    addMessage('assistant', `网络异常：${error.message}`);
  }
});

const eventSource = new EventSource('/api/subagents/stream?interval=1');
eventSource.addEventListener('subagents', (event) => {
  streamState.textContent = '实时同步';
  const payload = JSON.parse(event.data);
  renderSubagents(payload.subagents || []);
});

eventSource.onerror = () => {
  streamState.textContent = '连接断开，自动重连中';
};

bootstrap().catch(() => {
  streamState.textContent = '初始加载失败';
});
