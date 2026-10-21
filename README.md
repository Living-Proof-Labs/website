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

Push to `main`. The workflow publishes the site root to GitHub Pages.

In the GitHub repo **Settings → Pages**, set source to **GitHub Actions** and configure the custom domain `livingprooflabs.com` with HTTPS enforced.

### First publish (empty `Living-Proof-Labs/website` repo)

From a machine logged into GitHub:

```bash
git clone https://github.com/Living-Proof-Labs/website.git
cd website
git remote add source <URL-of-this-project-repo>
git fetch source main
git reset --hard source/main
git push origin main
```

Or add a second remote to an existing clone of this project and `git push github main`.

After the first push: **Settings → Pages → Build and deployment → Source: GitHub Actions**, then add custom domain `livingprooflabs.com` and enable **Enforce HTTPS**.

Cloudflare DNS for the apex and `www` is already pointed at GitHub Pages (proxied A/CNAME records).

### Cody (Cloud Agent) push access

This agent cannot push to `github.com` until a credential is available in the environment, for example:

- **Fine-grained PAT** (recommended): GitHub → Settings → Developer settings → Fine-grained tokens → resource owner **Living-Proof-Labs**, repository **website**, permissions **Contents** and **Actions** (write). Add the token as a secret in the Cursor Cloud Agent environment (e.g. `GH_TOKEN`), then ask Cody to push again.
- **Org invite**: not required if the PAT is on your user account with access to the org repo.

Do not paste tokens in chat; use environment secrets only.

## Contact

team@livingprooflabs.com
