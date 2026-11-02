# SMARTINI’s Open WebUI appearance

## Status and scope

Deployed with user authorization on Open WebUI **0.12.3**. The administrator ran the staged rollout helper. Candidate Nginx validation passed, only the proxy was replaced using its existing immutable image and configuration, and its original container was retained stopped for rollback. Open WebUI and the worker were not restarted. Live HTML injection, exact public asset hashes and MIME types, dashboard GET reachability and worker health passed. An authenticated desktop browser check verified both logos, Midnight, the Appearance selector and the exact greeting after a hard refresh. Full authenticated workflow and accessibility regression checks remain outstanding. Private mount paths, endpoints, state and backups remain on the server and are not committed here.

The originating screenshot shows the stock upper-left name/icon and selected Function repeated above the composer. The adapter replaces those two branding surfaces and the welcome-only model header. It does not modify stored Functions, selected models, prompts, chat messages, accounts, approvals, API routes, Telegram or ingestion.

## Design and supported extension points

Open WebUI 0.12.3 already loads `/static/custom.css`, but neither that hook nor `WEBUI_NAME` supplies a configurable welcome heading. `WEBUI_NAME` also appends upstream attribution. We leave both existing settings alone. Two small proxy snippets add a same-origin stylesheet and external script to HTML only; the rollout helper inlines them into a new proxy configuration. no bundled JavaScript, container image or upstream source is patched. No new runtime dependency or cloud service is used.

The script first checks `/api/version`, without credentials. Only exact version `0.12.3` enables customization. Each branding change additionally requires specific known elements. Unrecognized versions/markup retain the upstream interface; a missing logo retains the original branding/header. Shared-folder headings are left alone. The original greeting/model markup remains in the DOM, hidden accessibly only after the replacement image loads. The composer and its function selector are untouched.

Midnight and Forest override upstream gray palette tokens, including dark surfaces, borders and muted text. The original transparent PNG is reused byte-for-byte without a backing panel, border or padding. A CSS filter displays a light monochrome silhouette on dark themes so its navy lettering remains readable; light themes retain the original logo colors. Rich UI cards, dashboard, status colors and review controls retain their existing styles. This preserves their contrast and avoids changing content inside frames. It does not recolor every card/dashboard to midnight.

Upstream references:

- [0.12.3 HTML custom CSS hook](https://github.com/open-webui/open-webui/blob/v0.12.3/src/app.html)
- [Welcome header and separate composer](https://github.com/open-webui/open-webui/blob/v0.12.3/src/lib/components/chat/Placeholder.svelte)
- [Sidebar branding anchors](https://github.com/open-webui/open-webui/blob/v0.12.3/src/lib/components/layout/Sidebar.svelte)
- [Native theme persistence](https://github.com/open-webui/open-webui/blob/v0.12.3/src/lib/components/chat/Settings/General.svelte)
- [Branding license terms](https://github.com/open-webui/open-webui/blob/v0.12.3/LICENSE), including the small-deployment exception. Preserve upstream notices when distributing upstream software.

## Local preview

From the repository root:

```sh
python tools/preview_webui_theme.py
```

Open `http://127.0.0.1:8099`. Use `--port 8100` if needed. Stop with Ctrl+C. The server binds only loopback, serves an explicit file allowlist and returns a synthetic version response. It never contacts the real server or loads private data. This is an approximation of the screenshot structure, not a full Open WebUI build or live workflow test.

## Select and reset skins

Use **Appearance** below the sidebar logo: **Midnight**, **Forest**, or **Open WebUI theme**. Midnight is the initial SMARTINI’s default, including for browsers previously using light mode. Choice persists on this browser/origin only in `smartinis.skin.v1`; storage-disabled browsers keep the choice for the current page only. No account preferences are written. Another tab picks up changes by reloading.

Midnight/Forest select native dark mode. The first activation remembers the previous native theme in `smartinis.previous-theme.v1`. Selecting **Open WebUI theme** restores it and reloads so upstream can apply its full theme correctly. Then use Open WebUI Settings → General → Theme for native alternatives. While a SMARTINI’s skin is active, use the Appearance selector for consistent results; selecting native light mode alone will not disable SMARTINI’s palette. To reset SMARTINI’s default, remove only those two namespaced storage entries in browser developer tools and reload. Never clear all site data, which could sign you out or remove unrelated preferences.

## Manual integration alternative for future deployments

1. Use an idle maintenance window. Record the running image/version and existing mounted proxy paths privately. Inspect only relevant Compose image/volume and branding/theme settings. Preserve current custom CSS, security headers, WebSocket forwarding, worker routes and private configurations. Do not pull images or recreate Open WebUI. The checked-in `deploy/nginx.conf` is a reference; do not overwrite the actual configuration with it.
2. Stage a new directory containing only `assets/openwebui/smartinis-ui.js`, `assets/openwebui/smartinis-ui.css`, and `assets/brand/smartinis-logo.png` (same basename). Keep `preview.html` out of the live assets directory. Mount it **read-only** at `/opt/smartinis-ui` in the existing proxy. Stage both `deploy/openwebui/*.conf` includes in a mounted configuration directory. Exact host mount paths must come from the real deployment.
3. Include `proxy-locations.conf` inside the existing Nginx `server {}` block. Include `proxy-html.conf` inside its existing `location / {}` block. Do not include the HTML filter in `/meeting-ui/`, API or WebSocket locations. It matches only HTML responses and preserves all existing proxy headers/timeouts. Check for inherited/duplicate `Accept-Encoding` settings and merge deliberately.
4. Verify `ngx_http_sub_module` with `nginx -V`, then run `nginx -t` inside the existing proxy. Confirm the upstream HTML has one `</head>` and that gzip is disabled for this upstream response; check downstream compression still works. Validate the existing CSP permits same-origin script/style loads. Do not weaken CSP or add inline-script allowances. If a module/CSP constraint prevents this integration, leave the original interface active. Palette-only CSS can be merged into an existing custom stylesheet after review, but it cannot replace the greeting. Do not invent a compiled-bundle patch as a fallback.
5. Prefer a parallel loopback-only preview proxy using the same upstream and snippets, then validate in an authenticated browser. If the existing proxy already mounts the parent directories, only config validation and a proxy reload may be needed. Adding a bind mount can require recreating **the proxy only**; obtain deployment authorization before doing that. No Open WebUI/worker/model restart is required by these assets. Preserve every existing service, volume, image pin and private route.
6. Back up only the changed proxy configuration and public assets privately. With rollout authorized, activate/reload the proxy, hard-refresh, then run the live checklist below. Do not include backups/configuration containing secrets in Git or public Pages. The Pages build remains the roadmap-only allowlist; this feature does not publish the UI or server.

## Acceptance and upgrade checklist

- Confirm the live version is still 0.12.3 and only one script/style pair is injected. Both assets return correct MIME types; logo returns image/png. No CSP errors, redirect loops or broken WebSocket connections.
- Open new Audio, Notes and Text chats. Same logo in sidebar and hero; greeting exactly **Ready to work, what’s on your mind?**. No large repeated function name. Lower selection remains visible and changes functions normally. Open a shared folder: its own heading remains intact.
- Switch skins, refresh, open another tab, return to native theme, sign out/in. Test a browser with storage denied. This choice is browser-scoped, not account-scoped.
- Check keyboard navigation, screen-reader heading/logo labels, 200% zoom, 360px mobile and wide desktop. Skin picker and composer must remain reachable. Check text, muted text, borders, focused controls and semantic status colors in both skins. No new motion is added.
- Open an existing chat and all three cards, navigate to the dashboard, open a synthetic review, change a draft and cancel it. On a separately authorized synthetic workflow, exercise revision/approval and ingestion. Confirm existing owner scoping and Telegram behavior. Offline preview does not certify these live operations; do not approve or ingest private records just to test appearance.
- Simulate unavailable logo, unavailable version endpoint, changed markup and a different version on a preview proxy. Original UI must remain usable. Re-test these cases before allowing a new Open WebUI version; update the adapter only after inspecting that version's source and testing navigation. Never broaden the version gate blindly.

## Rollback

For this deployment, use the retained rollout directory on the server:

```sh
sudo python3 /path/to/the/retained-rollout/apply.py --rollback
```

Replace the example path with the actual private rollout path. This stops the new proxy, restores the retained original container and starts it. It checks the container ID before changing anything. Do not delete the retained rollout directory: the active proxy mounts its candidate configuration and public assets. Keep the original stopped proxy until rollback is no longer needed. For a future manual integration using include statements instead, remove only those includes, validate with `nginx -t`, and reload the proxy. Hard-refresh browsers afterward.

Skin colors disappear when the injected stylesheet is removed. Native dark mode may remain because it was selected for the skin. To restore the prior native choice, select **Open WebUI theme** before disabling the adapter, or select a native theme in Open WebUI settings afterward. No database restore, Function re-import, account reset or worker restart is needed.

## Validation recorded for this change

Headless Chromium against the synthetic local preview passed: both branding surfaces, exact heading, single sidebar logo after repeated DOM updates, default Midnight, persisted Forest, return to native theme, preserved draft and function selection during skin changes, 360px layout without horizontal overflow, removal of the hero when navigating away, unsupported-version fallback, missing-logo fallback, and denied-storage session behavior. No JavaScript page errors occurred. Desktop and mobile screenshots were visually reviewed. Sample text contrast ratios: primary Midnight 15.01:1; muted Midnight on a panel 5.33:1; muted Forest on a panel 5.08:1. These measurements do not certify all upstream components.

The original 50 standard offline regression tests passed, including release packaging and exclusion of private files adjacent to UI assets. The release package built successfully, the public undated roadmap validated with 27 workstreams, JavaScript syntax passed and Git whitespace checks passed. Optional Ruff/Bandit reruns were unavailable in the accessible local environment; hosted CI remains to be run after an authorized push.

Live Nginx configuration validation and deployment verification passed as described above. Authenticated desktop visual verification now confirms both logos, the Midnight palette, the Appearance selector and exact greeting. A stale browser page initially displayed stock branding; a hard refresh loaded the deployed assets correctly. Full authenticated Audio/Notes/Text and chat navigation, screen-reader output, revision/approval, ingestion and Telegram regression checks remain outstanding; service health is not a substitute for those checks.

## Rollout helper source and packaging

`deploy/openwebui/apply.py` is the exact standalone helper used for this rollout. Stage it as `apply.py` alongside the two `.conf` snippets, a `public/` directory containing `smartinis-ui.js`, `smartinis-ui.css` and the unchanged `smartinis-logo.png`, and a `SHA256SUMS.json` mapping relative file paths to SHA-256 hashes. Run `sudo python3 apply.py --apply` only after deployment authorization. It requires the supported host-network/read-only-file-mount proxy layout, validates the installed image in a temporary container, preserves the existing proxy configuration and restores the old proxy automatically if HTTP verification fails. It does not pull images or restart WebUI/worker. Do not run it directly from an unstaged checkout.

`tests/test_webui_rollout.py` covers success, preflight failure without stopping the live proxy, and post-switch health failure with automatic rollback. The source-only release builder includes this helper; it does not execute it or include private runtime configurations/status files.

## Logos or theme missing on an already-open tab

A tab opened before deployment can still show the original Open WebUI interface. With a new, empty chat open, press **Ctrl+Shift+R** (Windows/Linux) to reload the page and assets. Verify the sidebar logo, Appearance selector, central logo and exact greeting. Repeat on other browsers/devices if needed. Do not clear all site data, delete chats or restart services to refresh branding. Save any unsent text before reloading. If a hard refresh does not resolve it, verify the supported version and public asset responses before changing selectors.

## Transparent logo follow-up

Both the sidebar and welcome logos now sit directly on the page with no white panel. This is a stylesheet-only update; the source PNG is unchanged. Dark themes use a light monochrome treatment for contrast. The live stylesheet can be replaced atomically inside the existing read-only asset mount without a proxy reload or any application restart. Retain the previous CSS outside the public directory for a targeted rollback, and update the rollout asset hash manifest with the new CSS digest. Refresh already-open browser pages after updating.
