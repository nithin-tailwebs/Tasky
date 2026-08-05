# Tasky — React UI · Design

**Status:** v1.0 — agreed, ready for implementation planning
**Date:** 2026-08-05
**Builds on:** `docs/superpowers/specs/2026-07-29-team-kanban-design.md` (product decisions)
**Contract:** `docs/api.md` — the API is complete, reviewed and merged. This spec does not change it.

---

## 1 · What we're building

The React front end for Tasky, covering the five screens the product spec named: Login, Boards,
Board, Card, My Tasks. The backend is done and unchanged by this work.

## 2 · Decisions

Product-level choices (React, Vite, `dnd-kit`, same origin, three fixed columns) were settled in the
July design spec and are not revisited here. What follows are the UI build decisions.

| Decision | Choice | Why |
|---|---|---|
| Language | **Plain JavaScript** | Optimise for shipping, per the product spec's stated priority |
| Server data | **Plain `fetch` + custom hooks** | No data-library dependency; the cost is hand-rolling optimistic drag, which §5 contains in one module |
| Styling | **Tailwind CSS** | Fast for a dense board; priority dots, overdue flags and column layout are quick to express |
| Routing | **React Router** | Five screens, and deep links must survive refresh |
| Testing | **Vitest, on the two risky files only** | ~15–20 tests where bugs actually live; no component or drag simulation tests |
| Sequencing | **Walking skeleton first** | Login → Boards → draggable Board is usable alone, and lands the risky work while scope is small |

## 3 · Structure

`frontend/` at the repo root, alongside the Django apps — one repo, one history.

```
frontend/
  src/
    api/          client.js, auth.js, boards.js, cards.js, comments.js
    hooks/        useBoards, useBoardCards, useCard, useComments, useUsers
    state/        moveCard.js        ← optimistic drag, pure, tested
    components/   Column, CardTile, PriorityDot, DueDate, Modal, …
    routes/       Login, Boards, Board, MyTasks
    App.jsx  main.jsx
  index.html  vite.config.js  package.json
```

### Dev: one origin, via proxy

Vite serves `:5173`, Django `:8000`. Left alone that is cross-origin and the session cookie dies,
which would defeat the same-origin premise the backend was built on. `vite.config.js` proxies
`/api` to `:8000` so the browser only ever sees `:5173`.

**No CORS, no `django-cors-headers`, no cross-site cookie flags.** The July spec ruled CORS out
deliberately; the proxy is what makes that hold in development.

### Production: Django serves the build

`docs/follow-ups.md` records that `STATIC_ROOT` and `collectstatic` were omitted *by design, for
this plan to supply*. In scope here:

- `npm run build` emits to `frontend/dist/`, which is added to `STATICFILES_DIRS`; `STATIC_ROOT`
  is set so `collectstatic` gathers it alongside Django admin's own assets
- a catch-all Django route returning `frontend/dist/index.html`, registered **after** `/api/` and
  `/admin/` so it never shadows them — this is what lets a deep link such as `/boards/3` survive a refresh

Out of scope, belonging to the deployment plan: the Docker multi-stage build, Apache, RDS.

## 4 · Auth and the API client

`App.jsx` calls `GET /api/auth/me/` once on mount. `200` renders the app; **`403` renders Login.**
Nothing renders until that resolves, so no screen flashes before the user is known.

`apiFetch` wraps every call and:

- calls `GET /api/auth/csrf/` once at startup so the `csrftoken` cookie exists
- attaches `X-CSRFToken` from that cookie to every POST / PATCH / DELETE
- disambiguates 403 — see §6

## 5 · Card data and the drag

### Grouping is the client's job

`GET /api/boards/{id}/cards/` **interleaves all three statuses** in one `position`-ordered list. The
board route reduces the response into `todo` / `in_progress` / `done` buckets before rendering.
Two cards in different columns sharing a `position` is expected, not corruption.

### Positions are opaque

`position` is not contiguous — gaps like `0, 2, 3` are normal after a delete, and `docs/api.md` is
explicit that they must never be read as corruption. The client therefore never computes from
`position` and never assumes `index === position`. Order comes from array order; the destination
*index* is what gets sent on a move.

### The move

`state/moveCard.js` is a pure function over the three buckets with the network call injected — which
is what makes it testable without dragging anything.

1. `dnd-kit` reports card, destination column, destination index.
2. **Snapshot** the buckets.
3. Apply locally: remove from the source bucket **first**, then insert at the target index. That
   order avoids the off-by-one that appears when reordering within a single column.
4. `POST /api/cards/{id}/move/` with `{status, position}`.
5. **On success, refetch the board's cards.** The server renumbers the whole column in a
   transaction; if a teammate dragged concurrently, the local guess at the resulting order is wrong.
   One cheap GET reconciles. Without it the board drifts and only a manual refresh corrects it.
6. **On error, restore the snapshot** — the card visibly springs back.
7. **On 404, drop the card and refetch.** The API returns 404 when the card was deleted before the
   move landed. Restoring the snapshot would resurrect a card that no longer exists.

## 6 · Errors

**403 means two different things**, and treating it as one would be a bug: "your session is gone",
and legitimately "you may not delete another person's comment". Blanket-treating it as logout would
eject the user to Login for clicking the wrong delete button.

On any 403, `apiFetch` re-checks `GET /api/auth/me/`. If that also 403s the session is genuinely
gone and the app bounces to Login. Otherwise it surfaces as a permission message and the user stays
where they are.

Otherwise: `400` renders field-level messages from the response body; network failure shows an
inline retry rather than a dead screen.

## 7 · Screens

### Phase 1 — walking skeleton

| Screen | Contents |
|---|---|
| Login | Username + password. `400` is bad credentials, shown inline. |
| Boards | Every board, unpaginated per the API, plus create. |
| Board | Three fixed columns, drag between and within, inline add-card. Priority dot and due date per tile; overdue flagged visually. |

### Phase 2

| Screen | Contents |
|---|---|
| Card | Modal: title, description, assignee, priority, due date, delete. |
| Comments | Flat thread inside the card modal. Delete shown only to the author. |
| My Tasks | `GET /api/me/tasks/` — my open cards across every board, soonest due first. |

### The card modal's sharp edge

The API rejects a PATCH that *changes* `status` or `board`, while tolerating them echoed back
unchanged. The edit form **simply never sends those two fields**, rather than depending on that
tolerance. Column changes go through `/move/`, the only path that renumbers correctly.

This is the same constraint `docs/follow-ups.md` warns against "fixing" in `boards/services.py`.

## 8 · Testing

Vitest. Roughly 15–20 tests across two files. No component tests, no `dnd-kit` simulation.

**`state/moveCard.js`** — reorder within a column; move across columns; rollback restores the exact
prior order; 404 drops the card rather than restoring it.

**`api/client.js`** — `X-CSRFToken` attached to unsafe methods and omitted from GET; the §6 403
disambiguation, both branches.

## 9 · Out of scope

Carried from the product spec: search / filter, labels, file attachments, email notifications,
activity history, subtasks, per-board permissions, password reset.

Also out: **realtime**. Teammates' changes appear on refresh, which the product spec's success
criteria explicitly allow.

Deployment (Docker multi-stage, Apache, RDS) is the plan after this one.

## 10 · Done when

- A user signs in, and a refresh keeps them signed in
- They create a board, add a card, and drag it between all three columns
- A failed drag springs the card back instead of leaving the board wrong
- They edit a card, assign it, set priority and due date, and comment
- My Tasks lists their cards across every board, soonest due first
- A deep link to `/boards/{id}` survives a browser refresh
- `npm run build` produces files Django serves
