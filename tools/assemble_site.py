#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble the GitHub Pages site and content-hash CSS and JavaScript filenames.

Source files stay unhashed. The output directory (default ./_site) gets copies
whose CSS and JS names include the first 8 hex characters of SHA-256 over the
file bytes. href and src in HTML, and string values in the web manifest, are
rewritten to those names. Other asset bytes are copied unchanged.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

from asset_hash import chained_local_css_js, hashed_relative, rewrite_url

ROOT_FILES = [
    "index.html",
    "404.html",
    "privacy.html",
    "terms.html",
    "CNAME",
    ".nojekyll",
    "favicon.ico",
    "site.webmanifest",
]
COPY_TREES = ["assets", "styles"]
_ATTR = re.compile(
    r"""(\b(?:href|src)\s*=\s*)(["'])([^"']*)(\2)""",
    re.IGNORECASE,
)
_JSON_STRING = re.compile(r'"((?:\\.|[^"\\])*)"')


def _source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _assert_safe_output(source: Path, out: Path) -> None:
    if out == source or _is_inside(source, out):
        raise SystemExit(f"refusing to assemble over {out}")
    protected = [source / name for name in ROOT_FILES]
    protected.extend(source / name for name in COPY_TREES)
    protected.append(source / ".git")
    for path in protected:
        if out == path or _is_inside(path, out):
            raise SystemExit(f"refusing to assemble over source path {path}")


def _rewrite_html(text: str, doc_rel: str, mapping: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        url = match.group(3)
        rewritten = rewrite_url(url, doc_rel, mapping)
        if rewritten == url:
            return match.group(0)
        quote = match.group(2)
        return f"{match.group(1)}{quote}{rewritten}{quote}"

    return _ATTR.sub(replace, text)


def _rewrite_manifest(text: str, doc_rel: str, mapping: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(1)
        if "\\" in raw:
            return match.group(0)
        rewritten = rewrite_url(raw, doc_rel, mapping)
        if rewritten == raw:
            return match.group(0)
        return f'"{rewritten}"'

    return _JSON_STRING.sub(replace, text)


def _fingerprint(out: Path) -> dict[str, str]:
    assets = sorted(
        path
        for pattern in ("**/*.css", "**/*.js")
        for path in out.glob(pattern)
        if path.is_file()
    )
    mapping: dict[str, str] = {}
    staged: list[tuple[Path, str, bytes]] = []
    for path in assets:
        rel = path.relative_to(out).as_posix()
        data = path.read_bytes()
        chained = chained_local_css_js(data.decode("utf-8"), rel, path.suffix)
        if chained:
            joined = ", ".join(chained)
            raise SystemExit(
                f"{rel} references local CSS/JS ({joined}); "
                "the assembler only rewrites HTML and manifest references"
            )
        dest_rel = hashed_relative(rel, data)
        if dest_rel in mapping.values():
            raise SystemExit(f"fingerprint collision for {dest_rel}")
        mapping[rel] = dest_rel
        staged.append((path, dest_rel, data))
    for src, dest_rel, data in staged:
        dest = out.joinpath(*dest_rel.split("/"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if src.resolve() != dest.resolve():
            src.unlink()
    return mapping


def assemble(out: Path) -> dict[str, str]:
    source = _source_root()
    out = out if out.is_absolute() else Path.cwd() / out
    out = out.resolve()
    _assert_safe_output(source, out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in ROOT_FILES:
        shutil.copy2(source / name, out / name)
    for tree in COPY_TREES:
        shutil.copytree(source / tree, out / tree)

    mapping = _fingerprint(out)
    for path in sorted(out.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(out).as_posix()
        if path.suffix == ".html":
            original = path.read_text(encoding="utf-8")
            rewritten = _rewrite_html(original, rel, mapping)
        elif path.suffix == ".webmanifest":
            original = path.read_text(encoding="utf-8")
            rewritten = _rewrite_manifest(original, rel, mapping)
        else:
            continue
        if rewritten != original:
            path.write_text(rewritten, encoding="utf-8")
    for src, dest in sorted(mapping.items()):
        print(f"{src} -> {dest}")
    return mapping


def main() -> None:
    if len(sys.argv) > 2:
        raise SystemExit("usage: assemble_site.py [OUTPUT_DIR]")
    assemble(Path(sys.argv[1]) if len(sys.argv) == 2 else Path("_site"))


if __name__ == "__main__":
    main()
