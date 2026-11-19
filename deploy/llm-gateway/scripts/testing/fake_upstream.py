"""Fake LLM provider for testing the gateway without real API keys.

Answers OpenAI-style  POST /v1/chat/completions  and
        Anthropic-style POST /v1/messages
with a fixed reply. Like a real provider it reports usage of 10 input tokens and
min(50, max_tokens) output tokens, so the gateway's real cost-calculation and
budget code paths are exercised. Standard library only.
"""

import json
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

IN_TOKENS, MAX_OUT_TOKENS = 10, 50


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: dict, status: int = 200) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # health check
        self._send({"ok": True})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(length) or b"{}")
        model = req.get("model", "fake")
        out = min(
            MAX_OUT_TOKENS,
            int(req.get("max_tokens") or req.get("max_completion_tokens") or MAX_OUT_TOKENS),
        )
        if self.path.rstrip("/").endswith("/chat/completions"):
            self._send(
                {
                    "id": f"chatcmpl-{uuid.uuid4().hex}",
                    "object": "chat.completion",
                    "created": 0,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "Fake OpenAI-style reply."},
                        }
                    ],
                    "usage": {
                        "prompt_tokens": IN_TOKENS,
                        "completion_tokens": out,
                        "total_tokens": IN_TOKENS + out,
                    },
                }
            )
        elif self.path.rstrip("/").endswith("/messages"):
            self._send(
                {
                    "id": f"msg_{uuid.uuid4().hex}",
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [{"type": "text", "text": "Fake Anthropic-style reply."}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": IN_TOKENS, "output_tokens": out},
                }
            )
        else:
            self._send({"error": f"unknown path {self.path}"}, 404)

    def log_message(self, *args: object) -> None:  # keep container logs quiet
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
