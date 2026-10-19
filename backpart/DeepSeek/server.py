"""Chat backend for the personal site.

* ``/deepseek_backend/*``  persistent chat sessions, history and image attachments (SQLite + files)
* ``/deepseek/api/*``      thin proxy to an OpenAI-compatible LLM endpoint, exposing the small
                           Ollama-like protocol the browser UI expects
* ``/``                    the static site in ``frontpart/`` (optional, on by default)

Run with ``python server.py`` (see README) or ``flask --app server run``.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import shutil
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from flask import (
    Blueprint,
    Flask,
    Response,
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    request,
    send_from_directory,
    stream_with_context,
)
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.security import safe_join

import db as dbmod
from config import Config
from llm import LLMClient, LLMError

BACKEND_PREFIX = "/deepseek_backend"
LLM_PREFIX = "/deepseek/api"
ROLES = {"system", "user", "assistant"}
B64_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")

# Image types accepted for upload. The type is decided from the file's magic bytes,
# never from the client-supplied filename or Content-Type.
UPLOAD_TYPES = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def sniff_image(data: bytes) -> str | None:
    """Return the file extension ("png", "jpg", "gif", "webp") if ``data`` looks like a supported image."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


# --------------------------------------------------------------------------- validation


def json_object(*, allow_empty: bool = False) -> dict[str, Any]:
    if allow_empty and not request.get_data():
        return {}
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Request body must be a JSON object")
    return data


def clean_text(value: Any, field: str, cfg: Config, *, max_chars: int | None = None, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ApiError(f"'{field}' must be a string")
    limit = max_chars or cfg.max_message_chars
    if len(value) > limit:
        raise ApiError(f"'{field}' is too long (max {limit} characters)", 413)
    return value


def parse_session_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ApiError("'session_id' must be an integer")
    try:
        session_id = int(value)
    except ValueError:
        raise ApiError("'session_id' must be an integer") from None
    if session_id < 1:
        raise ApiError("'session_id' must be a positive integer")
    return session_id


def parse_images(value: Any, cfg: Config) -> list[str]:
    """Accept ``None``, a comma-separated string, or a list of base64 strings."""
    if value in (None, "", []):
        return []
    if isinstance(value, str):
        items = [p for p in value.split(",") if p.strip()]
    elif isinstance(value, list):
        items = value
    else:
        raise ApiError("'images' must be a list of base64 strings")
    if len(items) > cfg.max_images_per_message:
        raise ApiError(f"At most {cfg.max_images_per_message} images per message")
    cleaned = []
    for item in items:
        if not isinstance(item, str):
            raise ApiError("'images' must contain base64 strings")
        item = item.strip()
        if len(item) > cfg.max_image_b64_chars:
            raise ApiError("An image is too large", 413)
        if not B64_RE.match(item):
            raise ApiError("'images' must contain plain base64 (no data: URI prefix)")
        cleaned.append(item)
    return cleaned


def parse_chat_messages(raw: Any, cfg: Config) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ApiError("'messages' must be a non-empty list")
    if len(raw) > cfg.max_messages_per_request:
        raise ApiError(f"Too many messages (max {cfg.max_messages_per_request})")
    cleaned = []
    for msg in raw:
        if not isinstance(msg, dict):
            raise ApiError("Each message must be an object")
        role = msg.get("role")
        if role not in ROLES:
            raise ApiError(f"Message role must be one of {sorted(ROLES)}")
        content = clean_text(msg.get("content"), "content", cfg, required=False)
        images = parse_images(msg.get("images"), cfg) if role == "user" else []
        if not content.strip() and not images:
            continue  # the UI sends an empty placeholder for the reply it is about to stream
        cleaned.append({"role": role, "content": content, "images": images})
    if not cleaned:
        raise ApiError("'messages' contains no content")
    return cleaned


# --------------------------------------------------------------------------- app factory


def create_app(config: Config | None = None, llm: Any | None = None) -> Flask:
    cfg = config or Config.from_env()
    app = Flask(__name__, static_folder=None)
    app.config["CFG"] = cfg
    app.config["MAX_CONTENT_LENGTH"] = cfg.max_request_bytes
    app.extensions["llm"] = llm or LLMClient(
        cfg.llm_base_url, api_key=cfg.llm_api_key, default_model=cfg.llm_model, timeout=cfg.llm_timeout
    )
    if not app.debug:
        app.logger.setLevel(logging.INFO)

    dbmod.init_db(cfg.database_path)
    cfg.media_dir.mkdir(parents=True, exist_ok=True)

    @app.teardown_appcontext
    def close_db(_exc: BaseException | None) -> None:
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    @app.errorhandler(ApiError)
    def handle_api_error(exc: ApiError):
        return jsonify({"error": exc.message}), exc.status

    @app.errorhandler(HTTPException)
    def handle_http_error(exc: HTTPException):
        if isinstance(exc, RequestEntityTooLarge):
            return jsonify({"error": "Request body is too large"}), 413
        if request.path.startswith((BACKEND_PREFIX, LLM_PREFIX, "/healthz")):
            return jsonify({"error": exc.description or exc.name}), exc.code
        return exc

    app.register_blueprint(chat_bp)
    app.register_blueprint(llm_bp)

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    if cfg.frontend_dir and Path(cfg.frontend_dir).is_dir():
        register_frontend(app, Path(cfg.frontend_dir))
    else:

        @app.get("/")
        def index():
            return jsonify({"service": "mypage chat backend", "frontend": "not configured"})

    return app


def register_frontend(app: Flask, root: Path) -> None:
    """Serve the static site (``index.html`` for directories), so one process runs everything."""

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def frontend(path: str):
        target = safe_join(str(root), path)
        if target is None:
            abort(404)
        target_path = Path(target)
        if target_path.is_dir():
            if path and not request.path.endswith("/"):
                return redirect("/" + path.strip("/") + "/", code=301)
            path = f"{path.strip('/')}/index.html" if path.strip("/") else "index.html"
        elif not target_path.is_file():
            abort(404)
        return send_from_directory(root, path)


# --------------------------------------------------------------------------- chat sessions

chat_bp = Blueprint("chat", __name__, url_prefix=BACKEND_PREFIX)


def cfg_() -> Config:
    return current_app.config["CFG"]


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = dbmod.connect(cfg_().database_path)
    return g.db


def require_session(session_id: int) -> sqlite3.Row:
    row = get_db().execute("SELECT id, session_name FROM chat_sessions WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise ApiError(f"Session {session_id} does not exist", 404)
    return row


@chat_bp.post("/create_session")
def create_session():
    cfg = cfg_()
    data = json_object(allow_empty=True)
    name = clean_text(data.get("session_name", "New Chat"), "session_name", cfg, max_chars=cfg.max_session_name_chars)
    name = name.strip() or "New Chat"
    user_id = data.get("user_id") or str(uuid.uuid4())
    user_id = clean_text(user_id, "user_id", cfg, max_chars=100)
    db = get_db()
    cur = db.execute("INSERT INTO chat_sessions (session_name, user_id) VALUES (?, ?)", (name, user_id))
    db.commit()
    session_id = cur.lastrowid
    (cfg.media_dir / str(session_id)).mkdir(parents=True, exist_ok=True)
    return jsonify({"session_id": session_id, "user_id": user_id, "session_name": name}), 201


@chat_bp.get("/get_session")
def get_sessions():
    rows = get_db().execute("SELECT id, session_name FROM chat_sessions ORDER BY id DESC").fetchall()
    return jsonify([{"session_id": r["id"], "session_name": r["session_name"]} for r in rows])


@chat_bp.post("/rename_session")
def rename_session():
    cfg = cfg_()
    data = json_object()
    session_id = parse_session_id(data.get("session_id"))
    name = clean_text(data.get("session_name"), "session_name", cfg, max_chars=cfg.max_session_name_chars).strip()
    if not name:
        raise ApiError("'session_name' must not be empty")
    require_session(session_id)
    db = get_db()
    db.execute("UPDATE chat_sessions SET session_name = ? WHERE id = ?", (name, session_id))
    db.commit()
    return jsonify({"session_id": session_id, "session_name": name})


@chat_bp.post("/delete_session")
def delete_session():
    data = json_object()
    session_id = parse_session_id(data.get("session_id"))
    require_session(session_id)
    db = get_db()
    db.execute("DELETE FROM chat_history WHERE session_id = ?", (session_id,))
    db.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
    db.commit()
    shutil.rmtree(cfg_().media_dir / str(session_id), ignore_errors=True)
    return jsonify({"message": f"Session {session_id} deleted successfully!"})


@chat_bp.post("/save_chat")
def save_chat():
    cfg = cfg_()
    data = json_object()
    session_id = parse_session_id(data.get("session_id"))
    user_message = clean_text(data.get("user", ""), "user", cfg, required=False)
    assistant_message = clean_text(data.get("assistant", ""), "assistant", cfg, required=False)
    images = parse_images(data.get("images"), cfg)
    if not user_message.strip() and not images:
        raise ApiError("'user' must not be empty unless images are attached")
    require_session(session_id)
    db = get_db()
    db.execute(
        "INSERT INTO chat_history (session_id, user, assistant, image_base64) VALUES (?, ?, ?, ?)",
        (session_id, user_message, assistant_message, ",".join(images)),
    )
    db.commit()
    return jsonify({"message": "Chat saved!"}), 201


@chat_bp.get("/load_chat/<int:session_id>")
def load_chat(session_id: int):
    """Return the last ``history_limit`` turns of a session, oldest first."""
    require_session(session_id)
    rows = (
        get_db()
        .execute(
            """
        SELECT user, assistant, image_base64 FROM (
            SELECT id, user, assistant, image_base64 FROM chat_history
            WHERE session_id = ? ORDER BY id DESC LIMIT ?
        ) ORDER BY id ASC
        """,
            (session_id, cfg_().history_limit),
        )
        .fetchall()
    )
    history: list[dict[str, Any]] = []
    for row in rows:
        history.append({"role": "user", "content": row["user"], "images": row["image_base64"] or None})
        history.append({"role": "assistant", "content": row["assistant"], "images": None})
    return jsonify(history)


@chat_bp.post("/get_base64/<int:session_id>")
def upload_image(session_id: int):
    """Validate and store an uploaded image, and return it base64-encoded for the UI."""
    cfg = cfg_()
    require_session(session_id)
    if request.content_length is not None and request.content_length > cfg.max_upload_bytes + 64 * 1024:
        raise ApiError(f"Image is too large (max {cfg.max_upload_bytes // (1024 * 1024)} MB)", 413)
    upload = request.files.get("image")
    if upload is None:
        raise ApiError("No image file provided")
    data = upload.stream.read(cfg.max_upload_bytes + 1)
    if not data:
        raise ApiError("Empty file")
    if len(data) > cfg.max_upload_bytes:
        raise ApiError(f"Image is too large (max {cfg.max_upload_bytes // (1024 * 1024)} MB)", 413)
    ext = sniff_image(data)
    if ext is None:
        raise ApiError("Unsupported image type (allowed: png, jpg, gif, webp)", 415)
    folder = cfg.media_dir / str(session_id)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    (folder / filename).write_bytes(data)
    return jsonify(
        {
            "imageBase64": base64.b64encode(data).decode("ascii"),
            "mimeType": UPLOAD_TYPES[ext],
            "filename": filename,
        }
    ), 201


# --------------------------------------------------------------------------- LLM proxy

llm_bp = Blueprint("llm", __name__, url_prefix=LLM_PREFIX)


def llm_client() -> Any:
    return current_app.extensions["llm"]


def resolve_model(value: Any) -> str:
    cfg = cfg_()
    if value in (None, ""):
        return cfg.llm_model
    if not isinstance(value, str) or len(value) > 200:
        raise ApiError("'model' must be a string")
    return value


@llm_bp.get("/tags")
def tags():
    """List models. Falls back to the configured default if the upstream has no /models route."""
    cfg = cfg_()
    try:
        names = llm_client().list_models()
        warning = None
    except LLMError as exc:
        current_app.logger.warning("Could not list models: %s", exc)
        names, warning = [], str(exc)
    if not names:
        names = [cfg.llm_model]
    body: dict[str, Any] = {"models": [{"name": n, "id": n} for n in names]}
    if warning:
        body["warning"] = warning
    return jsonify(body)


@llm_bp.post("/chat")
def chat():
    cfg = cfg_()
    data = json_object()
    model = resolve_model(data.get("model"))
    messages = parse_chat_messages(data.get("messages"), cfg)
    stream = data.get("stream", True)
    if not isinstance(stream, bool):
        raise ApiError("'stream' must be a boolean")

    client = llm_client()
    try:
        if not stream:
            text = client.chat(model, messages)
            return jsonify({"model": model, "message": {"role": "assistant", "content": text}, "done": True})
        chunks = client.stream_chat(model, messages)
    except LLMError as exc:
        return jsonify({"error": str(exc)}), 502

    def ndjson():
        try:
            for text in chunks:
                piece = {"model": model, "message": {"role": "assistant", "content": text}, "done": False}
                yield json.dumps(piece) + "\n"
        except LLMError as exc:
            yield json.dumps({"error": str(exc), "done": True}) + "\n"
            return
        yield json.dumps({"model": model, "message": {"role": "assistant", "content": ""}, "done": True}) + "\n"

    return Response(stream_with_context(ndjson()), mimetype="application/x-ndjson", headers={"X-Accel-Buffering": "no"})


@llm_bp.post("/generate")
def generate():
    """One-shot, non-streaming completion for a single prompt (used for session titles)."""
    cfg = cfg_()
    data = json_object()
    model = resolve_model(data.get("model"))
    prompt = clean_text(data.get("prompt"), "prompt", cfg)
    if not prompt.strip():
        raise ApiError("'prompt' must not be empty")
    try:
        text = llm_client().chat(model, [{"role": "user", "content": prompt, "images": []}])
    except LLMError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify({"model": model, "response": text, "done": True})


def main() -> None:
    cfg = Config.from_env()
    app = create_app(cfg)
    app.run(host=cfg.host, port=cfg.port, debug=cfg.debug)


if __name__ == "__main__":
    main()
