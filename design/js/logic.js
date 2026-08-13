/* Tasky — Projects & Membership prototype.
   Pure role-permission rules, no DOM, no network — mirrors the matrix in
   docs/superpowers/specs/2026-08-13-tasky-projects-membership-design.md
   exactly, so this file IS the spec's permission table, executable. */

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

  return {
    ROLE_LABEL,
    canInvite, canRemove, canChangeRole,
    canTransferOwnership, canDeleteProject, canLeave,
  };
})();
