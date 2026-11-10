#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble the GitHub Pages site and content-hash CSS and JavaScript filenames.

Source files stay unhashed. The output directory (default ./_site) gets:

- current CSS and JS under name.<sha8>.ext
- the same current bytes at the unhashed paths (styles/main.css, assets/nav.js)
  so HTML cached from before fingerprinting still resolves
- the previous release's CSS and JS under their own content hashes, so HTML
  cached from that deploy still resolves

New HTML references only the current hashed names. The previous release is the
latest v* tag reachable from HEAD that is not HEAD itself, or main^1 when no
such tag exists.
"""

from __future__ import annotations

import re
import shutil
import subprocess
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
        # Keep the unhashed path as a transition alias of the current bytes.
        if not src.is_file():
            src.write_bytes(data)
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
        print(f"alias {src}")
    carry_forward(source, out, set(mapping.values()))
    return mapping


def _git(repo: Path, args: list[str], *, text: bool) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=text,
    )


def previous_revision(repo: Path) -> tuple[str, str] | None:
    """Latest v* tag reachable from HEAD that is not HEAD, else main's parent.

    Returns (display name, commit sha). None when git cannot see either.
    """
    head = _git(repo, ["rev-parse", "HEAD"], text=True)
    if head.returncode != 0:
        return None
    head_sha = head.stdout.strip()
    tags = _git(repo, ["tag", "--merged", "HEAD", "--sort=-v:refname"], text=True)
    if tags.returncode == 0:
        for name in tags.stdout.splitlines():
            if not name.startswith("v"):
                continue
            peeled = _git(repo, ["rev-parse", f"{name}^{{commit}}"], text=True)
            if peeled.returncode != 0:
                continue
            sha = peeled.stdout.strip()
            if sha and sha != head_sha:
                return name, sha
    for spec in ("main^1", "origin/main^1"):
        parent = _git(repo, ["rev-parse", "--verify", spec], text=True)
        if parent.returncode == 0 and parent.stdout.strip():
            return spec, parent.stdout.strip()
    return None


def place_carry_forward(
    out: Path,
    label: str,
    rel: str,
    data: bytes,
    current_names: set[str],
) -> None:
    """Write one previous-revision CSS/JS file under its content-hash name."""
    dest_rel = hashed_relative(rel, data)
    dest = out.joinpath(*dest_rel.split("/"))
    if dest.is_file() and dest.read_bytes() == data:
        note = "already present"
        if dest_rel in current_names:
            note = "already present; same bytes as current"
        print(f"carry-forward {label}: {rel} -> {dest_rel} ({note})")
        return
    if dest.is_file():
        print(
            f"carry-forward {label}: {rel} -> {dest_rel} "
            "skipped, path already has different bytes"
        )
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"carry-forward {label}: {rel} -> {dest_rel}")


def carry_forward(repo: Path, out: Path, current_names: set[str]) -> None:
    """Publish the previous release's CSS and JS under their hashed names."""
    found = previous_revision(repo)
    if found is None:
        print("carry-forward: skipped, no previous revision")
        return
    name, sha = found
    label = f"{name} ({sha[:12]})"
    print(f"carry-forward revision: {label}")
    listing = _git(repo, ["ls-tree", "-r", "--name-only", sha], text=True)
    if listing.returncode != 0:
        print(f"carry-forward {label}: skipped, cannot list files")
        return
    # Only files the site can request. src/worker.js is not published to Pages.
    paths = [
        line
        for line in listing.stdout.splitlines()
        if (line.startswith("styles/") and line.endswith(".css"))
        or (line.startswith("assets/") and line.endswith(".js"))
    ]
    if not paths:
        print(f"carry-forward {label}: no CSS or JS files")
        return
    for rel in paths:
        blob = _git(repo, ["cat-file", "blob", f"{sha}:{rel}"], text=False)
        if blob.returncode != 0:
            print(f"carry-forward {label}: {rel} skipped, file not in that revision")
            continue
        place_carry_forward(out, label, rel, blob.stdout, current_names)


def main() -> None:
    if len(sys.argv) > 2:
        raise SystemExit("usage: assemble_site.py [OUTPUT_DIR]")
    assemble(Path(sys.argv[1]) if len(sys.argv) == 2 else Path("_site"))


if __name__ == "__main__":
    main()
