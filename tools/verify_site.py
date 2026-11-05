#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the static-site inputs that GitHub Pages deploys."""

from html.parser import HTMLParser
import os
import sys
from pathlib import Path


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


def main() -> None:
    # Optional root (e.g. _site) so CI checks the assembled artifact.
    if len(sys.argv) > 1:
        os.chdir(sys.argv[1])
    required = [
        "index.html",
        "404.html",
        "privacy.html",
        "terms.html",
        "CNAME",
        ".nojekyll",
        "assets",
        "assets/aaron-roller.jpg",
        "assets/aaron-roller.webp",
        "favicon.ico",
        "site.webmanifest",
        "assets/favicon.svg",
        "assets/favicon-32.png",
        "assets/apple-touch-icon.png",
        "assets/icon-192.png",
        "assets/icon-512.png",
        "assets/og.png",
        "styles",
    ]
    missing = [path for path in required if not Path(path).exists()]
    if missing:
        raise SystemExit(f"Missing deploy inputs: {', '.join(missing)}")

    page = Links()
    page.feed(Path("index.html").read_text())
    unresolved = sorted(set(page.fragments) - page.ids)
    if unresolved:
        raise SystemExit(f"Unresolved fragment links: {', '.join(unresolved)}")


if __name__ == "__main__":
    main()
