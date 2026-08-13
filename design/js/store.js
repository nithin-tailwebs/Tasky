/* Mock data source for the Projects & Membership prototype.
   Enforces the same rules the real API will, so this prototype is an
   honest model of the feature rather than a picture of it — every
   permission check here has a matching row in the spec's error table. */

const Store = (() => {

  const LATENCY = 140;   // enough to see optimistic updates land
  let nextId = 100;
  const id = () => ++nextId;

  // The same people the real `seed_demo` command creates.
  const users = [
    { id: 1, username: 'asha',  display_name: 'Asha Rao' },
    { id: 2, username: 'kabir', display_name: 'Kabir Menon' },
    { id: 3, username: 'lena',  display_name: 'Lena Fischer' },
  ];
  const userById = (uid) => users.find(u => u.id === Number(uid));

  let me = null;

  // Seeded so signing in as Asha alone walks through Owner, Admin and
  // Member views without switching accounts, plus one pending invitation.
  let projects = [
    { id: 1, key: 'TASKY', name: 'Tasky Redesign',   description: 'The multi-project expansion itself' },
    { id: 2, key: 'WEB',   name: 'Website Refresh',  description: '' },
    { id: 3, key: 'CLNT',  name: 'Client Portal',    description: '' },
    { id: 4, key: 'MKT',   name: 'Marketing Launch', description: '' },
  ];

  let memberships = [
    { id: id(), project: 1, user: 1, role: 'owner' },   // Asha owns Tasky Redesign
    { id: id(), project: 1, user: 2, role: 'admin' },
    { id: id(), project: 2, user: 2, role: 'owner' },
    { id: id(), project: 2, user: 1, role: 'admin' },   // Asha admins Website Refresh
    { id: id(), project: 3, user: 3, role: 'owner' },
    { id: id(), project: 3, user: 2, role: 'admin' },
    { id: id(), project: 3, user: 1, role: 'member' },  // Asha is a plain member of Client Portal
    { id: id(), project: 4, user: 3, role: 'owner' },
  ];

  let invitations = [
    // Pending invite waiting for Asha to accept/decline on first login.
    { id: id(), project: 4, invited_user: 1, invited_by: 3, status: 'pending', created_at: new Date().toISOString() },
  ];

  /* ---- plumbing ---- */

  const wait = (v) => new Promise(res => setTimeout(() => res(clone(v)), LATENCY));
  const clone = (v) => (v === null || v === undefined) ? v : JSON.parse(JSON.stringify(v));

  function fail(status, message) {
    return Promise.reject(Object.assign(new Error(message), { status }));
  }

  const membershipFor = (projectId, userId) =>
    memberships.find(m => m.project === Number(projectId) && m.user === Number(userId));

  const myRole = (projectId) => {
    const m = membershipFor(projectId, me.id);
    return m ? m.role : null;
  };

  function requireMember(projectId) {
    if (!myRole(projectId)) throw Object.assign(new Error("You don't have access to this project."), { status: 403 });
  }

  /* ---- auth ---- */

  function login(username, password) {
    const user = users.find(u => u.username === username.trim().toLowerCase());
    if (!user || !password) {
      // Identical message for an unknown username and a wrong password —
      // matches the real API's anti-enumeration behaviour.
      return fail(400, 'Incorrect username or password.');
    }
    me = user;
    return wait(user);
  }

  function logout() { me = null; return wait(null); }
  function getMe() { return me ? wait(me) : fail(403, 'Authentication credentials were not provided.'); }

  /* ---- projects ---- */

  function decorateProject(project) {
    return Object.assign({}, project, {
      my_role: myRole(project.id),
      member_count: memberships.filter(m => m.project === project.id).length,
    });
  }

  const listMyProjects = () => wait(
    projects.filter(p => membershipFor(p.id, me.id)).map(decorateProject)
  );

  function getProject(projectId) {
    const project = projects.find(p => p.id === Number(projectId));
    if (!project) return fail(404, 'Not found.');
    try { requireMember(projectId); } catch (err) { return Promise.reject(err); }
    return wait(decorateProject(project));
  }

  function createProject({ name, key }) {
    if (!name || !name.trim()) return fail(400, 'This field may not be blank.');
    const cleanKey = (key || '').trim().toUpperCase();
    if (!/^[A-Z]{2,10}$/.test(cleanKey)) return fail(400, 'Key must be 2–10 letters, e.g. TASKY.');
    if (projects.some(p => p.key === cleanKey)) return fail(400, `"${cleanKey}" is already taken.`);
    const project = { id: id(), key: cleanKey, name: name.trim(), description: '' };
    projects.push(project);
    memberships.push({ id: id(), project: project.id, user: me.id, role: 'owner' });
    return wait(decorateProject(project));
  }

  function deleteProject(projectId) {
    if (myRole(projectId) !== 'owner') return fail(403, 'Only the owner can delete a project.');
    projects = projects.filter(p => p.id !== Number(projectId));
    memberships = memberships.filter(m => m.project !== Number(projectId));
    invitations = invitations.filter(i => i.project !== Number(projectId));
    return wait(null);
  }

  /* ---- membership ---- */

  const decorateMembership = (m) => Object.assign({}, m, { user_detail: userById(m.user) });

  function listMembers(projectId) {
    try { requireMember(projectId); } catch (err) { return Promise.reject(err); }
    const rank = { owner: 0, admin: 1, member: 2 };
    return wait(
      memberships.filter(m => m.project === Number(projectId))
        .sort((a, b) => rank[a.role] - rank[b.role] || a.id - b.id)
        .map(decorateMembership)
    );
  }

  function removeMember(projectId, userId) {
    const actingRole = myRole(projectId);
    const target = membershipFor(projectId, userId);
    if (!target) return fail(404, 'Not found.');
    if (Number(userId) === me.id) return fail(400, 'Use "Leave project" to remove yourself.');
    const allowed = (actingRole === 'owner' && target.role !== 'owner') ||
                     (actingRole === 'admin' && target.role === 'member');
    if (!allowed) return fail(403, "You don't have permission to remove this member.");
    memberships = memberships.filter(m => m.id !== target.id);
    return wait(null);
  }

  function leaveProject(projectId) {
    const role = myRole(projectId);
    if (!role) return fail(404, 'Not found.');
    if (role === 'owner') return fail(400, 'Transfer ownership before leaving a project you own.');
    memberships = memberships.filter(m => !(m.project === Number(projectId) && m.user === me.id));
    return wait(null);
  }

  function changeRole(projectId, userId, newRole) {
    if (myRole(projectId) !== 'owner') return fail(403, 'Only the owner can change member roles.');
    if (!['admin', 'member'].includes(newRole)) return fail(400, 'Invalid role.');
    const target = membershipFor(projectId, userId);
    if (!target) return fail(404, 'Not found.');
    if (target.role === 'owner') return fail(403, "The owner's role can't be changed here — transfer ownership instead.");
    target.role = newRole;
    return wait(decorateMembership(target));
  }

  function transferOwnership(projectId, newOwnerUserId) {
    if (myRole(projectId) !== 'owner') return fail(403, 'Only the owner can transfer ownership.');
    const target = membershipFor(projectId, newOwnerUserId);
    if (!target || target.role !== 'admin') return fail(400, 'Ownership can only be transferred to an existing Admin.');
    membershipFor(projectId, me.id).role = 'admin';
    target.role = 'owner';
    return wait(null);
  }

  /* ---- invitations ---- */

  const decorateInvitation = (inv) => Object.assign({}, inv, {
    project_detail: projects.find(p => p.id === inv.project),
    invited_by_detail: userById(inv.invited_by),
    invited_user_detail: userById(inv.invited_user),
  });

  const listMyInvitations = () => wait(
    invitations.filter(i => i.invited_user === me.id && i.status === 'pending').map(decorateInvitation)
  );

  function listProjectInvitations(projectId) {
    try { requireMember(projectId); } catch (err) { return Promise.reject(err); }
    return wait(
      invitations.filter(i => i.project === Number(projectId) && i.status === 'pending').map(decorateInvitation)
    );
  }

  function listInvitableUsers(projectId) {
    try { requireMember(projectId); } catch (err) { return Promise.reject(err); }
    const memberIds = new Set(memberships.filter(m => m.project === Number(projectId)).map(m => m.user));
    const invitedIds = new Set(
      invitations.filter(i => i.project === Number(projectId) && i.status === 'pending').map(i => i.invited_user)
    );
    return wait(users.filter(u => !memberIds.has(u.id) && !invitedIds.has(u.id)));
  }

  function inviteMember(projectId, userId) {
    if (!canActingInvite(projectId)) return fail(403, "You don't have permission to invite members.");
    if (membershipFor(projectId, userId)) return fail(400, 'Already a member of this project.');
    if (invitations.some(i => i.project === Number(projectId) && i.invited_user === Number(userId) && i.status === 'pending')) {
      return fail(400, 'Already invited — waiting on a response.');
    }
    const inv = {
      id: id(), project: Number(projectId), invited_user: Number(userId),
      invited_by: me.id, status: 'pending', created_at: new Date().toISOString(),
    };
    invitations.push(inv);
    return wait(decorateInvitation(inv));
  }
  function canActingInvite(projectId) {
    const role = myRole(projectId);
    return role === 'owner' || role === 'admin';
  }

  function acceptInvitation(invitationId) {
    const inv = invitations.find(i => i.id === Number(invitationId));
    if (!inv) return fail(404, 'Not found.');
    if (inv.invited_user !== me.id) return fail(403, 'You can only respond to your own invitations.');
    inv.status = 'accepted';
    memberships.push({ id: id(), project: inv.project, user: me.id, role: 'member' });
    return wait(null);
  }

  function declineInvitation(invitationId) {
    const inv = invitations.find(i => i.id === Number(invitationId));
    if (!inv) return fail(404, 'Not found.');
    if (inv.invited_user !== me.id) return fail(403, 'You can only respond to your own invitations.');
    inv.status = 'declined';
    return wait(null);
  }

  return {
    login, logout, getMe,
    listMyProjects, getProject, createProject, deleteProject,
    listMembers, removeMember, leaveProject, changeRole, transferOwnership,
    listMyInvitations, listProjectInvitations, listInvitableUsers,
    inviteMember, acceptInvitation, declineInvitation,
  };
})();
