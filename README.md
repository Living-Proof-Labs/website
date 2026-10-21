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

Push to `main`. The workflow publishes `index.html`, `assets/`, `styles/`, `CNAME`, and `.nojekyll` to GitHub Pages. The first run creates the Pages site (`enablement: true`). The workflow token has `administration: write`, which that API call requires. If the repository secret `PAGES_ENABLE_TOKEN` is set, that token is used instead.

The `CNAME` file sets the custom domain to `livingprooflabs.com`.

Cloudflare DNS already points the apex and `www` at GitHub Pages (proxied A records and a `www` CNAME to `living-proof-labs.github.io`). SSL mode is Full, and Always Use HTTPS is on. Leave the mail and Notion records unchanged.

A Cloudflare Worker named `living-proof-labs` is also routed to `livingprooflabs.com/*` and `www.livingprooflabs.com/*`, so visitors currently get that Worker. Remove those routes when GitHub Pages should be the origin again.

If the deploy still cannot create the Pages site, open [Settings → Pages](https://github.com/Living-Proof-Labs/website/settings/pages), set **Source** to **GitHub Actions**, and re-run the workflow. Enable **Enforce HTTPS** once GitHub has issued a certificate.

## Contact

team@livingprooflabs.com
