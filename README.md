# Living Proof Labs — Website

Marketing site for [Living Proof Labs](https://livingprooflabs.com): verification for robots entering human environments.

## Stack

- Static HTML and CSS (no build step)
- GitHub Pages with GitHub Actions (`.github/workflows/deploy.yml`)
- Custom domain via `CNAME` and Cloudflare DNS

## Local preview

```bash
python3 -m http.server 8765
```

Open http://127.0.0.1:8765

## Deploy

Push to `main`. The workflow publishes `index.html`, `privacy.html`, `terms.html`, `assets/`, `styles/`, `CNAME`, and `.nojekyll` to GitHub Pages. The legal pages are drafts pending counsel, not a completed review.

Creating the Pages site the first time needs repository administration, and a workflow cannot grant that to `GITHUB_TOKEN` (`administration` is not a valid workflow permission). Either:

- Open [Settings → Pages](https://github.com/Living-Proof-Labs/website/settings/pages), set **Source** to **GitHub Actions**, then re-run the workflow. Enable **Enforce HTTPS** once GitHub has issued a certificate.
- Or add a repository secret `PAGES_ENABLE_TOKEN` (fine-grained PAT on this repo with **Pages** and **Administration** write). The workflow passes it to `configure-pages` with `enablement: true`.

The `CNAME` file contains only `livingprooflabs.com`, with no scheme, path, or trailing newline. GitHub rejects anything else as “not properly formatted.”

`https://livingprooflabs.com` is served by the Cloudflare Worker in `src/worker.js`, which proxies the GitHub Pages site and presents Cloudflare’s certificate. GitHub’s Enforce HTTPS checkbox stays locked until a custom domain is saved on the Pages site; `github.io` cannot turn HTTPS off. Mail and the Notion `hub` records are unchanged.

## Contact

team@livingprooflabs.com
