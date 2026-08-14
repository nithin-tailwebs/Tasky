# Tasky — Work Item Hierarchy (Sub-project 2a of 13)

**Status:** Design approved in chat 2026-08-14. Awaiting Phase 1 (vanilla JS prototype) sign-off before Phase 2 development, per the hard rule in `CLAUDE.md`.

## Context

This is the second sub-project in Tasky's expansion from a single-board
Kanban tool toward a broader, Jira-inspired feature set. The full roadmap
(13 sub-projects, redrawn 2026-08-14 after reviewing Jira's actual feature
set) is:

1. Projects & Membership — shipped
2. **Work Item Hierarchy — this document**
3. Workflows (custom statuses/workflows)
4. Labels
5. Search
6. Backlog & Sprints
7. Releases
8. Task Detail UX
9. Permissions & Admin
10. Project Types & Setup
11. Automation
12. Notifications
13. Reporting & Dashboards

Sub-project 2 itself was further split during brainstorming into three
pieces, since its full 13-item source list was as large as all of
sub-project 1:

- **2a — Core Work Item Hierarchy (this document).** Issue types,
  hierarchy, unique IDs, components, issue linking. Replaces the current
  `Card` model.
- **2b — Custom Fields & Screens** (not yet designed). Depends on 2a's
  issue types existing.
- **2c — Bulk Operations & Import** (not yet designed). Depends on 2a's
  work items existing.

This document covers only 2a.

## Renaming Card → WorkItem

The existing `boards.Card` model, serializer, viewset, URL path
(`/api/cards/`), and every reference across the codebase (~150 existing
tests) renames to `WorkItem` / `/api/work-items/`. This is a deliberate,
approved breaking change — cleaner than keeping a model called `Card`
that can hold an Epic. It breaks the already-shipped UI's API calls
until the UI is updated to show hierarchy, which it needs regardless.

`Board`, `Comment`, and the project-scoping work from sub-project 1 are
otherwise unaffected — a `WorkItem` still belongs to exactly one `Board`,
the same as `Card` did.

## Data model

**WorkItem** (renamed from `Card`; existing fields — `title`,
`description`, `status`, `priority`, `due_date`, `assignee`, `board`,
`position`, `created_by`, `created_at`, `updated_at` — are unchanged)
gains:

- `item_type` — one of `epic`, `story`, `task`, `bug`, `subtask`. Fixed
  set, identical for every project — no per-project type schemes in this
  sub-project.
- `key` — e.g. `TASKY-123`. Unique, system-generated at creation, never
  editable afterward (see "Unique ID generation" below).
- `parent` — self-referential FK, nullable, `on_delete=SET_NULL`.
  Enforced by `item_type`:
  - `epic` → `parent` must be empty.
  - `story` / `task` / `bug` → `parent` is optional; if set, must be an
    `epic`.
  - `subtask` → `parent` is **required** and must be a `story`, `task`,
    or `bug` (never an `epic`, never another `subtask`).
- A work item's `parent` (when set) must share the same `board` as the
  child. Enforced on both create and re-parenting.

Deleting a work item **orphans** its children (`parent` → null) rather
than cascading the delete — matches the existing `SET_NULL` pattern
already used for `Board.created_by` in this codebase.

**Component**
- `project` (FK, `related_name="components"`), `name`. Unique together
  on `(project, name)`.
- Applied to `WorkItem` via a `ManyToManyField`.
- Only Owner/Admin can create, rename, or delete a project's components.
  Any project member can apply or remove an *existing* component on a
  work item they can edit.
- Deleting a component removes it from any work items that had it — the
  work items themselves are unaffected.

**WorkItemLink**
- `item_a`, `item_b` — both FKs to `WorkItem`. Symmetric: there is no
  "from"/"to" direction. Stored with a canonical ordering (lower `id`
  as `item_a`) so `A relates to B` and `B relates to A` are the same
  row, enforced by a `UniqueConstraint` on `(item_a, item_b)`.
- `created_by`, `created_at`.
- No self-links. Linking two items already in a parent/child
  relationship is rejected (400) rather than allowed as a second,
  confusing relationship.
- Any project member can create or remove a link between two items they
  can both see (both items resolve to a project the caller belongs to).

## Unique ID generation

- `Project` gains `next_item_number`, an integer counter starting at 1.
- Creating a `WorkItem` locks the `Project` row (`select_for_update`),
  reads `next_item_number`, assigns `key = f"{project.key}-{n}"`,
  increments the counter, and saves — all inside one transaction. This
  needs real locking, unlike `next_position`'s intentionally-unlocked
  pattern elsewhere in this codebase (documented in
  `boards/services.py` and `docs/follow-ups.md`): a duplicate `key`
  would be an actual correctness bug, not a harmless, self-healing gap.
- The counter is shared across every `item_type` and every `Board` in
  the project — Epics, Stories, Tasks, Bugs, and Subtasks all draw from
  the same sequence, so `TASKY-1, TASKY-2, TASKY-3…` reflects creation
  order regardless of type or board.

## API surface

```
GET    /api/work-items/                       every work item in a project I'm a member of
POST   /api/work-items/                       {board, item_type, title, description?, status?,
                                                priority?, due_date?, assignee?, parent?, components?}
GET/PUT/PATCH/DELETE /api/work-items/{id}/     item_type and key are immutable after creation
POST   /api/work-items/{id}/move/              unchanged from Card — drag-and-drop within a board's columns
GET    /api/boards/{id}/work-items/            renamed from /api/boards/{id}/cards/
GET    /api/work-items/{id}/children/          direct children of an epic/story/task/bug

GET/POST /api/work-items/{id}/links/           list / create a "relates to" link
DELETE /api/work-item-links/{id}/              remove a link

GET    /api/projects/{id}/components/          list a project's components
POST   /api/projects/{id}/components/          create (Owner/Admin only)
PATCH/DELETE /api/projects/{id}/components/{id}/   rename/delete (Owner/Admin only)
```

Re-parenting (`PATCH parent`) is allowed, but every write to `parent`
re-validates the hierarchy and same-board rules above.

## Error handling

| Case | Response |
|---|---|
| Invalid parent for the item's type (wrong type, or Epic given a parent, or Subtask given no parent) | 400 |
| Parent and child on different boards | 400 |
| Attempt to change `item_type` or `key` via PATCH | 400 |
| Self-link | 400 |
| Duplicate link between the same pair | 400 |
| Linking two items already in a parent/child relationship | 400 |
| Non-Owner/Admin creates, renames, or deletes a component | 403 |
| Non-member touches any work item, component, or link | 403 (via existing `IsProjectMember`, unchanged from sub-project 1 — `WorkItem` still resolves to a project through `board.project`) |
| Non-member request for a genuinely nonexistent id | 404 (existence checked before membership, same pattern as sub-project 1) |
| Unauthenticated request | 403, never 401 (existing site-wide convention) |

## Testing

Extends the pytest suite from sub-project 1 (163 tests as of that
sub-project's final review):

- Hierarchy validation: every (`item_type`, parent `item_type`)
  combination — the 5 valid shapes and every invalid one.
- Same-board constraint on both create and re-parent.
- Orphaning on parent delete (child survives, `parent` becomes null).
- Key generation: sequential across mixed types on the same project;
  no duplicate keys under the row-locking scheme.
- Components: Owner/Admin can manage the list, a plain Member cannot;
  applying/removing an existing component is open to any member;
  deleting a component clears it from work items without deleting them.
- Links: symmetric visibility from either item; duplicate/self/parent-
  child-conflict rejection; removal from either side removes for both.
- Full regression of the renamed `Card` → `WorkItem` surface — every
  existing Card-era test updated to the new model/serializer/viewset
  names and the new `/api/work-items/` path.

## Out of scope (deferred to later sub-projects)

- Custom fields, field configuration schemes, screens — sub-project 2b.
- Bulk edit, CSV import, issue templates — sub-project 2c.
- A hierarchy level above Epic (e.g. "Initiative") — not requested;
  revisit only if a real need shows up.
- Per-project issue type schemes (enabling/disabling types per
  project) — deferred; every project gets the same 5 types for now.
- Additional link types beyond "relates to" (blocks, duplicates,
  clones) — deferred; add only if "relates to" proves insufficient.
- Configurable/custom workflows and statuses — sub-project 3. `status`
  stays the existing fixed three-value field in this sub-project.
