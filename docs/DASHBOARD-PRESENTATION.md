# Dashboard presentation update — 30 October 2026

The existing SMARTINI’s logo/wordmark now appears in the top-left header. The recap and history previews render Markdown headings, bold/italic, nested/numbered lists, tables, blockquotes and code blocks. Old literal escaped newlines before Markdown blocks are normalized for display only; code stays literal.

Stored recap text, revision/approval hashes, model prompts, transcript/review controls, ingestion and Telegram are unchanged. No generation or worker restart is required.

The renderer uses vendored Marked 17.0.5 only to tokenize Markdown. It creates an explicit allowlist of DOM elements with text nodes. Raw HTML stays inert, unsafe URL schemes are not linked and Markdown images are not fetched. No CDN, cloud dependency or runtime package installation is introduced. The bundled script includes the MIT license.

Browser checks passed for formatting, source preservation, hostile HTML/links, no remote image requests and desktop/mobile layout. The existing review/recovery browser flow is also checked.

Maintainers: edit `assets/dashboard/dashboard-app.js` or `assets/dashboard/dashboard.template.html`, then run `python tools/build_dashboard_assets.py`. Verify with `--check`. The built `dashboard.js` and `dashboard.html` are self-contained so the existing server routes continue to work. `dashboard.css` is maintained directly. The source-only release builder includes the local renderer sources and license.
