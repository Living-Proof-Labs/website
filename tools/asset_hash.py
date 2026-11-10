#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Content-hash names for CSS and JavaScript published in the assembled site.

The filename token is the first 8 lowercase hex characters of SHA-256 over the
file bytes, for example styles/main.css -> styles/main.<sha8>.css. Source files
in the repository stay unhashed; only the deploy assembly renames them.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

HASH_LEN = 8
# Unhashed names kept in the assembly so HTML cached from before fingerprinting
# still resolves. Their bytes are the current release; new HTML must not use them.
TRANSITION_ALIASES = ("styles/main.css", "assets/nav.js")
_FINGERPRINT = re.compile(
    rf"^(?P<stem>.+)\.(?P<hash>[0-9a-f]{{{HASH_LEN}}})\.(?P<ext>css|js)$"
)
_CSS_URL = re.compile(r"""url\(\s*['"]?([^'")\s]+)['"]?\s*\)""", re.IGNORECASE)
_CSS_IMPORT = re.compile(
    r"""@import\s+(?:url\(\s*)?['"]([^'"]+)['"]""",
    re.IGNORECASE,
)
_JS_QUOTED_ASSET = re.compile(r"""['"]([^'"]+\.(?:css|js))['"]""", re.IGNORECASE)


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:HASH_LEN]


def unhashed_name(rel_posix: str) -> str | None:
    """Map styles/main.<sha8>.css back to styles/main.css, if it is fingerprinted."""
    parent, name = posixpath.split(rel_posix)
    match = _FINGERPRINT.fullmatch(name)
    if match is None:
        return None
    plain = f"{match.group('stem')}.{match.group('ext')}"
    return posixpath.join(parent, plain) if parent else plain


def hashed_relative(rel_posix: str, data: bytes) -> str:
    """Return rel_posix with .<sha8> inserted before the final extension."""
    parent, name = posixpath.split(rel_posix)
    stem, ext = posixpath.splitext(name)
    filename = f"{stem}.{content_hash(data)}{ext}"
    return posixpath.join(parent, filename) if parent else filename


def local_css_js_path(url: str) -> str | None:
    """URL path of a same-site CSS/JS reference, or None when it is external."""
    parts = urlsplit(url.strip())
    if parts.scheme in {"http", "https", "data"} or parts.netloc:
        return None
    path = unquote(parts.path)
    if not re.search(r"\.(?:css|js)$", path, re.IGNORECASE):
        return None
    return path


def site_relative_key(doc_rel_posix: str, url: str) -> str | None:
    """Map a reference in doc_rel_posix to a site-root relative CSS/JS path."""
    path = local_css_js_path(url)
    if path is None:
        return None
    if path.startswith("/"):
        norm = posixpath.normpath(path)
        if norm == "/" or not norm.startswith("/"):
            return None
        key = norm[1:]
    else:
        base = posixpath.dirname(doc_rel_posix)
        norm = posixpath.normpath(posixpath.join(base, path))
        if norm.startswith("../") or norm == "..":
            return None
        key = norm
    if not key or key == ".":
        return None
    return key


def rewrite_url(url: str, doc_rel_posix: str, mapping: dict[str, str]) -> str:
    """Replace a local CSS/JS URL path when mapping contains its site-relative key."""
    key = site_relative_key(doc_rel_posix, url)
    if key is None or key not in mapping:
        return url
    path = local_css_js_path(url)
    if path is None or path not in url:
        return url
    new_key = mapping[key]
    if path.startswith("/"):
        new_path = "/" + new_key
    elif path.startswith("./"):
        new_path = "./" + new_key
    else:
        base = posixpath.dirname(doc_rel_posix)
        new_path = new_key if base in {"", "."} else posixpath.relpath(new_key, base)
    return url.replace(path, new_path, 1)


def chained_local_css_js(text: str, doc_rel: str, suffix: str) -> list[str]:
    """Local CSS/JS paths referenced from inside a CSS or JS file."""
    urls: list[str] = []
    if suffix == ".css":
        urls.extend(match.group(1) for match in _CSS_URL.finditer(text))
        urls.extend(match.group(1) for match in _CSS_IMPORT.finditer(text))
    elif suffix == ".js":
        urls.extend(match.group(1) for match in _JS_QUOTED_ASSET.finditer(text))
    return [url for url in urls if site_relative_key(doc_rel, url) is not None]


class _HtmlRefs(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name in {"href", "src"} and value:
                self.urls.append(value)


def html_reference_urls(text: str) -> list[str]:
    parser = _HtmlRefs()
    parser.feed(text)
    return parser.urls


def _json_strings(node: object) -> list[str]:
    found: list[str] = []
    if isinstance(node, str):
        found.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            found.extend(_json_strings(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(_json_strings(value))
    return found


def manifest_reference_urls(text: str) -> list[str]:
    return _json_strings(json.loads(text))


def check_fingerprints(root: Path) -> list[str]:
    """Fail when HTML or a manifest points at unhashed, missing, or mismatched CSS/JS.

    External stylesheets (for example fonts.googleapis.com) are ignored. A name
    counts as fingerprinted only when it ends in .<8 lowercase hex>.css or .js
    and those 8 characters are the SHA-256 prefix of the file bytes.
    """
    failures: list[str] = []
    documents = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix in {".html", ".webmanifest"}
        ),
        key=lambda path: path.as_posix(),
    )
    for path in documents:
        doc_rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".html":
            urls = html_reference_urls(text)
        else:
            try:
                urls = manifest_reference_urls(text)
            except json.JSONDecodeError as exc:
                failures.append(f"{doc_rel}: invalid webmanifest ({exc})")
                continue
        for url in urls:
            key = site_relative_key(doc_rel, url)
            if key is None:
                continue
            name = posixpath.basename(key)
            match = _FINGERPRINT.fullmatch(name)
            target = root.joinpath(*key.split("/"))
            where = f"{doc_rel}: {url}"
            if match is None:
                failures.append(f"{where} references unhashed CSS/JS asset {key}")
                continue
            if not target.is_file():
                failures.append(f"{where} references missing CSS/JS asset {key}")
                continue
            actual = content_hash(target.read_bytes())
            if actual != match.group("hash"):
                failures.append(
                    f"{where} content hash {actual} does not match filename {key}"
                )
    return failures


def _css_js_files(root: Path) -> list[Path]:
    return sorted(
        path
        for pattern in ("**/*.css", "**/*.js")
        for path in root.glob(pattern)
        if path.is_file()
    )


def _documents(root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix in {".html", ".webmanifest"}
        ),
        key=lambda path: path.as_posix(),
    )


def check_assembled(root: Path) -> list[str]:
    """Check an assembled _site: aliases, current HTML refs, and carry-forward.

    Transition aliases (styles/main.css, assets/nav.js) must exist and match the
    current hashed files. Every HTML or manifest CSS/JS reference must be one of
    those current hashed names. Other fingerprinted files are carry-forward
    copies: their filename hash must match their bytes, and HTML must not
    reference them.
    """
    failures: list[str] = []
    current: dict[str, str] = {}
    for alias in TRANSITION_ALIASES:
        path = root.joinpath(*alias.split("/"))
        if not path.is_file():
            failures.append(f"missing transition alias {alias}")
            continue
        data = path.read_bytes()
        hashed = hashed_relative(alias, data)
        current[alias] = hashed
        hashed_path = root.joinpath(*hashed.split("/"))
        if not hashed_path.is_file() or hashed_path.read_bytes() != data:
            failures.append(f"current hashed file {hashed} does not match alias {alias}")

    current_names = set(current.values())
    carried: set[str] = set()
    alias_set = set(TRANSITION_ALIASES)
    for path in _css_js_files(root):
        rel = path.relative_to(root).as_posix()
        if rel in alias_set:
            continue
        match = _FINGERPRINT.fullmatch(path.name)
        data = path.read_bytes()
        if match is None:
            failures.append(f"{rel} is an unhashed CSS/JS file and not a transition alias")
            continue
        actual = content_hash(data)
        kind = "current" if rel in current_names else "carried-forward"
        if actual != match.group("hash"):
            failures.append(f"{kind} file {rel} content hash {actual} does not match filename")
            continue
        if rel not in current_names:
            carried.add(rel)

    for path in _documents(root):
        doc_rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".html":
            urls = html_reference_urls(text)
        else:
            try:
                urls = manifest_reference_urls(text)
            except json.JSONDecodeError as exc:
                failures.append(f"{doc_rel}: invalid webmanifest ({exc})")
                continue
        for url in urls:
            key = site_relative_key(doc_rel, url)
            if key is None:
                continue
            where = f"{doc_rel}: {url}"
            if key in alias_set:
                failures.append(f"{where} references unhashed transition alias {key}")
                continue
            if key in current_names:
                target = root.joinpath(*key.split("/"))
                if not target.is_file():
                    failures.append(f"{where} references missing CSS/JS asset {key}")
                continue
            target = root.joinpath(*key.split("/"))
            name = posixpath.basename(key)
            match = _FINGERPRINT.fullmatch(name)
            plain = unhashed_name(key) if match is not None else None
            if plain in alias_set and plain not in current:
                continue
            if key in carried or (
                match is not None
                and target.is_file()
                and content_hash(target.read_bytes()) == match.group("hash")
            ):
                failures.append(f"{where} references carried-forward CSS/JS asset {key}")
                continue
            if match is None:
                failures.append(f"{where} references unhashed CSS/JS asset {key}")
                continue
            if not target.is_file():
                failures.append(f"{where} references missing CSS/JS asset {key}")
                continue
            actual = content_hash(target.read_bytes())
            failures.append(f"{where} content hash {actual} does not match filename {key}")
    return failures
