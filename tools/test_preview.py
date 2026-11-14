# SPDX-License-Identifier: Apache-2.0
"""Preview packaging regression checks (no Cloudflare access)."""
import tempfile
import unittest
from unittest.mock import patch
import assemble_preview
from pathlib import Path
from assemble_preview import package, HEADERS, ROBOTS, ROOT


class PreviewTests(unittest.TestCase):
    def test_symlink_rejected_before_assembly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'source'
            root.mkdir()
            (root / 'assets').mkdir()
            (root / 'assets' / 'link').symlink_to('/not-a-real-secret')
            with patch.object(assemble_preview, 'ROOT', root):
                with patch.object(assemble_preview.subprocess, 'run') as run:
                    with self.assertRaises(SystemExit):
                        package(Path(tmp) / 'preview')
                    run.assert_not_called()
                    self.assertFalse((Path(tmp) / 'preview').exists())

    def test_css_receives_staged_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            real_run = assemble_preview.subprocess.run
            with patch.object(assemble_preview.subprocess, 'run', wraps=real_run) as run:
                package(Path(tmp) / 'preview')
                commands = [call.args[0] for call in run.call_args_list]
                css = next(c for c in commands if c[1].endswith('check_css.py'))
                verify = next(c for c in commands if c[1].endswith('verify_site.py'))
                self.assertEqual(css[2], verify[2])

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
