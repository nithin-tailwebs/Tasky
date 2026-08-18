# Tasky — Labels (Sub-project 4 of 13)

**Status:** Design approved in chat 2026-08-18. Phase 1 prototype (`design/`) not yet
built — required before Phase 2 (Django/DRF implementation) can begin, per this
repo's hard rule.

## Context

This is sub-project 4 in Tasky's expansion from a single-board Kanban tool
toward a broader, Jira-inspired feature set. The full roadmap (13
sub-projects, redrawn 2026-08-14) is:

1. Projects & Membership — shipped
2. Work Item Hierarchy — shipped (backend + UI)
   - 2b. Custom Fields & Screens — shipped (backend + `design/` prototype)
   - 2c. Bulk Operations & Import — not yet designed
3. Workflows — design + `design/` prototype built, awaiting sign-off
4. **Labels — this document**
5. Search
6. Backlog & Sprints
7. Releases
8. Task Detail UX
9. Permissions & Admin
10. Project Types & Setup
11. Automation
12. Notifications
13. Reporting & Dashboards

The original v1 spec explicitly deferred labels: "Overlaps with priority...
revisit when priority proves too coarse." That reasoning predates
`Component` (added in sub-project 2a) — a project-scoped, admin-managed tag
applied to work items via M2M. Structurally, a naive Label would be nearly
identical to `Component`, so this brainstorm's central question was what
makes Labels a genuinely different feature rather than `Component` renamed.

## Scope decisions from brainstorming

- **Free-form, self-serve tagging is the actual differentiator.**
  `Component` stays the curated "which subsystem does this touch" list,
  managed by a project's Owner/Admin. A `Label` is the opposite: any
  project member can type a brand-new label directly onto a work item, with
  no pre-registration step and no approval gate. This is the real Jira
  distinction (Components are governed; Labels are casual, ad-hoc tags like
  "urgent", "needs-design", "customer-reported") and is what keeps the two
  features from doing the same job under different names.
- **Labels are global, not project-scoped** — matching `CustomField`/
  `Screen` from sub-project 2b, not `Component`. The same "urgent" typed on
  a Tasky Redesign item and a Website Refresh item is the identical row.
  This sets up a shared vocabulary for cross-project search/reporting later
  (sub-projects 5 and 13) and avoids the same word meaning different things
  in different projects.
- **Governance is split by risk, not uniform.** Applying a label (including
  inventing a new one) is as unrestricted as editing any other work item
  field — any project member. Renaming, recoloring, or deleting a `Label`
  is gated to any project Owner, matching 2b's tier for global-impact
  changes, since those actions affect every project using that label, not
  just the one the acting user is in.
- **Color is optional and auto-assigned, not manually chosen at creation.**
  Manually picking a color would add friction to the frictionless "just
  type it" flow that's the entire point of this sub-project. Instead, a
  label's color is deterministically hashed from its name into a small
  fixed palette — the same name always renders the same color, even across
  a delete-and-recreate. An Owner can change a label's color later via the
  manage tier, same as renaming.

## Data model

**`Label`** (global, not project-scoped)
- `name` — unique, case-insensitive (matching `CustomField`/`Screen`'s
  existing duplicate-name check style).
- `color` — assigned automatically on creation (see below); not part of
  the create payload.
- `created_by`, `created_at`.

**`WorkItem.labels`** — M2M to `Label`. No through-model fields needed
(no per-work-item label metadata, unlike `ScreenField`'s `required`).

**Color assignment:** a small fixed palette (8–10 colors, chosen to match
the existing design system's palette conventions — see
`design/css/app.css`'s existing `--type-*` color tokens for the established
style). A label's color is `palette[hash(name) % palette.length]` —
deterministic, no stored "next color" counter, and stable across a
delete-and-recreate of the same name.

**Deleting a `Label`** removes it from every work item that referenced it
(the M2M row simply goes away) without touching those work items otherwise
— no "still in use" guard, matching how `Component` deletion already
behaves in this codebase today. Labels are deliberately lightweight; adding
a usage guard here would work against the "casual tag" design intent.

## API surface

```
GET /api/labels/                    list every global Label (any authenticated user — for autocomplete)
GET/PATCH/DELETE /api/labels/{id}/  rename/recolor (Owner of any project) / delete (Owner of any project)
```

No `POST /api/labels/`. A label is never created directly — only
implicitly, through a work item write that names one that doesn't exist yet
(see below). `GET /api/labels/` has no project scoping (same
`IsAuthenticated`-only tier as `CustomField`/`Screen`'s list endpoints) since
it exists purely to power autocomplete while typing a label onto a work
item in any project.

**`WorkItemSerializer` gains, on `/api/work-items/`:**
- `labels` (write) — a list of **names** (strings), not ids. This is the
  one place in the API surface that differs from every other tagging
  mechanism here: `component_ids` and a Screen's `field` always require the
  row to already exist; `labels` resolves each name case-insensitively
  against existing `Label` rows — reusing a match, creating a new `Label`
  for anything unmatched — all within the same request, in one transaction.
  Two names in the same write that differ only by case (`["urgent",
  "Urgent"]`) collapse to a single `Label`, not two.
- `labels_detail` (read) — `[{id, name, color}, ...]`, matching the
  `components`/`components_detail` naming convention from 2a.

Applying/removing labels on a work item requires the same permission as
editing any other work item field — any project member, no separate check
(unlike `components`, which does check the components belong to the item's
project; that check doesn't apply here since labels are global by design).

## Error handling

| Case | Response |
|---|---|
| Unauthenticated request | 403, never 401 |
| Non-Owner (of any project) renames/recolors/deletes a `Label` | 403 |
| `PATCH`/`DELETE` a genuinely nonexistent label id | 404 |
| A work item's `labels` write includes a blank/whitespace-only name | 400, naming `labels` |
| A write names the same label twice with different casing | Collapsed to one label, not rejected |
| Applying/removing labels on a work item | Any project member — no separate permission check |

## Testing

- Writing a brand-new label name on a work item creates the `Label` row
  and links it, in one request.
- Writing an existing name (any casing) reuses the row rather than
  creating a duplicate.
- Two work items in two different projects both using "urgent" share the
  identical `Label` row — proves the global scope.
- Renaming/recoloring requires Owner of any project; a plain member is
  rejected.
- Deleting a `Label` unassigns it from every work item that had it,
  without touching those work items otherwise.
- Color is deterministic: the same label name always resolves to the same
  palette color, including after a delete-and-recreate.

## Out of scope (deferred to later sub-projects)

- **Label descriptions.** Not requested; a name and a color are enough for
  a casual tag.
- **Per-project restriction or allow-lists** (hiding certain labels from
  certain projects). Every label is usable everywhere, per the global-scope
  decision — no per-project visibility layer.
- **Bulk merge tooling** ("combine these two labels into one"). A plain
  rename covers the common case; a dedicated merge operation is real scope
  no one has asked for yet.
- **Manual color choice at creation time.** Colors are always
  auto-assigned; only the Owner-tier manage screen can change one
  afterward.
