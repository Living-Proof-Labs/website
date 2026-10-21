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

The `CNAME` file sets the custom domain to `livingprooflabs.com`.

Cloudflare DNS already points the apex and `www` at GitHub Pages (proxied A records and a `www` CNAME to `living-proof-labs.github.io`). SSL mode is Full, and Always Use HTTPS is on. Leave the mail and Notion records unchanged.

A Cloudflare Worker named `living-proof-labs` is also routed to `livingprooflabs.com/*` and `www.livingprooflabs.com/*`, so visitors currently get that Worker. Remove those routes when GitHub Pages should be the origin again.

## Contact

team@livingprooflabs.com
