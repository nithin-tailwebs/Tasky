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
| GET | `/api/boards/` | every board in a project I'm a member of; unpaginated |
| POST | `/api/boards/` | `{project, name, description?}`; `description` is optional; creator is taken from the session; `project` must be one I'm a member of |
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

**`project` cannot be changed via `PATCH`/`PUT` on `/api/boards/{id}/`** — boards do not
move between projects, mirroring the rule already in place for `status` and `board` on
cards. A `PATCH` that echoes back the board's current, unchanged `project` alongside
other real edits is accepted.

## Projects
Every board and card now lives inside a project. Membership is invite-only — nobody
joins a project by any route other than accepting a pending invitation.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/projects/` | projects I'm a member of |
| POST | `/api/projects/` | `{key, name, description?}`; `key` is 2–10 letters, case-insensitive on input but stored uppercase, unique across the system; creator becomes Owner |
| GET | `/api/projects/{id}/` | 403 if I'm not a member (not 404 — see below), 404 if the id doesn't exist at all |
| DELETE | `/api/projects/{id}/` | Owner only; cascades to the project's boards, cards, comments, memberships and invitations |
| GET | `/api/projects/{id}/members/` | sorted Owner, then Admin, then Member |
| DELETE | `/api/projects/{id}/members/{user_id}/` | removes a member; also doubles as "leave" when `user_id` is your own — Owner can remove anyone but themself (and cannot leave without transferring ownership first, 400 if they try), Admin can remove Members only (but can leave freely), Member can only leave |
| POST | `/api/projects/{id}/members/{user_id}/role/` | `{role: "admin"\|"member"}`; Owner only; the Owner's own role can't be changed here |
| POST | `/api/projects/{id}/transfer-ownership/` | `{user_id}`; Owner only; target must already be an Admin; the caller becomes an Admin |
| POST | `/api/projects/{id}/invite/` | `{user_id}`; Owner or Admin; 400 if already a member or already invited |

**A non-member touching a project (or its boards/cards) gets `403`, not `404`.** A
genuinely nonexistent id still 404s — existence is checked first, membership second.

Every project role is one of `owner`, `admin`, `member`. There is exactly one Owner at
all times; the Owner cannot leave a project without transferring ownership to an
existing Admin first (there is no "leave" endpoint of its own — the client models
"leave" as removing your own membership, subject to the same owner restriction as any
other removal).

## Cards
| Method | Path | Notes |
|---|---|---|
| GET | `/api/cards/` | every card on a board in a project I'm a member of — not filtered to "my boards" specifically, but scoped by project membership |
| POST | `/api/cards/` | `{board, title, description?, status?, priority?, due_date?, assignee?}`; `status` defaults to `todo` when omitted; `board` must belong to a project I'm a member of |
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
| DELETE | `/api/comments/{id}/` | if the comment has an author, only that author can delete it (otherwise 403); if the comment's author account has been deleted (`author` is `null`), any signed-in user who is a member of the comment's project can delete it (403 for non-members) |

## Invitations
| Method | Path | Notes |
|---|---|---|
| GET | `/api/invitations/` | my own pending invitations |
| POST | `/api/invitations/{id}/accept/` | creates a Member-role membership; 403 if it isn't your invitation |
| POST | `/api/invitations/{id}/decline/` | 403 if it isn't your invitation |

## Me
| Method | Path | Notes |
|---|---|---|
| GET | `/api/me/tasks/` | my open cards in a project I'm still a member of, soonest due first |
| GET | `/api/users/` | `id`, `username`, `display_name` for the assignee dropdown |
