#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the static-site inputs that GitHub Pages deploys.

Without arguments, checks the source tree, where CSS and JS stay unhashed.
With a root (the assembled _site), every HTML or manifest reference to a local
CSS or JS file must be a content-hashed filename that exists and matches the
file bytes. Inside a git checkout, CSS and JS from HEAD^1 and the two newest
v* tags must be present under their content hashes. That check fails when no
previous revision is visible unless --first-run or ASSEMBLE_FIRST_RUN is set.
`--self-test` assembles a temporary site and covers the failure cases.
"""

from html.parser import HTMLParser
from contextlib import redirect_stdout
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from assemble_site import (
    carry_forward_revisions,
    first_run_enabled,
    list_revision_assets,
    place_carry_forward,
)
from asset_hash import (
    TRANSITION_ALIASES,
    check_assembled,
    check_fingerprints,
    content_hash,
    hashed_relative,
    unhashed_name,
)

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


def check_tree(assembled: bool, *, first_run: bool = False) -> None:
    missing = [path for path in _required(assembled) if not Path(path).exists()]
    if missing:
        raise SystemExit(f"Missing deploy inputs: {', '.join(missing)}")

    page = Links()
    page.feed(Path("index.html").read_text(encoding="utf-8"))
    unresolved = sorted(set(page.fragments) - page.ids)
    if unresolved:
        raise SystemExit(f"Unresolved fragment links: {', '.join(unresolved)}")

    if assembled:
        root = Path(".")
        failures = check_assembled(root)
        failures.extend(check_unique_hashed_assets(root))
        repo = _git_root(root)
        if repo is not None:
            failures.extend(
                check_revision_carry_forward(repo, root, first_run=first_run)
            )
        if failures:
            details = "\n".join(failures)
            raise SystemExit(f"Fingerprinted CSS/JS check failed:\n{details}")


def _run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, env=env)


def _git_root(start: Path) -> Path | None:
    proc = _run(["git", "-C", str(start), "rev-parse", "--show-toplevel"])
    if proc.returncode != 0:
        return None
    path = Path(proc.stdout.strip())
    return path if path.is_dir() else None


def check_unique_hashed_assets(root: Path) -> list[str]:
    """Fingerprinted CSS/JS bytes match their names and are stored once.

    Transition aliases are the same bytes as the current hashed files and are
    not counted. Two fingerprinted files with identical bytes are a duplicate.
    A filename whose hash is not the SHA-256 prefix of its bytes is a mismatch.
    """
    failures: list[str] = []
    seen: dict[bytes, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in {".css", ".js"}:
            continue
        rel = path.relative_to(root).as_posix()
        if rel in TRANSITION_ALIASES:
            continue
        data = path.read_bytes()
        plain = unhashed_name(rel)
        if plain is None:
            failures.append(f"unhashed CSS/JS file is not a transition alias: {rel}")
            continue
        if hashed_relative(plain, data) != rel:
            failures.append(
                f"mismatched file {rel}: content hash {content_hash(data)} "
                "does not match filename"
            )
            continue
        prior = seen.get(data)
        if prior is not None:
            failures.append(f"duplicate content hash in {prior} and {rel}")
            continue
        seen[data] = rel
    return failures


def check_revision_carry_forward(repo: Path, root: Path, *, first_run: bool) -> list[str]:
    """Require hashed CSS/JS from HEAD^1 and the two newest eligible v* tags."""
    revisions = carry_forward_revisions(repo)
    if not revisions:
        if first_run:
            return []
        return [
            "no previous revision (HEAD^1 or a v* tag); "
            "pass --first-run or set ASSEMBLE_FIRST_RUN=1 for the first deploy only"
        ]
    failures: list[str] = []
    for name, sha in revisions:
        label = f"{name} ({sha[:12]})"
        assets, error = list_revision_assets(repo, sha)
        if error is not None:
            failures.append(f"carry-forward {label}: {error}")
            continue
        for rel, data in assets:
            dest_rel = hashed_relative(rel, data)
            dest = root.joinpath(*dest_rel.split("/"))
            kind = (
                "HEAD^1 carry-forward"
                if name == "HEAD^1"
                else f"carry-forward from {label}"
            )
            if not dest.is_file():
                failures.append(f"missing {kind} {dest_rel}")
            elif dest.read_bytes() != data:
                failures.append(f"mismatched {kind} {dest_rel}")
    return failures


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
            revisions = carry_forward_revisions(repo)
            if not revisions:
                errors.append("carry-forward found no previous revision in this checkout")
            else:
                labels = [label for label, _sha in revisions]
                print(
                    "carry-forward revisions: "
                    + ", ".join(f"{label} ({sha[:12]})" for label, sha in revisions)
                )
                if labels[0] != "HEAD^1":
                    errors.append(f"carry-forward revisions do not start with HEAD^1: {labels}")
                tags = [label for label in labels if label.startswith("v")]
                if len(tags) != 2:
                    errors.append(f"expected the last 2 v* tags, got {tags}")
                head_sha = _run(["git", "-C", str(repo), "rev-parse", "HEAD"]).stdout.strip()
                if any(sha == head_sha for _label, sha in revisions):
                    errors.append("HEAD itself was included in carry-forward")
                for display, sha in revisions:
                    marker = f"carry-forward revision: {display} ({sha[:12]})"
                    if marker not in assemble_log:
                        errors.append(f"assemble log missing {marker!r}\n{assemble_log}")
                history = check_revision_carry_forward(repo, assembled, first_run=False)
                if history:
                    errors.append(
                        "assembled site failed carry-forward history check:\n"
                        + "\n".join(history)
                    )
                else:
                    print("positive: HEAD^1 and the last 2 tags are carried forward")
                unique = check_unique_hashed_assets(assembled)
                if unique:
                    errors.append(
                        "real assembly has duplicate or mismatched files:\n"
                        + "\n".join(unique)
                    )
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

            deduped_dir = tmp / "deduped"
            (deduped_dir / "styles").mkdir(parents=True)
            dedupe_log = io.StringIO()
            with redirect_stdout(dedupe_log):
                place_carry_forward(
                    deduped_dir, "v0.0.2 (aaaaaaaaaaaa)", "styles/main.css", previous_css, set()
                )
                place_carry_forward(
                    deduped_dir, "v0.0.1 (bbbbbbbbbbbb)", "styles/main.css", previous_css, set()
                )
            deduped_files = list((deduped_dir / "styles").glob("*.css"))
            dedupe_text = dedupe_log.getvalue()
            if (
                len(deduped_files) != 1
                or deduped_files[0].read_bytes() != previous_css
                or "deduped, same content hash" not in dedupe_text
                or check_unique_hashed_assets(deduped_dir)
            ):
                errors.append(f"place_carry_forward did not dedupe:\n{dedupe_text}")
            else:
                print("dedupe: identical content left one matching file")

            collision = tmp / "collision"
            (collision / "styles").mkdir(parents=True)
            collision_rel = hashed_relative("styles/main.css", previous_css)
            collision_path = collision.joinpath(*collision_rel.split("/"))
            collision_path.write_bytes(b"different-bytes\n")
            try:
                place_carry_forward(
                    collision, "HEAD^1 (abc123def456)", "styles/main.css", previous_css, set()
                )
            except SystemExit as exc:
                if "mismatched" not in str(exc):
                    errors.append(f"carry-forward byte mismatch raised the wrong error: {exc}")
                else:
                    print("negative: carry-forward byte mismatch failed as expected")
                    print(str(exc))
            else:
                errors.append("mismatched carry-forward bytes should fail")

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

    _carry_forward_fixture_tests(repo, errors)

    for path, data in source_bytes.items():
        if path.read_bytes() != data:
            errors.append(f"source file was modified: {path}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("self-test: ok")
    return 0


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.name=Carry Forward",
        "-c",
        "user.email=carry-forward@example.com",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        message,
    )


def _tag(repo: Path, name: str) -> None:
    _git(repo, "-c", "tag.gpgsign=false", "tag", name)


def _seed_site(dest: Path, source: Path) -> None:
    for name in (
        "index.html",
        "404.html",
        "privacy.html",
        "terms.html",
        "CNAME",
        ".nojekyll",
        "favicon.ico",
        "site.webmanifest",
    ):
        shutil.copy2(source / name, dest / name)
    shutil.copytree(source / "assets", dest / "assets")
    shutil.copytree(source / "styles", dest / "styles")
    tools = dest / "tools"
    tools.mkdir()
    for name in ("assemble_site.py", "asset_hash.py", "verify_site.py"):
        shutil.copy2(source / "tools" / name, tools / name)


def _mark(path: Path, marker: str) -> None:
    text = path.read_text(encoding="utf-8")
    needle = "/* carry-forward-marker:"
    if needle in text:
        text = text[: text.rindex(needle)].rstrip() + "\n"
    path.write_text(f"{text}\n/* carry-forward-marker: {marker} */\n", encoding="utf-8")


def _blob(repo: Path, rev: str, rel: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "blob", f"{rev}:{rel}"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode())
    return proc.stdout


def _css_js_files(root: Path) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    for folder in ("styles", "assets"):
        for path in (root / folder).rglob("*"):
            if path.is_file() and path.suffix in {".css", ".js"}:
                found[path.relative_to(root).as_posix()] = path.read_bytes()
    return found


def _carry_forward_fixture_tests(source: Path, errors: list[str]) -> None:
    """Negative cases that need a git history different from this checkout."""
    try:
        _history_fixture(source, errors)
        _first_run_fixture(source, errors)
    except RuntimeError as exc:
        errors.append(f"carry-forward fixture failed: {exc}")


def _history_fixture(source: Path, errors: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        repo = Path(tmp_name) / "repo"
        repo.mkdir()
        _seed_site(repo, source)
        _git(repo, "init", "-b", "main")
        _mark(repo / "styles" / "main.css", "A")
        _mark(repo / "assets" / "nav.js", "J1")
        _commit(repo, "base")
        _tag(repo, "v0.0.1")

        index = repo / "index.html"
        index.write_text(index.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        _commit(repo, "same css and js")
        _tag(repo, "v0.0.2")

        _mark(repo / "styles" / "main.css", "C")
        _commit(repo, "head parent")

        _mark(repo / "styles" / "main.css", "D")
        _mark(repo / "assets" / "nav.js", "J2")
        _commit(repo, "head")
        _tag(repo, "v9.9.9")

        assemble = repo / "tools" / "assemble_site.py"
        verify = repo / "tools" / "verify_site.py"
        site = repo / "_site"
        proc = _run([sys.executable, str(assemble), str(site)])
        log = proc.stdout + proc.stderr
        if proc.returncode != 0:
            errors.append(f"history fixture assemble failed:\n{log}")
            return
        for label in ("HEAD^1", "v0.0.2", "v0.0.1"):
            if f"carry-forward revision: {label} (" not in log:
                errors.append(f"history fixture log missing {label}:\n{log}")
        if "carry-forward revision: v9.9.9 (" in log:
            errors.append("history fixture carried the tag on HEAD")
        if "deduped, same content hash" not in log:
            errors.append(f"history fixture did not dedupe:\n{log}")

        css_a = _blob(repo, "v0.0.1", "styles/main.css")
        css_c = _blob(repo, "HEAD^1", "styles/main.css")
        css_d = _blob(repo, "HEAD", "styles/main.css")
        js_1 = _blob(repo, "v0.0.1", "assets/nav.js")
        js_2 = _blob(repo, "HEAD", "assets/nav.js")
        if css_a != _blob(repo, "v0.0.2", "styles/main.css"):
            errors.append("history fixture tags were supposed to share CSS bytes")
            return
        expected = {
            "styles/main.css": css_d,
            hashed_relative("styles/main.css", css_d): css_d,
            hashed_relative("styles/main.css", css_a): css_a,
            hashed_relative("styles/main.css", css_c): css_c,
            "assets/nav.js": js_2,
            hashed_relative("assets/nav.js", js_2): js_2,
            hashed_relative("assets/nav.js", js_1): js_1,
        }
        actual = _css_js_files(site)
        identity = check_unique_hashed_assets(site)
        if actual != expected or identity:
            errors.append(
                "dedupe left duplicate or mismatched files:\n"
                f"expected {sorted(expected)}\nactual {sorted(actual)}\n{identity}"
            )
        else:
            print("dedupe: no duplicate or mismatched files")

        carried_css = hashed_relative("styles/main.css", css_c)
        current_css = hashed_relative("styles/main.css", css_d)
        index_html = (site / "index.html").read_text(encoding="utf-8")
        if (
            f"styles/{Path(current_css).name}" not in index_html
            or f"styles/{Path(carried_css).name}" in index_html
            or 'href="styles/main.css"' in index_html
        ):
            errors.append("history fixture HTML does not reference only the current hash")

        proc = _run([sys.executable, str(verify), str(site)])
        if proc.returncode != 0:
            errors.append(
                f"history fixture verify should pass:\n{proc.stdout}{proc.stderr}"
            )

        head_file = site.joinpath(*carried_css.split("/"))
        saved = head_file.read_bytes()
        head_file.unlink()
        proc = _run([sys.executable, str(verify), str(site)])
        output = proc.stdout + proc.stderr
        if proc.returncode == 0 or "missing HEAD^1 carry-forward" not in output:
            errors.append(f"missing HEAD^1 carry-forward should fail:\n{output}")
        else:
            print("negative: missing HEAD^1 carry-forward failed as expected")
            print(output.strip())
        head_file.write_bytes(saved)

        duplicate = site.joinpath(*hashed_relative("assets/main.css", css_a).split("/"))
        duplicate.write_bytes(css_a)
        identity = check_unique_hashed_assets(site)
        proc = _run([sys.executable, str(verify), str(site)])
        output = proc.stdout + proc.stderr
        if (
            proc.returncode == 0
            or not any("duplicate" in item for item in identity)
            or "duplicate" not in output
        ):
            errors.append(f"duplicate hashed file should fail:\n{identity}\n{output}")
        else:
            print("negative: duplicate hashed file failed as expected")
            print(output.strip())
        duplicate.unlink()

        head_file.write_bytes(b"not-the-bytes\n")
        identity = check_unique_hashed_assets(site)
        proc = _run([sys.executable, str(verify), str(site)])
        output = proc.stdout + proc.stderr
        if proc.returncode == 0 or not any("mismatched" in item for item in identity):
            errors.append(f"dedupe mismatch should fail:\n{identity}\n{output}")
        elif "mismatched" not in output:
            errors.append(f"verify should report the dedupe mismatch:\n{output}")
        else:
            print("negative: dedupe mismatch failed as expected")
            print(output.strip())


def _first_run_fixture(source: Path, errors: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp_name:
        repo = Path(tmp_name) / "repo"
        repo.mkdir()
        _seed_site(repo, source)
        _git(repo, "init", "-b", "main")
        _commit(repo, "only")
        assemble = repo / "tools" / "assemble_site.py"
        verify = repo / "tools" / "verify_site.py"
        site = repo / "_site"

        proc = _run([sys.executable, str(assemble), str(site)])
        output = proc.stdout + proc.stderr
        if proc.returncode == 0 or "no previous revision" not in output:
            errors.append(f"assemble without previous revision should fail:\n{output}")
        else:
            print("negative: no previous revision without the override failed assemble")
            print(output.strip())

        proc = _run([sys.executable, str(verify), str(site)])
        output = proc.stdout + proc.stderr
        if proc.returncode == 0 or "no previous revision" not in output:
            errors.append(f"verify without previous revision should fail:\n{output}")
        else:
            print("negative: no previous revision without the override failed verify")
            print(output.strip())

        proc = _run([sys.executable, str(assemble), "--first-run", str(site)])
        if proc.returncode != 0 or "first-run override" not in proc.stdout:
            errors.append(
                f"assemble --first-run should pass:\n{proc.stdout}{proc.stderr}"
            )
            return
        proc = _run([sys.executable, str(verify), "--first-run", str(site)])
        if proc.returncode != 0:
            errors.append(f"verify --first-run should pass:\n{proc.stdout}{proc.stderr}")
        else:
            print("positive: --first-run override passed assemble and verify")

        site_env = repo / "_site_env"
        env = os.environ.copy()
        env["ASSEMBLE_FIRST_RUN"] = "1"
        proc = _run([sys.executable, str(assemble), str(site_env)], env=env)
        if proc.returncode != 0 or "first-run override" not in proc.stdout:
            errors.append(
                f"ASSEMBLE_FIRST_RUN assemble should pass:\n{proc.stdout}{proc.stderr}"
            )
            return
        proc = _run([sys.executable, str(verify), str(site_env)], env=env)
        if proc.returncode != 0:
            errors.append(
                f"ASSEMBLE_FIRST_RUN verify should pass:\n{proc.stdout}{proc.stderr}"
            )
        else:
            print("positive: ASSEMBLE_FIRST_RUN override passed assemble and verify")

        proc = _run([sys.executable, str(verify), str(site_env)])
        output = proc.stdout + proc.stderr
        if proc.returncode == 0 or "no previous revision" not in output:
            errors.append(f"verify must still fail when the override is unset:\n{output}")


def main() -> None:
    args = [arg for arg in sys.argv[1:] if arg != "--first-run"]
    first_run = first_run_enabled("--first-run" in sys.argv[1:])
    if args == ["--self-test"]:
        raise SystemExit(self_test())
    if len(args) > 1:
        raise SystemExit(
            "usage: verify_site.py [--self-test | [--first-run] [ASSEMBLED_ROOT]]"
        )
    assembled = len(args) == 1
    if assembled:
        os.chdir(args[0])
    check_tree(assembled, first_run=first_run)


if __name__ == "__main__":
    main()
