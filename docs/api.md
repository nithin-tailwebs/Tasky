# Tasky API

Session-cookie auth, same origin. Every endpoint needs a signed-in session except
`GET /api/auth/csrf/` and `POST /api/auth/login/`.

**An unauthenticated call to any other endpoint returns `403`, not `401`.** DRF's
`SessionAuthentication` treats "no session" as "not permitted" rather than "please
authenticate" (there's no `WWW-Authenticate` challenge to issue for a cookie-based
scheme), so `IsAuthenticated` rejects it with 403. The React error interceptor needs
to branch on 403-for-anonymous, not 401.

Any unsafe request (POST, PATCH, DELETE) must carry an `X-CSRFToken` header whose value
is the `csrftoken` cookie. Call `GET /api/auth/csrf/` once on app load to be handed one.

## Auth
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/auth/csrf/` | — | 204, sets the `csrftoken` cookie |
| POST | `/api/auth/login/` | `{username, password}` | the user, or 400 |
| POST | `/api/auth/logout/` | — | 204 |
| GET | `/api/auth/me/` | — | the signed-in user |

## Boards
| Method | Path | Notes |
|---|---|---|
| GET | `/api/boards/` | every board; unpaginated |
| POST | `/api/boards/` | `{name, description?}`; `description` is optional; creator is taken from the session |
| GET/PUT/PATCH/DELETE | `/api/boards/{id}/` | |
| GET | `/api/boards/{id}/cards/` | every card on the board — see the ordering note below |

**Ordering of `/api/boards/{id}/cards/` is NOT "grouped by column."** The queryset
orders by `Card.Meta.ordering = ["position", "id"]`, which is a single ordering
applied across *all three* statuses at once, not per-column. In practice that means
the three columns **interleave**: `todo#0, in_progress#0, done#0, todo#1, …` — a
card's `position` is only unique *within its own `status`*, so two different-status
cards can and will share the same `position` value back to back in this list. The
client must **group the response by `status` itself** (into `todo` / `in_progress`
/ `done` buckets) before rendering columns; do not assume the API hands back
already-grouped or already-column-ordered data.

## Cards
| Method | Path | Notes |
|---|---|---|
| GET | `/api/cards/` | **every card in the system, unscoped by board** — not filtered to "my boards" or any board in particular |
| POST | `/api/cards/` | `{board, title, description?, status?, priority?, due_date?, assignee?}`; `status` defaults to `todo` when omitted |
| GET/PUT/PATCH/DELETE | `/api/cards/{id}/` | `position` is read-only here; `status` and `board` cannot be changed here either — see below |
| POST | `/api/cards/{id}/move/` | `{status, position}` — the drag-and-drop endpoint; returns the updated card, or 404 if the card was deleted before the move could be applied |

`status` is one of `todo`, `in_progress`, `done`, and **defaults to `todo` when omitted on create.**
`priority` is `1` low, `2` medium, `3` high; responses also carry `priority_label`.

**`status` cannot be changed via `PATCH`/`PUT` on `/api/cards/{id}/`.** A request whose `status` differs from the card's current value is rejected with 400: `{"status": "Status cannot be changed here — POST to /api/cards/{id}/move/ instead."}`. Moving a card between columns is *only* done via `POST /api/cards/{id}/move/`, which is the one endpoint that renumbers both the source and destination columns correctly. A `PATCH` that echoes back the card's current, unchanged `status` alongside other real edits (e.g. `title`) is accepted — a UI PATCHing back the full set of fields it holds does not need to strip `status` out, it just must not try to change it that way.

**`board` cannot be changed via `PATCH`/`PUT` on `/api/cards/{id}/` either, for the same reason.** Cards do not move between boards in this product at all — a request whose `board` differs from the card's current board is rejected with 400: `{"board": "Cards cannot be moved between boards."}`. As with `status`, a `PATCH` that echoes back the card's current, unchanged `board` alongside other real edits is accepted.

Card responses also carry read-only extras beyond the writable fields above: `assignee_detail` (a nested `{id, username, display_name}` object for the current `assignee`, returned alongside the raw `assignee` id), `created_by` (a nested user object), and `priority_label` (the human-readable form of `priority`). None of these three are accepted on write.

**`position` is not a system-wide contiguous `0..n-1` invariant** — it is only guaranteed to give a column a deterministic total order (ties broken by `id`), and it is renormalised to a clean `0..n-1` at the moment `/move/` renumbers that column. Deleting a card, for instance, does **not** renumber anything afterward, so gaps (`0, 2, 3`, say) are expected and harmless — never treat a gap as a sign of corrupted data, and never rely on `position` values being consecutive.

## Comments
| Method | Path | Notes |
|---|---|---|
| GET/POST | `/api/cards/{id}/comments/` | POST takes `{body}`; author comes from the session |
| DELETE | `/api/comments/{id}/` | author only, otherwise 403 |

## Me
| Method | Path | Notes |
|---|---|---|
| GET | `/api/me/tasks/` | my open cards across every board, soonest due first |
| GET | `/api/users/` | `id`, `username`, `display_name` for the assignee dropdown |
