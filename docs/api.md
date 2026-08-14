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
| GET | `/api/boards/{id}/work-items/` | every work item on the board — see the ordering note below |

**Ordering of `/api/boards/{id}/work-items/` is NOT "grouped by column."** The queryset
orders by `WorkItem.Meta.ordering = ["position", "id"]`, which is a single ordering
applied across *all three* statuses at once, not per-column. In practice that means
the three columns **interleave**: `todo#0, in_progress#0, done#0, todo#1, …` — a
work item's `position` is only unique *within its own `status`*, so two different-status
work items can and will share the same `position` value back to back in this list. The
client must **group the response by `status` itself** (into `todo` / `in_progress`
/ `done` buckets) before rendering columns; do not assume the API hands back
already-grouped or already-column-ordered data.

**`project` cannot be changed via `PATCH`/`PUT` on `/api/boards/{id}/`** — boards do not
move between projects, mirroring the rule already in place for `status` and `board` on
work items. A `PATCH` that echoes back the board's current, unchanged `project` alongside
other real edits is accepted.

## Projects
Every board and work item now lives inside a project. Membership is invite-only — nobody
joins a project by any route other than accepting a pending invitation.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/projects/` | projects I'm a member of |
| POST | `/api/projects/` | `{key, name, description?}`; `key` is 2–10 letters, case-insensitive on input but stored uppercase, unique across the system; creator becomes Owner |
| GET | `/api/projects/{id}/` | 403 if I'm not a member (not 404 — see below), 404 if the id doesn't exist at all |
| DELETE | `/api/projects/{id}/` | Owner only; cascades to the project's boards, work items, comments, memberships and invitations |
| GET | `/api/projects/{id}/members/` | sorted Owner, then Admin, then Member |
| DELETE | `/api/projects/{id}/members/{user_id}/` | removes a member; also doubles as "leave" when `user_id` is your own — Owner can remove anyone but themself (and cannot leave without transferring ownership first, 400 if they try), Admin can remove Members only (but can leave freely), Member can only leave |
| POST | `/api/projects/{id}/members/{user_id}/role/` | `{role: "admin"\|"member"}`; Owner only; the Owner's own role can't be changed here |
| POST | `/api/projects/{id}/transfer-ownership/` | `{user_id}`; Owner only; target must already be an Admin; the caller becomes an Admin |
| POST | `/api/projects/{id}/invite/` | `{user_id}`; Owner or Admin; 400 if already a member or already invited |

**A non-member touching a project (or its boards/work items) gets `403`, not `404`.** A
genuinely nonexistent id still 404s — existence is checked first, membership second.

Every project role is one of `owner`, `admin`, `member`. There is exactly one Owner at
all times; the Owner cannot leave a project without transferring ownership to an
existing Admin first (there is no "leave" endpoint of its own — the client models
"leave" as removing your own membership, subject to the same owner restriction as any
other removal).

## Work Items
| Method | Path | Notes |
|---|---|---|
| GET | `/api/work-items/` | every work item on a board in a project I'm a member of |
| POST | `/api/work-items/` | `{board, item_type, title, description?, status?, priority?, due_date?, assignee?, parent?, components?}` |
| GET/PUT/PATCH/DELETE | `/api/work-items/{id}/` | `key`, `item_type`, `position` are immutable; `status`/`board` unchanged from before |
| POST | `/api/work-items/{id}/move/` | unchanged — the drag-and-drop endpoint |
| GET | `/api/boards/{id}/work-items/` | every work item on that board |
| GET | `/api/work-items/{id}/children/` | direct children only (not grandchildren) |
| GET/POST | `/api/work-items/{id}/links/` | list / create a "relates to" link; POST body is `{item: <other work item id>}` |

`status` is one of `todo`, `in_progress`, `done`, and **defaults to `todo` when omitted on create.**
`priority` is `1` low, `2` medium, `3` high; responses also carry `priority_label`.

`item_type` is one of `epic`, `story`, `task`, `bug`, `subtask` — fixed for every project. `key` (e.g. `TASKY-123`) is generated on create from a per-project counter shared across every type and board, and can never be changed afterward. `parent` must be an Epic for a Story/Task/Bug, must be a Story/Task/Bug for a Subtask (required, not optional), can never be set on an Epic, and must be on the same board as the child — violating any of these is a `400` naming `parent`. Deleting a work item clears its children's `parent` rather than deleting them.

**`status` cannot be changed via `PATCH`/`PUT` on `/api/work-items/{id}/`.** A request whose `status` differs from the work item's current value is rejected with 400: `{"status": "Status cannot be changed here — POST to /api/work-items/{id}/move/ instead."}`. Moving a work item between columns is *only* done via `POST /api/work-items/{id}/move/`, which is the one endpoint that renumbers both the source and destination columns correctly. A `PATCH` that echoes back the work item's current, unchanged `status` alongside other real edits (e.g. `title`) is accepted — a UI PATCHing back the full set of fields it holds does not need to strip `status` out, it just must not try to change it that way.

**`board` cannot be changed via `PATCH`/`PUT` on `/api/work-items/{id}/` either, for the same reason.** Work items do not move between boards in this product at all — a request whose `board` differs from the work item's current board is rejected with 400: `{"board": "Work items cannot be moved between boards."}`. As with `status`, a `PATCH` that echoes back the work item's current, unchanged `board` alongside other real edits is accepted.

Work item responses also carry read-only extras beyond the writable fields above: `assignee_detail` (a nested `{id, username, display_name}` object for the current `assignee`, returned alongside the raw `assignee` id), `created_by` (a nested user object), `priority_label` (the human-readable form of `priority`), `parent_detail` (a nested summary of the parent — `{id, key, title, item_type, status}` — alongside the raw `parent` id, or `null` with no parent), and `components_detail` (the full nested `Component` objects for the current `components`, alongside the raw `components` id list). `key` is likewise response-only, system-generated on create. None of these are accepted on write.

**`position` is not a system-wide contiguous `0..n-1` invariant** — it is only guaranteed to give a column a deterministic total order (ties broken by `id`), and it is renormalised to a clean `0..n-1` at the moment `/move/` renumbers that column. Deleting a work item, for instance, does **not** renumber anything afterward, so gaps (`0, 2, 3`, say) are expected and harmless — never treat a gap as a sign of corrupted data, and never rely on `position` values being consecutive.

## Components
| Method | Path | Notes |
|---|---|---|
| GET/POST | `/api/projects/{id}/components/` | POST is Owner/Admin only |
| PATCH/DELETE | `/api/projects/{id}/components/{id}/` | Owner/Admin only |

Any project member can apply an existing component to a work item via `PATCH /api/work-items/{id}/ {"components": [...]}"` — a component from a different project than the work item's is rejected with `400`.

## Work Item Links
| Method | Path | Notes |
|---|---|---|
| DELETE | `/api/work-item-links/{id}/` | removes the link from both sides |

See `GET/POST /api/work-items/{id}/links/` above for listing/creating. Self-links, duplicate links, and linking two items already in a parent/child relationship are all rejected with `400`.

**`DELETE /api/work-item-links/{id}/` requires membership in *both* linked items' projects, not just one.** This mirrors the AND semantics the create path already enforces — a link can only be created between two items the caller can see (member of both items' projects), so removing it holds the same bar. A caller who is a member of only one side's project gets `403`.

## Comments
| Method | Path | Notes |
|---|---|---|
| GET/POST | `/api/work-items/{id}/comments/` | POST takes `{body}`; author comes from the session |
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
| GET | `/api/me/tasks/` | my open work items in a project I'm still a member of, soonest due first |
| GET | `/api/users/` | `id`, `username`, `display_name` for the assignee dropdown |
