# DX Slash Commands

The developer-experience commands built for The Commons. All run **in your local Claude Code session** — no Anthropic API key or GitHub Action required. They're the on-demand counterparts to the automated CI/Action layer (some of which is gated on an API key that isn't wired up yet).

Invoke any of these by typing the slash command in Claude Code, e.g. `/repo-review`.

| Command | One-liner | Writes files? |
|---|---|---|
| [`/write-tickets`](#write-tickets) | Turn a feature description or backlog into ordered, paste-ready tickets | No |
| [`/orchestrate`](#orchestrate) | Delegate a batch of tickets to parallel engineering subagents | Yes (feature code) |
| [`/review`](#review) | Review a PR or the current branch against `REVIEW.md` | No |
| [`/repo-review`](#repo-review) | Full-repo multi-agent audit → triaged findings + Apply Queue | Report only |
| [`/refresh-docs`](#refresh-docs) | Check every doc for staleness vs. the code and fix it in place | Yes (docs) |

---

## /write-tickets

**What:** Converts a feature description (prose) or an indented backlog `.md` into self-contained, paste-ready engineering tickets. Each ticket carries its own context — affected files, approach, why, acceptance criteria — so a cold Claude instance can execute it with no memory of the conversation.

**Output:** A build-order wave list + one fenced ticket per unit of work, in dependency order, with `⚠️` markers on anything it had to assume.

**Use it when:** you have a feature or a rough backlog and want it broken into parallelizable, delegatable work.

```
/write-tickets <feature description | path to backlog .md>
```

Produces tickets only — it does **not** implement anything. Feeds directly into `/orchestrate`.

---

## /orchestrate

**What:** Acts as an orchestrator that takes a set of tickets, builds a dependency graph, groups them into parallel waves, and delegates each unit to a scoped engineering subagent (via the Agent tool). It holds the global picture; subagents get tight, single-ticket briefs.

**Key behaviors:**
- Spawns subagents at medium effort with disjoint file scopes so parallel writes can't collide.
- After each wave, runs a `ticket-verifier` pass (verify → fix → re-verify once → escalate) before integrating.
- Runs integration checks (build + tests) itself to catch cross-ticket breakage.

**Use it when:** you have tickets (ideally from `/write-tickets`) and want them built in parallel.

```
/orchestrate
<paste tickets here, or let it ask>
```

This is the one command that **writes feature code**. Pair it with `/write-tickets` upstream.

---

## /review

**What:** Reviews a PR (or your current working branch) against `REVIEW.md` — the project's real guardrails (no `neon_auth` migrations, no `django.contrib.auth.User`, correct auth+permission classes on new endpoints, CSS variables over hardcoded hex, no `useState` in pure display components, etc.).

**Why it exists:** it's the manual, in-session equivalent of the `claude-review.yml` GitHub Action. That Action needs an `ANTHROPIC_API_KEY` repo secret to run; this command needs nothing but your Claude Code session.

**Use it when:** before opening a PR, or to review someone else's, without waiting on (or paying for) the automated Action.

```
/review            # reviews the current branch
/review <PR#>      # reviews a specific PR
```

Comments/flags only — it does not push fixes.

---

## /repo-review

**What:** A full-repository multi-agent audit. Fans out five domain subagents in parallel — prod-wiring & deploy, test suite, backend architecture, frontend/styling, docs — each returning findings in a shared severity schema (P0–P3). Consolidates into a single triaged report with an **Apply Queue** you approve before anything changes.

**Source of truth:** [`docs/review-playbook.md`](review-playbook.md) — the skill is a thin dispatcher over it.

**Output:** `docs/review/YYYY-MM-DD-findings.md` — findings + proposed diffs. **Report-first: applies nothing.**

**Use it when:** before a release, after a large feature lands, or on a cadence to catch prod-wiring rot and doc drift.

```
/repo-review
```

This is the manual equivalent of the (API-key-gated) weekly scheduled review workflow.

---

## /refresh-docs

**What:** Checks every doc in the repo for staleness against the actual code. Fans out five read-only subagents (core orientation, architecture/data-model, backend subsystems, frontend/broadcast, ops/deploy), each grepping the code to verify every factual claim — file paths, function names, model fields, endpoints, env vars, commands.

**Output:** A consolidated report at `docs/refresh/YYYY-MM-DD.md`, sorted by impact (critical / moderate / minor).

**Modes:**
- `/refresh-docs` — **default: applies** high-confidence corrections directly to the doc files; lists medium-confidence findings for human review.
- `/refresh-docs --report-only` — proposes without writing anything.

**Skips** forward-looking design docs (`prd-*.md`, `tickets-*.md`, `seo-hub-pages.md`) — those describe intended state, not current state. Never changes code to match docs; only docs to match code.

```
/refresh-docs                # find + fix stale docs
/refresh-docs --report-only  # find only, write nothing
```

---

## How these relate to the automated layer

Several of these commands are the on-demand version of a CI job or GitHub Action from the AI-code-factory roadmap. The automated versions call `claude-code-action`, which needs an `ANTHROPIC_API_KEY` repo secret (not currently wired up). The slash commands need only your Claude Code session, so they work today:

| Automated (needs API key) | On-demand slash command (works now) |
|---|---|
| `claude-review.yml` PR review Action | `/review` |
| Weekly scheduled repo-review workflow | `/repo-review` |
| Doc-sync / staleness in the weekly run | `/refresh-docs` |

The lint layer (Ruff/ESLint/mypy via pre-commit + CI gate) and the in-session lint hook run without any API key — they don't call Claude.
