# Living Proof Labs — Website

Marketing site for [Living Proof Labs](https://livingprooflabs.com): verification for robots entering human environments.

## Stack

- Static HTML and CSS. Deploy fingerprints CSS and JavaScript filenames; there is no application build.
- GitHub Pages with GitHub Actions (`.github/workflows/deploy.yml`)
- Custom domain via `CNAME` and Cloudflare DNS

## Local preview

```bash
python3 -m http.server 8765
```

Open http://127.0.0.1:8765

## Deploy

Push to `main`. The workflow assembles `_site` from `index.html`, `404.html`, `privacy.html`, `terms.html`, `assets/`, `styles/`, `CNAME`, and `.nojekyll`, then publishes that directory to GitHub Pages. CSS and JavaScript filenames in the assembly are content-hashed (`styles/main.<sha256-8>.css`, `assets/nav.<sha256-8>.js`) and new HTML references only those current names. The assembly also keeps `styles/main.css` and `assets/nav.js` with the current bytes, and carries forward CSS and JS from `HEAD^1` and up to the two newest `v*` tags reachable from HEAD, excluding HEAD itself. The same content hash is stored once, so HTML cached from the previous commit or from a recent tagged, untagged, or cancelled release still resolves. Files in the repository stay unhashed, so `python3 -m http.server` still serves the source tree. The legal pages are drafts pending counsel, not a completed review.

Assembly and `tools/verify_site.py` fail when they cannot see `HEAD^1` or a previous `v*` tag. That keeps a shallow checkout from publishing a site that drops cached CSS and JS. The first deploy of a history with neither can set `ASSEMBLE_FIRST_RUN=1` or pass `--first-run` to both commands. The deploy workflow does not set that override.

Creating the Pages site the first time needs repository administration, and a workflow cannot grant that to `GITHUB_TOKEN` (`administration` is not a valid workflow permission). Either:

- Open [Settings → Pages](https://github.com/Living-Proof-Labs/website/settings/pages), set **Source** to **GitHub Actions**, then re-run the workflow. Enable **Enforce HTTPS** once GitHub has issued a certificate.
- Or add a repository secret `PAGES_ENABLE_TOKEN` (fine-grained PAT on this repo with **Pages** and **Administration** write). The workflow passes it to `configure-pages` with `enablement: true`.

The `CNAME` file contains only `livingprooflabs.com`, with no scheme, path, or trailing newline. GitHub rejects anything else as “not properly formatted.”

`https://livingprooflabs.com` is proxied by Cloudflare to GitHub Pages. Cloudflare presents the certificate. The Worker in `src/worker.js` is not attached to the hostname. Mail and the Notion `hub` records are unchanged.

## Releases

The repository adopts the versioned [Living Proof Labs shared semantic-release
workflow](https://github.com/Living-Proof-Labs/collaboration-guidelines/blob/v6.0.2/docs/releases.md).
It publishes only after the static-site checks pass on trusted `main`, and
creates GitHub Releases and `vX.Y.Z` tags only, with no generated changelog or
version-bump commit.

Semantic-release examines eligible commits since the previous release. Pull
requests are merged with merge commits, using the pull-request title as the
merge-commit title, so use [Conventional Commit](https://www.conventionalcommits.org/)
titles: `feat:` is minor; `fix:`, `docs:`, `chore:`, `ci:`, and other maintenance
types are patch; a title such as `feat!:` is major. Conventional individual
commits can also affect the calculated version. If using a `BREAKING CHANGE:`
footer instead, include it in the merge-commit body. Squashing is not required.

## Contact

team@livingprooflabs.com
