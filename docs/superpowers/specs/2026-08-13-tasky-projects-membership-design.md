# Tasky — Projects & Membership (Sub-project 1 of 7)

**Status:** Design approved in chat 2026-08-13. Phase 1 prototype (`design/`) signed off in chat 2026-08-14. Phase 2 (Django/DRF implementation) is unlocked.

## Context

Tasky is expanding from a single-board Kanban tool into a multi-project,
Jira-like tool. The full expansion was decomposed into seven sequenced
sub-projects (see decomposition agreed in chat, 2026-08-13):

1. **Projects & Membership** — this document
2. Work Item Hierarchy (epics/stories/subtasks, unique IDs)
3. Labels
4. Search
5. Backlog & Sprints
6. Releases
7. Task Detail UX (modal + new-tab)

Sub-projects 2–7 all live inside a Project and depend on this one. This
document covers only Projects & Membership.

Today, Boards are standalone — not scoped to any project. This design
introduces Project as the top-level container; Boards move underneath
it.

## Data model

**Project**
- `name`
- `key` — unique across the system, 2–10 uppercase letters, set by the
  creator at creation time (validated unique, not auto-derived). This
  key becomes the prefix for work item IDs in sub-project 2 (e.g.
  `TASKY-123`).
- `description`
- `created_at`

**ProjectMembership**
- `project` (FK), `user` (FK) — unique together
- `role`: `owner` | `admin` | `member`
- `joined_at`

Exactly one `owner` per project at all times.

**Invitation**
- `project` (FK)
- `invited_user` (FK to an existing account — there is no public
  signup yet; when email login ships later, this extends to inviting
  by email address for users without an account yet)
- `invited_by` (FK)
- `status`: `pending` | `accepted` | `declined`
- `created_at`, `responded_at`

**Board**
- Gains a `project` FK. A project may have multiple boards. Card,
  column/status, and position semantics are unchanged from the current
  implementation — only the ownership scope changes.

## Roles & permissions

| Action | Owner | Admin | Member |
|---|---|---|---|
| View/participate in project content (boards, cards, comments) | ✓ | ✓ | ✓ |
| Invite new members | ✓ | ✓ | ✗ |
| Remove a Member | ✓ | ✓ | ✗ |
| Remove an Admin | ✓ | ✗ | ✗ |
| Promote Member → Admin / demote Admin → Member | ✓ | ✗ | ✗ |
| Transfer ownership | ✓ | ✗ | ✗ |
| Delete project | ✓ | ✗ | ✗ |
| Leave project | only after transferring ownership | ✓ | ✓ |

Every project-scoped endpoint (projects, boards, cards) returns `403`
for a non-member, never `401` — consistent with the existing API
convention documented in `docs/api.md`.

## Flows

- **Create project** — user supplies `name` + `key`. Creator becomes
  Owner. `400` if the key is already taken.
- **Invite** — Owner/Admin picks an existing user (search by
  name/username) and sends an invite. `400` if the user is already a
  member or already has a pending invite to this project.
- **Accept/decline** — the invited user sees pending invites on their
  "My Projects" page. Accepting creates a `ProjectMembership` with
  role `member`. Declining marks the invite `declined`. Only the
  invited user may respond to their own invite (`403` otherwise).
- **Remove a member** — Owner/Admin removes a Member. Admins cannot
  remove other Admins or the Owner (`403` — Owner-only for that).
- **Leave voluntarily** — any Member or Admin can leave at any time.
  The Owner is blocked (`400`, explicit message) until they transfer
  ownership.
- **Transfer ownership** — Owner designates an existing Admin as the
  new Owner; the previous Owner becomes an Admin, in one transaction.
- **Promote/demote Admin** — Owner-only, toggles Member ↔ Admin.
- **Delete project** — Owner-only; cascades to boards, cards,
  memberships, and invitations.
- **Navigation** — "My Projects" page lists the user's projects plus a
  pending-invitations section. Inside a project, a header dropdown
  switches to another project.

## API surface

```
GET    /api/projects/                     list projects I'm a member of
POST   /api/projects/                     create project (name, key)
GET    /api/projects/{id}/                project detail (includes my role)
DELETE /api/projects/{id}/                delete (owner only)
GET    /api/projects/{id}/members/        list members + roles
DELETE /api/projects/{id}/members/{uid}/  remove member / leave (self)
POST   /api/projects/{id}/members/{uid}/role/       promote/demote (owner only)
POST   /api/projects/{id}/transfer-ownership/       {user_id} (owner only)
POST   /api/projects/{id}/invite/         {user_id} (owner/admin)
GET    /api/invitations/                  my pending invitations
POST   /api/invitations/{id}/accept/
POST   /api/invitations/{id}/decline/
```

Existing board/card endpoints (`docs/api.md`) are unchanged in shape,
but now resolve access through project membership instead of being
globally visible.

## Error handling

| Case | Response |
|---|---|
| Duplicate project key | `400` |
| Invite a user already a member | `400` |
| Invite a user with an existing pending invite | `400` |
| Non-owner/admin attempts to invite | `403` |
| Admin attempts to remove an Admin or the Owner | `403` |
| Non-owner attempts delete/promote/demote/transfer | `403` |
| Owner attempts to leave without transferring first | `400` |
| Responding to someone else's invitation | `403` |
| Non-member accesses a project's boards/cards | `403` |
| Unauthenticated request | `403` (never `401`, per existing convention) |

## Testing

Extends the existing pytest suite (currently 92 tests):

- Role-permission matrix: every action × every role, confirming
  allowed/forbidden outcomes.
- Invitation lifecycle: pending → accepted, pending → declined,
  duplicate-invite prevention, responding to another user's invite.
- Ownership transfer: transfer to a non-admin (should fail — must be
  an existing Admin), owner leave blocked pre-transfer, owner leave
  allowed post-transfer.
- Board/card access now correctly scoped to project membership
  (non-members get `403`).

## Migration note

Existing standalone Boards need a `project` assigned before this ships
— out of scope for this design doc, to be handled as a data migration
in the implementation plan (e.g. a one-off "Legacy" project owned by
an admin, or per-board manual assignment — implementation plan will
decide).

## Out of scope (deferred to later sub-projects or explicitly not done here)

- Epics, stories, subtasks, unique work-item IDs — sub-project 2.
- Labels, search, sprints/backlog, releases — sub-projects 3–6.
- Email-based invitations to non-existing accounts — deferred until
  email login exists; the `Invitation` model is shaped so this extends
  cleanly later.
- Per-board permissions distinct from project-level roles — not
  requested; all boards in a project share the same membership.
