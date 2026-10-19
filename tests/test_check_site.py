"""The link checker must actually fail on broken sites (otherwise CI would be decoration)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_site  # noqa: E402

PAGE = """<!DOCTYPE html><html lang="en"><head><title>t</title>{head}</head><body>{body}</body></html>"""


def make_site(tmp_path, pages: dict[str, str], files: dict[str, str] | None = None) -> Path:
    for rel, html in pages.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
    for rel, content in (files or {}).items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return tmp_path


def test_valid_site_passes(tmp_path):
    root = make_site(
        tmp_path,
        {
            "index.html": PAGE.format(
                head='<link rel="stylesheet" href="a.css">',
                body='<a href="sub/">sub</a><a href="sub/x.html#top-id">x</a><a href="#here" id="here">h</a>'
                '<a href="mailto:a@b.c">m</a><a href="https://example.com">e</a><img src="p.png" alt="">',
            ),
            "sub/index.html": PAGE.format(head="", body="<a href='../index.html'>home</a>"),
            "sub/x.html": PAGE.format(head="", body='<h1 id="top-id">x</h1>'),
        },
        {"a.css": "body{background:url('bg.png')}", "bg.png": "x", "p.png": "x"},
    )
    assert check_site.check_site(root) == []


def test_missing_targets_are_reported(tmp_path):
    root = make_site(
        tmp_path,
        {
            "index.html": PAGE.format(
                head='<link rel="stylesheet" href="missing.css"><script src="nope.js"></script>',
                body='<a href="gone.html">g</a><img src="img/none.png" alt="">'
                '<video poster="poster.jpg"><source src="v.webm"></video><iframe src="doc.pdf"></iframe>',
            )
        },
    )
    errors = check_site.check_site(root)
    for needle in ("missing.css", "nope.js", "gone.html", "none.png", "poster.jpg", "v.webm", "doc.pdf"):
        assert any(needle in e for e in errors), needle


def test_broken_fragment_and_css_url_and_root_relative(tmp_path):
    root = make_site(
        tmp_path,
        {
            "index.html": PAGE.format(
                head='<link rel="stylesheet" href="a.css">',
                body='<a href="#nowhere">n</a><a href="other.html#absent">o</a><a href="/abs.html">a</a>',
            ),
            "other.html": PAGE.format(head="", body='<p id="present"></p>'),
        },
        {"a.css": "body{background:url(missing-bg.png)}"},
    )
    errors = "\n".join(check_site.check_site(root))
    assert "#nowhere" in errors
    assert "absent" in errors
    assert "root-relative" in errors
    assert "missing-bg.png" in errors


def test_link_escaping_the_site_root_is_rejected(tmp_path):
    (tmp_path / "secret.txt").write_text("x")
    site = tmp_path / "site"
    make_site(site, {"index.html": PAGE.format(head="", body='<a href="../secret.txt">s</a>')})
    assert any("outside the site" in e for e in check_site.check_site(site))


def test_real_site_has_no_broken_local_links():
    repo = Path(__file__).resolve().parents[1]
    assert check_site.check_site(repo / "frontpart") == []
