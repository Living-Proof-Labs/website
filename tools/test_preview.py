# SPDX-License-Identifier: Apache-2.0
"""Preview packaging regression checks (no Cloudflare access)."""
import tempfile
import unittest
from pathlib import Path
from assemble_preview import package, HEADERS, ROBOTS, ROOT


class PreviewTests(unittest.TestCase):
    def test_package(self):
        original = (ROOT / 'CNAME').read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'preview'
            package(out)
            self.assertEqual((out / '_headers').read_text(), HEADERS)
            self.assertEqual((out / 'robots.txt').read_text(), ROBOTS)
            self.assertFalse((out / 'CNAME').exists())
            self.assertFalse((out / '_worker.js').exists())
            self.assertTrue((out / 'index.html').is_file())
            self.assertTrue(list((out / 'styles').glob('main.*.css')))
            with self.assertRaises(SystemExit):
                package(out)
            self.assertEqual((out / 'robots.txt').read_text(), ROBOTS)
        self.assertEqual((ROOT / 'CNAME').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
