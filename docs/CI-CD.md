# SMARTINI’s CI/CD

The local repository contains two workflows. They become available on GitHub only after an authorized commit and push. No GitHub settings have been changed and no cloud run or deployment has been performed as part of this setup.

## Continuous integration

`SMARTINI CI` (`.github/workflows/roadmap-ci.yml`) runs on pull requests, pushes to `main`, manual requests and reusable calls from the Pages workflow. The existing filename is retained for compatibility; checks cover the repository, not only the roadmap.

Required jobs:

- `lint`: Ruff fatal syntax/control-flow checks across Python source, plus Node syntax checks for all tracked JavaScript files.
- `test`: the existing `tools/check_all.py` synthetic offline suites, then roadmap data, undated sequence and dependency validation.
- `security`: Gitleaks scans both history and current files with redaction, plus Bandit high-severity/high-confidence Python findings. A scanner download must match its pinned SHA-256 before execution.
- `build`: after all three checks succeed, build the existing source-only runtime ZIP and the allowlisted static roadmap. The runtime package is neither uploaded nor deployed.

All jobs use GitHub-hosted Ubuntu and read-only repository permissions. Action revisions are pinned to verified full commit SHAs. Direct Python check-tool versions are pinned in `requirements-ci.txt`; transitive dependencies and the existing runtime environment are not a fully locked dependency set. Review and update pins deliberately. No self-hosted runner, private network connection, runtime credential or real meeting fixture is used. Do not add production secrets to these workflows.

Local checks in a separate development environment:

```powershell
python -m pip install -r requirements-ci.txt
ruff check --no-cache --select E9,F63,F7,F82 .
python tools/check_all.py
python tools/check_roadmap.py
bandit -r . -x ./.git,./tests,./review_tests,./work,./dist -lll -iii
python tools/build_release.py --output dist/local-ci-check
python tools/check_roadmap.py --output dist/local-pages-check
```

Use fresh output directories. Never install check tools into the accepted server environment. Run `node --check` for JavaScript changes. Gitleaks must be installed from a verified official release to run `gitleaks git . --redact --no-banner` and `gitleaks dir . --redact --no-banner`. Do not post findings publicly or add broad secret-scan exclusions to get a green build.

Local validation found no fatal Python lint errors, no high-severity/high-confidence Bandit findings and no Gitleaks findings in history or current files. The prior complete Windows regression run had one temporary SQLite cleanup error in `test_audit_and_idempotent_repeated_request` (295 passed, one error); the existing runtime code is unchanged. The Ubuntu workflow and environment gates still need their first GitHub run after an authorized push. A green local scan is not proof that every security risk is covered.

## Manual public delivery

`Publish roadmap (manual)` (`.github/workflows/roadmap-pages.yml`) accepts only `main` with the confirmation `PUBLISH`. It reruns the complete reusable CI workflow for the same commit. After success it rebuilds and uploads only the four public roadmap files plus `.nojekyll`. Only the final deployment job has Pages/OIDC write permissions and uses the `github-pages` environment. There is no automatic server deployment or push-triggered publication.

Before first publication:

1. In Settings → Rules/Branches protect `main`: require pull requests, resolved conversations and the successful `lint`, `test`, `security`, `build` checks. Select their exact displayed contexts after the first CI run. Require review where practical; block force pushes/deletion and avoid bypasses. Do not replace stronger existing rules.
2. In Settings → Pages choose **GitHub Actions** as the source.
3. Create the **github-pages** environment before the first publishing run. Allow only branch `main`; configure required reviewers and no administrator bypass where supported. Prevent self-review only when a second reviewer is available. Environment protection features depend on plan/visibility. If reviewers are unavailable, retain the explicit manual confirmation and protected-branch review process.
4. Review only the public artifact. No private dashboards, operational docs, real meetings, endpoints, credentials, recordings, logs or backup contents belong in it. Add no environment secrets.
5. Run the publishing workflow on `main`, enter `PUBLISH`, inspect checks, and approve the environment deployment if required. Use the returned Pages URL to verify the public result.

Repository rules and reviewer gates are GitHub settings, not enforced merely by adding YAML. The initial setup intentionally does not alter those settings, commit, push or publish. See [roadmap preview and publishing](ROADMAP.md) for the public artifact allowlist and rollback steps.

GitHub references: [secure workflow practices](https://docs.github.com/en/actions/reference/security/secure-use), [Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
