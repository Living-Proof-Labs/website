#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble the GitHub Pages site and content-hash CSS and JavaScript filenames.

Source files stay unhashed. The output directory (default ./_site) gets:

- current CSS and JS under name.<sha8>.ext
- the same current bytes at the unhashed paths (styles/main.css, assets/nav.js)
  so HTML cached from before fingerprinting still resolves
- CSS and JS from HEAD^1 and up to the two newest v* tags reachable from
  HEAD, excluding HEAD itself, under their own content hashes

The same content hash is written once. New HTML references only the current
hashed names. Assembly fails when none of those revisions can be resolved,
unless ASSEMBLE_FIRST_RUN=1 or --first-run is set for a first deploy.
"""

from __future__ import annotations

import os
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


def assemble(out: Path, *, first_run: bool = False) -> dict[str, str]:
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
    carry_forward(
        source,
        out,
        set(mapping.values()),
        first_run=first_run,
    )
    return mapping


def _git(repo: Path, args: list[str], *, text: bool) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=text,
    )


FIRST_RUN_ENV = "ASSEMBLE_FIRST_RUN"


def first_run_enabled(flag: bool = False) -> bool:
    """True when a first deploy with no parent and no v* tag is explicit."""
    if flag:
        return True
    return os.environ.get(FIRST_RUN_ENV, "").strip().lower() in {"1", "true", "yes"}


def carry_forward_revisions(repo: Path) -> list[tuple[str, str]]:
    """HEAD^1, then the two newest v* tags reachable from HEAD excluding HEAD.

    Each item is (label, full commit sha). The same sha may appear twice when
    HEAD^1 is also a tag. Empty when git cannot see a first parent or an
    eligible tag, which is a root commit or a checkout without that history.
    """
    head = _git(repo, ["rev-parse", "--verify", "HEAD"], text=True)
    if head.returncode != 0:
        return []
    head_sha = head.stdout.strip()
    revisions: list[tuple[str, str]] = []
    parent = _git(repo, ["rev-parse", "--verify", "HEAD^1"], text=True)
    if parent.returncode == 0 and parent.stdout.strip():
        revisions.append(("HEAD^1", parent.stdout.strip()))
    tags = _git(repo, ["tag", "--merged", "HEAD", "--sort=-v:refname"], text=True)
    if tags.returncode == 0:
        kept = 0
        for name in tags.stdout.splitlines():
            if not name.startswith("v"):
                continue
            peeled = _git(repo, ["rev-parse", "--verify", f"{name}^{{commit}}"], text=True)
            if peeled.returncode != 0:
                continue
            sha = peeled.stdout.strip()
            if not sha or sha == head_sha:
                continue
            revisions.append((name, sha))
            kept += 1
            if kept == 2:
                break
    return revisions


def list_revision_assets(repo: Path, sha: str) -> tuple[list[tuple[str, bytes]], str | None]:
    """CSS and JS a browser could have cached from sha.

    src/worker.js is not published to Pages and is ignored. The second value
    is an error string when the revision cannot be read.
    """
    listing = _git(repo, ["ls-tree", "-r", "--name-only", sha], text=True)
    if listing.returncode != 0:
        return [], "cannot list files"
    paths = [
        line
        for line in listing.stdout.splitlines()
        if (line.startswith("styles/") and line.endswith(".css"))
        or (line.startswith("assets/") and line.endswith(".js"))
    ]
    assets: list[tuple[str, bytes]] = []
    for rel in paths:
        blob = _git(repo, ["cat-file", "blob", f"{sha}:{rel}"], text=False)
        data = blob.stdout
        if blob.returncode != 0 or not isinstance(data, bytes):
            return [], f"{rel} not in that revision"
        assets.append((rel, data))
    return assets, None


def place_carry_forward(
    out: Path,
    label: str,
    rel: str,
    data: bytes,
    current_names: set[str],
) -> None:
    """Write one previous-revision CSS/JS file under its content-hash name.

    The same bytes are stored once. A path that already holds different bytes
    is a mismatch and fails the assembly.
    """
    dest_rel = hashed_relative(rel, data)
    dest = out.joinpath(*dest_rel.split("/"))
    if dest.is_file():
        existing = dest.read_bytes()
        if existing == data:
            if dest_rel in current_names:
                note = "deduped, same content hash as current"
            else:
                note = "deduped, same content hash"
            print(f"carry-forward {label}: {rel} -> {dest_rel} ({note})")
            return
        raise SystemExit(
            f"carry-forward {label}: {rel} -> {dest_rel} mismatched existing bytes"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"carry-forward {label}: {rel} -> {dest_rel}")


def carry_forward(
    repo: Path,
    out: Path,
    current_names: set[str],
    *,
    first_run: bool,
) -> None:
    """Publish HEAD^1 and recent tags' CSS and JS under their hashed names."""
    revisions = carry_forward_revisions(repo)
    if not revisions:
        if first_run:
            print(
                "carry-forward: first-run override, no previous revision "
                "(HEAD^1 or a v* tag)"
            )
            return
        raise SystemExit(
            "carry-forward: no previous revision (HEAD^1 or a v* tag). "
            "Refusing to publish a site that drops CSS and JS that cached HTML may "
            "still request. Set ASSEMBLE_FIRST_RUN=1 or pass --first-run for the "
            "first deploy only."
        )
    summary = ", ".join(f"{name} ({sha[:12]})" for name, sha in revisions)
    print(f"carry-forward revisions: {summary}")
    for name, sha in revisions:
        label = f"{name} ({sha[:12]})"
        print(f"carry-forward revision: {label}")
        assets, error = list_revision_assets(repo, sha)
        if error is not None:
            raise SystemExit(f"carry-forward {label}: {error}")
        if not assets:
            print(f"carry-forward {label}: no CSS or JS files")
            continue
        for rel, data in assets:
            place_carry_forward(out, label, rel, data, current_names)


def main() -> None:
    args = sys.argv[1:]
    flag = "--first-run" in args
    args = [arg for arg in args if arg != "--first-run"]
    if len(args) > 1:
        raise SystemExit("usage: assemble_site.py [--first-run] [OUTPUT_DIR]")
    assemble(
        Path(args[0]) if args else Path("_site"),
        first_run=first_run_enabled(flag),
    )


if __name__ == "__main__":
    main()
