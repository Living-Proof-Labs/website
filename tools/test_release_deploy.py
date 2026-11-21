# SPDX-License-Identifier: Apache-2.0
"""Verify website production deployment requires an exact verified release tag."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WebsiteReleaseDeploy(unittest.TestCase):
    def test_deploy_requires_exact_release_tag_after_release(self) -> None:
        deploy = (ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
        release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

        self.assertIsNone(re.search(r"^\s*push:\s*$", deploy, re.MULTILINE))
        self.assertIsNotNone(re.search(r"^\s*workflow_call:\s*$", deploy, re.MULTILINE))
        self.assertIn('git rev-parse "${RELEASE_TAG}^{commit}"', deploy)
        self.assertIn("ref: ${{ inputs.release_tag }}", deploy)

        self.assertIn("needs: [verify, release]", release)
        self.assertIn("needs.release.outputs.published == 'true'", release)
        self.assertIn("uses: ./.github/workflows/deploy.yml", release)
        self.assertIn("release_tag: ${{ needs.release.outputs.git-tag }}", release)


if __name__ == "__main__":
    unittest.main()
