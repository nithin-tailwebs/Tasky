# Tasky API

Session-cookie auth, same origin. Every endpoint needs a signed-in session except
`GET /api/auth/csrf/` and `POST /api/auth/login/`.

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
| GET/PATCH/DELETE | `/api/boards/{id}/` | |
| GET | `/api/boards/{id}/cards/` | every card on the board, ordered by column position |

## Cards
| Method | Path | Notes |
|---|---|---|
| POST | `/api/cards/` | `{board, title, description?, status?, priority?, due_date?, assignee?}` |
| GET/PATCH/DELETE | `/api/cards/{id}/` | `position` is read-only here; `status` cannot be changed here either — see below |
| POST | `/api/cards/{id}/move/` | `{status, position}` — the drag-and-drop endpoint; returns the updated card, or 404 if the card was deleted before the move could be applied |

`status` is one of `todo`, `in_progress`, `done`.
`priority` is `1` low, `2` medium, `3` high; responses also carry `priority_label`.

**`status` cannot be changed via `PATCH`/`PUT` on `/api/cards/{id}/`.** A request whose `status` differs from the card's current value is rejected with 400: `{"status": "Status cannot be changed here — POST to /api/cards/{id}/move/ instead."}`. Moving a card between columns is *only* done via `POST /api/cards/{id}/move/`, which is the one endpoint that renumbers both the source and destination columns correctly. A `PATCH` that echoes back the card's current, unchanged `status` alongside other real edits (e.g. `title`) is accepted — a UI PATCHing back the full set of fields it holds does not need to strip `status` out, it just must not try to change it that way.

Card responses also carry read-only extras beyond the writable fields above: `assignee_detail` (a nested `{id, username, display_name}` object for the current `assignee`, returned alongside the raw `assignee` id), `created_by` (a nested user object), and `priority_label` (the human-readable form of `priority`). None of these three are accepted on write.

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
