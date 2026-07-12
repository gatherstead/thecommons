---
description: Turn a feature description or backlog markdown into ordered, self-contained, paste-ready engineering tickets
argument-hint: "[feature description | path to backlog .md]"
---

# Write Tickets

Convert a feature description (prose) or a backlog markdown file into a set of **self-contained, paste-ready tickets**. The consumer of a ticket is a *fresh* Claude Code instance with **no memory of this conversation** — so every ticket must stand alone.

This command produces tickets. It does **not** implement them.

## Input

$ARGUMENTS

If the input above is empty, ask the user to paste a feature description or give a path to a backlog `.md` file before proceeding. If it's a file path, read the **raw** markdown (indentation is meaningful).

## Inputs

The user gives you one of:

- **A feature description** — a paragraph or two of English describing something they want built.
- **A backlog `.md` file** — a bulleted list of items. **Read the raw markdown, not a rendered view** — indentation is meaningful:
  - A **top-level bullet** = one ticket (or an epic, if it has enough sub-structure to warrant splitting).
  - **Nested bullets** = requirements, constraints, sub-tasks, acceptance details, or file hints *for that ticket*. Deeper nesting = finer-grained detail scoped to its parent.
  - A nested bullet that is itself a substantial deliverable → split it into its own ticket and record the dependency on its parent.
  - Preserve any inline hints the user wrote (file paths, "must", "don't", example values) — they encode acceptance criteria.

If it's ambiguous whether a bullet is a ticket or a detail, make a call, split toward *smaller* tickets, and mark the split with `⚠️` (see "Marking uncertainty").

## Process

1. **Load repo context first.** Before writing any ticket, read the system-of-record docs so tickets reference real files, patterns, and guardrails:
   - Root: `AGENTS.md`, `ARCHITECTURE.md`, `CODING_STYLE.md`, `CLAUDE.md`, `PROJECT_CONTEXT.md`.
   - Whichever sub-orientation applies to the feature: `backendServer/AGENTS.md`, `theCommonsWeb/AGENTS.md`, `broadcastWeb/AGENTS.md`, `docs/broadcast.md`, `docs/index.md`.
   - If a doc contradicts the code, trust the code (per `CLAUDE.md`).

2. **Ground each ticket in the actual codebase.** For every ticket, locate the real files, models, endpoints, or components it touches (use Grep/Glob/Explore — don't guess paths). A ticket that names `backendServer/events/models.py:Event` beats one that says "the events model." If you can't find something, say so and mark it `⚠️`.

3. **Determine ordering by necessity.** Build a dependency graph: ticket B depends on A if B cannot start (or cannot pass its acceptance criteria) until A exists. Order the output so dependencies come first. Group independent tickets that can run at the same time into **waves**.

4. **Handle non-software tickets.** If a ticket is *not* code (e.g. "register a domain", "set up a Postmark account", "get a Google verification"), do **not** write implementation steps yourself. Instead the ticket body is a **prompt to an AI** that, when pasted, will produce a bullet-point action plan. Format:
   > **Prompt for AI:** "Generate a numbered checklist of the concrete steps to <goal>, including any accounts, credentials, DNS records, or approvals needed, and where in this repo (env vars, settings files) each result gets wired."

5. **Mark uncertainty.** Where you're guessing — an acceptance criterion you inferred, a file you couldn't confirm, an ambiguous scope split, a design decision the user didn't specify — put your best guess and flag it inline with `⚠️ ASSUMPTION:` or `⚠️ CONFIRM:` so the user knows exactly what to review. Never silently invent requirements.

6. **Carry the ticket ID.** If the source backlog numbers items (this repo uses forms like `10.2`, `T12` — see `CLAUDE.md`), reuse those IDs. Otherwise mint a **new suite**: read `Next suite number` from `notion-sync/STATE.md`, use it as the suite `N`, and number tickets `N.1, N.2, …`.

7. **Offer to queue the suite for Notion — but ask first.** After emitting the tickets, do **not** write anything yet. Ask the user whether the tickets are good enough to go to the outbox (e.g. "Ready to queue Suite N to the Notion outbox, or want to revise first?"). Keep iterating on the tickets until they give an explicit go-ahead. **Only on their approval**, append a `NEW SUITE` block to `notion-sync/OUTBOX.md → Pending changes` (formats defined in that file's preamble), then update `notion-sync/STATE.md`: bump `Next suite number` and add the suite to the ledger in the `Open` column. The suite card body is a tight **Why / Outcomes / QA** summary distilled from the tickets; each ticket becomes a subpage carrying its **full** text. Never touch Notion directly — the desktop app does that. Per `CLAUDE.md`.

## Ticket template

Emit each ticket in exactly this shape. Keep it tight — every line earns its place, but a cold instance must be able to execute from this alone.

```markdown
### [<ID>] <Short imperative title>

**Why:** <1–2 sentences of motivation — the user/business reason, not a restatement of the title.>

**Context / affected files:**
- `path/to/file.py` — <what lives here / why it matters>
- <existing pattern to follow, e.g. "mirror the dedupe flow in events/ingest.py">
- <relevant guardrail from AGENTS.md / CODING_STYLE.md>

**Approach:** <How to go about it. Enough to orient a fresh instance: the sequence of changes, the pattern to copy, gotchas. If the user asked for a test-first flow, say "Start with a failing test/eval at <path>, then …".>

**Acceptance criteria:**
- [ ] <Testable outcome 1>
- [ ] <Testable outcome 2>
- [ ] <Tests/build pass — name the command, e.g. `DJANGO_SETTINGS_MODULE=backend.settings.test uv run python manage.py test`>

**Depends on:** <ticket IDs, or "none">
**Can parallelize with:** <ticket IDs, or "none">
```

For a non-software ticket, replace **Approach**/**Acceptance criteria** with the **Prompt for AI** block from step 4, plus an acceptance line like "Result recorded in `<file/env>` and confirmed working."

## Output format

Return two things, in this order:

1. **Build order (top of the response).** A wave list so the user sees the plan at a glance and knows what to fan out:
   ```
   Wave 1 (parallel):  T1, T3
   Wave 2 (parallel):  T2 (needs T1), T4 (needs T1)
   Wave 3:             T5 (needs T2, T4)
   ```
2. **The tickets**, in dependency order, each in the template above, in fenced code blocks so the user can copy one cleanly into another Claude Code instance.

Close with a short **"Review these"** list linking every `⚠️` marker, so the user has one place to check your guesses.

## Done when

- Every ticket is self-contained (a cold instance could execute it without this conversation).
- Every ticket names real files/patterns from the repo, or flags what couldn't be confirmed.
- Tickets are ordered by necessity and grouped into parallel waves.
- Non-software work is expressed as an AI prompt, not invented steps.
- Every assumption or gap is marked with `⚠️` and collected in "Review these".
- The user was asked whether to queue the suite; the outbox/`STATE.md` were written **only after** an explicit go-ahead (counter bumped, ledger row added). No approval → nothing written.
- **No feature code was written** — this command only produces tickets.
