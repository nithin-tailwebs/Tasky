# Tasky — Projects & Membership (design prototype)

Plain HTML, CSS and vanilla JavaScript. No framework, no build step, no
package manager — same rules as `../ui/`.

**This is Phase 1 of the redesign** described in
`../docs/superpowers/specs/2026-08-13-tasky-projects-membership-design.md`
(sub-project 1 of 7: Projects & Membership). It exists so the feature can be
seen and corrected cheaply, before any Django/DRF work starts. Per this
repo's hard rule, Phase 2 (production implementation) does not begin until
this prototype is signed off in the user's own words.

It is intentionally scoped to just this sub-project — it does **not**
reproduce the existing board/card screens (those are unchanged and already
production in `../ui/`). A "Boards" section inside each project is a stub
note saying so.

## Run it

No server required — open `index.html` directly in a browser. There's no
backend to reach, so unlike `../ui/`, absolute `/static/...` paths aren't
needed.

Sign in as `asha`, `kabir` or `lena` — any password works.

## Suggested walkthrough (as Asha)

The mock data is seeded so one login walks through every role and the
invite lifecycle:

1. **Sign in as `asha`.** The Projects page shows a **pending invitation**
   to "Marketing Launch" from Lena — Accept or Decline it.
2. You have two projects already:
   - **Tasky Redesign (`TASKY`)** — you're **Owner**. Open it: Invite (only
     Lena is invitable — Kabir's already a member), demote/promote Kabir's
     role with the dropdown next to his row, Transfer ownership, Remove a
     member, Delete project.
   - **Website Refresh (`WEB`)** — you're **Admin**. Invite is available;
     no Transfer/Delete; you can Leave.
3. **Create a project** from the Projects page — try a duplicate key
   (`TASKY`) to see it rejected, then a real one.
4. **Sign out, sign in as `lena`** — she owns "Client Portal" (`CLNT`),
   where Asha is a plain Member. From Lena's Owner view you can see the
   full member-management surface from the other side.
5. **Sign out, sign in as `kabir`** — he's Admin on "Client Portal", so you
   can see an Admin removing a Member (allowed) vs. trying to touch an
   Admin/Owner (not offered, matching the permission matrix).

All state is in memory — refreshing the page resets it to the seed above.

## Files

| File | What it is |
|---|---|
| `index.html` | Shell and every screen's markup, as `<template>` blocks |
| `css/app.css` | Visual system — same tokens and components as `../ui/`, extended for these new screens |
| `js/logic.js` | Pure role-permission rules — no DOM, no network. This file **is** the spec's permission matrix, executable |
| `js/store.js` | Mock data source. Enforces the same rules a real API would (see the error table in the spec) |
| `js/app.js` | Views, hash routing, modals, and the interaction polish (skeleton loading, staggered row entrances, animated modal/toast lifecycle) |

## What to check when reviewing

- Does the Owner / Admin / Member permission split match what you expect
  day to day — who can invite, remove, promote, delete, leave?
- Is invite-then-accept the right shape, or did you actually want
  immediate add?
- Is the project switcher + "All projects" page enough for navigating
  multiple projects, or do you want something more?
- Anything from the spec's data model or flows that reads wrong once
  you're actually clicking it, rather than reading it.
