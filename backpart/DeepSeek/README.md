# Chat backend (Flask + SQLite)

One process that serves

- the static site from `../../frontpart/` at `/`,
- chat sessions, history and image uploads at `/deepseek_backend/*` (SQLite + files),
- an LLM proxy at `/deepseek/api/*` that talks to any OpenAI-compatible `/v1/chat/completions` server.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python server.py                   # http://127.0.0.1:5000
# or: flask --app server run
```

Configuration is read from environment variables only; copy [`.env.example`](.env.example) for the full list. The important ones:

| Variable | Default | Meaning |
| --- | --- | --- |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | OpenAI-compatible base URL (Ollama, `https://api.deepseek.com`, `https://api.openai.com/v1`, ...) |
| `LLM_API_KEY` | empty | Bearer token for the upstream; never logged, never sent to the browser |
| `LLM_MODEL` | `deepseek-llm:7b` | Fallback model when the UI sends none or `/models` cannot be listed |
| `LLM_TIMEOUT` | `120` | Seconds to wait for the upstream (read timeout) |
| `DATABASE_PATH` / `MEDIA_DIR` | `data/chat.db`, `data/media` | Relative paths are resolved against this directory, not the working directory |
| `FRONTEND_DIR` | `../../frontpart` | Static site to serve; empty string disables it |
| `MAX_UPLOAD_MB` | `5` | Largest accepted image |
| `MAX_IMAGES_PER_MESSAGE` | `4` | Attachments per message |
| `MAX_MESSAGE_CHARS` | `50000` | Largest text field |
| `HISTORY_LIMIT` | `10` | Turns returned by `load_chat` |
| `HOST` / `PORT` | `127.0.0.1` / `5000` | Bind address |
| `FLASK_DEBUG` | `0` | Never enable on an exposed interface (Werkzeug debugger) |

Without a model, `python tools/mock_llm.py` starts an OpenAI-compatible stub on port 11435 (`MOCK_LLM_PORT` to change it).

## API

All bodies are JSON unless noted; errors are `{"error": "..."}` with a 4xx/5xx status.

| Method and path | Purpose |
| --- | --- |
| `POST /deepseek_backend/create_session` | `{session_name?, user_id?}` returns `{session_id, user_id, session_name}` (201) |
| `GET /deepseek_backend/get_session` | list sessions, newest first |
| `POST /deepseek_backend/rename_session` | `{session_id, session_name}` |
| `POST /deepseek_backend/delete_session` | `{session_id}`; removes history and uploaded files |
| `POST /deepseek_backend/save_chat` | `{session_id, user, assistant, images?}` (`images`: list or comma-separated base64) |
| `GET /deepseek_backend/load_chat/<id>` | last `HISTORY_LIMIT` turns, oldest first, as `{role, content, images}` messages |
| `POST /deepseek_backend/get_base64/<id>` | multipart field `image`; stores the file, returns `{imageBase64, mimeType, filename}` (415 for non-images, 413 when too large) |
| `GET /deepseek/api/tags` | `{models: [{id, name}]}`; falls back to `LLM_MODEL` plus a `warning` if the upstream is unreachable |
| `POST /deepseek/api/chat` | `{model?, messages: [{role, content, images?}], stream?}`; streams newline-delimited JSON (`{"message": {"content": ...}, "done": false}`), 502 if the upstream fails before streaming |
| `POST /deepseek/api/generate` | `{model?, prompt}` returns `{response}` (used for session titles) |
| `GET /healthz` | liveness probe |

```bash
curl -s -X POST localhost:5000/deepseek_backend/create_session -H 'Content-Type: application/json' -d '{"session_name":"demo"}'
curl -sN -X POST localhost:5000/deepseek/api/chat -H 'Content-Type: application/json' \
     -d '{"messages":[{"role":"user","content":"Say hi"}]}'
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest            # 112 tests, no network, the LLM is faked or mocked with `responses`
```

`tests/conftest.py` provides a `FakeLLM` that is injected through `create_app(config, llm=...)`; `tests/test_llm_client.py` exercises the real `LLMClient` against mocked HTTP (SSE parsing, reasoning tokens, auth header, error mapping, image parts).
