#!/usr/bin/env python3
"""Check that every local link and asset referenced by the static site exists.

    python3 scripts/check_site.py [site_dir]        # default: frontpart
    python3 scripts/check_site.py frontpart --external   # also HEAD-check http(s) links (needs network)

Checked: <a href>, <img src>, <script src>, <link href>, <source src>, <video poster>,
<object data>, <iframe src>, in-page #fragments, and url(...) references in local CSS files.
Root-relative URLs ("/x") are reported because they break when the site is hosted under a
sub-path (for example GitHub Pages project sites). Exit status is 1 if any problem is found.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

URL_ATTRS = {
    "a": ["href"],
    "img": ["src"],
    "script": ["src"],
    "link": ["href"],
    "source": ["src"],
    "video": ["poster", "src"],
    "audio": ["src"],
    "object": ["data"],
    "iframe": ["src"],
}
SKIP_SCHEMES = {"mailto", "tel", "data", "javascript"}
CSS_URL_RE = re.compile(r"url\(\s*['\"]?([^'\")]+?)['\"]?\s*\)")


class Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[tuple[str, int]] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if attr.get("id"):
            self.ids.add(attr["id"])
        if tag == "a" and attr.get("name"):
            self.ids.add(attr["name"])
        for name in URL_ATTRS.get(tag, []):
            value = attr.get(name)
            if value and value.strip():
                self.refs.append((value.strip(), self.getpos()[0]))


def resolve_local(source: Path, ref: str, root: Path) -> Path:
    path = unquote(urlparse(ref).path)
    target = (source.parent / path).resolve()
    if path.endswith("/") or target.is_dir():
        target = target / "index.html"
    return target


def check_ref(source: Path, ref: str, line: int, root: Path, errors: list[str], externals: set[str]) -> None:
    parsed = urlparse(ref)
    where = f"{source.relative_to(root)}:{line}"
    if parsed.scheme in ("http", "https"):
        externals.add(ref)
        return
    if parsed.scheme in SKIP_SCHEMES:
        return
    if parsed.scheme or ref.startswith("//"):
        errors.append(f"{where}: unsupported URL {ref!r}")
        return
    if ref.startswith("#"):
        return  # fragment-only links are checked by the caller (needs the page's ids)
    if ref.startswith("/"):
        errors.append(f"{where}: root-relative URL {ref!r} breaks under a sub-path; use a relative URL")
        return
    target = resolve_local(source, ref, root)
    if root not in target.parents and target != root:
        errors.append(f"{where}: {ref!r} points outside the site")
    elif not target.is_file():
        errors.append(f"{where}: {ref!r} does not exist (looked for {target.relative_to(root)})")


def check_site(root: Path, external: bool = False) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    externals: set[str] = set()
    pages = sorted(root.rglob("*.html"))
    if not pages:
        return [f"no HTML files found under {root}"]

    for page in pages:
        parser = Collector()
        parser.feed(page.read_text(encoding="utf-8"))
        for ref, line in parser.refs:
            check_ref(page, ref, line, root, errors, externals)
            frag = urlparse(ref).fragment
            if ref.startswith("#") and frag and frag not in parser.ids and frag != "top":
                errors.append(f"{page.relative_to(root)}:{line}: in-page anchor {ref!r} has no matching id")
            elif frag and not ref.startswith("#") and urlparse(ref).scheme == "":
                target = resolve_local(page, ref, root)
                if target.suffix == ".html" and target.is_file():
                    other = Collector()
                    other.feed(target.read_text(encoding="utf-8"))
                    if frag not in other.ids:
                        errors.append(f"{page.relative_to(root)}:{line}: {ref!r} - no id {frag!r} in {target.name}")

    for css in sorted(root.rglob("*.css")):
        for match in CSS_URL_RE.finditer(css.read_text(encoding="utf-8")):
            ref = match.group(1)
            if ref.startswith(("data:", "http:", "https:", "#")):
                continue
            target = (css.parent / unquote(urlparse(ref).path)).resolve()
            if not target.is_file():
                errors.append(f"{css.relative_to(root)}: url({ref}) does not exist")

    if external:
        for url in sorted(externals):
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "mypage-link-check"})
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
                    if resp.status >= 400:
                        errors.append(f"external {url}: HTTP {resp.status}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"external {url}: {exc}")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("site_dir", nargs="?", default="frontpart")
    ap.add_argument("--external", action="store_true", help="also check http(s) links (needs network)")
    args = ap.parse_args(argv)
    root = Path(args.site_dir)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    errors = check_site(root, external=args.external)
    for e in errors:
        print("ERROR", e)
    pages = len(list(root.rglob("*.html")))
    status = f"FAILED, {len(errors)} problem(s)" if errors else "all local links OK"
    print(f"checked {pages} HTML files: {status}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
