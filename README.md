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

Push to `main`. The workflow publishes `index.html`, `assets/`, `styles/`, `CNAME`, and `.nojekyll` to GitHub Pages.

Creating the Pages site the first time needs repository administration, and a workflow cannot grant that to `GITHUB_TOKEN` (`administration` is not a valid workflow permission). Either:

- Open [Settings → Pages](https://github.com/Living-Proof-Labs/website/settings/pages), set **Source** to **GitHub Actions**, then re-run the workflow. Enable **Enforce HTTPS** once GitHub has issued a certificate.
- Or add a repository secret `PAGES_ENABLE_TOKEN` (fine-grained PAT on this repo with **Pages** and **Administration** write). The workflow passes it to `configure-pages` with `enablement: true`.

The `CNAME` file contains only `livingprooflabs.com`, with no scheme, path, or trailing newline. GitHub rejects anything else as “not properly formatted.”

The custom domain on GitHub Pages is `livingprooflabs.com`. Cloudflare DNS for the apex is GitHub Pages’ A and AAAA addresses, and `www` is a CNAME to `living-proof-labs.github.io`. Those records are DNS-only, so GitHub can see them and issue the certificate. Enforce HTTPS stays unavailable until that certificate exists. Mail and the Notion `hub` records are unchanged.

Leave the Worker in `src/worker.js` detached. Once the custom domain is saved, `github.io` redirects to the apex, and a Worker that follows that redirect calls itself.

## Contact

team@livingprooflabs.com
