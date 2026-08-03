# Tasky

An internal team Kanban board — Jira's useful 10%, self-hosted on our own EC2.

**Status:** the backend is built and tested. The Django REST API (boards, cards,
comments, session-cookie auth) is complete, with a Django admin for support/ops use
and a `seed_demo` management command for populating local data to develop the UI
against. The React UI and the production deployment are the next two plans.

## Where the thinking lives

| Document | What's in it |
|---|---|
| [Design spec](docs/superpowers/specs/2026-07-29-team-kanban-design.md) | What we're building, the stack, the data model, the feature set, and the open questions |
| [`docs/api.md`](docs/api.md) | The API contract — every endpoint, request/response shape, and the behavioral gotchas (403-not-401 for anonymous calls, `status`/`board` write restrictions, column ordering). The React work is built against this document. |

## Stack (decided)

- **Django + Django REST Framework** — the API
- **React** — the board UI, served by Django as static files (same origin, no CORS) — **not yet built**
- **MySQL** — local install for dev, RDS on the server
- **Docker** — Django runs containerised in both environments
- **Apache** — reverse proxy on the EC2 box — **not yet configured**

## Running it

```bash
cp .env.example .env        # then fill in real values for local dev
docker compose up
```

The API is served at `http://localhost:8000/api/`. Django admin is at `/admin/`.

## Tests

```bash
docker compose run --rm web pytest
```

## Seeding local data

To populate demo boards, people and cards for developing the UI against:

```bash
docker compose run --rm web python manage.py seed_demo
```

This is **local/dev use only** — it creates demo accounts with a well-known,
committed password. Never run it against a shared, staging or production database.

## Next steps

1. **React UI** — build the board against [`docs/api.md`](docs/api.md).
2. **Deployment** — containerised Django + RDS + Apache reverse proxy on EC2.
