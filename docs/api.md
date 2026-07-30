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
| POST | `/api/boards/` | `{name, description}`; creator is taken from the session |
| GET/PATCH/DELETE | `/api/boards/{id}/` | |
| GET | `/api/boards/{id}/cards/` | every card on the board, ordered by column position |

## Cards
| Method | Path | Notes |
|---|---|---|
| POST | `/api/cards/` | `{board, title, description?, status?, priority?, due_date?, assignee?}` |
| GET/PATCH/DELETE | `/api/cards/{id}/` | `position` is read-only here |
| POST | `/api/cards/{id}/move/` | `{status, position}` — the drag-and-drop endpoint |

`status` is one of `todo`, `in_progress`, `done`.
`priority` is `1` low, `2` medium, `3` high; responses also carry `priority_label`.

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
