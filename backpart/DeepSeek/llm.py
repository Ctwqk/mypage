"""Thin client for OpenAI-compatible chat endpoints (Ollama, DeepSeek API, OpenAI, vLLM, ...).

The browser front end speaks a small Ollama-like protocol (``{"message": {"content": ...}}``
newline-delimited JSON). This module talks to the upstream in the OpenAI wire format and
leaves the translation to ``server.py``. Reasoning tokens (``reasoning_content`` /
``reasoning`` deltas) are re-wrapped in ``<think>...</think>`` so the UI can style them.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from typing import Any

import requests

IMAGE_SNIFF = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


class LLMError(Exception):
    """The upstream model server failed or returned something unusable."""


def mime_from_b64(b64: str) -> str:
    """Guess an image MIME type from the first bytes of a base64 string (default PNG)."""
    try:
        head = base64.b64decode(b64[:48] + "=" * (-len(b64[:48]) % 4))
    except (ValueError, TypeError):
        return "image/png"
    for magic, mime in IMAGE_SNIFF:
        if head.startswith(magic):
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert ``{role, content, images?: [base64]}`` into OpenAI chat messages."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        images = msg.get("images") or []
        if images:
            parts: list[dict[str, Any]] = []
            if msg.get("content"):
                parts.append({"type": "text", "text": msg["content"]})
            for b64 in images:
                url = f"data:{mime_from_b64(b64)};base64,{b64}"
                parts.append({"type": "image_url", "image_url": {"url": url}})
            out.append({"role": msg["role"], "content": parts})
        else:
            out.append({"role": msg["role"], "content": msg.get("content") or ""})
    return out


def _error_message(resp: requests.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error")
        if isinstance(err, dict):
            err = err.get("message")
        if err:
            return f"LLM server returned HTTP {resp.status_code}: {err}"
    except ValueError:
        pass
    return f"LLM server returned HTTP {resp.status_code}"


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        default_model: str = "",
        timeout: float = 120.0,
        session: requests.Session | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout
        self._http = session or requests.Session()

    # -- helpers ---------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post(self, payload: dict[str, Any], *, stream: bool) -> requests.Response:
        try:
            resp = self._http.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=(10, self.timeout),
                stream=stream,
            )
        except requests.RequestException as exc:
            raise LLMError(f"Cannot reach LLM server at {self.base_url}: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            message = _error_message(resp)
            resp.close()
            raise LLMError(message)
        return resp

    # -- public API ------------------------------------------------------------------
    def list_models(self) -> list[str]:
        try:
            resp = self._http.get(f"{self.base_url}/models", headers=self._headers(), timeout=(10, 30))
        except requests.RequestException as exc:
            raise LLMError(f"Cannot reach LLM server at {self.base_url}: {exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise LLMError(_error_message(resp))
        try:
            data = resp.json().get("data", [])
            return [m["id"] for m in data if isinstance(m, dict) and m.get("id")]
        except (ValueError, AttributeError) as exc:
            raise LLMError("LLM server returned an invalid model list") from exc

    def chat(self, model: str, messages: list[dict[str, Any]]) -> str:
        """Single, non-streaming completion. Returns the assistant text."""
        payload = {"model": model or self.default_model, "messages": to_openai_messages(messages), "stream": False}
        resp = self._post(payload, stream=False)
        try:
            message = resp.json()["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("LLM server returned an unexpected response") from exc
        text = message.get("content") or ""
        reasoning = message.get("reasoning_content") or message.get("reasoning")
        if reasoning:
            text = f"<think>{reasoning}</think>{text}"
        return text

    def stream_chat(self, model: str, messages: list[dict[str, Any]]) -> Iterator[str]:
        """Start a streaming completion.

        The HTTP request (and status check) happens immediately, so connection errors
        surface here as ``LLMError`` before any bytes are sent to the browser. The returned
        iterator yields text fragments and may raise ``LLMError`` if the stream breaks.
        """
        payload = {"model": model or self.default_model, "messages": to_openai_messages(messages), "stream": True}
        resp = self._post(payload, stream=True)
        return self._iter_stream(resp)

    @staticmethod
    def _iter_stream(resp: requests.Response) -> Iterator[str]:
        in_think = False
        try:
            for raw in resp.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0].get("delta", {})
                except (ValueError, KeyError, IndexError, TypeError):
                    continue
                reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                content = delta.get("content")
                if reasoning:
                    yield ("" if in_think else "<think>") + reasoning
                    in_think = True
                if content:
                    yield ("</think>" if in_think else "") + content
                    in_think = False
            if in_think:
                yield "</think>"
        except requests.RequestException as exc:
            raise LLMError(f"LLM stream interrupted: {exc.__class__.__name__}") from exc
        finally:
            resp.close()
