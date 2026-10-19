"""Runtime configuration, read from environment variables.

Nothing in here is secret by default: the API key comes only from ``LLM_API_KEY``.
Relative paths are resolved against this directory, not the process working
directory, so the server behaves the same wherever it is started from.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _int_env(env: dict, name: str, default: int, *, minimum: int = 1) -> int:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    return value


def _float_env(env: dict, name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}")
    return value


def _path_env(env: dict, name: str, default: str) -> Path:
    path = Path(env.get(name) or default).expanduser()
    return path if path.is_absolute() else (BASE_DIR / path).resolve()


@dataclass(frozen=True)
class Config:
    # LLM (any OpenAI-compatible /chat/completions endpoint: Ollama, DeepSeek, OpenAI, vLLM, ...)
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = field(default="", repr=False)  # never printed in logs / reprs
    llm_model: str = "deepseek-llm:7b"
    llm_timeout: float = 120.0

    # Storage
    database_path: Path = BASE_DIR / "data" / "chat.db"
    media_dir: Path = BASE_DIR / "data" / "media"

    # Static front end served by Flask (set to an empty string to disable)
    frontend_dir: Path | None = (BASE_DIR / ".." / ".." / "frontpart").resolve()

    # Limits
    max_upload_bytes: int = 5 * 1024 * 1024
    max_images_per_message: int = 4
    max_message_chars: int = 50_000
    max_messages_per_request: int = 50
    max_session_name_chars: int = 200
    history_limit: int = 10  # number of (user, assistant) turns returned by /load_chat

    # Server
    host: str = "127.0.0.1"
    port: int = 5000
    debug: bool = False

    @classmethod
    def from_env(cls, env: dict | None = None) -> Config:
        env = dict(os.environ if env is None else env)
        frontend_raw = env.get("FRONTEND_DIR")
        if frontend_raw is not None and frontend_raw.strip() == "":
            frontend_dir = None
        else:
            frontend_dir = _path_env(env, "FRONTEND_DIR", str(cls.frontend_dir))
        return cls(
            llm_base_url=(env.get("LLM_BASE_URL") or cls.llm_base_url).rstrip("/"),
            llm_api_key=env.get("LLM_API_KEY", ""),
            llm_model=env.get("LLM_MODEL") or cls.llm_model,
            llm_timeout=_float_env(env, "LLM_TIMEOUT", cls.llm_timeout),
            database_path=_path_env(env, "DATABASE_PATH", str(cls.database_path)),
            media_dir=_path_env(env, "MEDIA_DIR", str(cls.media_dir)),
            frontend_dir=frontend_dir,
            max_upload_bytes=_int_env(env, "MAX_UPLOAD_MB", 5) * 1024 * 1024,
            max_images_per_message=_int_env(env, "MAX_IMAGES_PER_MESSAGE", cls.max_images_per_message),
            max_message_chars=_int_env(env, "MAX_MESSAGE_CHARS", cls.max_message_chars),
            history_limit=_int_env(env, "HISTORY_LIMIT", cls.history_limit),
            host=env.get("HOST") or cls.host,
            port=_int_env(env, "PORT", cls.port),
            debug=env.get("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"},
        )

    @property
    def max_image_b64_chars(self) -> int:
        """Largest base64 string that can come from an image of ``max_upload_bytes``."""
        return (self.max_upload_bytes + 2) // 3 * 4

    @property
    def max_request_bytes(self) -> int:
        """Upper bound for any request body (JSON with images is the largest case)."""
        images = self.max_images_per_message * (self.max_image_b64_chars + 1)
        # 4 bytes per char is the worst case for UTF-8 JSON text; two text fields per save.
        text = 2 * self.max_message_chars * 4
        return images + text + 64 * 1024
