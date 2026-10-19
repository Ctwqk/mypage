"""LLMClient against a mocked HTTP layer (the `responses` library); no network access."""

import json

import pytest
import requests
import responses
from conftest import GIF_BYTES, JPEG_BYTES, PNG_BYTES, WEBP_BYTES, b64

from llm import LLMClient, LLMError, mime_from_b64, to_openai_messages

BASE = "http://llm.test/v1"


def sse(*events):
    lines = []
    for event in events:
        lines.append("data: " + (event if isinstance(event, str) else json.dumps(event)))
        lines.append("")
    return "\n".join(lines) + "\n"


def delta(content=None, **extra):
    d = {"content": content, **extra} if content is not None else dict(extra)
    return {"choices": [{"delta": d}]}


@pytest.fixture
def client():
    return LLMClient(BASE, api_key="sk-test-123", default_model="m1")


@responses.activate
def test_stream_yields_text_fragments_and_stops_at_done(client):
    responses.post(f"{BASE}/chat/completions", body=sse(delta("Hel"), delta("lo"), "[DONE]", delta("ignored")))
    assert list(client.stream_chat("m1", [{"role": "user", "content": "hi"}])) == ["Hel", "lo"]


@responses.activate
def test_stream_request_shape_and_auth_header(client):
    responses.post(f"{BASE}/chat/completions", body=sse("[DONE]"))
    list(client.stream_chat("some-model", [{"role": "user", "content": "hi"}]))
    req = responses.calls[0].request
    assert req.headers["Authorization"] == "Bearer sk-test-123"
    assert json.loads(req.body) == {
        "model": "some-model",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }


@responses.activate
def test_no_authorization_header_without_api_key():
    responses.post(f"{BASE}/chat/completions", body=sse("[DONE]"))
    list(LLMClient(BASE).stream_chat("m", [{"role": "user", "content": "hi"}]))
    assert "Authorization" not in responses.calls[0].request.headers


@responses.activate
def test_empty_model_falls_back_to_default(client):
    responses.post(f"{BASE}/chat/completions", body=sse("[DONE]"))
    list(client.stream_chat("", [{"role": "user", "content": "hi"}]))
    assert json.loads(responses.calls[0].request.body)["model"] == "m1"


@responses.activate
def test_reasoning_tokens_are_wrapped_in_think_tags(client):
    responses.post(
        f"{BASE}/chat/completions",
        body=sse(
            delta(reasoning_content="Let me "),
            delta(reasoning_content="think."),
            delta("Answer"),
            delta("!"),
        ),
    )
    out = list(client.stream_chat("m1", [{"role": "user", "content": "q"}]))
    assert "".join(out) == "<think>Let me think.</think>Answer!"


@responses.activate
def test_ollama_style_reasoning_field_and_unterminated_think(client):
    responses.post(f"{BASE}/chat/completions", body=sse(delta(reasoning="hmm")))
    assert "".join(client.stream_chat("m1", [{"role": "user", "content": "q"}])) == "<think>hmm</think>"


@responses.activate
def test_malformed_and_keepalive_lines_are_skipped(client):
    body = ": keep-alive\n\ndata: {not json}\n\n" + sse(delta("ok"), "[DONE]")
    responses.post(f"{BASE}/chat/completions", body=body)
    assert list(client.stream_chat("m1", [{"role": "user", "content": "q"}])) == ["ok"]


@responses.activate
def test_http_error_message_is_extracted_and_key_is_not_leaked(client):
    responses.post(f"{BASE}/chat/completions", status=401, json={"error": {"message": "Incorrect API key"}})
    with pytest.raises(LLMError) as exc:
        client.stream_chat("m1", [{"role": "user", "content": "q"}])
    assert "401" in str(exc.value)
    assert "Incorrect API key" in str(exc.value)
    assert "sk-test-123" not in str(exc.value)


@responses.activate
def test_http_error_without_json_body(client):
    responses.post(f"{BASE}/chat/completions", status=500, body="<html>oops</html>")
    with pytest.raises(LLMError, match="HTTP 500"):
        client.chat("m1", [{"role": "user", "content": "q"}])


@responses.activate
def test_connection_error_becomes_llm_error(client):
    responses.post(f"{BASE}/chat/completions", body=requests.ConnectionError("refused"))
    with pytest.raises(LLMError, match="Cannot reach LLM server"):
        client.chat("m1", [{"role": "user", "content": "q"}])


@responses.activate
def test_non_streaming_chat_returns_text_with_reasoning(client):
    responses.post(
        f"{BASE}/chat/completions",
        json={"choices": [{"message": {"content": "42", "reasoning_content": "compute"}}]},
    )
    assert client.chat("m1", [{"role": "user", "content": "q"}]) == "<think>compute</think>42"


@responses.activate
def test_non_streaming_chat_with_unexpected_body(client):
    responses.post(f"{BASE}/chat/completions", json={"nope": 1})
    with pytest.raises(LLMError, match="unexpected"):
        client.chat("m1", [{"role": "user", "content": "q"}])


@responses.activate
def test_list_models_parses_openai_format(client):
    responses.get(f"{BASE}/models", json={"data": [{"id": "a"}, {"id": "b"}, {"object": "x"}]})
    assert client.list_models() == ["a", "b"]
    assert responses.calls[0].request.headers["Authorization"] == "Bearer sk-test-123"


@responses.activate
def test_list_models_errors(client):
    responses.get(f"{BASE}/models", status=404, json={"error": "not found"})
    with pytest.raises(LLMError):
        client.list_models()


def test_base_url_trailing_slash_is_normalised():
    assert LLMClient("http://x/v1/").base_url == "http://x/v1"


# ---- message conversion -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "mime"),
    [
        (PNG_BYTES, "image/png"),
        (JPEG_BYTES, "image/jpeg"),
        (GIF_BYTES, "image/gif"),
        (WEBP_BYTES, "image/webp"),
        (b"unknown bytes here", "image/png"),
    ],
)
def test_mime_from_b64(data, mime):
    assert mime_from_b64(b64(data)) == mime


def test_mime_from_b64_survives_garbage():
    assert mime_from_b64("!!!not base64!!!") == "image/png"


def test_to_openai_messages_plain_and_multimodal():
    img = b64(JPEG_BYTES)
    out = to_openai_messages(
        [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "describe", "images": [img]},
            {"role": "user", "content": "", "images": [img]},
            {"role": "assistant", "content": "ok"},
        ]
    )
    assert out[0] == {"role": "system", "content": "be brief"}
    assert out[1]["content"][0] == {"type": "text", "text": "describe"}
    assert out[1]["content"][1]["image_url"]["url"] == f"data:image/jpeg;base64,{img}"
    assert len(out[2]["content"]) == 1  # image only, no empty text part
    assert out[3] == {"role": "assistant", "content": "ok"}
