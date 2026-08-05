# Tasky — design prototype

Plain HTML, CSS and vanilla JavaScript. No framework, no build step, no package
manager. This is the **design phase** deliverable: the complete UI and its
business logic, made clickable so it can be corrected cheaply before anything is
built for real.

**Nothing in `frontend/` or the React plan is in play until this is signed off.**
See the hard rule at the top of `../CLAUDE.md`.

## Look at it

```bash
cd design && python3 -m http.server 5500
```

Then open http://127.0.0.1:5500 — sign in as `alice` with any password.

No backend needed. It runs on a mock store seeded with a board about building
Tasky itself.

## Files

| File | What it is |
|---|---|
| `index.html` | The shell and every screen's markup, as `<template>` blocks |
| `css/app.css` | The whole visual system |
| `js/logic.js` | **Business logic — pure, no DOM, no network.** Grouping, the optimistic move, overdue rules |
| `js/store.js` | Mock data source. Enforces the same server rules the real API does |
| `js/api.js` | Real data source against the live Django API. Same interface as the store |
| `js/app.js` | Views, hash routing, drag and drop, wiring |

`store.js` and `api.js` implement the same interface, so switching to the real
backend is one line at the top of `app.js`:

```js
const DATA_SOURCE = 'api';   // was 'store'
```

## The design

**Colour is attention.** Only In Progress is saturated. To Do stays neutral and
Done recedes — so the board tells you where attention belongs before you read a
word of it.

**The left edge rule.** Each card carries a vertical rule on its left edge.
Its *thickness* is priority (1px low, 2px medium, 4px high) and its *colour*
turns red when the card is overdue. One device carries two dimensions and stays
legible in a dense column, which a row of coloured dots does not.

**Monospace for data.** Every date, count and id is monospace. The audience is
engineers and aligned digits genuinely scan faster in a list. It is functional,
not stylistic.

## Honest about the rules

The prototype is a model of the product, not a picture of it. The mock store
enforces what the real API enforces, so these behave correctly here:

- Sign-in failure says the same thing for an unknown username and a wrong
  password — a different message would let anyone enumerate who works here
- Changing a card's `status` through the edit form is **rejected**; columns
  change only by dragging
- A failed drag springs the card back to exactly where it was
- Deleting someone else's comment is refused, and that refusal does **not**
  sign you out
- `GET /boards/{id}/cards/` returns all three columns interleaved in one list;
  the client groups them
- Card positions are not contiguous, and gaps are never treated as corruption

## Not built yet

Search, labels, attachments, notifications, activity history, subtasks,
per-board permissions and password reset are all out of scope for v1 — see
`../docs/superpowers/specs/2026-07-29-team-kanban-design.md`. Teammates' changes
appear on refresh; there is no realtime.
