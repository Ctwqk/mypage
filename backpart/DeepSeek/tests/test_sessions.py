from conftest import PNG_BYTES, upload

BASE = "/deepseek_backend"


def test_create_and_list_sessions_newest_first(client):
    a = client.post(f"{BASE}/create_session", json={"session_name": "first"}).get_json()
    b = client.post(f"{BASE}/create_session", json={"session_name": "second"}).get_json()
    assert a["session_id"] != b["session_id"]
    listing = client.get(f"{BASE}/get_session").get_json()
    assert [s["session_name"] for s in listing] == ["second", "first"]
    assert set(listing[0]) == {"session_id", "session_name"}


def test_create_session_defaults_and_generated_user_id(client):
    data = client.post(f"{BASE}/create_session").get_json()
    assert data["session_name"] == "New Chat"
    assert len(data["user_id"]) >= 32  # uuid4


def test_create_session_creates_media_folder(client, cfg):
    sid = client.post(f"{BASE}/create_session", json={}).get_json()["session_id"]
    assert (cfg.media_dir / str(sid)).is_dir()


def test_create_session_rejects_bad_input(client):
    assert client.post(f"{BASE}/create_session", json={"session_name": 123}).status_code == 400
    assert client.post(f"{BASE}/create_session", json={"session_name": "x" * 500}).status_code == 413
    assert client.post(f"{BASE}/create_session", data="not json", content_type="application/json").status_code == 400
    assert client.post(f"{BASE}/create_session", json=["a"]).status_code == 400


def test_rename_session(client, session_id):
    resp = client.post(f"{BASE}/rename_session", json={"session_id": session_id, "session_name": "  Renamed  "})
    assert resp.status_code == 200
    assert client.get(f"{BASE}/get_session").get_json()[0]["session_name"] == "Renamed"


def test_rename_session_validation(client, session_id):
    assert (
        client.post(f"{BASE}/rename_session", json={"session_id": session_id, "session_name": "  "}).status_code == 400
    )
    assert client.post(f"{BASE}/rename_session", json={"session_id": 9999, "session_name": "x"}).status_code == 404
    assert client.post(f"{BASE}/rename_session", json={"session_id": "abc", "session_name": "x"}).status_code == 400
    assert client.post(f"{BASE}/rename_session", json={"session_name": "x"}).status_code == 400


def test_delete_session_removes_history_and_media(client, cfg, session_id):
    client.post(f"{BASE}/save_chat", json={"session_id": session_id, "user": "hi", "assistant": "hello"})
    upload(client, session_id, PNG_BYTES, "a.png")
    assert any((cfg.media_dir / str(session_id)).iterdir())

    resp = client.post(f"{BASE}/delete_session", json={"session_id": session_id})
    assert resp.status_code == 200
    assert client.get(f"{BASE}/get_session").get_json() == []
    assert not (cfg.media_dir / str(session_id)).exists()
    assert client.get(f"{BASE}/load_chat/{session_id}").status_code == 404


def test_delete_unknown_or_missing_id(client):
    assert client.post(f"{BASE}/delete_session", json={"session_id": 424242}).status_code == 404
    assert client.post(f"{BASE}/delete_session", json={}).status_code == 400


def test_sessions_survive_app_restart(cfg, llm):
    from server import create_app

    create_app(cfg, llm=llm).test_client().post(f"{BASE}/create_session", json={"session_name": "persisted"})
    restarted = create_app(cfg, llm=llm).test_client()
    assert [s["session_name"] for s in restarted.get(f"{BASE}/get_session").get_json()] == ["persisted"]
