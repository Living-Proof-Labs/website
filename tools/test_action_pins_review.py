# SPDX-License-Identifier: Apache-2.0
"""Third-party Action pins name one exact release (Vera review of #40).

Offline: every third-party ``uses:`` in .github/workflows is either a full 40-hex commit SHA
with an exact ``# vX.Y.Z`` comment, or an exact ``@vX.Y.Z`` tag (no floating ``@v4``).
LIVINGPROOF_NETWORK=1 also checks that each SHA is the commit of its commented tag and that
each exact tag exists upstream.

Run with: python3 tools/test_action_pins_review.py
"""

from __future__ import annotations

import json
import os
import re
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
TAG = r"v\d+\.\d+\.\d+"
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(?P<ref>\S+)(?P<rest>.*)$", re.MULTILINE)
SHA_PIN = re.compile(r"^(?P<repo>[\w.-]+/[\w.-]+)(?:/[\w./-]+)?@(?P<sha>[0-9a-f]{40})$")
TAG_PIN = re.compile(rf"^(?P<repo>[\w.-]+/[\w.-]+)(?:/[\w./-]+)?@(?P<tag>{TAG})$")
COMMENT = re.compile(rf"^\s*#\s*(?P<tag>{TAG})\s*$")


def third_party_uses() -> list[tuple[str, str, str]]:
    found = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        for match in USES.finditer(path.read_text(encoding="utf-8")):
            ref = match["ref"]
            if ref.startswith(("./", "Living-Proof-Labs/", "docker://")):
                continue
            found.append((path.name, ref, match["rest"]))
    return found


def commit_of(repo: str, tag: str) -> str:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/commits/{tag}",
        headers={"Accept": "application/vnd.github+json"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["sha"]


class ActionPins(unittest.TestCase):
    def test_every_third_party_action_names_one_exact_release(self) -> None:
        found = third_party_uses()
        self.assertTrue(found, "expected third-party Actions in the workflows")
        for name, ref, rest in found:
            with self.subTest(file=name, ref=ref):
                if SHA_PIN.match(ref):
                    self.assertRegex(rest, COMMENT, f"{name}: {ref} lacks an exact # vX.Y.Z comment")
                else:
                    self.assertRegex(ref, TAG_PIN, f"{name}: {ref} is neither a SHA nor an exact tag")

    def test_a_floating_major_tag_is_rejected(self) -> None:
        self.assertIsNone(TAG_PIN.match("actions/checkout@v4"))
        self.assertIsNotNone(TAG_PIN.match("actions/checkout@v4.4.0"))

    @unittest.skipUnless(os.environ.get("LIVINGPROOF_NETWORK"), "set LIVINGPROOF_NETWORK=1")
    def test_pins_resolve_to_their_upstream_tags(self) -> None:
        cache: dict[tuple[str, str], str] = {}
        for name, ref, rest in third_party_uses():
            with self.subTest(file=name, ref=ref):
                sha_pin = SHA_PIN.match(ref)
                if sha_pin:
                    key = (sha_pin["repo"], COMMENT.match(rest)["tag"])
                else:
                    tag_pin = TAG_PIN.match(ref)
                    key = (tag_pin["repo"], tag_pin["tag"])
                if key not in cache:
                    cache[key] = commit_of(*key)
                if sha_pin:
                    self.assertEqual(sha_pin["sha"], cache[key], f"{name}: {ref} is not {key[1]}")
                else:
                    self.assertRegex(cache[key], r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
