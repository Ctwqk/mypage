"""Shared fixtures. No test talks to a real LLM: the model is always a fake or a mocked HTTP layer."""

from __future__ import annotations

import base64
import io
from dataclasses import replace

import pytest

from config import Config
from llm import LLMError
from server import create_app

# Smallest valid-looking files; only the magic bytes matter to the server.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF_BYTES = b"GIF89a" + b"\x00" * 32
WEBP_BYTES = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def upload(client, session_id: int, data: bytes, filename: str = "pic.png", field: str = "image"):
    """POST a multipart image upload."""
    return client.post(
        f"/deepseek_backend/get_base64/{session_id}",
        data={field: (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


class FakeLLM:
    """Stands in for ``llm.LLMClient``; records calls and replays canned output."""

    def __init__(self):
        self.models = ["fake-small", "fake-large"]
        self.pieces = ["Hello", ", ", "world"]
        self.calls: list[tuple] = []
        self.error: LLMError | None = None  # raised when the request is made
        self.stream_error: LLMError | None = None  # raised after the first piece

    def list_models(self):
        self.calls.append(("list_models",))
        if self.error:
            raise self.error
        return list(self.models)

    def chat(self, model, messages):
        self.calls.append(("chat", model, messages))
        if self.error:
            raise self.error
        return "".join(self.pieces)

    def stream_chat(self, model, messages):
        self.calls.append(("stream_chat", model, messages))
        if self.error:
            raise self.error

        def gen():
            for i, piece in enumerate(self.pieces):
                yield piece
                if i == 0 and self.stream_error:
                    raise self.stream_error

        return gen()


@pytest.fixture
def cfg(tmp_path) -> Config:
    return replace(
        Config(),
        database_path=tmp_path / "data" / "chat.db",
        media_dir=tmp_path / "data" / "media",
        frontend_dir=None,
        max_upload_bytes=4096,
        history_limit=3,
        llm_model="fake-small",
    )


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def app(cfg, llm):
    return create_app(cfg, llm=llm)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def session_id(client) -> int:
    resp = client.post("/deepseek_backend/create_session", json={"session_name": "Test"})
    assert resp.status_code == 201
    return resp.get_json()["session_id"]
