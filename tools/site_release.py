# SPDX-License-Identifier: Apache-2.0
"""Bind the same verified website build to its version and exact GitHub attempt."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile

STABLE = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
POS = r"[1-9][0-9]*"


def identity(version, commit, run, attempt):
    if not (
        re.fullmatch(rf"{STABLE}(?:-(?:pr\.{POS}|main)\.{POS}\.{POS})?", version)
        and re.fullmatch(r"[0-9a-f]{40}", commit)
        and all(re.fullmatch(POS, value) for value in (run, attempt))
    ):
        raise ValueError("Invalid website version, commit, run or attempt")
    return {
        "version": version,
        "source_commit": commit,
        "run_id": run,
        "run_attempt": attempt,
        "source_dirty": False,
    }


def stamp(site, version, commit, run, attempt):
    expected = identity(version, commit, run, attempt)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
    if head != commit or dirty:
        raise ValueError("Website version plan requires the exact clean checkout")
    for name in ("index.html", "404.html", "privacy.html", "terms.html"):
        page = site / name
        html = page.read_text(encoding="utf-8")
        if html.count("</footer>") != 1:
            raise ValueError(f"Cannot locate exactly one footer in {name}")
        href = f"https://github.com/Living-Proof-Labs/website/tree/{commit}"
        provenance = f'<p><a href="{href}">Site build {version}</a></p>'
        page.write_text(
            html.replace("</footer>", provenance + "\n</footer>"), encoding="utf-8"
        )
    (site / "build.json").write_text(
        json.dumps(expected, sort_keys=True) + "\n", encoding="utf-8"
    )


def check(path, version, commit, run, attempt, digest):
    expected = identity(version, commit, run, attempt)
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Missing or malformed website artifact digest")
    with path.open("rb") as stream:
        observed_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if observed_digest != digest:
        raise ValueError("Website artifact bytes differ from the verified build")
    with tarfile.open(path, mode="r:") as archive:
        items = [
            item
            for item in archive.getmembers()
            if item.name in ("build.json", "./build.json")
        ]
        if len(items) != 1 or not items[0].isfile():
            raise ValueError("Website artifact must contain one regular build identity")
        with archive.extractfile(items[0]) as stream:
            observed = json.load(stream)
    if observed != expected or observed["source_dirty"] is not False:
        raise ValueError(
            "Website artifact does not match its exact version, source, run and attempt"
        )


if __name__ == "__main__":
    operation, path, *values = sys.argv[1:]
    try:
        {"stamp": stamp, "check": check}[operation](Path(path), *values)
    except (KeyError, ValueError, OSError, tarfile.TarError, TypeError) as error:
        raise SystemExit(str(error)) from error
