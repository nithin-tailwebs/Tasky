# Tasky — Workflows (Sub-project 3 of 13)

**Status:** Design approved in chat 2026-08-18. Phase 1 prototype (`design/`) not yet
built — required before Phase 2 (Django/DRF implementation) can begin, per this
repo's hard rule.

## Context

This is sub-project 3 in Tasky's expansion from a single-board Kanban tool
toward a broader, Jira-inspired feature set. The full roadmap (13
sub-projects, redrawn 2026-08-14) is:

1. Projects & Membership — shipped
2. Work Item Hierarchy — shipped (backend + UI)
   - 2b. Custom Fields & Screens — shipped (backend; `design/` prototype committed same day)
   - 2c. Bulk Operations & Import — not yet designed
3. **Workflows — this document**
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

(Sub-project 2's scope was split into 2a — Work Item Hierarchy — and two
further pieces, 2b and 2c, per the design docs for those; 2c hasn't been
picked up yet and has no dependency on this document, so it isn't blocking.)

Today, `WorkItem.status` is a fixed 3-value enum (`todo`, `in_progress`,
`done`) baked directly into the model (`boards/models.py`), identical across
every board in every project. The original v1 spec explicitly ruled out
custom columns as "the fiddliest logic in a kanban build" — this sub-project
revisits that call now that the product has grown well past v1's single-board
scope.

## Scope decisions from brainstorming

- **Custom statuses only, no transition rules.** A project can define its own
  named statuses beyond To Do/In Progress/Done. Any status can move to any
  other status — there is no "you can't skip from To Do straight to Done"
  validation. This is a deliberate simplification: transition rules are
  real Jira-workflow territory and meaningfully more UI/validation surface
  than a small team's actual need. Revisit if a project asks for it twice.
- **Per-project, not per-item-type.** One status list per project, shared by
  every board and every item type (Epic/Story/Task/Bug/Subtask) in it —
  matching how `Board` already relates to `Project`. 2b's per-project-per-
  item-type granularity (Screens) was considered and rejected here as
  unnecessary added config surface for something not yet requested.
- **Every status carries a category.** `todo` / `in_progress` / `done` is a
  fixed three-value vocabulary, but unlike today, **many statuses can share a
  category** — a project might have "Blocked" and "In Review" both tagged
  `in_progress` alongside the default "In Progress" itself (which can be
  renamed or deleted, same as any other status). This category is what
  existing "done-ness" logic (`MyTasksView` excluding finished work, future
  overdue-flagging) keys off, instead of a hardcoded status string.

## Data model

**`WorkItemStatus`**
- `project` (FK) — real per-project rows, not a global/shared enum.
- `name` — e.g. "To Do", "Blocked", "Awaiting QA".
- `category` — one of `todo`, `in_progress`, `done`. Changeable after
  creation (a project can decide "In Review" should count as done).
- `position` — integer, for column order. Same stable-ordering pattern as
  `ScreenField`/`FieldOption` from sub-project 2b: hand-ordered, renumbered
  to a clean `0..n-1` on reorder/delete.
- Unique together on `(project, name)`, case-insensitive at the serializer
  level (matching `CustomField`/`Screen`'s existing duplicate-name checks).

**`WorkItem.status`** changes from a `CharField` with fixed `choices` to a
required `ForeignKey` to `WorkItemStatus`, `on_delete=PROTECT` — a real
database-level backstop behind the API's own "can't delete a status still in
use" guard, not just an application-level check.

**Every project gets 3 default statuses**, seeded identically for both paths:
- On creation: To Do (`todo`, position 0), In Progress (`in_progress`,
  position 1), Done (`done`, position 2) — created alongside the `Project`
  row itself, same transaction.
- On this sub-project's rollout: a data migration creates the same 3 rows for
  every existing `Project`, then repoints every existing `WorkItem.status`
  string value to the matching new row in its own project. Nothing about an
  existing work item's visible status changes.

**Invariant, enforced at the API layer:** at least one status must exist in
each of the three categories at all times, for every project. A `DELETE` or a
`PATCH` changing `category` that would leave a category empty is rejected —
without this, "what counts as done" becomes undefined for that project.

**Default status for a new work item:** the lowest-`position` status whose
category is `todo`, unless the create request names one explicitly — the
natural "new cards start in the leftmost column" behavior.

## API surface

```
GET/POST /api/projects/{id}/statuses/           list this project's statuses (any member) / create one (Owner/Admin)
PATCH/DELETE /api/projects/{id}/statuses/{id}/   rename, recategorize, reorder / delete (Owner/Admin)
```

Mirrors `Component`'s existing endpoint shape and permission tier exactly
(`GET/POST /api/projects/{id}/components/`, `PATCH/DELETE
/api/projects/{id}/components/{id}/` from sub-project 2a) — same nesting
under project, same Owner/Admin-write, any-member-read split.

- `POST` body: `{name, category}`. New status appends to the end of the
  project's overall ordering (not per-category — `position` is one flat
  sequence across all statuses in the project, same as how a board's columns
  read left to right regardless of category).
- `PATCH` body: any of `{name?, category?, position?}`.
- `DELETE`: 400 if any `WorkItem` still references it; 400 if it's the last
  status in its category.

**`WorkItem` and the move endpoint:**
- `WorkItemSerializer`'s `status` field changes from a `ChoiceField` to a
  `PrimaryKeyRelatedField` scoped to the item's own project's statuses —
  validated the same way `parent`/`components` already are (object-level
  `validate()`, project-match check).
- `POST /api/work-items/{id}/move/` keeps its existing `{status, position}`
  shape; `status` becomes a `WorkItemStatus` id instead of a string enum
  value, and `MoveWorkItemSerializer` validates it belongs to the item's own
  project instead of using a fixed `ChoiceField`.
- `MyTasksView`'s `.exclude(status=WorkItem.Status.DONE)` becomes
  `.exclude(status__category=WorkItemStatus.Category.DONE)`.

## Board rendering (design/ prototype and eventual UI)

The board goes from "3 hardcoded columns" to "N columns, in `position`
order, colored/grouped by `category`" — still exactly 3 visual categories,
so a done column still *reads* as done even when a project has 5 statuses
spread across those 3 categories. `design/js/logic.js`'s `STATUSES`/
`STATUS_LABELS` constants — currently a fixed array — become data fetched
per-project, the same shift 2b already made for custom fields (fixed
`Logic.FIELD_TYPES` stayed fixed; the per-project *configuration* built on
top of it became dynamic).

## Error handling

| Case | Response |
|---|---|
| Non-member touches any project's `/statuses/` endpoint | 403 (`IsProjectMember`) |
| Non-Owner/Admin creates/renames/reorders/deletes a status | 403 |
| `DELETE` a status still referenced by any `WorkItem` | 400, naming the status and how many items use it |
| `DELETE`/`PATCH category` that would leave a category with zero statuses | 400 |
| `POST`/`PATCH` with an invalid `category` value | 400 |
| Move (`POST /api/work-items/{id}/move/`) to a status id from a different project | 400 |
| Genuinely nonexistent status id | 404 |
| Unauthenticated request | 403, never 401 |

## Testing

- Every project seeds 3 default statuses on creation; existing projects get
  them via data migration with existing work items correctly repointed
  (verify no data loss — every pre-migration `(work_item, status_string)`
  pair maps to the identical status after migration).
- Create/rename/reorder/delete a status; delete guard when in-use; delete
  guard for last-in-category (both via `DELETE` and via `PATCH category`).
- Changing a status's `category` re-buckets it for `MyTasksView`/board-
  column-grouping purposes.
- `move/` and work item create/edit validate the target status belongs to
  the item's own project — cross-project status id is rejected.
- A new work item with no explicit status lands in the lowest-position
  `todo`-category status.
- Cross-project isolation: Project A's statuses aren't usable or visible
  from Project B's endpoints.

## Out of scope (deferred to later sub-projects)

- **Transition rules** (which status → status moves are allowed) — this
  sub-project is statuses only. A considered deferral: real Jira-workflow
  transition logic is meaningfully more UI and validation surface than
  requested, and no user has asked for it yet.
- **Per-item-type workflows** (e.g. Bugs having a different status list than
  Stories, the way 2b's Screens work) — per-project only, for now.
- **Status colors/icons** beyond category-based board coloring — not
  requested; easy to add later as a plain field on `WorkItemStatus` without
  any data model restructuring.
