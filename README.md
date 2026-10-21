# Living Proof Labs — Website

Marketing site for [Living Proof Labs](https://livingprooflabs.com): verification for robots entering human environments.

**Production is live:** [https://livingprooflabs.com](https://livingprooflabs.com) (`www` 301s to the apex).

## Stack

- Static HTML and CSS (no build step)
- Cloudflare Worker `living-proof-labs` serving files from KV (`SITE`)
- Custom domains `livingprooflabs.com` and `www.livingprooflabs.com` on the Rollerbot Creations Cloudflare account
- Preview: [https://living-proof-labs.rollerbot-creations.workers.dev](https://living-proof-labs.rollerbot-creations.workers.dev)
- Optional GitHub Pages backup via `.github/workflows/deploy.yml` (not enabled until Pages write access is granted)

## Local preview

```bash
python3 -m http.server 8765
```

Open http://127.0.0.1:8765

## Deploy

Production is already published from this repo’s `index.html`, `styles/main.css`, and `assets/favicon.svg`.

To publish updates with Wrangler (needs a Cloudflare API token with Workers Scripts Edit and Workers KV Storage Edit):

```bash
npx wrangler kv key put --binding SITE index.html --path index.html
npx wrangler kv key put --binding SITE styles/main.css --path styles/main.css
npx wrangler kv key put --binding SITE assets/favicon.svg --path assets/favicon.svg
npx wrangler deploy
```

Account ID: `77ba1de72cc51cc8832b4c795e6074cf`. KV namespace: `living-proof-labs-site` (`0afd76db6412480d85c4e8ccc12da043`).

GitHub Actions will run the same steps when repo secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` are set.

### Enable GitHub Pages (optional backup)

The GitHub Pages job cannot publish until Pages is enabled on the repo.

**Option A — UI (fastest):** [Living-Proof-Labs/website → Settings → Pages](https://github.com/Living-Proof-Labs/website/settings/pages) → **Build and deployment** → **Source: GitHub Actions**. Re-run the [Deploy workflow](https://github.com/Living-Proof-Labs/website/actions/workflows/deploy.yml) on `main`.

**Option B — PAT:** Add a repository secret `PAGES_ENABLE_TOKEN` (fine-grained PAT on **website** with **Contents**, **Pages**, and **Administration** read/write). The workflow passes it to `configure-pages` with `enablement: true`.

**Option C — Cursor GitHub App:** In GitHub → **Living-Proof-Labs** → **Settings** → **GitHub Apps** → Cursor → grant the permissions in the table below.

If you enable Pages later, do **not** point `livingprooflabs.com` DNS back at `github.io` — Cloudflare already serves the domain from the Worker. GitHub Pages would only be a `*.github.io` backup.

## GitHub access this agent still needs

The Cursor GitHub App can push this branch, but the REST API reports every repo permission as **false**. That still blocks enabling GitHub Pages, setting the homepage, and managing Actions.

Grant the Cursor GitHub App (org **Living-Proof-Labs** → Settings → GitHub Apps → Cursor) **read and write** on this repo for:

| Permission | Why |
| --- | --- |
| **Contents** | Push branches and keep the Worker/workflow files in git |
| **Pages** | Enable GitHub Pages (Actions source) as a backup host |
| **Administration** | Set Pages custom domain / Enforce HTTPS / homepage |
| **Workflows** | Update `.github/workflows/deploy.yml` |
| **Actions** | See and rerun deploy workflows |
| **Pull requests** | Open and update PRs from the agent |

Then re-run this agent (or ask it to enable Pages).

Optional, for unattended Cloudflare deploys from GitHub Actions: add repository secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID=77ba1de72cc51cc8832b4c795e6074cf`. Do not paste tokens in chat.

A Cloudflare Pages project `living-proof-labs` also exists (`living-proof-labs.pages.dev`) but has no deployment. Direct Upload asset APIs reject the OAuth session used here; the Worker is the live origin.

Email routing, `hub.livingprooflabs.com` → Notion, SPF/DKIM, and the Google site-verification TXT record were left in place.

## Contact

team@livingprooflabs.com
