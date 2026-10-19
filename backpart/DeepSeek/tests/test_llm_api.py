import json

import pytest
from conftest import PNG_BYTES, b64

from llm import LLMError

API = "/deepseek/api"


def ndjson(resp):
    return [json.loads(line) for line in resp.get_data(as_text=True).splitlines() if line.strip()]


def user_msg(text, **extra):
    return {"role": "user", "content": text, **extra}


# ---- /tags -----------------------------------------------------------------------------


def test_tags_lists_upstream_models(client):
    body = client.get(f"{API}/tags").get_json()
    assert [m["name"] for m in body["models"]] == ["fake-small", "fake-large"]
    assert body["models"][0]["id"] == "fake-small"  # the UI reads model.id || model.name
    assert "warning" not in body


def test_tags_falls_back_to_default_model_when_upstream_is_down(client, llm):
    llm.error = LLMError("Cannot reach LLM server")
    resp = client.get(f"{API}/tags")
    assert resp.status_code == 200
    body = resp.get_json()
    assert [m["name"] for m in body["models"]] == ["fake-small"]
    assert "Cannot reach" in body["warning"]


# ---- /chat -----------------------------------------------------------------------------


def test_chat_streams_ndjson_in_the_format_the_ui_expects(client, llm):
    resp = client.post(f"{API}/chat", json={"model": "fake-large", "messages": [user_msg("hi")], "stream": True})
    assert resp.status_code == 200
    assert resp.mimetype == "application/x-ndjson"
    chunks = ndjson(resp)
    assert "".join(c["message"]["content"] for c in chunks) == "Hello, world"
    assert [c["done"] for c in chunks] == [False, False, False, True]
    assert llm.calls[-1][:2] == ("stream_chat", "fake-large")


def test_chat_defaults_to_streaming_and_default_model(client, llm):
    resp = client.post(f"{API}/chat", json={"messages": [user_msg("hi")]})
    assert resp.mimetype == "application/x-ndjson"
    assert llm.calls[-1][1] == "fake-small"


def test_chat_non_streaming(client):
    resp = client.post(f"{API}/chat", json={"messages": [user_msg("hi")], "stream": False})
    assert resp.status_code == 200
    assert resp.get_json()["message"] == {"role": "assistant", "content": "Hello, world"}


def test_chat_drops_the_empty_placeholder_message_the_ui_appends(client, llm):
    messages = [
        user_msg("q1"),
        {"role": "assistant", "content": "a1"},
        user_msg("q2"),
        {"role": "assistant", "content": None},
    ]
    client.post(f"{API}/chat", json={"messages": messages})
    forwarded = llm.calls[-1][2]
    assert [m["content"] for m in forwarded] == ["q1", "a1", "q2"]


def test_chat_forwards_images_to_the_model(client, llm):
    img = b64(PNG_BYTES)
    client.post(f"{API}/chat", json={"messages": [user_msg("what is this?", images=[img])]})
    assert llm.calls[-1][2][0]["images"] == [img]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"messages": []},
        {"messages": "hi"},
        {"messages": ["hi"]},
        {"messages": [{"role": "root", "content": "hi"}]},
        {"messages": [{"role": "user", "content": 42}]},
        {"messages": [{"role": "assistant", "content": None}]},  # nothing left after dropping placeholders
        {"messages": [user_msg("hi")], "stream": "yes"},
        {"messages": [user_msg("hi")], "model": {"x": 1}},
        {"messages": [user_msg("hi", images=["data:image/png;base64,AAAA"])]},
        {"messages": [user_msg("x")] * 51},
    ],
)
def test_chat_validation_errors_do_not_reach_the_model(client, llm, payload):
    resp = client.post(f"{API}/chat", json=payload)
    assert resp.status_code == 400
    assert "error" in resp.get_json()
    assert not [c for c in llm.calls if c[0] in ("chat", "stream_chat")]


def test_chat_rejects_oversized_message(client):
    resp = client.post(f"{API}/chat", json={"messages": [user_msg("x" * 60_000)]})
    assert resp.status_code == 413


def test_chat_rejects_non_json_body(client):
    resp = client.post(f"{API}/chat", data="hello", content_type="text/plain")
    assert resp.status_code == 400


def test_chat_upstream_failure_is_a_502_json_error(client, llm):
    llm.error = LLMError("LLM server returned HTTP 401: bad key")
    resp = client.post(f"{API}/chat", json={"messages": [user_msg("hi")]})
    assert resp.status_code == 502
    assert resp.get_json()["error"] == "LLM server returned HTTP 401: bad key"


def test_chat_stream_that_breaks_midway_reports_an_error_line(client, llm):
    llm.stream_error = LLMError("LLM stream interrupted")
    chunks = ndjson(client.post(f"{API}/chat", json={"messages": [user_msg("hi")]}))
    assert chunks[0]["message"]["content"] == "Hello"
    assert chunks[-1] == {"error": "LLM stream interrupted", "done": True}


# ---- /generate -------------------------------------------------------------------------


def test_generate_returns_response_text(client, llm):
    resp = client.post(f"{API}/generate", json={"model": "fake-large", "prompt": "Summarize: cats", "stream": False})
    assert resp.status_code == 200
    assert resp.get_json()["response"] == "Hello, world"
    kind, model, messages = llm.calls[-1]
    assert (kind, model) == ("chat", "fake-large")
    assert messages[0]["content"] == "Summarize: cats"


@pytest.mark.parametrize("payload", [{}, {"prompt": ""}, {"prompt": "   "}, {"prompt": 3}])
def test_generate_validation(client, payload):
    assert client.post(f"{API}/generate", json=payload).status_code == 400


def test_generate_upstream_failure(client, llm):
    llm.error = LLMError("boom")
    assert client.post(f"{API}/generate", json={"prompt": "x"}).status_code == 502
