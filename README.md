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

Push to `main`. The workflow publishes the site root to GitHub Pages and enables the Pages site on the first successful run (`actions/configure-pages` with `enablement: true`). The `CNAME` file sets the custom domain to `livingprooflabs.com`.

Cloudflare DNS already points the apex and `www` at GitHub Pages (proxied A records and a `www` CNAME). SSL mode is Full, and Always Use HTTPS is on. Do not change the mail or Notion records.

If the deploy fails because the Actions token cannot create the Pages site, either:

- In the repo, open **Settings → Pages → Build and deployment** and set **Source** to **GitHub Actions**, then re-run the workflow. Add `livingprooflabs.com` if the `CNAME` file did not, and enable **Enforce HTTPS** once the certificate is ready.
- Or grant the Cursor GitHub App **Pages: Read and write** and **Administration: Read and write** on `Living-Proof-Labs/website`, then ask the agent to enable Pages again. Do not paste tokens in chat.

## Contact

team@livingprooflabs.com
