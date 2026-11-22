# SPDX-License-Identifier: Apache-2.0
"""Local coverage for the shared website build and fail-closed deployment gates."""

import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import unittest

from site_release import check, identity

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
VERSION = "1.8.20"
RUN = "123"
ATTEMPT = "2"


def workflow(name):
    return (ROOT / ".github/workflows" / f"{name}.yml").read_text(encoding="utf-8")


def shell_step(text, name):
    block = text.split(f"      - name: {name}\n", 1)[1].split("\n      - ", 1)[0]
    _, body = block.split("        run: |\n", 1)
    return "\n".join(line[10:] for line in body.splitlines())


class WebsiteReleaseDeploy(unittest.TestCase):
    def test_writes_are_not_available_to_PR_or_read_only_replay(self):
        deploy, release, build = map(workflow, ("deploy", "release", "site-artifact"))
        self.assertNotRegex(deploy, re.compile(r"^  push:", re.MULTILINE))
        self.assertNotIn("workflow_dispatch", release)
        self.assertIn("needs: [verify, version, site]", release)
        self.assertIn(
            "needs.version.outputs.run-attempt == github.run_attempt", release
        )
        self.assertIn("needs.release.outputs.published == 'true'", release)
        self.assertIn("expected-version: ${{ needs.version.outputs.version }}", release)
        self.assertIn("expected-commit: ${{ needs.version.outputs.commit }}", release)
        self.assertIn("replay-tag: ${{ inputs.release_tag }}", deploy)
        self.assertIn("inputs.artifact_id || needs.site.outputs.artifact-id", deploy)
        self.assertNotIn("contents: write", deploy + build)
        self.assertNotIn("pages: write", build)
        self.assertNotIn("enablement:", deploy)
        self.assertNotIn("github-token:", deploy + build)
        self.assertLess(
            deploy.index("Require matching ID and name readback"),
            deploy.index("Require current main inside the deployment lock"),
        )
        self.assertLess(
            deploy.index("Require current main inside the deployment lock"),
            deploy.index("Deploy the verified website"),
        )
        self.assertIn("pages-artifact.outputs.artifact-id", deploy)
        self.assertIn("artifact_name: github-pages-${{ github.run_attempt }}", deploy)
        self.assertEqual(
            set(
                re.findall(
                    r"semantic-release(?:-candidate)?\.yml@(v[^ \n]+)", release + deploy
                )
            ),
            {"v9.9.2"},
        )

    def test_same_build_adds_preview_and_stable_identity_and_rejects_dirty_source(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            repo = root / "repo"
            repo.mkdir()
            for args in [
                ("init", "-q"),
                ("config", "user.name", "Fixture"),
                ("config", "user.email", "fixture@example.invalid"),
                ("commit", "--allow-empty", "-qm", "fixture"),
            ]:
                subprocess.run(["git", *args], cwd=repo, check=True)
            head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo, text=True
            ).strip()
            for version in (VERSION, VERSION + "-pr.57.12.2"):
                site = root / version
                site.mkdir()
                for page in ("index.html", "404.html", "privacy.html", "terms.html"):
                    (site / page).write_text("<footer>Keep branding</footer>")
                args = [
                    "python3",
                    str(ROOT / "tools/site_release.py"),
                    "stamp",
                    str(site),
                    version,
                    head,
                    RUN,
                    ATTEMPT,
                ]
                subprocess.run(args, cwd=repo, check=True)
                self.assertEqual(
                    json.loads((site / "build.json").read_text()),
                    identity(version, head, RUN, ATTEMPT),
                )
                self.assertIn(
                    f"Site build {version}", (site / "index.html").read_text()
                )
                self.assertIn("Keep branding", (site / "index.html").read_text())
                (repo / "untracked").touch()
                self.assertNotEqual(
                    subprocess.run(args, cwd=repo, capture_output=True).returncode, 0
                )
                (repo / "untracked").unlink()

    def test_archive_fails_on_changed_bytes_identity_and_duplicate_record(self):
        with tempfile.TemporaryDirectory() as work:
            archive = Path(work) / "artifact.tar"

            def seed(data, n=1):
                payload = json.dumps(data).encode()
                with tarfile.open(archive, "w") as tar:
                    for _ in range(n):
                        entry = tarfile.TarInfo("build.json")
                        entry.size = len(payload)
                        tar.addfile(entry, io.BytesIO(payload))
                return hashlib.sha256(archive.read_bytes()).hexdigest()

            expected = identity(VERSION, SHA, RUN, ATTEMPT)
            good = seed(expected)
            check(archive, VERSION, SHA, RUN, ATTEMPT, good)
            for delta in (
                {"source_commit": "b" * 40},
                {"source_dirty": True},
                {"run_attempt": "1"},
                {"version": "1.8.19"},
            ):
                digest = seed({**expected, **delta})
                with self.assertRaises(ValueError):
                    check(archive, VERSION, SHA, RUN, ATTEMPT, digest)
            with self.assertRaises(ValueError):
                check(archive, VERSION, SHA, RUN, ATTEMPT, seed(expected, n=2))
            with self.assertRaises(ValueError):
                check(archive, VERSION, SHA, RUN, ATTEMPT, "0" * 64)

    def test_final_runtime_name_and_id_must_both_match_tar_digest(self):
        script = shell_step(
            workflow("deploy"), "Require matching ID and name readback of the exact tar"
        )
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            name = "github-pages-2"
            a = root / "id" / name
            b = root / "name"
            a.mkdir(parents=True)
            b.mkdir()
            for folder in (a, b):
                (folder / "artifact.tar").write_bytes(b"sealed")
            env = {
                **os.environ,
                "ID_READBACK": str(a.parent),
                "NAME_READBACK": str(b),
                "EXPECTED_NAME": name,
                "EXPECTED_TAR": hashlib.sha256(b"sealed").hexdigest(),
            }
            self.assertEqual(
                subprocess.run(
                    ["bash", "-c", script], env=env, capture_output=True
                ).returncode,
                0,
            )
            (b / "artifact.tar").write_bytes(b"wrong")
            self.assertNotEqual(
                subprocess.run(
                    ["bash", "-c", script], env=env, capture_output=True
                ).returncode,
                0,
            )

    def test_stable_replay_requires_exact_tag_current_main_and_published_release(self):
        deploy = workflow("deploy")
        provenance = shell_step(
            deploy, "Require the published stable release and exact current-run source"
        )
        freshness = shell_step(
            deploy, "Require current main inside the deployment lock"
        )
        with tempfile.TemporaryDirectory() as work:
            repo = Path(work)
            for cmd in (
                ["init", "-q"],
                ["config", "user.name", "Fixture"],
                ["config", "user.email", "fixture@example.invalid"],
                ["commit", "--allow-empty", "-qm", "fixture"],
                ["tag", "-am", "Fixture tag", f"v{VERSION}"],
            ):
                subprocess.run(["git", *cmd], cwd=repo, check=True)
            head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=repo, text=True
            ).strip()
            gh = repo / "gh"
            gh.write_text(
                '#!/bin/sh\ncase "$2" in */releases/tags/*) printf "%s" "$RECORD";; */git/ref/heads/main) printf "%s" "$REMOTE";; *) exit 9;; esac\n'
            )
            gh.chmod(0o755)
            record = {
                "tag_name": f"v{VERSION}",
                "draft": False,
                "prerelease": False,
                "published_at": "2026-11-22T00:00:00Z",
            }
            env = {
                **os.environ,
                "PATH": f"{repo}:{os.environ['PATH']}",
                "GITHUB_SHA": head,
                "GITHUB_REPOSITORY": "example/fixture",
                "GITHUB_RUN_ID": RUN,
                "GITHUB_RUN_ATTEMPT": ATTEMPT,
                "SOURCE": head,
                "RELEASE_TAG": f"v{VERSION}",
                "VERSION": VERSION,
                "PLAN_RUN": RUN,
                "PLAN_ATTEMPT": ATTEMPT,
                "ARTIFACT_ID": "99",
                "RECORD": json.dumps(record),
                "REMOTE": head,
            }

            def run(script, **overrides):
                return subprocess.run(
                    ["bash", "-c", script],
                    cwd=repo,
                    env={**env, **overrides},
                    capture_output=True,
                ).returncode

            self.assertEqual(run(provenance), 0)
            self.assertEqual(run(freshness), 0)
            self.assertNotEqual(run(freshness, REMOTE="b" * 40), 0)
            self.assertNotEqual(run(provenance, PLAN_ATTEMPT="1"), 0)
            self.assertNotEqual(run(provenance, RELEASE_TAG="v1.8.19"), 0)
            for delta in (
                {"draft": True},
                {"prerelease": True},
                {"published_at": None},
            ):
                self.assertNotEqual(
                    run(provenance, RECORD=json.dumps({**record, **delta})), 0
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
