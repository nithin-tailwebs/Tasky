# Tasky — design prototype

Plain HTML, CSS and vanilla JavaScript. No framework, no build step, no
package manager — same rules as `../ui/`.

**This is Phase 1 of the redesign**, per this repo's hard rule: Phase 2
(production Django/DRF implementation) does not begin for a sub-project
until its prototype is signed off here, in the user's own words. This
directory grows as each sub-project's design is approved — it's a running
prototype of the whole product, not a one-off mockup.

| Sub-project | Spec | Status |
|---|---|---|
| 1 — Projects & Membership | `../docs/superpowers/specs/2026-08-13-tasky-projects-membership-design.md` | Signed off, **shipped to production** (`../ui/`, `../projects/`) |
| 2a — Work Item Hierarchy | `../docs/superpowers/specs/2026-08-14-tasky-work-item-hierarchy-design.md` | Signed off, **shipped to production** (`boards/models.py`, `../ui/`) |
| 2b — Custom Fields & Screens | `../docs/superpowers/specs/2026-08-18-tasky-custom-fields-screens-design.md` | **Prototype below — awaiting sign-off** |

Because sub-projects 1 and 2a already shipped, this prototype's Projects &
Membership and Board/work-item screens are now mostly a faithful *replica*
of what's live in `../ui/` — they exist here so sub-project 2b's new
screens (Fields, Screens, custom field inputs on a work item) have
somewhere real to hang off, not because that part still needs review.

## Run it

No server required — open `index.html` directly in a browser. There's no
backend to reach, so unlike `../ui/`, absolute `/static/...` paths aren't
needed.

Sign in as `asha`, `kabir` or `lena` — any password works.

## Suggested walkthrough (as Asha)

1. **Sign in as `asha`.** The Projects page shows a pending invitation to
   "Marketing Launch" — Accept or Decline it. You're Owner of
   **Tasky Redesign (`TASKY`)** and Admin of **Website Refresh (`WEB`)**.
2. **Open Tasky Redesign, then open its Sprint Board.** Seeded with a
   realistic hierarchy: Epic `TASKY-1` "Redesign onboarding", with a Story
   and a Task under it, a Subtask under the Story, and a standalone Bug.
   Notice each card's key, type badge, and (for children) a chip pointing
   at its parent.
3. **Click a card to open it.** Try:
   - Changing its **Parent** — the dropdown only offers types the
     hierarchy actually allows (a Subtask only sees Stories/Tasks/Bugs on
     this board, an Epic sees no parent field at all).
   - Toggling **Components** — Frontend/Backend are pre-seeded; try
     adding one via the Components section back on the project page
     first, then apply it here.
   - **+ Link an item** — pick another item on the board, save, then
     remove it again from the "Related items" list.
   - Opening a **child** from the Epic's Children list — jumps straight
     to that item's own detail view.
4. **Add a new work item** via "+ Add work item" in any column — pick
   Subtask as the type before picking a parent, and notice the parent
   field requires one and only offers valid Story/Task/Bug candidates.
   Try picking Epic as the type — the parent field disables entirely.
5. **Delete the Epic** (open it, Delete). Its Story and Task survive on
   the board, just without a parent chip anymore — nothing cascades.
6. **Sign out, sign in as `lena` or `kabir`** to see the Projects &
   Membership flows from an Owner/Admin/Member angle other than Asha's —
   unchanged from sub-project 1's prototype, now shipped in `../ui/`.

## Sub-project 2b — Custom Fields & Screens

7. **Open Fields (top nav).** Only Owners of some project can manage
   these (Asha qualifies). Add a field of each type — try a Select or
   Multi-select and add a couple of options to it. Try changing a field's
   type after creation — it's blocked, per spec. Try deleting a field
   that's on a Screen — also blocked, until you remove it from the
   Screen first.
8. **Open Screens.** Create a screen, add a few of the fields you just
   made to it, reorder them, and toggle "required" on one.
9. **Back on the Tasky Redesign project page**, under "Field screens",
   point one or two item types (e.g. Task) at the screen you built. Try
   "None" — that item type goes back to built-in fields only.
10. **Open the Sprint Board and add or open a Task.** The screen's custom
    fields now render in the create form and the detail modal, in the
    screen's order, with the required ones marked. Leave a required one
    blank and save — the error lands under that specific field. Save
    successfully, then reopen the item to see the value persisted.
11. **Reassign that item type to a different screen (or "None")** back on
    the project page, then reopen the same work item — its old field's
    saved value still shows, under "Other saved values", read-only, per
    the spec's "orphaned values stay visible" rule.

All state is in memory — refreshing the page resets it to the seed above.

## Files

| File | What it is |
|---|---|
| `index.html` | Shell and every screen's markup, as `<template>` blocks |
| `css/app.css` | Visual system — same tokens and components as `../ui/`, extended for these new screens |
| `js/logic.js` | Pure rules — no DOM, no network. This file **is** the specs' permission matrix and hierarchy rules, executable |
| `js/store.js` | Mock data source. Enforces the same rules a real API would (see each spec's error table) |
| `js/app.js` | Views, hash routing, modals, and the interaction polish (skeleton loading, staggered row entrances, animated modal/toast lifecycle) |

## What to check when reviewing sub-project 2b

- Is one screen per item type (not separate create/edit/view screens)
  enough, or did you want the create form and the detail view to differ?
- Is "None" (built-in fields only) a good default for an item type with
  no screen assigned, or should new projects require picking one?
- Does "orphaned values stay visible, read-only, once a field drops off
  the screen" match what you'd expect, or is that surprising/unwanted?
- Are 8 field types the right set, or is something obviously missing
  (e.g. a URL type) before this goes to backend?
- Anything from the spec's data model or flows that reads wrong once
  you're actually clicking it, rather than reading it.
