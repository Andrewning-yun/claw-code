from __future__ import annotations

import argparse
import json
import os
import threading
import time
from dataclasses import dataclass, asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

# 尝试导入 requests 库用于 API 调用
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# API 配置
DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_BASE_URL = "https://api.anthropic.com"
DEFAULT_MAX_TOKENS = 4096


@dataclass
class SubagentState:
    id: str
    name: str
    status: str
    task: str
    progress: int
    last_updated: float


class SubagentRegistry:
    def __init__(self) -> None:
        now = time.time()
        self._lock = threading.Lock()
        self._states: list[SubagentState] = [
            SubagentState(
                id="planner",
                name="Planner",
                status="idle",
                task="Waiting for a new objective",
                progress=0,
                last_updated=now,
            ),
            SubagentState(
                id="coder",
                name="Coder",
                status="idle",
                task="No coding task assigned",
                progress=0,
                last_updated=now,
            ),
            SubagentState(
                id="reviewer",
                name="Reviewer",
                status="idle",
                task="No review in queue",
                progress=0,
                last_updated=now,
            ),
        ]

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(item) for item in self._states]

    def apply_prompt(self, prompt: str) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            for index, state in enumerate(self._states):
                status = "working" if index < 2 else "queued"
                progress = min(95, 20 + index * 25)
                task = (
                    f"Analyzing prompt: {prompt[:80]}"
                    if index == 0
                    else f"Building answer draft for: {prompt[:80]}"
                    if index == 1
                    else "Waiting for draft completion"
                )
                self._states[index] = SubagentState(
                    id=state.id,
                    name=state.name,
                    status=status,
                    task=task,
                    progress=progress,
                    last_updated=now,
                )
            return [asdict(item) for item in self._states]

    def complete_cycle(self) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            completed: list[SubagentState] = []
            for state in self._states:
                completed.append(
                    SubagentState(
                        id=state.id,
                        name=state.name,
                        status="done",
                        task="Cycle complete",
                        progress=100,
                        last_updated=now,
                    )
                )
            self._states = completed
            return [asdict(item) for item in self._states]

    def reset_to_idle(self) -> list[dict[str, Any]]:
        """重置所有 subagent 为空闲状态"""
        now = time.time()
        with self._lock:
            self._states = [
                SubagentState(
                    id="planner",
                    name="Planner",
                    status="idle",
                    task="Waiting for a new objective",
                    progress=0,
                    last_updated=now,
                ),
                SubagentState(
                    id="coder",
                    name="Coder",
                    status="idle",
                    task="No coding task assigned",
                    progress=0,
                    last_updated=now,
                ),
                SubagentState(
                    id="reviewer",
                    name="Reviewer",
                    status="idle",
                    task="No review in queue",
                    progress=0,
                    last_updated=now,
                ),
            ]
            return [asdict(item) for item in self._states]


# 对话历史存储
class ChatSession:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._messages: list[dict[str, str]] = []

    def add_user_message(self, content: str) -> None:
        with self._lock:
            self._messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        with self._lock:
            self._messages.append({"role": "assistant", "content": content})

    def get_messages(self) -> list[dict[str, str]]:
        with self._lock:
            return list(self._messages)

    def clear(self) -> None:
        with self._lock:
            self._messages = []


# 全局会话
chat_session = ChatSession()


def call_claude_api(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """调用 Claude API 并返回响应"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "错误: 未设置 ANTHROPIC_API_KEY 环境变量。请设置后再试。"

    if not HAS_REQUESTS:
        return "错误: requests 库未安装。请运行: pip install requests"

    # 获取之前的历史消息
    messages = chat_session.get_messages()
    messages.append({"role": "user", "content": prompt})

    url = f"{DEFAULT_BASE_URL}/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    data = {
        "model": model,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "messages": messages,
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        result = response.json()

        # 提取文本内容
        if "content" in result:
            for block in result["content"]:
                if block.get("type") == "text":
                    return block.get("text", "无法解析响应")

        return "无法解析 API 响应"

    except requests.exceptions.Timeout:
        return "错误: API 请求超时，请稍后重试。"
    except requests.exceptions.RequestException as e:
        return f"错误: API 请求失败 - {str(e)}"


class ClawWebHandler(BaseHTTPRequestHandler):
    registry = SubagentRegistry()
    static_root = Path(__file__).resolve().parent / "web"

    def _write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _write_file(self, file_name: str, content_type: str) -> None:
        path = self.static_root / file_name
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        payload = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._write_file("index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._write_file("app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._write_file("styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/subagents":
            self._write_json({"subagents": self.registry.snapshot()})
            return
        if parsed.path == "/api/subagents/stream":
            query = parse_qs(parsed.query)
            interval = float(query.get("interval", ["1.0"])[0])
            self._sse_stream(max(interval, 0.25))
            return

        # 检查 API 状态
        if parsed.path == "/api/status":
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            self._write_json({
                "api_configured": bool(api_key),
                "requests_available": HAS_REQUESTS,
                "model": DEFAULT_MODEL,
            })
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/chat":
            self._handle_chat()
            return

        if parsed.path == "/api/chat/clear":
            chat_session.clear()
            self.registry.reset_to_idle()
            self._write_json({"status": "cleared"})
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def _handle_chat(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_payload = self.rfile.read(content_length)
        try:
            body = json.loads(raw_payload or b"{}")
        except json.JSONDecodeError:
            self._write_json({"error": "Invalid JSON body"}, status=HTTPStatus.BAD_REQUEST)
            return

        prompt = str(body.get("message", "")).strip()
        if not prompt:
            self._write_json({"error": "message is required"}, status=HTTPStatus.BAD_REQUEST)
            return

        # 更新 subagent 状态为处理中
        working_states = self.registry.apply_prompt(prompt)

        # 调用 Claude API
        answer = call_claude_api(prompt)

        # 保存对话历史
        chat_session.add_user_message(prompt)
        chat_session.add_assistant_message(answer)

        # 完成subagent状态
        completion = self.registry.complete_cycle()

        self._write_json(
            {
                "assistant": answer,
                "subagents": completion,
                "intermediate": working_states,
                "timestamp": time.time(),
            }
        )

    def _sse_stream(self, interval: float) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            for _ in range(60):
                payload = json.dumps({"subagents": self.registry.snapshot(), "timestamp": time.time()})
                self.wfile.write(f"event: subagents\ndata: {payload}\n\n".encode("utf-8"))
                self.wfile.flush()
                time.sleep(interval)
        except (BrokenPipeError, ConnectionResetError):
            return


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run claw-code browser chat frontend")
    parser.add_argument("--host", default="127.0.0.1", help="Host address")
    parser.add_argument("--port", default=8080, type=int, help="Port number")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Claude model to use")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    # 检查 API 配置
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("=" * 50)
        print("警告: ANTHROPIC_API_KEY 环境变量未设置")
        print("请设置后再使用聊天功能:")
        print("  Windows: set ANTHROPIC_API_KEY=你的API密钥")
        print("  Mac/Linux: export ANTHROPIC_API_KEY=你的API密钥")
        print("=" * 50)
        print()

    if HAS_REQUESTS:
        print(f"✓ requests 库已安装")
    else:
        print(f"✗ requests 库未安装，聊天功能不可用")
        print(f"  请运行: pip install requests")
        print()

    print(f"Serving claw web UI on http://{args.host}:{args.port}")
    print(f"使用模型: {args.model}")
    print("按 Ctrl+C 停止服务")

    server = ThreadingHTTPServer((args.host, args.port), ClawWebHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()