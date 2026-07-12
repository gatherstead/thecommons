<!-- ═══════════════════════════════════════════════════════════════════════
     OUTBOX — hand this whole file to the Claude desktop app (Notion MCP).
     Claude Code appends to "Pending changes" below; it NEVER touches Notion.
     After the desktop app applies the changes, clear the "Pending changes"
     section back to "_(empty)_". Keep everything above it intact.
     ═══════════════════════════════════════════════════════════════════════ -->

# Prompt for Claude desktop (Notion sync)

You are updating my project Kanban board in Notion via the Notion MCP. Apply the
**Pending changes** at the bottom of this file, then stop. Work idempotently — if a
card or subpage already exists, update it in place instead of creating a duplicate.

## Board model

- The board is a Kanban with these columns, left → right:
  **💡 Idea · 📋 Open · 🔨 In Progress · 🧪 Needs QA · 🚀 Staged for Prod · ✅ In Prod**
- **One suite = one card.** A card titled like `Suite 14 — <name>`. Its column is given per change.
- **Each ticket = one subpage** of its suite card, titled `14.1 — <title>`, `14.2 — <title>`, …

### Suite card body (keep it to a few tight bullets)

```
**Why** — <high-level overview: the reason this suite exists>
**Outcomes** — <the actionable things this suite ships>
**QA** — <the actionable ways to verify it>
```

### Ticket subpage body (full detail)

The full ticket text is provided inline in the change below — paste it verbatim into the
subpage. Also set a **Status** property on the subpage to the ticket's own status
(same six values as the columns) so granular progress lives on the ticket while the
card shows the suite's overall column.

## How to apply a change

- **`NEW SUITE`** → create the suite card in the named column, write the suite body,
  then create one subpage per ticket with its full text and Status.
- **`MOVE SUITE`** → move the suite card to the named column.
- **`MOVE TICKET`** → set the named ticket subpage's Status property.
- **`UPDATE`** → overwrite the named card/subpage body with the provided text.

When done, tell me a one-line summary per change applied.

## Change block templates

Each pending change is one block, fenced by `--- BEGIN CHANGE` / `--- END CHANGE`.

```
--- BEGIN CHANGE
type: NEW SUITE
suite: 14
title: <suite name>
column: Open
body: |
  **Why** — …
  **Outcomes** — …
  **QA** — …
tickets:
  - id: 14.1
    title: <ticket title>
    status: Open
    text: |
      <full paste-ready ticket text>
  - id: 14.2
    ...
--- END CHANGE

--- BEGIN CHANGE
type: MOVE SUITE
suite: 14
column: In Progress
--- END CHANGE

--- BEGIN CHANGE
type: MOVE TICKET
ticket: 14.2
status: Needs QA
--- END CHANGE

--- BEGIN CHANGE
type: UPDATE
target: 14.1        # a ticket id, or "suite 14" for the card body
body: |
  <replacement text>
--- END CHANGE
```

---

# Pending changes

_(empty)_
