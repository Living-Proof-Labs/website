# Living Proof Labs Website

This repository hosts the Living Proof Labs stealth-mode website for GitHub Pages.

## Local preview

```bash
python -m http.server 8000
```

Then visit `http://localhost:8000`.

## Deployment

GitHub Actions builds and deploys the site on every **push** (any branch). The **validate** job runs on push and pull requests; the **deploy** job runs only on push and does not require validation to pass.

### Enabling GitHub Pages (first-time setup)

If the deploy job fails with **404 / "Not Found"** or *"Ensure GitHub Pages has been enabled"*:

1. Open **Settings → Pages**:  
   [https://github.com/Living-Proof-Labs/website/settings/pages](https://github.com/Living-Proof-Labs/website/settings/pages)
2. Under **Build and deployment**, set **Source** to **GitHub Actions**.
3. Save. The next push will deploy via the workflow.

### "Branch not allowed to deploy" (environment protection rules)

If deploy fails with *"Branch X is not allowed to deploy to github-pages due to environment protection rules"*:

1. Open **Settings → Environments** → **github-pages**.
2. Under **Deployment branches**, choose **All branches** (for branch previews) or add the branch(es) you want to allow.
3. Save. Pushes to those branches will then be able to deploy.
