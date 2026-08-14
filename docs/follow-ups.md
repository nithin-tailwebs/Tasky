# Known follow-ups

Carried out of the backend build (2026-07-30). Nothing here blocks the backend — each item was
considered and consciously deferred. Recorded so the next two plans don't rediscover them.

## Before the app is reachable by anyone

| Item | Why |
|---|---|
| **Rotate the dev superuser** | `admin` / `admin-dev-12345` was created during development. It lives in the dev database only — never committed — but must not survive onto a shared box. |
| **`seed_demo` creates known-password accounts** | The command now prints a warning naming its target database, but nothing technically prevents it running against a shared environment. Local use only. |

## Deployment plan

- `DEBUG=0`, `CSRF_TRUSTED_ORIGINS`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`
- `STATIC_ROOT` + `collectstatic` (absent by design — the React build lands in the UI plan)
- gunicorn worker tuning, the Apache reverse-proxy config, RDS connection and security groups
- Split `requirements.txt` so `pytest`/`pytest-django` don't ship in the production image
- `SECRET_KEY` is now guarded: with `DEBUG=0` and no key in the environment (or an empty one),
  the app refuses to start rather than silently using the committed development key.

## Security items judged low-risk for an internal tool

- **`POST /api/auth/login/` is not CSRF-protected.** DRF's `APIView.as_view()` is `csrf_exempt`, and
  `SessionAuthentication.enforce_csrf()` only runs when authenticating an existing session — which
  login never is. Exposure is login-CSRF (forcing a victim's browser into an attacker's session).
  Fix if wanted: `@method_decorator(csrf_protect, name="post")` on `LoginView`.
- **No login throttling.** Worth revisiting once the box is network-reachable.

## Deliberate non-goals — do not "fix" these

- **`next_position()` is intentionally unlocked.** Two concurrent creates into the same column can
  produce a duplicate position. This is benign *only* because `Card.Meta.ordering = ["position", "id"]`
  is a total order and `move_card` renumbers whole columns, so the first drag heals it. The reasoning
  is recorded in `boards/services.py`. Adding a lock is not the fix; **breaking either of those two
  properties is what would turn it into a bug.**
- **Card positions are not contiguous `0..n-1`.** Deleting the card at position 0 and creating a new
  one yields `1, 2, 3` — no concurrency involved. The guarantee is a *deterministic total order*,
  renormalised on every move. Gaps are expected and harmless. Renumber-on-delete was considered and
  rejected: nothing reads positions in a way contiguity would protect.
- **No concurrency tests.** Threaded tests against a shared host MySQL are flaky. The one real
  concurrency bug found in this build is pinned by two deterministic regression tests instead.
- **`assignee` on a card is not validated against project membership.** `GET /api/users/` (the assignee
  dropdown) returns every active user, unscoped by project — a card can be assigned to someone who isn't a
  member of that card's project. This was harmless before the Projects & Membership work (everyone could
  see every card); now that `MyTasksView` and card retrieval are project-scoped, that assignee silently
  can't see or open the card they were assigned. Left as-is deliberately: restricting `assignee` to project
  members was never requested by any spec or plan, and doing it now would need to touch existing tests that
  intentionally assign cards to non-members. Whoever picks up the "Work Item Hierarchy" sub-project should
  decide whether to close this.

## Known breakage from the Work Item Hierarchy rename

- **`ui/static/js/api.js` and `ui/static/js/store.js` still call `/api/cards/`.** The
  `/api/cards/` → `/api/work-items/` rename (Work Item Hierarchy sub-project) updated the
  backend and `docs/api.md` but not the UI, which now 403/404s on every card create, update,
  delete, move, and comment call. Recorded here so it isn't rediscovered as a mystery bug —
  the fix belongs to whichever sub-project next touches the UI for hierarchy.

## Local development note

This machine's `.env` uses `MYSQL_PORT=3307` because a second MySQL occupies 3306. `.env.example`
keeps the conventional 3306 — adjust per machine.
