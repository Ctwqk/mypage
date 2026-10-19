import base64

import pytest
from conftest import GIF_BYTES, JPEG_BYTES, PNG_BYTES, WEBP_BYTES, upload


@pytest.mark.parametrize(
    ("data", "ext", "mime"),
    [
        (PNG_BYTES, "png", "image/png"),
        (JPEG_BYTES, "jpg", "image/jpeg"),
        (GIF_BYTES, "gif", "image/gif"),
        (WEBP_BYTES, "webp", "image/webp"),
    ],
)
def test_valid_images_are_stored_and_returned_as_base64(client, cfg, session_id, data, ext, mime):
    resp = upload(client, session_id, data, f"whatever.{ext}")
    assert resp.status_code == 201
    body = resp.get_json()
    assert base64.b64decode(body["imageBase64"]) == data
    assert body["mimeType"] == mime
    assert body["filename"].endswith(f".{ext}")
    assert (cfg.media_dir / str(session_id) / body["filename"]).read_bytes() == data
    assert "url" not in body  # no server file-system paths leak to the client


def test_filename_and_extension_from_client_are_ignored(client, cfg, session_id):
    resp = upload(client, session_id, PNG_BYTES, "../../evil.php")
    assert resp.status_code == 201
    stored = list((cfg.media_dir / str(session_id)).iterdir())
    assert len(stored) == 1
    assert stored[0].suffix == ".png"
    assert not list(cfg.media_dir.parent.glob("**/evil*"))


def test_each_upload_gets_a_unique_name(client, session_id):
    names = {upload(client, session_id, PNG_BYTES).get_json()["filename"] for _ in range(3)}
    assert len(names) == 3  # the original code overwrote a single file called "image"


def test_non_image_content_is_rejected_even_with_image_name(client, cfg, session_id):
    resp = upload(client, session_id, b"<?php echo 1; ?>", "shell.png")
    assert resp.status_code == 415
    assert not any((cfg.media_dir / str(session_id)).iterdir())


def test_svg_is_not_accepted(client, session_id):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert upload(client, session_id, svg, "x.svg").status_code == 415


def test_oversized_upload_is_rejected(client, cfg, session_id):
    big = PNG_BYTES + b"\x00" * cfg.max_upload_bytes
    resp = upload(client, session_id, big)
    assert resp.status_code == 413
    assert not any((cfg.media_dir / str(session_id)).iterdir())


def test_upload_at_the_limit_is_accepted(client, cfg, session_id):
    data = PNG_BYTES + b"\x00" * (cfg.max_upload_bytes - len(PNG_BYTES))
    assert len(data) == cfg.max_upload_bytes
    assert upload(client, session_id, data).status_code == 201


def test_missing_or_empty_file(client, session_id):
    assert upload(client, session_id, PNG_BYTES, field="file").status_code == 400
    assert upload(client, session_id, b"").status_code == 400


def test_upload_for_unknown_session(client):
    assert upload(client, 999, PNG_BYTES).status_code == 404
