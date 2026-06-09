# The Commons — Claude Code Context

Read these files before any task — they are the system of record:

1. [`AGENTS.md`](AGENTS.md) — Repository map, tech stack, cross-cutting concerns, guardrails
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) — Models, endpoints, auth bridge, deployment
3. [`CODING_STYLE.md`](CODING_STYLE.md) — Design philosophy + frontend/backend conventions

For deployment: [`DEPLOY.md`](DEPLOY.md)
For backend orientation: [`backendServer/AGENTS.md`](backendServer/AGENTS.md)
For frontend orientation: [`theCommonsWeb/AGENTS.md`](theCommonsWeb/AGENTS.md)
For deep-dive guides: [`docs/index.md`](docs/index.md)

## Quick Start

```bash
# Backend
cd backendServer && uv sync && python manage.py migrate && python manage.py runserver

# Frontend
cd theCommonsWeb && npm install && npm run dev
```

## Claude-Specific Notes

- If a doc contradicts the code, **trust the code** and flag the doc drift.
- In task recaps, include the **ticket name** if given (10.2, T12, etc.).
- `backendServer/vercel.json`, `build.sh`, `main.py` are legacy dead files — ignore them.
- Run `python manage.py migrate` after model changes — but never for `neon_auth` mirrors (`managed = False`).
- Frontend type-checks with `npm run build`. Backend tests with `python manage.py test`.
