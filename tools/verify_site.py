#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the static-site inputs that GitHub Pages deploys.

Without arguments, checks the source tree, where CSS and JS stay unhashed.
With a root (the assembled _site), every HTML or manifest reference to a local
CSS or JS file must be a content-hashed filename that exists and matches the
file bytes. `--self-test` assembles a temporary site and covers the failure cases.
"""

from html.parser import HTMLParser
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from assemble_site import place_carry_forward, previous_revision
from asset_hash import check_assembled, check_fingerprints, content_hash

_SOURCE_ONLY = {"assets/nav.js", "styles/main.css"}
_REQUIRED = [
    "index.html",
    "404.html",
    "privacy.html",
    "terms.html",
    "CNAME",
    ".nojekyll",
    "assets",
    "assets/logo.jpg",
    "assets/lifecycle/development.webp",
    "assets/lifecycle/simulation.webp",
    "assets/lifecycle/lab.webp",
    "assets/lifecycle/real-world.webp",
    "assets/nav.js",
    "favicon.ico",
    "site.webmanifest",
    "assets/favicon.svg",
    "assets/favicon-32.png",
    "assets/apple-touch-icon.png",
    "assets/icon-192.png",
    "assets/icon-512.png",
    "assets/og.png",
    "styles",
    "styles/main.css",
]
_PAGES = ["index.html", "404.html", "privacy.html", "terms.html"]


class Links(HTMLParser):
    """Collect IDs and same-page fragment links from the home page."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.fragments: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if "id" in attributes and attributes["id"] is not None:
            self.ids.add(attributes["id"])
        href = attributes.get("href", "")
        if tag == "a" and href is not None and href.startswith("#"):
            self.fragments.append(href[1:])


def _required(assembled: bool) -> list[str]:
    if assembled:
        return [path for path in _REQUIRED if path not in _SOURCE_ONLY]
    return list(_REQUIRED)


def check_tree(assembled: bool) -> None:
    missing = [path for path in _required(assembled) if not Path(path).exists()]
    if missing:
        raise SystemExit(f"Missing deploy inputs: {', '.join(missing)}")

    page = Links()
    page.feed(Path("index.html").read_text(encoding="utf-8"))
    unresolved = sorted(set(page.fragments) - page.ids)
    if unresolved:
        raise SystemExit(f"Unresolved fragment links: {', '.join(unresolved)}")

    if assembled:
        failures = check_assembled(Path("."))
        if failures:
            details = "\n".join(failures)
            raise SystemExit(f"Fingerprinted CSS/JS check failed:\n{details}")


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)


def self_test() -> int:
    """Assemble this repo and show that unhashed or missing CSS/JS refs fail."""
    repo = Path(__file__).resolve().parents[1]
    tools = Path(__file__).resolve().parent
    verify = Path(__file__).resolve()
    assemble = tools / "assemble_site.py"
    check_css = tools / "check_css.py"
    errors: list[str] = []
    source_bytes = {
        path: path.read_bytes()
        for path in [
            repo / "index.html",
            repo / "404.html",
            repo / "privacy.html",
            repo / "terms.html",
            repo / "styles" / "main.css",
            repo / "assets" / "nav.js",
            repo / "site.webmanifest",
        ]
    }

    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        assembled = tmp / "site"
        proc = _run([sys.executable, str(assemble), str(assembled)])
        assemble_log = proc.stdout
        if proc.returncode != 0:
            errors.append(f"assemble failed:\n{proc.stdout}{proc.stderr}")
        else:
            print(assemble_log.strip())
            proc = _run([sys.executable, str(verify), str(assembled)])
            if proc.returncode != 0:
                errors.append(
                    f"assembled site should pass:\n{proc.stdout}{proc.stderr}"
                )
            else:
                print("positive: assembled site passed fingerprint check")

            proc = _run([sys.executable, str(check_css), str(assembled)])
            if proc.returncode != 0:
                errors.append(f"assembled CSS brace check failed:\n{proc.stdout}{proc.stderr}")
            else:
                print(proc.stdout.strip())

            css_hash = content_hash(source_bytes[repo / "styles" / "main.css"])
            js_hash = content_hash(source_bytes[repo / "assets" / "nav.js"])
            css_name = f"main.{css_hash}.css"
            js_name = f"nav.{js_hash}.js"
            hashed_css = assembled / "styles" / css_name
            hashed_js = assembled / "assets" / js_name
            if not hashed_css.is_file() or hashed_css.read_bytes() != source_bytes[repo / "styles" / "main.css"]:
                errors.append("assembled CSS is missing or does not match source bytes")
            if not hashed_js.is_file() or hashed_js.read_bytes() != source_bytes[repo / "assets" / "nav.js"]:
                errors.append("assembled JS is missing or does not match source bytes")
            alias_css = assembled / "styles" / "main.css"
            alias_js = assembled / "assets" / "nav.js"
            if not alias_css.is_file() or alias_css.read_bytes() != source_bytes[repo / "styles" / "main.css"]:
                errors.append("transition alias styles/main.css is missing or is not the current bytes")
            if not alias_js.is_file() or alias_js.read_bytes() != source_bytes[repo / "assets" / "nav.js"]:
                errors.append("transition alias assets/nav.js is missing or is not the current bytes")
            if (assembled / "src").exists() or any(assembled.rglob("worker*.js")):
                errors.append("assembly published src/worker.js")
            revision = previous_revision(repo)
            if revision is None:
                errors.append("carry-forward found no previous revision in this checkout")
            else:
                display, sha = revision
                marker = f"carry-forward revision: {display} ({sha[:12]})"
                if marker not in assemble_log:
                    errors.append(f"assemble log missing {marker!r}\n{assemble_log}")
            if (assembled / "site.webmanifest").read_bytes() != source_bytes[repo / "site.webmanifest"]:
                errors.append("manifest changed even though it references no CSS or JS")

            replacements = [(css_name, "main.css"), (js_name, "nav.js")]
            for name in _PAGES:
                restored = (assembled / name).read_text(encoding="utf-8")
                for hashed, original in replacements:
                    restored = restored.replace(hashed, original)
                if restored != source_bytes[repo / name].decode("utf-8"):
                    errors.append(f"{name} changed beyond the fingerprinted filename")
            page_404 = (assembled / "404.html").read_text(encoding="utf-8")
            index = (assembled / "index.html").read_text(encoding="utf-8")
            if f'/styles/{css_name}' not in page_404 or f'/assets/{js_name}' not in page_404:
                errors.append("404.html did not rewrite absolute CSS/JS paths")
            if "/styles/main.css" in page_404 or "/assets/nav.js" in page_404:
                errors.append("404.html still references an unhashed CSS or JS path")
            if f'href="styles/{css_name}"' not in index or "nav.js" in index:
                errors.append("index.html stylesheet reference was not fingerprinted")
            for name in ("privacy.html", "terms.html"):
                text = (assembled / name).read_text(encoding="utf-8")
                if (
                    f'href="styles/{css_name}"' not in text
                    or f'src="assets/{js_name}"' not in text
                    or 'href="styles/main.css"' in text
                    or 'src="assets/nav.js"' in text
                ):
                    errors.append(f"{name} CSS/JS references were not fingerprinted")

            unhashed = tmp / "unhashed"
            shutil.copytree(assembled, unhashed)
            unhashed_index = unhashed / "index.html"
            unhashed_index.write_text(
                unhashed_index.read_text(encoding="utf-8").replace(
                    f"styles/{css_name}", "styles/main.css"
                ),
                encoding="utf-8",
            )
            proc = _run([sys.executable, str(verify), str(unhashed)])
            output = proc.stderr + proc.stdout
            if proc.returncode == 0 or "unhashed" not in output or "transition alias" not in output:
                errors.append(f"unhashed alias reference should fail:\n{output}")
            else:
                print("negative: HTML reference to transition alias failed as expected")
                print(output.strip())

            missing = tmp / "missing"
            shutil.copytree(assembled, missing)
            missing_index = missing / "index.html"
            missing_index.write_text(
                missing_index.read_text(encoding="utf-8").replace(
                    f"styles/{css_name}", "styles/main.00000000.css"
                ),
                encoding="utf-8",
            )
            proc = _run([sys.executable, str(verify), str(missing)])
            output = proc.stderr + proc.stdout
            if proc.returncode == 0 or "missing" not in output:
                errors.append(f"missing fingerprinted asset should fail:\n{output}")
            else:
                print("negative: missing fingerprinted CSS failed as expected")
                print(output.strip())

            no_alias = tmp / "no-alias"
            shutil.copytree(assembled, no_alias)
            (no_alias / "styles" / "main.css").unlink()
            proc = _run([sys.executable, str(verify), str(no_alias)])
            output = proc.stderr + proc.stdout
            if proc.returncode == 0 or "missing transition alias" not in output:
                errors.append(f"missing transition alias should fail:\n{output}")
            else:
                print("negative: missing transition alias failed as expected")
                print(output.strip())

            carried_ok = tmp / "carried-ok"
            shutil.copytree(assembled, carried_ok)
            extra = b"/* previous release */\nbody{color:#123456}\n"
            extra_digest = content_hash(extra)
            extra_name = f"main.{extra_digest}.css"
            (carried_ok / "styles" / extra_name).write_bytes(extra)
            proc = _run([sys.executable, str(verify), str(carried_ok)])
            if proc.returncode != 0:
                errors.append(
                    f"unreferenced carry-forward file should pass:\n{proc.stdout}{proc.stderr}"
                )
            else:
                print("positive: unreferenced carry-forward file passed")

            carried_ref = tmp / "carried-ref"
            shutil.copytree(carried_ok, carried_ref)
            carried_index = carried_ref / "index.html"
            carried_index.write_text(
                carried_index.read_text(encoding="utf-8").replace(
                    f"styles/{css_name}", f"styles/{extra_name}"
                ),
                encoding="utf-8",
            )
            proc = _run([sys.executable, str(verify), str(carried_ref)])
            output = proc.stderr + proc.stdout
            if proc.returncode == 0 or "carried-forward" not in output:
                errors.append(f"HTML reference to carry-forward file should fail:\n{output}")
            else:
                print("negative: HTML reference to carry-forward file failed as expected")
                print(output.strip())

            carried_bad = tmp / "carried-bad"
            shutil.copytree(assembled, carried_bad)
            (carried_bad / "styles" / "main.0123abcd.css").write_bytes(b"not-the-hash\n")
            proc = _run([sys.executable, str(verify), str(carried_bad)])
            output = proc.stderr + proc.stdout
            if proc.returncode == 0 or "does not match" not in output or "carried-forward" not in output:
                errors.append(f"carry-forward hash mismatch should fail:\n{output}")
            else:
                print("negative: carry-forward hash mismatch failed as expected")
                print(output.strip())

            placed = tmp / "placed"
            (placed / "styles").mkdir(parents=True)
            previous_css = b"old-css\n"
            place_carry_forward(placed, "v0 (abc123def456)", "styles/main.css", previous_css, set())
            placed_name = f"main.{content_hash(previous_css)}.css"
            placed_file = placed / "styles" / placed_name
            if not placed_file.is_file() or placed_file.read_bytes() != previous_css:
                errors.append("carry-forward did not write a distinct previous hash")
            else:
                print(f"positive: distinct carry-forward file styles/{placed_name}")

        mismatch = tmp / "mismatch"
        (mismatch / "styles").mkdir(parents=True)
        body = b"body{color:#051722}\n"
        (mismatch / "styles" / "main.0123abcd.css").write_bytes(body)
        (mismatch / "index.html").write_text(
            '<link rel="stylesheet" href="styles/main.0123abcd.css" />\n',
            encoding="utf-8",
        )
        mismatch_failures = check_fingerprints(mismatch)
        if not any("does not match" in item for item in mismatch_failures):
            errors.append(f"hash mismatch should fail: {mismatch_failures}")
        else:
            print("negative: content hash mismatch failed as expected")
            print(mismatch_failures[0])

        external = tmp / "external"
        digest = content_hash(body)
        (external / "styles").mkdir(parents=True)
        (external / "styles" / f"main.{digest}.css").write_bytes(body)
        (external / "index.html").write_text(
            "\n".join(
                [
                    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=DM+Sans&display=swap" />',
                    f'<link rel="stylesheet" href="/styles/main.{digest}.css" />',
                ]
            ),
            encoding="utf-8",
        )
        external_failures = check_fingerprints(external)
        if external_failures:
            errors.append(f"external stylesheet should be ignored: {external_failures}")
        else:
            print("positive: external stylesheet ignored; absolute fingerprinted CSS passed")

    for path, data in source_bytes.items():
        if path.read_bytes() != data:
            errors.append(f"source file was modified: {path}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("self-test: ok")
    return 0


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        raise SystemExit(self_test())
    if len(sys.argv) > 2:
        raise SystemExit("usage: verify_site.py [--self-test | ASSEMBLED_ROOT]")
    assembled = len(sys.argv) == 2
    if assembled:
        os.chdir(sys.argv[1])
    check_tree(assembled)


if __name__ == "__main__":
    main()
