"""The Flask app also serves the static site, so `python server.py` runs everything."""

from dataclasses import replace

import pytest

from config import Config
from server import create_app

REPO_FRONTEND = Config().frontend_dir


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site"
    (root / "sub").mkdir(parents=True)
    (root / "index.html").write_text("<h1>home</h1>")
    (root / "sub" / "index.html").write_text("<h1>sub</h1>")
    (root / "sub" / "page.html").write_text("<p>page</p>")
    (tmp_path / "secret.txt").write_text("top secret")
    return root


@pytest.fixture
def static_client(cfg, llm, site):
    return create_app(replace(cfg, frontend_dir=site), llm=llm).test_client()


def test_root_and_directories_serve_index_html(static_client):
    assert b"home" in static_client.get("/").data
    assert b"sub" in static_client.get("/sub/").data
    assert b"page" in static_client.get("/sub/page.html").data


def test_directory_without_trailing_slash_redirects_so_relative_links_work(static_client):
    resp = static_client.get("/sub")
    assert resp.status_code == 301
    assert resp.headers["Location"].endswith("/sub/")


@pytest.mark.parametrize(
    "path", ["/nope.html", "/sub/nope", "/../secret.txt", "/%2e%2e/secret.txt", "/sub/../../secret.txt"]
)
def test_missing_and_traversal_paths_are_404(static_client, path):
    assert static_client.get(path).status_code == 404


def test_encoded_absolute_path_does_not_escape_the_site_root(static_client, tmp_path):
    resp = static_client.get("/%2Fetc/passwd")
    assert resp.status_code == 404
    assert b"root:" not in resp.data


def test_api_routes_win_over_static_and_unknown_api_paths_return_json(static_client):
    assert static_client.get("/healthz").get_json() == {"status": "ok"}
    resp = static_client.get("/deepseek_backend/nope")
    assert resp.status_code == 404
    assert "error" in resp.get_json()
    # POST-only routes: a GET falls through to the static catch-all and is a JSON 404
    assert static_client.get("/deepseek_backend/create_session").status_code == 404
    assert static_client.post("/healthz").status_code == 405


def test_without_frontend_dir_root_describes_the_service(client):
    assert client.get("/").get_json()["frontend"] == "not configured"


def test_real_site_pages_are_served(cfg, llm):
    """Every page linked from the nav loads through Flask (guards against moved files)."""
    client = create_app(replace(cfg, frontend_dir=REPO_FRONTEND), llm=llm).test_client()
    for path in [
        "/",
        "/index.html",
        "/projects/",
        "/contact/",
        "/publications/",
        "/aboutme/resume.html",
        "/aboutme/Taiwei_Cui_CV.pdf",
        "/deepseek_/",
        "/deepseek_/script.js",
        "/deepseek_/styles.css",
        "/assets/site.css",
    ]:
        resp = client.get(path)
        assert resp.status_code == 200, path
        resp.close()
