from __future__ import annotations

import argparse
import json
import threading
import time
from dataclasses import dataclass, asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


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

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/chat":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

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

        working_states = self.registry.apply_prompt(prompt)
        completion = self.registry.complete_cycle()

        answer = (
            "这是一个前端/后端联动的最小可用实现。"
            "你已经可以在浏览器聊天，并看到 subagent 状态变化。"
            "下一步建议接入真实 LLM 与任务队列。"
        )
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), ClawWebHandler)
    print(f"Serving claw web UI on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
