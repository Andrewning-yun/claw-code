"""
Web Server for Claude Chat Frontend.

This server provides:
- Static file serving for the frontend
- REST API for chat functionality
- Agent status/management endpoints
- SSE (Server-Sent Events) for real-time agent updates
"""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

# Try to import anthropic, but make it optional
try:
    from anthropic import AsyncAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("Warning: anthropic package not installed. Install with: pip install anthropic")


# ==================== Data Models ====================

class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class Agent:
    """Represents a running agent."""
    id: str
    name: str
    status: AgentStatus = AgentStatus.IDLE
    created_at: datetime = field(default_factory=datetime.now)
    current_task: str = ""
    logs: list = field(default_factory=list)
    messages: list = field(default_factory=list)


@dataclass
class ChatMessage:
    """Represents a chat message."""
    id: str
    type: str  # "user" or "ai"
    text: str
    images: list = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


# ==================== Global State ====================

# Active agents (simulated for demo, can be extended to real agents)
active_agents: dict[str, Agent] = {}

# Chat history (in-memory, per topic)
chat_sessions: dict[str, list[dict]] = {}

# Claude API client
claude_client: Optional[AsyncAnthropic] = None

# Configuration
API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
API_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
API_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")


# ==================== Server Setup ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Server lifespan handler."""
    global claude_client
    
    # Initialize Claude client if API key is available
    if ANTHROPIC_AVAILABLE and API_KEY and API_KEY != "your-api-key-here":
        claude_client = AsyncAnthropic(
            api_key=API_KEY,
            base_url=API_BASE_URL,
        )
        print(f"Claude client initialized with model: {API_MODEL}")
    else:
        print("Claude API not configured. Using demo mode.")
    
    # Create some demo agents
    create_demo_agents()
    
    yield
    
    # Cleanup
    if claude_client:
        await claude_client.close()


def create_demo_agents():
    """Create some demo agents for demonstration."""
    agent1 = Agent(
        id="agent-1",
        name="Code Reviewer",
        status=AgentStatus.IDLE,
        current_task="Waiting for tasks...",
    )
    agent1.logs = [
        {"time": "10:30:15", "message": "Agent initialized"},
    ]
    
    agent2 = Agent(
        id="agent-2",
        name="File Scanner",
        status=AgentStatus.RUNNING,
        current_task="Scanning project files...",
    )
    agent2.logs = [
        {"time": "10:31:00", "message": "Starting file scan"},
        {"time": "10:31:05", "message": "Found 156 files"},
        {"time": "10:31:10", "message": "Analyzing dependencies..."},
    ]
    
    agent3 = Agent(
        id="agent-3",
        name="Bug Hunter",
        status=AgentStatus.IDLE,
        current_task="Waiting for tasks...",
    )
    
    active_agents[agent1.id] = agent1
    active_agents[agent2.id] = agent2
    active_agents[agent3.id] = agent3


# ==================== Create App ====================

app = FastAPI(
    title="Claude Chat API",
    description="Web API for Claude Chat Frontend",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get the directory containing this file
BASE_DIR = Path(__file__).parent


# ==================== Routes ====================

@app.get("/")
async def root():
    """Serve the main HTML file."""
    return FileResponse(str(BASE_DIR / "index.html"))


# --- Agent Management API ---

@app.get("/api/agents")
async def get_agents():
    """Get list of all agents."""
    return {
        "agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "status": agent.status.value,
                "current_task": agent.current_task,
                "created_at": agent.created_at.isoformat(),
                "log_count": len(agent.logs),
            }
            for agent in active_agents.values()
        ]
    }


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get detailed agent information."""
    agent = active_agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return {
        "id": agent.id,
        "name": agent.name,
        "status": agent.status.value,
        "current_task": agent.current_task,
        "created_at": agent.created_at.isoformat(),
        "logs": agent.logs,
        "messages": agent.messages,
    }


@app.post("/api/agents/{agent_id}/run")
async def run_agent(agent_id: str, task: dict):
    """Start an agent with a specific task."""
    agent = active_agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    task_text = task.get("task", "")
    if not task_text:
        raise HTTPException(status_code=400, detail="Task is required")
    
    # Update agent status
    agent.status = AgentStatus.RUNNING
    agent.current_task = task_text
    agent.logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": f"Starting task: {task_text[:50]}..."
    })
    
    # Simulate agent running (in real implementation, this would spawn a real agent)
    asyncio.create_task(simulate_agent_task(agent_id, task_text))
    
    return {"status": "started", "agent_id": agent_id}


@app.post("/api/agents/{agent_id}/stop")
async def stop_agent(agent_id: str):
    """Stop a running agent."""
    agent = active_agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    agent.status = AgentStatus.IDLE
    agent.current_task = "Waiting for tasks..."
    agent.logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": "Agent stopped by user"
    })
    
    return {"status": "stopped", "agent_id": agent_id}


async def simulate_agent_task(agent_id: str, task: str):
    """Simulate an agent working on a task."""
    await asyncio.sleep(2)
    
    agent = active_agents.get(agent_id)
    if not agent:
        return
    
    # Add some demo logs
    agent.logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": "Analyzing request..."
    })
    
    await asyncio.sleep(1)
    
    agent.logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": "Processing data..."
    })
    
    await asyncio.sleep(1)
    
    agent.logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": "Task completed!"
    })
    
    agent.status = AgentStatus.COMPLETED
    agent.current_task = "Task completed"


# --- Chat API ---

@app.post("/api/chat")
async def send_chat_message(message: dict):
    """Send a chat message and get AI response."""
    topic_id = message.get("topic_id", "default")
    text = message.get("text", "")
    images = message.get("images", [])
    
    if not text and not images:
        raise HTTPException(status_code=400, detail="Message is required")
    
    # Initialize session if needed
    if topic_id not in chat_sessions:
        chat_sessions[topic_id] = []
    
    # Add user message
    user_msg = {
        "id": str(uuid.uuid4()),
        "type": "user",
        "text": text,
        "images": images,
        "timestamp": datetime.now().isoformat(),
    }
    chat_sessions[topic_id].append(user_msg)
    
    # Get AI response
    ai_response = await get_ai_response(text, images, chat_sessions[topic_id])
    
    # Add AI message
    ai_msg = {
        "id": str(uuid.uuid4()),
        "type": "ai",
        "text": ai_response,
        "images": [],
        "timestamp": datetime.now().isoformat(),
    }
    chat_sessions[topic_id].append(ai_msg)
    
    return {
        "user_message": user_msg,
        "ai_message": ai_msg,
    }


@app.get("/api/chat/{topic_id}")
async def get_chat_history(topic_id: str):
    """Get chat history for a topic."""
    messages = chat_sessions.get(topic_id, [])
    return {"messages": messages}


@app.delete("/api/chat/{topic_id}")
async def clear_chat(topic_id: str):
    """Clear chat history for a topic."""
    if topic_id in chat_sessions:
        chat_sessions[topic_id] = []
    return {"status": "cleared"}


async def get_ai_response(user_text: str, images: list, chat_history: list) -> str:
    """Get AI response from Claude API or use demo responses."""
    global claude_client
    
    if claude_client and ANTHROPIC_AVAILABLE:
        try:
            # Build messages for Claude
            messages = []
            
            # Convert chat history to Claude format
            for msg in chat_history:
                role = "user" if msg["type"] == "user" else "assistant"
                content = msg["text"]
                
                # Handle images if any
                if msg.get("images"):
                    blocks = []
                    # Add image URLs as text blocks (simplified)
                    for img in msg["images"]:
                        blocks.append({
                            "type": "text",
                            "text": f"[Image: {img[:50]}...]"
                        })
                    blocks.append({"type": "text", "text": content})
                    messages.append({"role": role, "content": blocks})
                else:
                    messages.append({"role": role, "content": content})
            
            # Add current message if not already in history
            if not chat_history or chat_history[-1].get("text") != user_text:
                messages.append({"role": "user", "content": user_text})
            
            response = await claude_client.messages.create(
                model=API_MODEL,
                max_tokens=4096,
                messages=messages,
            )
            
            # Extract text from response
            result = ""
            for block in response.content:
                if hasattr(block, "text"):
                    result += block.text
            
            return result if result else "No response generated"
            
        except Exception as e:
            print(f"Claude API error: {e}")
            return f"Error: {str(e)}"
    
    # Demo mode - return sample responses
    return get_demo_response(user_text)


def get_demo_response(user_text: str) -> str:
    """Generate demo responses (when API is not configured)."""
    text_lower = user_text.lower()
    
    if any(word in text_lower for word in ["hello", "hi", "你好", "嗨"]):
        return "你好！我是 Claude AI 助手。有什么我可以帮助你的吗？"
    
    if any(word in text_lower for word in ["help", "帮助", "你能做什么"]):
        return """我可以帮助你完成以下任务：

1. **代码审查** - 分析代码质量并提供改进建议
2. **文件操作** - 读取、创建、编辑文件和代码
3. **问题解答** - 回答技术问题和编程相关问题
4. **任务执行** - 运行各种开发任务

请告诉我你需要什么帮助！"""
    
    if any(word in text_lower for word in ["天气", "weather"]):
        return "很抱歉，我是一个AI助手，没有获取实时天气信息的能力。但我可以帮你做很多事情！"
    
    # Default responses
    responses = [
        f"我收到了你的消息：'{user_text}'\n\n这是一个演示回复。要获取真正的AI回复，请在服务器环境变量中配置 ANTHROPIC_API_KEY。",
        f"感谢你的消息！\n\n你发送的内容已被处理。如果想使用真实的 Claude AI，请在 .env 文件中设置 ANTHROPIC_API_KEY。",
        f"收到！\n\n你的问题 '{user_text}' 已记录。目前使用的是演示模式，你可以：\n1. 配置 ANTHROPIC_API_KEY 使用真实AI\n2. 或者继续体验界面功能",
    ]
    
    import random
    return random.choice(responses)


# --- SSE Endpoint for Real-time Updates ---

@app.get("/api/events")
async def events(request: Request):
    """Server-Sent Events endpoint for real-time agent updates."""
    
    async def event_generator():
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break
            
            # Prepare event data
            event_data = {
                "agents": [
                    {
                        "id": agent.id,
                        "name": agent.name,
                        "status": agent.status.value,
                        "current_task": agent.current_task,
                        "log_count": len(agent.logs),
                    }
                    for agent in active_agents.values()
                ],
                "timestamp": datetime.now().isoformat(),
            }
            
            yield {
                "event": "agent_update",
                "data": json.dumps(event_data),
            }
            
            await asyncio.sleep(2)  # Send update every 2 seconds
    
    return EventSourceResponse(event_generator())


# ==================== Run Server ====================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 50)
    print("Claude Chat Server")
    print("=" * 50)
    print(f"API Key configured: {bool(API_KEY and API_KEY != 'your-api-key-here')}")
    print(f"Model: {API_MODEL}")
    print("=" * 50)
    
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )