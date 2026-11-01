# SMARTINI’s working instructions

## Keep the roadmap current

For every SMARTINI’s change, review and update `roadmap/roadmap-data.js` alongside the implementation so scope, status, dependencies and remaining validation reflect the actual result. For presentation changes, update the roadmap UI and its guide as appropriate. If a change has no roadmap impact, explicitly say it was reviewed and no data update was needed.

- Keep the roadmap undated: do not add calendar dates, times, durations or delivery estimates. Steps express proposed sequence only.
- Preserve the established phases and intentionally undefined Groceries-list scope. Do not claim work is delivered until its required validation is complete.
- Keep all public roadmap content free of real meetings, private source material, internal endpoints, credentials, logs and backups.
- Run `python tools/check_roadmap.py` after roadmap changes. Preserve accessible phase expand/collapse controls.
- Keep existing runtime behavior and unrelated uncommitted changes intact. Do not commit, push, publish or deploy without explicit user authorization.

See `CONTRIBUTING.md`, `docs/DEVELOPMENT.md`, `docs/ROADMAP.md` and `docs/CI-CD.md` for checks and setup.
