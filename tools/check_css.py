#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail if any stylesheet has unbalanced braces (e.g. an unclosed @media block after a merge)."""
import pathlib
import sys

failures = 0
for path in sorted(pathlib.Path('styles').rglob('*.css')):
    text, stack, line, i = path.read_text(), [], 1, 0
    while i < len(text):
        if text.startswith('/*', i):
            end = text.find('*/', i + 2)
            if end < 0:
                print(f'{path}:{line}: unterminated comment'); failures += 1; break
            line += text.count('\n', i, end); i = end + 2; continue
        c = text[i]
        if c in '"\'':
            end = text.find(c, i + 1)
            if end < 0 or '\n' in text[i:end]:
                print(f'{path}:{line}: unterminated string'); failures += 1; break
            i = end + 1; continue
        if c == '\n': line += 1
        elif c == '{': stack.append(line)
        elif c == '}':
            if not stack:
                print(f'{path}:{line}: unexpected "}}"'); failures += 1
            else: stack.pop()
        i += 1
    for opened in stack:
        print(f'{path}:{opened}: "{{" is never closed'); failures += 1
print(f'CSS brace check: {failures} failure(s)')
sys.exit(1 if failures else 0)
