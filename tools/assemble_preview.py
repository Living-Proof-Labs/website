#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a static, non-indexable Pages preview. Never deploys anything."""
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
from assemble_site import ROOT_FILES, COPY_TREES

ROOT = Path(__file__).resolve().parents[1]
HEADERS = '/*\n  X-Robots-Tag: noindex, nofollow, noarchive\n  Cache-Control: no-store\n'
ROBOTS = 'User-agent: *\nDisallow: /\n'


def package(output: Path) -> None:
    output = output.resolve()
    if output.exists():
        raise SystemExit(f'refusing to replace existing output: {output}')
    # Reject inputs before the production copier can dereference symlinks.
    for name in ROOT_FILES + COPY_TREES:
        source = ROOT / name
        if source.is_symlink():
            raise SystemExit(f'symlinks are not preview inputs: {name}')
        if source.is_dir() and any(p.is_symlink() for p in source.rglob('*')):
            raise SystemExit(f'symlinks are not preview inputs: {name}')
    with tempfile.TemporaryDirectory(prefix='lpl-preview-') as tmp:
        stage = Path(tmp) / 'site'
        for script, args in [('assemble_site.py', [str(stage)]),
                             ('verify_site.py', [str(stage)]),
                             ('check_css.py', [str(stage)])]:
            subprocess.run([sys.executable, str(ROOT / 'tools' / script), *args],
                           cwd=ROOT, check=True)
        (stage / 'CNAME').unlink()
        (stage / '.nojekyll').unlink()
        (stage / '_headers').write_text(HEADERS, encoding='utf-8')
        (stage / 'robots.txt').write_text(ROBOTS, encoding='utf-8')
        for path in stage.rglob('*'):
            if path.is_symlink():
                raise SystemExit(f'symlinks are not preview assets: {path.name}')
            if path.is_file() and path.stat().st_size > 25 * 1024 * 1024:
                raise SystemExit(f'asset exceeds Pages 25 MiB limit: {path.name}')
        if (stage / '_worker.js').exists() or (stage / 'functions').exists():
            raise SystemExit('preview must contain static assets only')
        shutil.copytree(stage, output)
    print(f'Static preview prepared at {output}; not deployed')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: assemble_preview.py NEW_OUTPUT_DIRECTORY')
    package(Path(sys.argv[1]))
