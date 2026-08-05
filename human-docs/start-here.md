# Start here

A map for everyone. Tell it what you're trying to do; it points you at the one doc worth
reading. **Human docs** (this folder) are written for people. **Agent / deep-dive docs**
(`docs/`, and the root `*.md` files) are the technical system of record — denser, but
canonical. Where a human doc doesn't exist yet, this map sends you to the agent doc that
covers the same ground.

> Status: the subsystem docs are written — all of them — and each opens with an Overview you
> can skim in under a minute before dropping into its Deep Dive. Every doc carries a
> **Last updated** line stating the commit it was checked against.
>
> The Docker cutover it used to caveat is **done**: production has run on Docker Compose since
> 2026-08-02 (PR #41), and [`containerization.md`](containerization.md) now describes it as
> settled fact rather than a plan.

---

## New here? Read these in order

1. **What is this and how does it fit together** → [`overview.md`](overview.md)
2. **How identity works** → [`auth.md`](auth.md)
3. **How an event gets from a website onto the site** → [`ingestion.md`](ingestion.md)
4. **The data model** → [`data-model.md`](data-model.md)
5. **Run it locally** → [`local-setup.md`](local-setup.md), then [`testing.md`](testing.md)

---

## "I want to…"

| I want to… | Read | Also useful |
|---|---|---|
| Understand the whole system | [`overview.md`](overview.md) | [`ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Get the project running on my machine | [`local-setup.md`](local-setup.md) | [`testing.md`](testing.md), [`docs/dev-db-isolation.md`](../docs/dev-db-isolation.md) |
| Work on sign-in / accounts / the JWT bridge | [`auth.md`](auth.md) | [`docs/runbook-auth-cutover.md`](../docs/runbook-auth-cutover.md), [`docs/prd-centralized-auth.md`](../docs/prd-centralized-auth.md) |
| Add or debug an event source | [`ingestion.md`](ingestion.md) | [`docs/ingestion-pipeline.md`](../docs/ingestion-pipeline.md), [`docs/safety-scoring.md`](../docs/safety-scoring.md), `/source-creation` skill |
| Diagnose a stuck / failing source | [`ingestion.md`](ingestion.md) | [`docs/ingestion-monitoring.md`](../docs/ingestion-monitoring.md) (`/devtools/monitor`) |
| Push events to other towns' calendars | [`broadcast.md`](broadcast.md) | [`docs/broadcast.md`](../docs/broadcast.md) **(source of truth)** |
| Work on the newsletter / digests | [`newsletter.md`](newsletter.md) | [`docs/redis-celery-handoff.md`](../docs/redis-celery-handoff.md) |
| Add a background job or scheduled task | [`async-jobs.md`](async-jobs.md) | [`docs/redis-celery-handoff.md`](../docs/redis-celery-handoff.md) |
| Deploy, or fix something in production | [`deploy-ops.md`](deploy-ops.md) | [`DEPLOY.md`](../DEPLOY.md) **(source of truth)**, [`docs/dev-db-isolation.md`](../docs/dev-db-isolation.md) |
| Understand how the stack is containerized | [`containerization.md`](containerization.md) | [`docs/adr/0001-containerization.md`](../docs/adr/0001-containerization.md), [`DEPLOY.md`](../DEPLOY.md) |
| Build UI on the main site | [`frontend.md`](frontend.md) | [`theCommonsWeb/AGENTS.md`](../theCommonsWeb/AGENTS.md) |
| Get the look-and-feel right | [`design-system.md`](design-system.md) | [`CODING_STYLE.md`](../CODING_STYLE.md) |
| Understand the admin / review workflow | — | [`docs/admin-backend.md`](../docs/admin-backend.md) |
| Run the test suites | [`testing.md`](testing.md) | [`backendServer/AGENTS.md`](../backendServer/AGENTS.md#testing) |

---

## Reference shelf (canonical, always current)

| Doc | What it is |
|---|---|
| [`README.md`](../README.md) | One-page project intro + local-dev quickstart |
| [`AGENTS.md`](../AGENTS.md) | Repository map — where everything lives |
| [`ARCHITECTURE.md`](../ARCHITECTURE.md) | System design: models, endpoints, auth bridge, async, deployment |
| [`CODING_STYLE.md`](../CODING_STYLE.md) | Design philosophy + frontend/backend conventions |
| [`DEPLOY.md`](../DEPLOY.md) | Production setup, nginx, the Docker Compose stack, deploy commands |
| [`docs/index.md`](../docs/index.md) | Full index of the agent-facing deep-dive guides |

---

_Keeping this current: new subsystem? Add a row to "I want to…" and, if it's a whole doc, to
[`README.md`](README.md)'s index too. Now that the cutover has landed, `containerization.md`
recommends folding itself into [`deploy-ops.md`](deploy-ops.md) — see its closing section. That
merge hasn't happened yet; when it does, this row goes with it._
