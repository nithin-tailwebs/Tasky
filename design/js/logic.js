/* Tasky — Projects & Membership + Work Item Hierarchy prototype.
   Pure role-permission and hierarchy rules, no DOM, no network — mirrors
   the matrices in docs/superpowers/specs/2026-08-13-...-membership-design.md
   and docs/superpowers/specs/2026-08-14-...-work-item-hierarchy-design.md
   exactly, so this file IS those specs' rule tables, executable. */

const Logic = (() => {

  const ROLE_LABEL = { owner: 'Owner', admin: 'Admin', member: 'Member' };

  const canInvite = (role) => role === 'owner' || role === 'admin';

  const canRemove = (actingRole, targetRole) =>
    (actingRole === 'owner' && targetRole !== 'owner') ||
    (actingRole === 'admin' && targetRole === 'member');

  const canChangeRole = (actingRole) => actingRole === 'owner';
  const canTransferOwnership = (actingRole) => actingRole === 'owner';
  const canDeleteProject = (actingRole) => actingRole === 'owner';
  const canLeave = (actingRole) => actingRole === 'admin' || actingRole === 'member';

  /* ---- Work item hierarchy (sub-project 2a) ---------------------------- */

  const ITEM_TYPES = ['epic', 'story', 'task', 'bug', 'subtask'];
  const ITEM_TYPE_LABEL = { epic: 'Epic', story: 'Story', task: 'Task', bug: 'Bug', subtask: 'Subtask' };

  // Exactly the shapes the spec allows: epic -> {story,task,bug} -> subtask.
  const VALID_PARENT_TYPES = {
    epic: [],
    story: ['epic'],
    task: ['epic'],
    bug: ['epic'],
    subtask: ['story', 'task', 'bug'],
  };

  const requiresParent = (itemType) => itemType === 'subtask';
  const canHaveParent = (itemType) => itemType !== 'epic';

  // parentType may be null/undefined (meaning "no parent").
  function isValidParent(itemType, parentType) {
    if (!parentType) return !requiresParent(itemType);
    return VALID_PARENT_TYPES[itemType].includes(parentType);
  }

  const canManageComponents = (role) => role === 'owner' || role === 'admin';

  const STATUSES = ['todo', 'in_progress', 'done'];
  const STATUS_LABELS = { todo: 'To Do', in_progress: 'In Progress', done: 'Done' };

  return {
    ROLE_LABEL,
    canInvite, canRemove, canChangeRole,
    canTransferOwnership, canDeleteProject, canLeave,
    ITEM_TYPES, ITEM_TYPE_LABEL, VALID_PARENT_TYPES,
    requiresParent, canHaveParent, isValidParent, canManageComponents,
    STATUSES, STATUS_LABELS,
  };
})();
