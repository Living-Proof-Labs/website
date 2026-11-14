# Cloudflare preview and migration plan

Tracks [website #21](https://github.com/Living-Proof-Labs/website/issues/21).
This is preparation, not a production hosting change or a deployed preview.

## Build the static preview

From a full-history checkout with reachable release tags:

```sh
python3 tools/assemble_preview.py /tmp/lpl-preview-new
```

Use a new output directory. The command refuses to overwrite an existing one.
It reuses the production assembler and verifier, retaining fingerprinted assets
and their compatibility copies. It removes the GitHub Pages CNAME marker and
adds preview-only `robots.txt` and `_headers`. Production assembly is unchanged.
There are no Functions, deployment calls, credentials or DNS changes here.

Cloudflare applies [_headers](https://developers.cloudflare.com/pages/configuration/headers/)
to static responses; this package requests `X-Robots-Tag: noindex, nofollow,
noarchive` and `Cache-Control: no-store`. Robots exclusion is not access control.
Anonymous previews must contain only material suitable for public disclosure.
The [25 MiB individual asset limit](https://developers.cloudflare.com/pages/platform/limits/)
is checked before producing the output. No local HTTP server test proves that
Cloudflare applied these headers: verify the actual deployed response later.

## Deployment boundary, still pending approval

1. Choose and approve a preview-only Pages project and exact credential scope.
   Pages Write is account-scoped; a project name is not a permission boundary.
   Do not claim production isolation until tested or use a separate account.
2. Build pull-request artifacts in a secretless `pull_request` job with only
   contents read. Never run PR code with deployment credentials or use
   `pull_request_target` to check out untrusted PR code.
3. A separately reviewed trusted deploy job should obtain explicit approval,
   select the exact successful run and commit, validate the artifact digest and
   contents, and deploy static assets only. Reject symlinks, path traversal,
   Functions and oversized files. Do not execute code from the artifact.
4. Bind the deployed URL, artifact digest, commit and run in a single updatable
   PR comment. Define retention and delete obsolete preview deployments only
   under approved cleanup scope; never delete production deployments.
5. Validate anonymously: homepage, nested assets, images/video, legal pages,
   404 behavior, robots exclusion and actual noindex response headers, plus
   mobile/desktop appearance. Test an update and confirm the new asset version.

## Verified account snapshot

Read-only API inspection found two Pages projects: `lpl-keel-preview-test`
(the November 4 experiment, whose latest preview uses Functions) and
`living-proof-labs` (no deployment). Both expose only their pages.dev domains.
This does not prove a CI credential exists or that any static upload works.
The existing website remains on GitHub Pages behind Cloudflare.

## Production cutover and rollback, separately approved

- Record the current apex/www DNS values, proxy settings, Pages configuration,
  deployed Git SHA and successful health checks before proposing any change.
- Inventory and preserve MX/TXT mail records, the Notion hub, docs and robot
  reports on GitHub Pages. Do not move them with the marketing website.
- Validate the exact production artifact on the chosen platform first. Do not
  deploy the preview package to production: it intentionally forbids indexing.
- Present the exact hostname/DNS changes, credential scope, deployment and
  rollback plan to Aaron. No cutover follows automatically from merging this.
- After approval, check TLS, apex/www redirects, navigation, legal links, media,
  indexing headers and mail/DNS invariants. Keep GitHub Pages available during
  the observation window; on regression restore the recorded DNS/configuration
  and previous known-good artifact, then verify recovery.
- Decide explicitly whether to retain or remove the old experiment. Do not
  delete it as a side effect of preparing the replacement.
