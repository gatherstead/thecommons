---
name: repo-review
description: 'Run a full-repository multi-agent review of The Commons — fans out five domain subagents (prod-wiring, tests, backend architecture, frontend/styling, docs) and consolidates their findings into a single triaged report with an Apply Queue. Use when the user asks to "review the repo", "run the review playbook", "do a full-repo review", audit prod wiring / the test suite / architecture / docs, or invokes /repo-review. Report-first: produces findings + proposed diffs, does NOT apply fixes.'
---

# Repo Review

Thin dispatcher for [`docs/review-playbook.md`](../../../docs/review-playbook.md) — the single source of truth for scope, severity rubric, finding schema, ground rules, reviewer configuration, the five domain charters, and consolidation. Nothing from the playbook is restated here; read it and run it.

## Steps

1. **Read `docs/review-playbook.md` in full.**

2. **Resolve scope from the arguments:**
   - No args → all five domains against the working tree.
   - A domain name (`prod`, `tests`, `backend`, `frontend`, `docs`) → run only the matching domain section (1–5, in that order).
   - A PR number or branch → run the selected domains, but tell each reviewer to restrict findings to that diff and skip whole-repo deliverables (domain 5 skips the `PROJECT_CONTEXT.md` refresh unless the diff touches docs).

3. **Spawn the selected domain subagents in parallel** (one `Agent` call each, same message; `Explore` for read-only survey, `general-purpose` if the domain needs to run tests). Build each prompt by pasting, verbatim from the playbook: the **Ground rules** block, the **Reviewer configuration** block, and that domain's **Scan** + **Guiding questions** section.

4. **Consolidate** per the playbook's Consolidation step. The orchestrator writes the findings file; subagents only return findings.

5. **Stop and report.** Summarize the P0/P1 count and top findings. Apply nothing — wait for the user to approve items from the Apply Queue.

## Done when

There's a triaged findings file at the playbook's output location with an Apply Queue and proposed doc diffs, and **zero feature changes** were made.
