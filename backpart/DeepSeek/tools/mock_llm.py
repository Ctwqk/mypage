"""A tiny OpenAI-compatible stub server, so the chat UI can be tried without any model.

    python tools/mock_llm.py            # listens on http://127.0.0.1:11435/v1
    LLM_BASE_URL=http://127.0.0.1:11435/v1 LLM_MODEL=mock-echo python server.py

It answers every prompt with a canned reply that echoes the last user message (and a short
"reasoning" part, to exercise the <think> styling). It is a development aid, not a model.
"""

from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODELS = ["mock-echo", "mock-echo-large"]


def last_user_text(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, list):
            content = " ".join(p.get("text", "") for p in content if p.get("type") == "text") or "[image]"
        return str(content)
    return ""


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.rstrip("/").endswith("/models"):
            self._send_json({"object": "list", "data": [{"id": m, "object": "model"} for m in MODELS]})
        else:
            self._send_json({"error": {"message": "not found"}}, 404)

    def do_POST(self):  # noqa: N802
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self._send_json({"error": {"message": "not found"}}, 404)
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length) or b"{}")
        prompt = last_user_text(req.get("messages", []))
        thinking = "The user wrote a message; I will echo it back. "
        answer = f"[mock reply] You said: {prompt}"

        if not req.get("stream"):
            return self._send_json({"choices": [{"message": {"role": "assistant", "content": answer}}]})

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def emit(delta: dict) -> None:
            data = f"data: {json.dumps({'choices': [{'delta': delta}]})}\n\n".encode()
            self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
            self.wfile.flush()
            time.sleep(0.02)

        for word in thinking.split(" "):
            emit({"reasoning_content": word + " "})
        for word in answer.split(" "):
            emit({"content": word + " "})
        done = b"data: [DONE]\n\n"
        self.wfile.write(f"{len(done):x}\r\n".encode() + done + b"\r\n0\r\n\r\n")
        self.wfile.flush()


def main() -> None:
    port = int(os.environ.get("MOCK_LLM_PORT", "11435"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"mock LLM on http://127.0.0.1:{port}/v1 (models: {', '.join(MODELS)})")
    server.serve_forever()


if __name__ == "__main__":
    main()
