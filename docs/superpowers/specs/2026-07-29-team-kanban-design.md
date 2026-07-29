# Tasky — Internal Team Kanban · Design

**Status:** DRAFT v0.1 — open questions in §9, not yet approved
**Date:** 2026-07-29
**Owner:** Siddharth (siddharthkajaria@tailwebs.com)

---

## 1 · What we're building

An internal Kanban board for the team — Jira's useful 10%, none of its weight.
Self-hosted on our own EC2 box, used inside the org only.

## 2 · Who uses it

A small team. Everyone signs in. Accounts are **created by an admin** — there is no public signup,
no invite emails, no password-reset flow in v1.

## 3 · Decisions already locked

| Decision | Choice | Why |
|---|---|---|
| Product shape | Kanban board, drag cards between columns | The most Jira-feeling feature; visual and immediately useful |
| Boards | **Multiple** — one per project | Retrofitting multi-board later means touching every query and screen |
| Columns | **Fixed three**: To Do / In Progress / Done | Custom columns were explicitly not wanted; skipping them removes the fiddliest logic in a kanban build |
| Users | Small team, shared cards, per-user login | It's a team tool, not a personal one |
| Signup | **Admin creates accounts** | No self-signup surface to defend |
| User management UI | **Django admin** (free, zero code) | Entire "admin creates accounts" requirement costs nothing |
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

### 5.1 · v1 — agreed core

- Login / logout
- Multiple boards, each with a name and description
- Cards with **title**, **description**, **assignee**
- Drag a card between the three columns, and reorder within a column
- Create / edit / delete boards and cards
- Add and manage teammates via `/admin/`

### 5.2 · v1 — proposed additions ⚠️ OPEN, needs a decision

Four things I'd argue belong in v1. **None are agreed yet** — see §9.

| Feature | What it is | Argument for v1 |
|---|---|---|
| **Due dates** | A date per card; overdue ones visibly flagged | One field. Without dates a board goes stale in about two weeks |
| **Priority** | High / Medium / Low as a coloured dot | Highest value per line of code on the whole list |
| **Comments** | A thread under each card | What makes it a *team* tool instead of a shared list — where "why did we do this" lives |
| **"My tasks" view** | Everything assigned to you, across all boards | Once there are 4+ boards this becomes the screen people actually open |

### 5.3 · Deliberately NOT in v1

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

## 6 · Data model

Four tables.

**User** — Django auth, but as a **custom user model** (`AUTH_USER_MODEL`) from day one.
> Identical to the default today. Django makes swapping it later genuinely painful, so it costs one file now
> and prevents the most common Django regret.

**Board** — `name` · `description` · `created_by` → User · `created_at` · `updated_at`
> v1: every signed-in person sees every board. No membership table.

**Card**
- `board` → Board
- `title` · `description`
- `status` → `todo` | `in_progress` | `done`
- `assignee` → User *(nullable — unassigned is a normal state)*
- `position` → integer, order within its column
- `created_by` → User · `created_at` · `updated_at`
- *(pending §5.2: `due_date`, `priority`)*

**Comment** *(only if §5.2 comments are approved)* — `card` → Card · `author` → User · `body` · `created_at`

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
GET    /api/users/               ← names for the assignee dropdown
```

`move/` is deliberately separate from `PATCH`. Reordering is a different operation, it touches multiple rows,
and keeping it apart stops update logic tangling with ordering logic.

## 8 · Screens

| # | Screen | What's on it |
|---|---|---|
| 1 | Login | Username + password |
| 2 | Boards | The list, plus "new board" |
| 3 | Board | The kanban — three columns, drag cards, add a card |
| 4 | Card | Modal to edit title, description, assignee — and delete |

Adding people is **not** a screen. That's `/admin/`, free from Django.

## 9 · Open questions

1. **Which of the four §5.2 features are in v1?** My recommendation: all four. They're small individually and
   they're the difference between a demo and something the team will keep using.
2. **Anything in §5.3 that needs pulling forward?** My recommendation: nothing.
3. **Project name** — `tasky` is a placeholder. Renaming is one `mv`.
4. **Roughly how many people** will use it? Changes nothing architecturally; useful sanity check on the
   "everyone sees everything" call in §6.

## 10 · Success criteria

v1 is done when, on the EC2 box:

- A teammate can be created in `/admin/` and sign in
- They can create a board, add a card, assign it, and drag it to Done
- Their change is visible to another teammate on refresh
- Closing the browser and returning loses nothing
