# Tasky

An internal team Kanban board — Jira's useful 10%, self-hosted on our own EC2.

**Status:** design stage. Nothing is built yet.

## Where the thinking lives

| Document | What's in it |
|---|---|
| [Design spec](docs/superpowers/specs/2026-07-29-team-kanban-design.md) | What we're building, the stack, the data model, the feature set, and the open questions |

## Stack (decided)

- **Django + Django REST Framework** — the API
- **React** — the board UI, served by Django as static files (same origin, no CORS)
- **MySQL** — local install for dev, RDS on the server
- **Docker** — Django runs containerised in both environments
- **Apache** — reverse proxy on the EC2 box

## Next step

Answer the open questions in §9 of the design spec, then the implementation plan gets written.
