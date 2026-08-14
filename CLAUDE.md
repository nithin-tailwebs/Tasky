# Tasky — working agreement

Internal team Kanban. Django + DRF + MySQL backend (complete), with a UI still being designed.

---

## Status

**Design signed off: 2026-08-05.** The prototype in `design/` is approved and Phase 2
(development) is unlocked. The rule below is satisfied — it is kept for the record, and it
applies again to any future redesign.

## HARD RULE — design is signed off before development starts

**Do not begin product development until the design has been explicitly signed off by the user.**

This is not a preference or a default that can be reasoned around. It holds even when:

- the design "looks obviously right" and building it seems faster
- a plan or spec already exists and appears approved
- the user asks for a feature that would be quick to just build
- an earlier session left scaffolding or a partial implementation in place

**What counts as sign-off:** the user saying, in their own words, that the design is
approved / signed off / good to build. Nothing else counts. Not silence, not "ok" to an
unrelated question, not a skill's internal approval gate, not your own judgement that the
design is complete.

**If you are unsure whether sign-off has happened, it has not.** Ask.

### The two phases

**Phase 1 — Design.** Plain HTML and vanilla JavaScript. No frameworks, no build step, no
package manager. The complete UI, every screen, with the business logic expressed in
vanilla JS so the flows are real and clickable rather than static pictures. This phase
exists so the product can be seen and corrected cheaply.

**Phase 2 — Development.** Only after sign-off. The production implementation.

## The UI is vanilla JS, on purpose

`ui/` is the production front end: plain HTML, CSS and JavaScript, served directly by
Django. **There is no build step, no npm, no `node_modules`, no framework.** Do not
introduce one.

React was specced and planned earlier, then dropped in favour of shipping the design that
was actually signed off. Those documents are kept for the record and marked superseded:

- `docs/superpowers/specs/2026-08-05-tasky-ui-design.md`
- `docs/superpowers/plans/2026-08-05-tasky-ui.md`

**They do not describe the current UI.** Read `ui/README.md` instead.

---

## Backend facts that bite

The API is finished and documented in `docs/api.md`. Read it before writing any client code.
Three behaviours cause bugs if missed:

- **Unauthenticated calls return `403`, never `401`.**
- **`status` and `board` cannot be changed via `PATCH`** on `/api/work-items/{id}/`. Column moves
  go only through `POST /api/work-items/{id}/move/`.
- **`GET /api/boards/{id}/work-items/` interleaves all three columns** in one position-ordered
  list. The client groups by `status` itself.

Also: `position` is not contiguous. Gaps like `0, 2, 3` are normal after a delete and must
never be treated as corruption.

`403` is ambiguous — it means both "session expired" and, legitimately, "you may not delete
another person's comment". Do not treat every 403 as a logout.

## Do not "fix" these

`docs/follow-ups.md` has a **deliberate non-goals** section covering three things in
`boards/services.py` that look like bugs and are not. Read it before touching that file.

## Running it

Docker here is Colima, not Docker Desktop. MySQL runs natively on the Mac, not in a container.

```bash
colima status || colima start --cpu 2 --memory 3 --disk 20
docker compose up                              # http://localhost:8000
docker compose run --rm web pytest             # 92 tests
docker compose run --rm web python manage.py seed_demo
```

`docs/handover.md` covers the machine-specific gotchas (port 3307, the `'tasky'@'%'` grant,
`bind-address`).
