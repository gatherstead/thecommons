# Claude Code review — one-time human setup (T8)

The automated PR review (`claude-review.yml`) and the weekly scheduled review
(`scheduled-repo-review.yml`) both run `anthropics/claude-code-action`, which needs
two things that only a repo admin can provision: the **Claude GitHub App** installed
on the repo, and an **`ANTHROPIC_API_KEY`** Actions secret. These are manual steps —
Claude cannot perform them for you. Do them once, then the review workflows will run.

Target repo: **`gatherstead/thecommons`**. You need **admin** on the repo and access to
the **Anthropic Console** (<https://console.anthropic.com>).

---

## 1. Install the Claude GitHub App

**Easiest path — from a Claude Code session in this repo:**

1. Open Claude Code in the repo root and run the slash command: `/install-github-app`
2. Follow the browser flow it opens; when asked which repositories, select
   **`gatherstead/thecommons`** (or "All repositories" if you prefer org-wide).
3. Approve the requested permissions (see §3 for what they must include).

**Manual path (if the slash command isn't available):**

1. Go to <https://github.com/apps/claude> → **Install** (or **Configure** if already installed).
2. Choose the **gatherstead** account/org.
3. Under **Repository access**, pick **Only select repositories** → check
   **`thecommons`** → **Install / Save**.

✅ **Verify:** GitHub → `gatherstead/thecommons` → **Settings → GitHub Apps** (under
"Integrations") shows **Claude** installed with access to this repo.

---

## 2. Create an Anthropic API key and add it as the repo secret

1. In the **Anthropic Console** → **Settings → API keys** → **Create Key**.
   Name it something traceable, e.g. `thecommons-gha-review`. Copy the key
   (`sk-ant-…`) — it's shown only once.
2. In GitHub: `gatherstead/thecommons` → **Settings → Secrets and variables → Actions**
   → **New repository secret**.
   - **Name:** `ANTHROPIC_API_KEY`  ← must match exactly (the workflows reference
     `${{ secrets.ANTHROPIC_API_KEY }}`)
   - **Secret:** paste the `sk-ant-…` key
   - **Add secret**

> Scope note: this is a **repository** secret, not an environment secret. Both review
> workflows trigger on `pull_request` / `schedule`, which read repo-level Actions
> secrets. Do **not** put it in a deployment environment.

✅ **Verify:** the secret **`ANTHROPIC_API_KEY`** appears (value hidden) under
**Settings → Secrets and variables → Actions → Repository secrets**.

---

## 3. Confirm the App's permissions

The review workflows declare `permissions: pull-requests: write` and `contents: read`,
so the installed App must be able to grant at least:

- **Pull requests: Read and write** — to post inline review comments.
- **Contents: Read** — to check out and read the diff.
- **Issues: Read and write** — the weekly `scheduled-repo-review.yml` posts its report
  via `gh issue create`.

If GitHub prompts for a permissions update after a workflow's first run, approve it at
**Settings → GitHub Apps → Claude → Configure**.

---

## 4. Smoke-test that it works

Once §1–§3 are done (and the Section 2 workflows T9/T11 are merged):

1. **PR review:** open a small test PR against `main`. The `review` job should run and
   post at least one inline comment. Touching `backendServer/backend/permissions.py`
   in that PR should additionally trigger the Opus `review-critical` job.
2. **Scheduled review:** GitHub → **Actions → Weekly repo review → Run workflow**
   (`workflow_dispatch`). It should finish green and open a new issue titled
   `Weekly repo review — <date>` with a "Docs to review" section — and change no code.

A failed run with a `401`/authentication error almost always means the
`ANTHROPIC_API_KEY` secret name is wrong or the key is invalid — recheck §2.

---

## Result checklist (record when complete)

- [ ] Claude GitHub App installed on `gatherstead/thecommons` (Settings → GitHub Apps)
- [ ] `ANTHROPIC_API_KEY` present under Settings → Secrets and variables → Actions
- [ ] App permissions include PRs: write, contents: read, issues: write
- [ ] A test PR triggered the `review` job successfully
- [ ] `workflow_dispatch` on the weekly review created an issue and applied no changes
