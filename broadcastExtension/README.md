# The Commons — Broadcast (browser extension)

A dormant Chrome/Chromium MV3 extension that autofills captcha-gated event
calendars for **manual review**. The Broadcast SPA sends it a recipe; the
extension opens the target form in a new tab, fills every field it can, and
hands off to the human to solve the captcha and click Submit. It never submits.

Buildless plain JS — no bundler. Files:

- `manifest.json` — MV3 manifest. No static content scripts (dormant on normal browsing).
- `background.js` — service worker. Validates the SPA origin, opens the tab, injects `content.js` once.
- `content.js` — per-field handlers (text/textarea/date/time/select/radio/checkbox/file/select2/terms).
- `popup.html` — minimal "connected" popup.

## Local development (load unpacked)

1. Visit `chrome://extensions`, enable **Developer mode**.
2. **Load unpacked** → select this `broadcastExtension/` directory.
3. Copy the extension's **ID** shown on the card.
4. In `broadcastWeb/.env`, set `VITE_BROADCAST_EXTENSION_ID=<that id>` and restart `pnpm dev`.
5. The SPA pings the extension on load; a `needs_manual` target then shows a
   **Manual review** button that drives the extension.

Without a pinned key (below), the unpacked ID is derived from the folder path
and is stable per machine.

### Verify dormancy

Visit any of the three target sites directly (Trumba/abc11, Triangle on the
Cheap, Triangle Weekender). Nothing should be injected — no banner, no edits.
The extension only acts on a tab it opened in response to a `fill` message.

## Distribution (unlisted Chrome Web Store)

Two-click install for clients, but requires a Google dev account (one-time $5)
and review — **you** handle the account and submission.

1. **Pin the extension ID** so `VITE_BROADCAST_EXTENSION_ID` is stable from dev → store:
   ```bash
   # generate a keypair once
   openssl genrsa 2048 | openssl pkcs8 -topk8 -nocrypt -out commons-broadcast.pem
   # derive the manifest "key" (base64 of the public DER)
   openssl rsa -in commons-broadcast.pem -pubout -outform DER | base64 -w0
   ```
   Add the printed value as a top-level `"key": "<base64>"` in `manifest.json`.
   Keep `commons-broadcast.pem` out of git (it signs the extension).
2. Update `externally_connectable.matches` and `background.js` `ALLOWED_ORIGINS`
   with the **prod SPA origin** (replace the `broadcast.thecommons.example`
   placeholder).
3. Zip the directory contents (not the parent folder) and create an **unlisted**
   listing in the Chrome Web Store dashboard.
4. Add a short privacy policy: no PII is collected or transmitted by the
   extension; data flows SPA → extension → the target site form only.
5. Submit for review.

## Out of scope (v1)

Firefox; reporting submission success back to the backend; porting the full
server-side imperative logic into JS beyond the hardcoded select2/terms drivers.


public key for manifest: "key": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAq7U2jt6RijeKBO0g+kbZvnprWrcle9RIz6bunNk3Ev5sLrtYYlNWP4hKU3OTqP/aR+CLI/mZ/O6j7RRW25RwGj2kxJPNrPo0mDxvYL6AnoL5dRbFqfQCB6EQG/PeZIK94k2VJIRdBuvviHAdp9P3Qbe/+b33HUiOFV+lmHLHnQUHyBV5u/A3fKEGOwvb0aUBBdxgTZYplmu0EdmViD5vgBHYk1xJjF98cJk4400EzOjudsvHb+Aij9FlfY/VvJv7i/e53FjTZQCJJEzAd22BkG2SIbZnlAd7dAjA34ETqYVpYNKolVHxzCxVMBcHsazIZXfR2FTzICfX6MFqSTA4DwIDAQAB"