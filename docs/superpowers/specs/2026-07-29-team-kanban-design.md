# Tasky — Internal Team Kanban · Design

**Status:** v1.0 — feature set agreed, ready for implementation planning
**Date:** 2026-07-29
**Owner:** Siddharth (siddharthkajaria@tailwebs.com)

---

## 1 · What we're building

An internal Kanban board for the team — Jira's useful 10%, none of its weight.
Self-hosted on our own EC2 box, used inside the org only.

## 2 · Who uses it

A small team. Everyone signs in. Accounts are **created by an admin** — there is no public signup,
no invite emails, no password-reset flow in v1.

## 3 · Decisions locked

| Decision | Choice | Why |
|---|---|---|
| Product shape | Kanban board, drag cards between columns | The most Jira-feeling feature; visual and immediately useful |
| Boards | **Multiple** — one per project | Retrofitting multi-board later means touching every query and screen |
| Columns | **Fixed three**: To Do / In Progress / Done | Custom columns explicitly not wanted; skipping them removes the fiddliest logic in a kanban build |
| Users | Small team, shared cards, per-user login | It's a team tool, not a personal one |
| Signup | **Admin creates accounts** | No self-signup surface to defend |
| User management UI | **Django admin** (free, zero code) | The entire "admin creates accounts" requirement costs nothing |
| Board visibility | **Everyone sees every board** | Right for a small internal team. Restricting later is one table plus one filter, not a rewrite |
| Serving | **Same origin** — Django serves the built React files | Deletes CORS and cross-site cookie problems entirely |
| Priority of effort | Working tool over deep learning | Optimise for shipping; learn by tweaking afterwards |

## 4 · Tech stack

| Layer | Choice |
|---|---|
| API | Django + Django REST Framework |
| UI | React, compiled to static files, served by Django |
| Database | **MySQL** |
| Runtime | Django runs in **Docker**, published on a port |
| Web server (EC2) | **Apache** (`mod_proxy` + `mod_proxy_http`) reverse-proxying to the container |
| Auth | Django session cookies (same origin — no tokens to manage) |
| Drag & drop | `dnd-kit` (React) |

**Environments**

| | Local (Mac) | Server (EC2) |
|---|---|---|
| Django | Docker | Docker |
| MySQL | **MySQL installed on the Mac**, container connects out to it | **RDS MySQL** (managed backups/patching) |
| React | Vite dev server, hot reload | Pre-built static files served by Django |
| Front door | direct to the port | Apache on 80/443, TLS terminates there |

Same code in both. The database connection string comes from an environment variable — that is the only difference.

## 5 · Feature set

### 5.1 · v1 — agreed, all of it

**Core**
- Login / logout
- Multiple boards, each with a name and description
- Cards with **title**, **description**, **assignee**
- Drag a card between the three columns, and reorder within a column
- Create / edit / delete boards and cards
- Add and manage teammates via `/admin/`

**Agreed additions**

| Feature | What it does |
|---|---|
| **Due dates** | A date per card. Overdue cards are visibly flagged |
| **Priority** | High / Medium / Low, shown as a coloured dot on the card |
| **Comments** | A thread under each card, so the reasoning lives with the work |
| **"My tasks"** | One screen listing everything assigned to you, across every board |

### 5.2 · Deliberately NOT in v1

Not "forgotten" — each is a considered deferral, with the trigger for revisiting it.

| Feature | Why it waits | Revisit when |
|---|---|---|
| Search / filter | Nothing to lose yet | Boards get busy enough to lose a card |
| Labels / tags | Overlaps with priority | Priority proves too coarse |
| File attachments | Needs S3, size limits, malware thinking — big scope jump | Someone actually asks twice |
| Email notifications | Needs SES and a sending domain | The team doesn't check the board on its own |
| Activity history | Nobody misses it early | An audit trail is needed |
| Subtasks / checklists | Real UI complexity; a card needing subtasks is usually two cards | Cards genuinely can't be split |
| Per-board permissions | Small team, everyone sees everything | Someone needs a board others can't see |
| Password reset | Admin can set a password in `/admin/` | Team grows past the point where that's tolerable |

## 6 · Data model

Four tables.

**User** — Django auth, but as a **custom user model** (`AUTH_USER_MODEL`) from day one.
> Identical to the default today. Django makes swapping it later genuinely painful, so it costs one file now
> and prevents the most common Django regret.

**Board** — `name` · `description` · `created_by` → User · `created_at` · `updated_at`

**Card**
- `board` → Board
- `title` · `description`
- `status` → `todo` | `in_progress` | `done`
- `priority` → `low` | `medium` | `high` *(default `medium`)*
- `due_date` → date *(nullable — most cards won't have one)*
- `assignee` → User *(nullable — unassigned is a normal state)*
- `position` → integer, order within its column
- `created_by` → User · `created_at` · `updated_at`

**Comment** — `card` → Card · `author` → User · `body` · `created_at`
> Edit and delete are author-only. No threading, no reactions — a flat list.

**Columns are not a table.** Three fixed statuses on the card instead. A table here would be pure overhead
given custom columns were ruled out.

**Ordering on drag:** the browser sends where the card landed (`status` + `position`); the server renumbers
that column inside a transaction. Blunt, but correct when two people drag at once — which fractional-index
approaches are not, without more care than this project warrants.

## 7 · API surface

Session cookies, same origin, no tokens.

```
POST   /api/auth/login/          POST /api/auth/logout/       GET /api/auth/me/

GET    /api/boards/              POST /api/boards/
GET    /api/boards/{id}/         PATCH /api/boards/{id}/      DELETE /api/boards/{id}/
GET    /api/boards/{id}/cards/

POST   /api/cards/               PATCH /api/cards/{id}/       DELETE /api/cards/{id}/
POST   /api/cards/{id}/move/     ← drag & drop

GET    /api/cards/{id}/comments/ POST /api/cards/{id}/comments/
DELETE /api/comments/{id}/       ← author only

GET    /api/me/tasks/            ← my cards across all boards
GET    /api/users/               ← names for the assignee dropdown
```

`move/` is deliberately separate from `PATCH`. Reordering is a different operation, it touches multiple rows,
and keeping it apart stops update logic tangling with ordering logic.

## 8 · Screens

| # | Screen | What's on it |
|---|---|---|
| 1 | Login | Username + password |
| 2 | Boards | The list, plus "new board" |
| 3 | Board | The kanban — three columns, drag cards, add a card. Priority dot and due date visible on each card |
| 4 | Card | Modal: title, description, assignee, priority, due date, comment thread — and delete |
| 5 | My tasks | Everything assigned to me across all boards, soonest due first |

Adding people is **not** a screen. That's `/admin/`, free from Django.

## 9 · Remaining open questions

Nothing blocking. Two loose ends:

1. **Project name** — `tasky` is a placeholder. Renaming is one `mv`.
2. **Team size** — changes nothing architecturally; a sanity check on the "everyone sees everything" call.

## 10 · Success criteria

v1 is done when, on the EC2 box:

- A teammate can be created in `/admin/` and sign in
- They can create a board, add a card, assign it, give it a priority and a due date, and drag it to Done
- They can comment on a card, and a teammate sees that comment
- "My tasks" shows them their own cards from every board
- Their changes are visible to another teammate on refresh
- Closing the browser and returning loses nothing
