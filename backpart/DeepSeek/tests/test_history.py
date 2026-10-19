import pytest
from conftest import PNG_BYTES, b64

BASE = "/deepseek_backend"


def save(client, session_id, user="hi", assistant="hello", **extra):
    return client.post(
        f"{BASE}/save_chat", json={"session_id": session_id, "user": user, "assistant": assistant, **extra}
    )


def test_load_chat_is_chronological_user_then_assistant(client, session_id):
    save(client, session_id, "q1", "a1")
    save(client, session_id, "q2", "a2")
    history = client.get(f"{BASE}/load_chat/{session_id}").get_json()
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "q1"),
        ("assistant", "a1"),
        ("user", "q2"),
        ("assistant", "a2"),
    ]


def test_load_chat_returns_only_the_most_recent_turns(client, session_id):
    # the fixture config uses history_limit=3
    for i in range(1, 6):
        save(client, session_id, f"q{i}", f"a{i}")
    history = client.get(f"{BASE}/load_chat/{session_id}").get_json()
    assert [m["content"] for m in history if m["role"] == "user"] == ["q3", "q4", "q5"]


def test_history_is_isolated_per_session(client, session_id):
    other = client.post(f"{BASE}/create_session", json={}).get_json()["session_id"]
    save(client, session_id, "mine", "ok")
    assert client.get(f"{BASE}/load_chat/{other}").get_json() == []


@pytest.mark.parametrize("as_list", [False, True])
def test_images_round_trip(client, session_id, as_list):
    imgs = [b64(PNG_BYTES), b64(PNG_BYTES + b"2")]
    save(client, session_id, "look", "nice", images=imgs if as_list else ",".join(imgs))
    user_msg = client.get(f"{BASE}/load_chat/{session_id}").get_json()[0]
    assert user_msg["images"] == ",".join(imgs)


def test_text_only_turn_has_no_images(client, session_id):
    save(client, session_id)
    assert client.get(f"{BASE}/load_chat/{session_id}").get_json()[0]["images"] is None


def test_image_only_message_is_allowed(client, session_id):
    assert save(client, session_id, user="", images=[b64(PNG_BYTES)]).status_code == 201


@pytest.mark.parametrize(
    "payload",
    [
        {"user": "", "assistant": "x"},  # empty text and no image
        {"user": 5, "assistant": "x"},
        {"user": "x", "assistant": ["not", "text"]},
        {"user": "x", "assistant": "y", "images": ["data:image/png;base64,AAAA"]},  # data URI, not raw base64
        {"user": "x", "assistant": "y", "images": ["<script>"]},
        {"user": "x", "assistant": "y", "images": [1]},
        {"user": "x", "assistant": "y", "images": ["QQ=="] * 5},  # > max_images_per_message (4)
        {"user": "x", "assistant": "y", "images": {"a": 1}},
    ],
)
def test_save_chat_rejects_invalid_payloads(client, session_id, payload):
    resp = client.post(f"{BASE}/save_chat", json={"session_id": session_id, **payload})
    assert resp.status_code in (400, 413)
    assert "error" in resp.get_json()
    assert client.get(f"{BASE}/load_chat/{session_id}").get_json() == []


def test_save_chat_rejects_oversized_message(client, session_id):
    resp = save(client, session_id, user="x" * 60_000)
    assert resp.status_code == 413


def test_save_chat_unknown_session(client):
    assert save(client, 777).status_code == 404
    assert client.post(f"{BASE}/save_chat", json={"user": "x", "assistant": "y"}).status_code == 400


def test_load_chat_unknown_session(client):
    assert client.get(f"{BASE}/load_chat/12345").status_code == 404


def test_sql_injection_attempt_is_stored_literally(client, session_id):
    nasty = "x'); DROP TABLE chat_history;--"
    save(client, session_id, nasty, "ok")
    assert client.get(f"{BASE}/load_chat/{session_id}").get_json()[0]["content"] == nasty
