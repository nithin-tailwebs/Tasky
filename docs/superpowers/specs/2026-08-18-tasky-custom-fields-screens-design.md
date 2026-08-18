# Tasky — Custom Fields & Screens (Sub-project 2b of 13)

**Status:** Design approved in chat 2026-08-18. Phase 1 prototype (`design/`) not yet
built — required before Phase 2 (Django/DRF implementation) can begin, per this
repo's hard rule.

## Context

This is the third sub-project in Tasky's expansion from a single-board Kanban
tool toward a broader, Jira-inspired feature set. The full roadmap (13
sub-projects) is:

1. Projects & Membership — shipped
2. Work Item Hierarchy — shipped (backend + UI)
3. **Custom Fields & Screens — this document (sub-project 2b)**
4. Bulk Operations & Import (2c) — depends on this document's field/screen model
5. Workflows (custom statuses/workflows)
6. Labels
7. Search
8. Backlog & Sprints
9. Releases
10. Task Detail UX
11. Permissions & Admin
12. Project Types & Setup
13. Automation
14. Notifications
15. Reporting & Dashboards

(Sub-project 2's original scope was split into 2a — Work Item Hierarchy,
shipped — and 2b — this document. 2b was itself scoped down from Jira's full
field-configuration model during brainstorming; see "Out of scope" below.)

This document covers 2b only: custom fields, screens (ordered field
groupings), and per-project-per-item-type screen assignment. It does not
cover bulk operations, CSV import, or issue templates — that's 2c, and it
explicitly depends on this document's `CustomField`/`Screen` model existing
first.

## Scope decisions from brainstorming

A few deliberate simplifications from Jira's actual model, chosen during
design:

- **One screen per item type per project**, not three (create/edit/view).
  A Screen controls the fields shown on both create and edit; viewing a work
  item always shows every field that has a saved value, regardless of the
  current screen assignment.
- **No separate "Screen Scheme" object.** Jira lets a named, reusable Screen
  Scheme be assigned to many projects at once. Tasky skips that layer: each
  project has its own direct `item_type → screen` mapping. `CustomField` and
  `Screen` objects themselves are still global and reusable across projects
  — only the scheme-as-a-named-shareable-object layer is cut.
- **Attachments are explicitly out of scope for this sub-project.** A
  file/media custom field type needs real infrastructure decisions (storage
  backend, size limits, allowed types) that Tasky doesn't have today — zero
  `MEDIA_ROOT`/`FileField` usage anywhere in the codebase currently. This
  becomes its own future sub-project once those decisions are made.

## Data model

**`CustomField`** (global, not project-scoped)
- `name`, `field_type` — one of `text_short`, `text_long`, `number`, `date`,
  `select`, `multiselect`, `checkbox`, `user_picker`. Fixed set, no custom
  types.
- `field_type` is **immutable after creation** — changing it would
  invalidate every existing saved value for that field, so it follows this
  codebase's existing immutable-after-creation convention (same as
  `WorkItem.item_type`/`key`).
- `created_by`.
- Any project Owner (Owner of *any* project, not necessarily the project
  using the field) can create, rename, or delete a `CustomField`. This is a
  deliberate self-serve choice — Tasky has no site-wide admin role beyond
  Django's own staff/superuser flag, and introducing one wasn't worth it for
  this sub-project.
- Deleting a `CustomField` is rejected (400) while it's still referenced by
  any `ScreenField` — an Owner must remove it from every Screen first. Once
  unreferenced, deleting it also deletes every `WorkItemFieldValue` for it.

**`FieldOption`** (child of `CustomField`, `select`/`multiselect` types only)
- `field` (FK), `label`, `position` (for stable ordering).
- Removing an option that's still referenced by any `WorkItemFieldValue` is
  rejected (400) until unreferenced — same philosophy as field deletion.

**`Screen`** (global, not project-scoped)
- `name`.
- Any project Owner can create, rename, or delete a `Screen` — same
  permission tier as `CustomField`.
- Deleting a `Screen` currently referenced by any `ProjectScreenAssignment`
  is rejected (400) until unassigned everywhere.

**`ScreenField`** (through-model, `Screen` ↔ `CustomField`)
- `screen` (FK), `field` (FK), `position` (ordering on the screen),
  `required` (bool). Unique together on `(screen, field)`.
- `required` is **per-screen, not per-field** — the same `CustomField` (e.g.
  "Story Points") can be required on one Screen and optional on another.

**`ProjectScreenAssignment`** (per-project)
- `project` (FK), `item_type`, `screen` (FK). Unique together on
  `(project, item_type)`.
- Editable by that project's Owner/Admin only — same management tier already
  used for `Component`.
- No row for a given `(project, item_type)` means that item type shows only
  the built-in fields (title/description/status/priority/due_date/assignee/
  components) — matching today's behavior exactly. Custom fields only appear
  once a project's Owner/Admin explicitly assigns a Screen to that item type.

**`WorkItemFieldValue`**
- `work_item` (FK), `field` (FK), `value` (text — coerced to/from
  `field.field_type` in the serializer, never trusted as already-typed at
  the database layer). For `select`/`multiselect`, `value` stores the
  `FieldOption`'s **id**, not its label — so renaming an option later
  doesn't invalidate values that already picked it.
- `multiselect` fields get multiple rows (same `work_item`/`field` pair,
  different `value`), one per selected option — no separate join table
  needed since each row already names both sides. Every other field type
  gets exactly one row per `(work_item, field)`.
- A write to `custom_fields` always **replaces** the full value set for
  each field named in the payload — delete any existing row(s) for that
  `(work_item, field)`, then insert the new one (or several, for
  `multiselect`), inside one transaction. This is upsert-by-replacement,
  not a diff, so there's no ambiguity between "edit this value" and
  "add a second value" for single-value field types.
- Unique together on `(work_item, field, value)` — belt-and-suspenders
  against a single write accidentally inserting the same `multiselect`
  option twice; the replace-on-write rule above is what actually prevents
  a single-value field from ever holding two rows.

## API surface

```
GET/POST /api/fields/                          list every global CustomField / create one (any Owner)
GET/PATCH/DELETE /api/fields/{id}/              rename; manage options (select/multiselect) via a nested options list;
                                                 field_type is immutable
GET/POST /api/screens/                          list every global Screen / create one (any Owner)
GET/PATCH/DELETE /api/screens/{id}/             rename; manage the ordered field list + each field's required flag
GET/PUT /api/projects/{id}/screen-assignments/  {epic, story, task, bug, subtask} → screen id or null
                                                 (that project's Owner/Admin)
```

`WorkItemSerializer` (existing endpoint, `/api/work-items/`) gains a
`custom_fields` object on read and write: `{field_id: value}` (a list of
values for `multiselect` fields).

**On create/edit:** Tasky resolves `(work_item.board.project, item_type)` →
`ProjectScreenAssignment`.
- No assignment for that item type → any `custom_fields` in the request is
  rejected (400), naming `custom_fields` — matches this codebase's existing
  reject-rather-than-silently-drop convention (e.g. the components-project-
  match check in sub-project 2a).
- An assignment exists → only fields listed on that Screen are accepted;
  anything else → 400. Fields marked `required` on that Screen must have a
  value → 400 if missing. Every value is type-checked against
  `field.field_type` (number parses as a number, date is ISO-8601, `select`
  value must be one of the field's current options, `user_picker` value must
  be a member of the work item's project, `multiselect` entries must each be
  a current option).
- Editing custom field values requires the same permission as editing any
  other work item field — any project member who can edit the work item,
  no separate tier.

**On view (`GET`):** every saved `WorkItemFieldValue` for the work item is
returned in `custom_fields`, regardless of whether its field is still on the
currently-assigned Screen for that item type. Changing a project's screen
assignment never retroactively deletes values — it only changes what the
create/edit form offers going forward.

## Error handling

| Case | Response |
|---|---|
| Non-Owner (of any project) creates/edits/deletes a `CustomField` or `Screen` | 403 |
| Non-Owner/Admin of a project edits that project's screen assignments | 403 |
| `custom_fields` submitted for an item type with no Screen assigned | 400, naming `custom_fields` |
| A `custom_fields` key not present on the assigned Screen | 400, naming `custom_fields` |
| A Screen-required field missing a value | 400, naming `custom_fields` |
| A value that doesn't type-check against its field's `field_type` | 400, naming `custom_fields` |
| Attempt to change `field_type` on an existing `CustomField` via PATCH | 400 |
| Delete a `CustomField` still referenced by any `Screen` | 400 |
| Remove a `FieldOption` still referenced by any `WorkItemFieldValue` | 400 |
| Delete a `Screen` still referenced by any `ProjectScreenAssignment` | 400 |
| Non-member touches any field/screen/work-item-custom-field endpoint | 403 (`IsProjectMember`, unchanged) |
| Genuinely nonexistent id | 404 (existence checked before membership, same pattern as sub-projects 1/2a) |
| Unauthenticated request | 403, never 401 |

## Testing

Extends the pytest suite from sub-project 2a (195 tests as of that
sub-project's final review):

- Every field type's value validation, valid and invalid, including
  `multiselect`'s multi-row storage.
- `field_type` immutability on PATCH.
- Screen field-list management: add/remove/reorder, per-field `required`
  toggling.
- Screen assignment: per-project, per-item-type, Owner/Admin can set it, a
  plain Member cannot.
- The no-screen-assigned default: custom_fields rejected, built-ins still
  work exactly as before this sub-project.
- The screen-assigned path: unlisted field rejected, required field missing
  rejected, valid submission accepted and correctly typed on read-back.
- View always shows saved values even after a screen reassignment orphans
  the field from the current screen.
- Deletion guards: field-in-use-on-screen, option-in-use-in-a-value,
  screen-in-use-in-an-assignment — each rejected until unreferenced, then
  succeeds once clear.
- Cross-project field/screen reuse: a `CustomField`/`Screen` created while a
  member of Project A is usable (assignable) from Project B by a different
  Owner, since both are global.

## Out of scope (deferred to later sub-projects)

- File/media attachment field type — needs storage-backend decisions Tasky
  doesn't have yet; own future sub-project.
- Separate create/edit/view screen contexts — one combined create+edit
  screen only, per the scope decision above.
- Named, multi-project-shareable "Screen Scheme" objects — direct
  per-project `item_type → screen` mapping only.
- A site-wide admin role for gatekeeping global field/screen creation — any
  project Owner can create them, deliberately, for this sub-project.
- Custom field-based search/filtering — sub-project 2c and/or the Search
  sub-project may pick this up once fields exist to search on.
- Field configuration schemes as a Jira-style separate layer from Screens —
  Tasky's Screen already carries the per-field required flag, so there's no
  separate "Field Configuration" object.
