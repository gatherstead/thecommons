---
description: Review a PR (or the current branch) against REVIEW.md — runs in your Claude Code session, no API key or GitHub Action needed
---

# Manual PR review

Review a code change against this repo's review standards, entirely inside the current
Claude Code session. This is the API-key-free alternative to the `claude-code-action`
review workflow — same rubric, run locally.

## Input — `$ARGUMENTS`

May contain a PR number, a branch name, or be empty:

- **A number** (e.g. `42`) → review GitHub PR #N: diff via `gh pr diff 42`, metadata via
  `gh pr view 42` (title, description, changed-file list).
- **A branch name** → diff that branch against `main`: `git diff main...<branch>` and
  `git diff --name-only main...<branch>`.
- **Empty** → review the current branch vs main: `git diff main...HEAD` and
  `git diff --name-only main...HEAD`.

If `gh` isn't authenticated for a PR number, fall back to the local-branch behavior and
say so.

## Step 1 — Load the standards (authoritative)

Read **`REVIEW.md`** (repo root) in full — it is the rubric, don't review from memory.
Skim `AGENTS.md` / `CODING_STYLE.md` only when a specific rule needs grounding.

## Step 2 — Get the diff and read for context

Get the diff per the Input rules. For each changed file, read enough surrounding code
(not just the hunk) to judge correctness — a hunk-only view misses real bugs.

## Step 3 — Apply every REVIEW.md guardrail

Walk each guardrail in REVIEW.md against the diff. Give **extra scrutiny** to anything
touching the auth bridge — a subtle bug here is a security issue:

- `backendServer/backend/jwt_auth.py`
- `backendServer/backend/permissions.py`
- `theCommonsWeb/src/lib/auth.ts`
- `theCommonsWeb/src/lib/lazy-auth-plugin.ts`

For these, reason explicitly about token verification, the `BearerTokenAuthentication`
path, permission classes, and the `neon_auth` (`BetterAuthUser`) mirror.

Also run REVIEW.md's **doc-sync check**: if the diff changes a model field, serializer,
or endpoint/route, check whether `ARCHITECTURE.md` §4/§5 or `PROJECT_CONTEXT.md` now
describes stale behavior. Flag-and-suggest only — never auto-edit the docs.

## Step 4 — Do NOT flag

- **Formatting / style** — Ruff and ESLint own it (REVIEW.md says so). No comments on
  quote style, import order, line length, etc.
- **Pre-existing issues outside the diff**, unless this change makes them materially worse.
- Don't invent findings to seem thorough. If it's clean, say it's clean.

## Step 5 — Report in-session

Group findings by severity, each referenced as `file:line`:

- **🔴 Blocking** — correctness / security / guardrail violations that must be fixed before merge.
- **🟡 Should-fix** — real issues that aren't merge-blockers.
- **🔵 Nits** — optional suggestions.
- **📄 Doc drift** — include the one-line corrected snippet inline for the author to paste.

End with a one-line verdict: **approve** / **approve-with-comments** / **request-changes**.

## Step 6 — Optional: post to GitHub

Only when the input was a PR number **and** the user explicitly confirms, post the summary
as a single PR comment: `gh pr comment <N> --body-file <tmpfile>`. Never post inline review
comments and never `gh pr review --approve/--request-changes` without explicit confirmation.
Default is session-only output.
