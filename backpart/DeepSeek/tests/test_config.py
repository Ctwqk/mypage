from pathlib import Path

import pytest

from config import BASE_DIR, Config


def test_defaults_point_at_local_ollama_and_loopback():
    cfg = Config.from_env({})
    assert cfg.llm_base_url == "http://localhost:11434/v1"
    assert cfg.llm_api_key == ""
    assert cfg.host == "127.0.0.1"  # not exposed on all interfaces by default
    assert cfg.debug is False


def test_environment_overrides():
    cfg = Config.from_env(
        {
            "LLM_BASE_URL": "https://api.deepseek.com/",
            "LLM_API_KEY": "sk-secret",
            "LLM_MODEL": "deepseek-chat",
            "LLM_TIMEOUT": "30",
            "MAX_UPLOAD_MB": "2",
            "HISTORY_LIMIT": "7",
            "PORT": "5055",
            "FLASK_DEBUG": "1",
        }
    )
    assert cfg.llm_base_url == "https://api.deepseek.com"
    assert cfg.llm_api_key == "sk-secret"
    assert cfg.llm_model == "deepseek-chat"
    assert cfg.llm_timeout == 30.0
    assert cfg.max_upload_bytes == 2 * 1024 * 1024
    assert cfg.history_limit == 7
    assert cfg.port == 5055
    assert cfg.debug is True


def test_api_key_is_not_in_repr():
    assert "sk-secret" not in repr(Config.from_env({"LLM_API_KEY": "sk-secret"}))


def test_relative_paths_resolve_against_backend_dir_not_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = Config.from_env({"DATABASE_PATH": "x/y.db", "MEDIA_DIR": str(tmp_path / "m")})
    assert cfg.database_path == (BASE_DIR / "x" / "y.db").resolve()
    assert cfg.media_dir == tmp_path / "m"


def test_default_frontend_dir_is_the_repo_frontpart():
    assert Config.from_env({}).frontend_dir == (BASE_DIR / ".." / ".." / "frontpart").resolve()


def test_empty_frontend_dir_disables_static_serving():
    assert Config.from_env({"FRONTEND_DIR": ""}).frontend_dir is None


@pytest.mark.parametrize(
    "env",
    [{"PORT": "abc"}, {"MAX_UPLOAD_MB": "0"}, {"LLM_TIMEOUT": "-1"}, {"HISTORY_LIMIT": "1.5"}],
)
def test_invalid_numbers_fail_fast(env):
    with pytest.raises(ValueError):
        Config.from_env(env)


def test_request_limit_covers_a_message_with_max_images():
    cfg = Config.from_env({})
    one_image = cfg.max_image_b64_chars
    assert cfg.max_request_bytes > cfg.max_images_per_message * one_image
    assert isinstance(cfg.database_path, Path)
