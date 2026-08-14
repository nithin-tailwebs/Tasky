# Handover — Tasky backend, 2026-07-30

Everything a fresh session needs to pick this up. Read this first, then `docs/api.md`.

## Where things stand

The **backend is complete and reviewed**. Nothing is merged and nothing is deployed.

```
branch:      feat/backend-api   (18 commits ahead of main, working tree clean)
base:        main
remote:      none — this repo has never been pushed anywhere
tests:       92 passing
```

The branch was deliberately **not** merged — that decision is still open. Options are merge to
`main` locally, or create a remote and open a PR.

## What exists

| Area | State |
|---|---|
| Django 5.2 + DRF on MySQL, in Docker | done |
| Session-cookie auth, same origin (login / logout / me / csrf) | done |
| Boards — CRUD, everyone sees every board | done |
| Cards — CRUD, priority, due date, assignee, comments | done |
| Drag-ordering via `POST /api/work-items/{id}/move/` | done, incl. a concurrency fix |
| "My tasks" across boards, users list for the assignee dropdown | done |
| Django admin — this is how teammates get created | done |
| `seed_demo` management command for local data | done |
| **React UI** | **not started — next plan** |
| **Deployment (Apache, RDS, EC2)** | **not started — the plan after that** |

## The four documents that matter

| File | What it's for |
|---|---|
| `docs/api.md` | **The API contract.** The UI work is built against this. It was verified statement-by-statement against the code, twice. |
| `docs/follow-ups.md` | What was deliberately deferred — and three things that *look* like bugs but are safe, with the reasoning. **Read the "deliberate non-goals" section before "fixing" anything in `boards/services.py`.** |
| `docs/superpowers/specs/2026-07-29-team-kanban-design.md` | The design spec: decisions, data model, feature set, and what's out of scope for v1 |
| `docs/superpowers/plans/2026-07-29-tasky-backend.md` | The executed build plan. Corrected post-review, so it no longer carries the concurrency bug it originally specified. |

A blow-by-blow record of the build — every review finding, every fix round, every deferred minor —
is in `.superpowers/sdd/2026-07-29-tasky-backend/progress.md`. That directory is gitignored scratch;
it survives locally but won't travel with the repo.

## Running it — machine-specific gotchas

**Docker here is Colima, not Docker Desktop.** Docker Desktop could not be installed: its Homebrew
cask needs an interactive `sudo` password for a symlink into `/usr/local/bin`, which a non-interactive
shell cannot supply, and it rolls the whole install back. Colima has no such requirement.

```bash
colima status || colima start --cpu 2 --memory 3 --disk 20
docker compose up                              # http://localhost:8000
docker compose run --rm web pytest             # the test command every task used
docker compose run --rm web python manage.py seed_demo
```

Colima does **not** start at login unless you run `brew services start colima`. If `docker` commands
fail with a socket error, that's why.

**MySQL runs natively on the Mac, not in a container.** Two things were configured that a fresh
clone would not have:

- `/opt/homebrew/etc/my.cnf` has `bind-address = 0.0.0.0`, so the container can reach the host.
  Without it you get an opaque "Can't connect to MySQL server".
- The DB user is `'tasky'@'%'` — the `%` matters, the container is not localhost — with grants on
  both `tasky.*` and `test_tasky.*`. pytest-django creates that second database and fails without
  the grant.

**This machine's `.env` uses `MYSQL_PORT=3307`**, because a second non-Homebrew MySQL occupies 3306.
`.env.example` keeps the conventional 3306. `.env` is gitignored; copy the example and adjust.

Watch the disk. It hit 413 MB free during this build and broke an install; ~9 GB now.

## Picking up the next piece

The design spec settles *what* to build. Neither remaining plan is written yet.

1. **React UI** — the board, drag-and-drop, the card modal, my-tasks, login. Build against
   `docs/api.md`. Three API behaviours will bite if missed, all documented there:
   `status` and `board` cannot be changed with a `PATCH` (use `/move/`); unauthenticated calls
   return **403**, not 401; and `GET /api/boards/{id}/work-items/` **interleaves** the three columns,
   so the client groups by `status` itself.
2. **Deployment** — Docker image behind Apache on EC2, RDS MySQL. `docs/follow-ups.md` lists the
   full scope, plus the pre-flight chore: rotate the dev superuser `admin` before anything is
   network-reachable.

## The one thing worth knowing about the build

The most expensive bug was in the *plan*, not the code: the move endpoint read a card's old column
before taking its database lock, so two people dragging the same card could leave a permanent gap
in the board's ordering. Found by an adversarial review, fixed, and pinned by two regression tests.
The plan document was corrected too, so re-reading it won't reintroduce it.

There are **no concurrency tests** anywhere, by choice — threaded tests against a shared host MySQL
are flaky. That bug class is covered by deterministic simulations instead.
