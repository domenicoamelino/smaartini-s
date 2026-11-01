# Interactive product roadmap

Open `roadmap/index.html` directly in a browser, or from repository root run:

```powershell
python -m http.server 8080 --bind 127.0.0.1 --directory roadmap
```

Visit `http://127.0.0.1:8080`. Stop with Ctrl+C. The page has no dependencies, remote fonts, analytics, network requests or private runtime integration. All assets use relative URLs, including under the GitHub project Pages path.

## Editing and interaction

Edit the JSON object assigned to `window.SMARTINI_ROADMAP` in `roadmap/roadmap-data.js`. Keep IDs stable; dependencies reference IDs. `step` selects a zero-based column from `steps`, or is `null` for delivered foundations and undefined horizons. No dates, durations or effort estimates are stored. Phase 2 dependency ordering is proposed; Phases 3 and 4 remain undefined. Groceries-list scope is intentionally undefined. LoRA is optional and does not block release.

This is an undated sequence view. Equal-width markers show proposed order only, not elapsed time or effort. Edit `steps` and task `step` values together to change the sequence. Dependencies in details express ordering within a column. Phase and status filters combine with text search. Overview/expanded controls horizontal detail; Select any phase heading (01–04) to expand or collapse its workstreams, using mouse, Enter or Space. Sections start expanded; your choices persist while filtering during the current page session. Reset clears filters and expands every section. Select any workstream or bar to view scope, sequence, dependencies and downstream work. Native buttons support keyboard navigation; the modal closes with Escape or Close and returns focus. A live count announces filtered results. A no-JavaScript fallback links the full data file.

Validate and build an exact public artifact:

```powershell
python tools/check_roadmap.py
node --check roadmap/roadmap.js
node --check roadmap/roadmap-data.js
python tools/check_roadmap.py --output dist/roadmap-preview
python tools/check_all.py
```

Use a fresh output directory each build. The builder copies only `index.html`, `roadmap.css`, `roadmap.js`, `roadmap-data.js`, plus an empty `.nojekyll`. Never publish the repo root, the existing `docs/` tree, dashboards or runtime deployment packages. The endpoint marker check is a limited guardrail, not proof of privacy: manually review every public line.

## CI/CD setup (prepared locally; not activated here)

See [CI/CD setup and checks](CI-CD.md) for repository-wide lint, offline tests, security/secrets scans, builds and required branch checks. GitHub Actions are pinned to full commit revisions; the secrets scanner archive is checksum verified. CI has no private server access. Publishing remains manually gated.

## Publishing GitHub Pages (manual)

After reviewing and authorizing your own commit/push:

1. In Settings → Pages, set Source to **GitHub Actions**. Do not choose root or `/docs` branch publishing.
2. Create/configure the **github-pages** environment *before* the first run. Restrict deployment branches to `main`, add required reviewers where the plan supports them, and disallow administrator bypass where practical. Prevent self-review only if another reviewer is available. Add no environment secrets. Features depend on repository visibility and GitHub plan; if reviewers are unavailable, retain the workflow's explicit manual gate and protected-main review process.
3. Review the four public source files and the built allowlist. The existing runtime, docs tree, source data, logs and backups must not enter the Pages artifact.
4. In Actions → **Publish roadmap (manual)** → Run workflow, select `main` and type `PUBLISH`. The workflow rejects other branches or confirmation values. It reruns the same CI/security checks for that commit, builds only the allowlist, then waits for any configured environment approval. Only the final deploy job has Pages/OIDC write permissions.
5. Approve the environment deployment if required. Read the deployed URL from the job. Expected project URL: `https://domenicoamelino.github.io/smaartini-s/` (not published by this change).

There is no push-triggered deployment, production deployment, automatic approval, release tagging or private server access. To roll back public content, revert the relevant public files through review, rerun checks, and manually publish again. To take the site offline, unpublish it in Pages settings.

GitHub references: [custom Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [deployment environments and protection availability](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

## Roadmap provenance and scope

The supplied continuation request is the authoritative roadmap inventory. The referenced conversation reader returned only content-reference placeholders for roadmap answers, so no additional hidden detail was inferred. Phase 1 includes the delivered recovery foundation; Phase 2 still requires full-platform recovery evidence. The public demo/video/docs are future work: this artifact provides the interactive roadmap, not a simulated live private dashboard. No runtime code or existing recovery work is changed.
