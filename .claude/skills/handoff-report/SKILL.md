---
name: handoff-report
description: >-
  Transfer working knowledge of an existing part of The Commons to someone who lacks it —
  what it does and who depends on it, Mermaid diagrams of real behaviour, data-model/interface
  tables, and the sharp edges that bite newcomers. Triggers: "how does X work", "document this
  service", "onboard someone onto Y", "I'm handing this off", "explain this subsystem",
  "write a handoff doc".
---

# Handoff Report

## Overview

A handoff report transfers working knowledge of a system that already exists to someone who
has to reason about it without you — a newcomer, an inheriting owner, a future maintainer of
this repo who wasn't around when it was built.

The format is deliberately narrow: prose for why it exists, diagrams for how it behaves,
tables for surface area, and an explicit list of what will surprise you. Each carries what the
others can't.

Two principles do most of the work:

- **Describe behaviour, not intent.** Read the code and say what it does. A report that
  documents what the system was supposed to do is worse than no report — the reader trusts it
  and debugs against a fiction.
- **The report stands completely alone.** Every reference pointing outside the document is a
  place the reader stops and doesn't come back.

## When to use

- Onboarding someone onto a service, subsystem, or domain in this repo (`ingestion/`,
  `broadcast/`, the auth bridge, the devtools monitor, etc.).
- Handing off ownership — leaving the project, rotating, going on leave. (This is the sole-dev
  → future-team case this skill exists for.)
- A neighbouring workstream needs to integrate and keeps asking how something works.
- Knowledge exists only in one session's context, one PR description, or one person's head.
- Post-hoc documentation of something built fast (a suite pushed in one sitting) and never
  written down properly.

**Not for:** point-in-time session status updates — this repo's `docs/handoff-suite-*.md` files
and `notion-sync/STATE.md` are that genre (what shipped, what's uncommitted, what to pick up
next). A handoff-report is durable subsystem knowledge, not a snapshot of where a session left
off. Also not for planning work that hasn't been built yet — use `/write-tickets` for that.

## Where the finished report lands

`docs/` is the system of record agents read on every task (per `CLAUDE.md`) — keep it lean and
agent-oriented, don't add human-onboarding material to it. A handoff report is written *for a
person*, so it lands in **`human-docs/`** instead:

1. Write it to `human-docs/<topic>.md` (e.g. `human-docs/ingestion-pipeline.md` — descriptive
   name, no suite number or date unless the report is itself dated point-in-time knowledge).
2. Add a row to the table in `human-docs/README.md` — Doc / Purpose / Written — so it's
   discoverable. An undiscoverable handoff report is as good as not written.
3. If `docs/*.md` or a per-directory `AGENTS.md` already covers this ground for agents, don't
   fork a duplicate — the handoff report can reference and go beyond it (more narrative context,
   the sharp edges an agent doc wouldn't include), but state at the top which `docs/` file it
   complements so the two don't drift into contradicting each other.

If the report is a one-off session status note instead (not durable subsystem knowledge), it
follows the `docs/handoff-suite-N-*.md` pattern instead of this skill's structure — that's
agent/continuation-facing state, not human onboarding, and it stays in `docs/`.

## Grounding — the part that makes it worth reading

Everything in the report is a claim about a system that exists, so everything is checkable.
Check it.

- **Read the source before writing the section.** Models in `models.py` for the data model,
  `urls.py`/views for interfaces, the actual task/handler for a flow. Never reconstruct
  behaviour from a ticket, a PR description, a commit message, or another doc — per
  `CLAUDE.md`, if a doc contradicts the code, trust the code and flag the drift.
- **Point at the module, never the line.** Name the file, function, or component —
  `ingestion/services.py`, "the `before_save` hook on `StagedEvent`" — so the reader knows
  where to look. Never `services.py:88`. Line numbers are wrong within a week of anyone
  touching the file, and a citation that's confidently wrong is worse than none: the reader
  lands somewhere unrelated and stops trusting the rest.
- **Explain the idea, don't index the code.** The value is in what the module does and why, at
  a level that survives refactoring. If a claim can only be supported by pointing at an exact
  line, it's too fine-grained for a handoff report — the reader needs the shape, the code shows
  the detail.
- **Say what you didn't verify.** "I couldn't find where this is cleaned up" is useful. A
  confident guess in the same sentence style as verified facts is not.
- **Date it and name what it reflects** — a commit hash (`git rev-parse HEAD`), a release, or
  just the date. A context-transfer doc is read long after it's written; the reader needs to
  know how much drift to expect.
- **Prefer the system's own vocabulary.** If the code calls it a `StagedEvent`, don't call it a
  "pending record" because it reads better. If it's a "source", don't call it a "feed" unless
  the code does.

## Structure

Use the sections that carry weight; drop the rest and renumber contiguously.

1. **What this is and who depends on it** — what the system does in plain terms, who the
   callers are, what breaks for them if it's down. Two or three paragraphs, no diagrams. A
   reader should be able to stop here and know whether they care.
2. **How it works** — a Mermaid diagram for every flow that earns one, not a representative
   sample. Lead with the common case, then the paths people get wrong. Read path before write
   path. See "Which flows get a diagram" below.
3. **Data model** — what the tables/collections are, what the non-obvious columns mean, what
   nullable actually signifies.
4. **Interfaces** — endpoints, Celery tasks, management commands, webhooks. Who calls each one.
5. **Sharp edges** — the non-obvious behaviour that will bite. See below.
6. **Known gaps** — what's unresolved, undocumented, or actively suspicious, and what you'd
   look at first.

After each diagram, add a short "N things worth calling out" list for what the diagram can't
say: why it's shaped this way, what it costs, what it rules out, and where the obvious-looking
change is the wrong one.

## Sharp edges

This is the section that justifies the report, and the one only a current owner can write. It
is not a list of bugs — it's the knowledge that would otherwise be transferred by someone
losing a day. This repo's memory already holds candidates worth mining when writing about a
given subsystem (e.g. the `Event` PK being `uuid` not `id` breaking `Count("id")`, or
`INGEST_SHARD_COUNT` silently limiting a plain `ingest_events` run) — check for standing
gotchas before assuming you've found something new.

Good entries: a field whose name lies about its contents; a sentinel value overloaded into a
normal column; ordering that looks incidental but isn't; a retry that's safe only because a
downstream call happens to be idempotent; a config that behaves differently in one environment
(dev vs. prod `DJANGO_ENV`, sharded vs. unsharded ingest); a "temporary" workaround load-bearing
enough that removing it breaks something distant.

Each entry: what it is, why it's that way, what happens if someone "fixes" it.

## Table shapes

Describe what exists. Columns adapt to the domain — layer, owner, and consumer columns all
earn their place in different systems.

| Table | Column | Meaning | Notes |
|---|---|---|---|
| `account` | `locked_until` | Null = not locked | Cleared on successful sign-in alongside the counter, in the sign-in handler (`auth.ts`). |

| Endpoint | Auth | Called by | Description |
|---|---|---|---|
| `GET /v2/staff/thing` | `view_thing` | Admin settings screen | Returns the caller's groups only; 404s rather than 403s on a foreign id. |

Name concrete values. "An expired sentinel" is not knowledge — `-infinity` is. If a column is
nullable and carries a magic value, state exactly what distinguishes null from the sentinel;
that ambiguity is a classic sharp edge.

## If the report covers proposed changes instead

Same structure, two swaps: add a New/Mod column to the tables so the reader can see what's
changing versus what's already there, and replace Sharp edges with a delivery sequence table
mapping each PR to the diagrams and rows it covers. Everything else — grounding, standalone
rule, diagram discipline — applies unchanged.

## The standalone rule

- No "companion to `<other>.md`", no "per §3 of the plan", no local file paths as pointers. The
  reader will not open them. Restate what they need inline, in a clause. (Naming a module is
  different — that's a signpost for verifying, not a document the reader has to go read.)
- Number sections contiguously. Don't leave a §2→§4 gap advertising a missing piece.
- Every § reference must resolve inside the report.
- If the report is derived from a working doc (a design doc, a ticket thread), treat it as a
  published copy. Regenerate when the source changes rather than patching, and expect the two
  to diverge in structure.

## Diagrams

### Which flows get a diagram

Diagram every flow that qualifies. Not one showcase diagram and prose for the rest — a
newcomer hits the uncommon paths too, and the retry, the failure, and the migration are exactly
the ones prose handles worst.

A flow earns a diagram when any of these is true:

- It crosses two or more components (view → DB → Celery task → worker).
- It branches in a way that changes the outcome (authorized vs. not, cache hit vs. miss, first
  run vs. subsequent).
- Ordering matters and isn't obvious from the names.
- State persists between steps, or a step is only safe because an earlier one ran.
- You catch yourself writing "then… then… but if…". That sentence is a diagram you haven't
  drawn yet.

Skip it when the flow is one call and a return, when there's no branch and fewer than three
steps, or when the diagram would restate the sentence above it. Ten diagrams that each earn
their place is a good report; ten that include four trivial ones trains the reader to skip all
of them.

Diagrams aren't confined to "How it works." A status lifecycle (`StagedEvent` states, a
`SourceRun` health level) belongs beside the data model; a decision tree explaining a sharp edge
belongs next to that sharp edge. Put the diagram where the question gets asked.

### Don't draw the same diagram twice

A redundant diagram costs more than a missing one. It pads the report, and it makes the reader
stop and work out whether two near-identical pictures differ in some way that matters.

Before adding one, check it against what's already drawn:

- **Same shape, different noun.** If "poll an ICS source" and "poll a scraper source" are the
  same six steps with a different fetcher, draw it once and note what varies.
- **Happy path plus one branch.** A failure that diverges for a step or two is an `alt` block
  inside the existing diagram, not a second diagram.
- **A subset.** If the read path is the write path with the last three steps removed, the write
  diagram already showed it.
- **A table redrawn.** An `erDiagram` that restates the data-model table adds nothing. Keep
  whichever one the reader will actually use, not both.

Split when the shape diverges; merge when only the values do. A branch that changes which
participants are involved, or most of the steps, earns its own diagram. A branch that changes
one call or a label is an `alt`.

### Picking the type

Reaching for `sequenceDiagram` every time is the most common way these reports get harder to
read than they need to be.

| What you're explaining | Type |
|---|---|
| Ordered interaction between components | `sequenceDiagram` |
| One entity moving through statuses over its lifetime | `stateDiagram-v2` |
| Branching logic, a decision tree, a dispatch table | `flowchart TD` |
| How tables/collections relate | `erDiagram` |
| What runs in parallel and what blocks | `flowchart LR` with subgraphs |

If a "flow" is really "this record can be in one of six states and only some transitions are
legal" (e.g. `StagedEvent.status`), a sequence diagram will fight you the whole way.

### Keeping them readable

- One flow per diagram — when the flows genuinely differ in shape. A diagram covering both a
  substantial read and a substantial write is two diagrams; one covering a happy path and its
  one-step failure is still one. See "Don't draw the same diagram twice."
- Five participants is a lot. Middleware, context objects, and validators are not participants
  — fold them into self-calls (`API->>API: check perms`).
- Watch nesting. `alt` inside `alt` inside `loop` renders wide and overflows a tracker's
  comment column. Two levels is usually the limit.
- Autonumber so readers can say "step 7" instead of describing a line.

### Mermaid syntax landmines

Mermaid renders labels as HTML — which is why `<br/>` works, and why these two break with
errors that don't point at the cause:

- `;` is a statement separator. A semicolon in message or Note text truncates the statement; the
  remainder parses as a new one and throws `Expecting 'SPACE', 'NEWLINE', 'create', 'box'...`.
  Use a comma or dash.
- `<...>` is swallowed as an HTML tag. `col = <sentinel>` silently loses the `<sentinel>`. Use
  `(sentinel)`.

Both are silent — one throws an error pointing nowhere near the cause, the other doesn't error
at all. Don't try to spot them by reading; run the two greps in "Before you publish."

### Where it renders

GitHub renders ```` ```mermaid ```` blocks natively — this matters here because handoff reports
land in `human-docs/` and get read on GitHub. VS Code's built-in Markdown preview does not — it
needs an extension, so don't promise it renders "everywhere."

Don't build an HTML page or separate artifact just to make diagrams render; GitHub already
renders them in `human-docs/`. Build a standalone artifact only when the content is genuinely
interactive, and deliver it through its own channel rather than linking it from a report the
reader can't follow the link from.

You usually can't verify rendering locally — `mmdc` is rarely installed. Say so and preview on
GitHub (or in the destination surface) before publishing.

## Process

1. **Establish who reads it and where it lands.** A newcomer needs the business context; an
   integrating workstream needs the interfaces. It's landing in `human-docs/` per "Where the
   finished report lands" above, not `docs/` — that decides emphasis, length, and structure.
2. **Read the system-of-record docs first**, per `CLAUDE.md`: root `AGENTS.md` →
   `ARCHITECTURE.md` → `CODING_STYLE.md`, plus whichever per-directory `AGENTS.md` or
   `docs/*.md` already touches this subsystem. Note where they're stale — flag drift rather
   than propagating it.
3. **Read the code and note which modules matter as you go.** Models, urls/views, tasks. This
   is most of the work, and skipping it is how reports become fiction.
4. **List every flow before drawing any of them.** Enumerate the paths through the system —
   happy path, each failure, each branch, each background job — mark which qualify per "Which
   flows get a diagram," then collapse the ones that share a shape. Deciding coverage up front
   is what stops the report from diagramming the first flow and prosing the rest, and the
   collapse pass is what stops the list from becoming twelve variations on one picture.
5. **Draft context → diagrams → tables → sharp edges → gaps.** Sharp edges accumulate while you
   read; keep a running list from step 3.
6. **Reread as the newcomer.** Every unexplained noun is a gap. Every "obviously" is a sharp
   edge you forgot to write down.
7. **Run the checks below**, then reread for the standalone rule — that one is invisible to
   grep.
8. **Add the row to `human-docs/README.md`** before calling it done — an unlisted doc doesn't
   count as written, per "Where the finished report lands."
9. **Have the current owner review before publishing.** They'll catch the confident-but-wrong
   sentence, which is the one that does real damage. Don't commit or push it yourself unless
   explicitly asked — surface it for review first.

### Before you publish

Two mechanical checks worth running literally, because both failures are silent and neither is
reliably caught by reading. Set `F` to the file.

```bash
# 1. Semicolons inside a diagram — ';' ends the statement, and the rest of the
#    line parses as a new one. Error message points nowhere near the cause.
awk '/^```mermaid/{b=1;next} /^```/{b=0} b{print NR": "$0}' "$F" | grep ';'

# 2. Stray angle brackets — labels render as HTML, so <sentinel> is swallowed
#    with no error at all. Strips <br/> and arrows first; any hit is real.
awk '/^```mermaid/{b=1;next} /^```/{b=0} b{print NR": "$0}' "$F" \
  | sed -e 's|<br */*>||g' -e 's|[-=][-.=]*>>*||g' | grep '[<>]'
```

Both should print nothing. Then check by eye, in rough order of how much damage each does:

1. **Does it stand alone?** Any pointer to another doc, any § that resolves nowhere, any
   section-number gap. This is the failure that wastes the most reader time and no tool sees
   it.
2. **Any line numbers?** `grep -nE '\.[a-z]+:[0-9]+' "$F"` — name the module instead.
3. **Do the diagrams cover the flows that matter, without duplicating each other?** Both
   directions are failures.
4. **Are the sharp edges the real ones?** If they read like a changelog rather than hard-won
   knowledge, the section isn't done.
5. **Is it in `human-docs/README.md`?**

None of this tells you the report is correct — that's what owner review in step 9 is for, and
it's the check that matters most.
