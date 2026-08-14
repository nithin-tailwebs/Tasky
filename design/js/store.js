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

  // Work Item Hierarchy (sub-project 2a) seed data ------------------------

  let boards = [
    { id: id(), project: 1, name: 'Sprint Board' },
    { id: id(), project: 2, name: 'Main Board' },
  ];
  const [board1] = boards;

  let components = [
    { id: id(), project: 1, name: 'Frontend' },
    { id: id(), project: 1, name: 'Backend' },
  ];

  let workItems = [];
  function seedItem(o) {
    const item = Object.assign({
      description: '', priority: 2, due_date: null, assignee: null,
      parent: null, position: 0, component_ids: [], created_by: 1,
    }, o);
    workItems.push(item);
    return item;
  }

  // One Epic, two of its children (a Story and a Task), a Subtask under
  // the Story, and a standalone Bug — enough to exercise every level of
  // the hierarchy and every valid parent shape from the seed alone.
  const epic = seedItem({
    id: id(), key: 'TASKY-1', board: board1.id, item_type: 'epic',
    title: 'Redesign onboarding', status: 'in_progress', priority: 3, assignee: 1,
  });
  const story1 = seedItem({
    id: id(), key: 'TASKY-2', board: board1.id, item_type: 'story', parent: epic.id,
    title: 'Design the welcome screen', status: 'todo', assignee: 3,
    component_ids: [components[0].id],
  });
  const task1 = seedItem({
    id: id(), key: 'TASKY-3', board: board1.id, item_type: 'task', parent: epic.id,
    title: 'Wire up the onboarding API', status: 'todo', assignee: 2,
    component_ids: [components[1].id],
  });
  seedItem({
    id: id(), key: 'TASKY-4', board: board1.id, item_type: 'subtask', parent: story1.id,
    title: 'Write the welcome copy', status: 'todo',
  });
  const bug1 = seedItem({
    id: id(), key: 'TASKY-5', board: board1.id, item_type: 'bug',
    title: 'Signup button misaligned on Safari', status: 'in_progress', priority: 3, assignee: 1,
  });

  let links = [
    {
      id: id(),
      item_a: Math.min(task1.id, bug1.id), item_b: Math.max(task1.id, bug1.id),
      created_by: 1, created_at: new Date().toISOString(),
    },
  ];

  const projectItemCounters = { 1: 6 }; // next number after the 5 seeded TASKY items

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

  /* ---- boards ---- */

  function listBoards(projectId) {
    try { requireMember(projectId); } catch (err) { return Promise.reject(err); }
    return wait(boards.filter(b => b.project === Number(projectId)));
  }

  function createBoard(projectId, name) {
    try { requireMember(projectId); } catch (err) { return Promise.reject(err); }
    if (!name || !name.trim()) return fail(400, 'This field may not be blank.');
    const board = { id: id(), project: Number(projectId), name: name.trim() };
    boards.push(board);
    return wait(board);
  }

  function getBoard(boardId) {
    const board = boards.find(b => b.id === Number(boardId));
    if (!board) return fail(404, 'Not found.');
    try { requireMember(board.project); } catch (err) { return Promise.reject(err); }
    return wait(board);
  }

  function boardProjectId(boardId) {
    const board = boards.find(b => b.id === boardId);
    return board ? board.project : null;
  }

  /* ---- work items ---- */

  function decorateWorkItem(item) {
    const parent = item.parent ? workItems.find(w => w.id === item.parent) : null;
    const children = workItems
      .filter(w => w.parent === item.id)
      .map(c => ({ id: c.id, key: c.key, title: c.title, item_type: c.item_type, status: c.status }));
    return Object.assign({}, item, {
      assignee_detail: item.assignee ? userById(item.assignee) : null,
      created_by_detail: userById(item.created_by),
      priority_label: { 1: 'Low', 2: 'Medium', 3: 'High' }[item.priority],
      parent_detail: parent
        ? { id: parent.id, key: parent.key, title: parent.title, item_type: parent.item_type }
        : null,
      children,
      components: components.filter(c => item.component_ids.includes(c.id)),
    });
  }

  function nextKey(projectId) {
    const project = projects.find(p => p.id === projectId);
    const n = projectItemCounters[projectId] || 1;
    projectItemCounters[projectId] = n + 1;
    return `${project.key}-${n}`;
  }

  // Shared by create and update: given a candidate item_type + parent work
  // item (or null), returns an error message string, or null if valid.
  function hierarchyError(itemType, parent) {
    if (!Logic.isValidParent(itemType, parent ? parent.item_type : null)) {
      const label = Logic.ITEM_TYPE_LABEL[itemType];
      const article = /^[AEIOU]/.test(label) ? 'An' : 'A';
      return Logic.requiresParent(itemType)
        ? `${article} ${label} must have a parent Story, Task, or Bug.`
        : `${article} ${label} can't have that parent.`;
    }
    return null;
  }

  function listBoardWorkItems(boardId) {
    const board = boards.find(b => b.id === Number(boardId));
    if (!board) return fail(404, 'Not found.');
    try { requireMember(board.project); } catch (err) { return Promise.reject(err); }
    return wait(workItems.filter(w => w.board === board.id).map(decorateWorkItem));
  }

  function getWorkItem(itemId) {
    const item = workItems.find(w => w.id === Number(itemId));
    if (!item) return fail(404, 'Not found.');
    try { requireMember(boardProjectId(item.board)); } catch (err) { return Promise.reject(err); }
    return wait(decorateWorkItem(item));
  }

  function createWorkItem(fields) {
    const board = boards.find(b => b.id === Number(fields.board));
    if (!board) return fail(404, 'Not found.');
    try { requireMember(board.project); } catch (err) { return Promise.reject(err); }

    if (!Logic.ITEM_TYPES.includes(fields.item_type)) return fail(400, 'Invalid item type.');
    if (!fields.title || !fields.title.trim()) return fail(400, 'This field may not be blank.');

    let parent = null;
    if (fields.parent) {
      parent = workItems.find(w => w.id === Number(fields.parent));
      if (!parent) return fail(400, 'Parent not found.');
      if (parent.board !== board.id) return fail(400, 'Parent must be on the same board.');
    }
    const hErr = hierarchyError(fields.item_type, parent);
    if (hErr) return fail(400, hErr);

    const item = seedItem({
      id: id(), key: nextKey(board.project), board: board.id, item_type: fields.item_type,
      title: fields.title.trim(), description: fields.description || '',
      status: fields.status || 'todo', priority: fields.priority || 2,
      due_date: fields.due_date || null, assignee: fields.assignee || null,
      parent: parent ? parent.id : null, component_ids: fields.component_ids || [],
      created_by: me.id,
    });
    const siblings = workItems.filter(w => w.board === board.id && w.status === item.status && w.id !== item.id);
    item.position = siblings.length;
    return wait(decorateWorkItem(item));
  }

  function updateWorkItem(itemId, fields) {
    const item = workItems.find(w => w.id === Number(itemId));
    if (!item) return fail(404, 'Not found.');
    try { requireMember(boardProjectId(item.board)); } catch (err) { return Promise.reject(err); }

    if ('item_type' in fields && fields.item_type !== item.item_type) {
      return fail(400, 'Type cannot be changed after creation.');
    }
    if ('key' in fields && fields.key !== item.key) {
      return fail(400, 'Key cannot be changed.');
    }
    if ('title' in fields && !String(fields.title).trim()) {
      return fail(400, 'This field may not be blank.');
    }

    let newParent;
    if ('parent' in fields) {
      const newParentId = fields.parent ? Number(fields.parent) : null;
      if (newParentId === item.id) return fail(400, "An item can't be its own parent.");
      newParent = newParentId ? workItems.find(w => w.id === newParentId) : null;
      if (newParentId && !newParent) return fail(400, 'Parent not found.');
      if (newParent && newParent.board !== item.board) {
        return fail(400, 'Parent must be on the same board.');
      }
      const hErr = hierarchyError(item.item_type, newParent);
      if (hErr) return fail(400, hErr);
    }

    if ('title' in fields) item.title = fields.title.trim();
    ['description', 'status', 'priority', 'due_date', 'assignee', 'component_ids'].forEach(f => {
      if (f in fields) item[f] = fields[f];
    });
    if (newParent !== undefined) item.parent = newParent ? newParent.id : null;

    return wait(decorateWorkItem(item));
  }

  function deleteWorkItem(itemId) {
    const item = workItems.find(w => w.id === Number(itemId));
    if (!item) return fail(404, 'Not found.');
    try { requireMember(boardProjectId(item.board)); } catch (err) { return Promise.reject(err); }
    // Orphan children — they survive, they just lose their parent link.
    workItems.forEach(w => { if (w.parent === item.id) w.parent = null; });
    workItems = workItems.filter(w => w.id !== item.id);
    links = links.filter(l => l.item_a !== item.id && l.item_b !== item.id);
    return wait(null);
  }

  /* ---- components ---- */

  function listComponents(projectId) {
    try { requireMember(projectId); } catch (err) { return Promise.reject(err); }
    return wait(components.filter(c => c.project === Number(projectId)));
  }

  function createComponent(projectId, name) {
    if (!Logic.canManageComponents(myRole(projectId))) {
      return fail(403, "You don't have permission to manage components.");
    }
    if (!name || !name.trim()) return fail(400, 'This field may not be blank.');
    if (components.some(c => c.project === Number(projectId) && c.name.toLowerCase() === name.trim().toLowerCase())) {
      return fail(400, `"${name.trim()}" already exists.`);
    }
    const component = { id: id(), project: Number(projectId), name: name.trim() };
    components.push(component);
    return wait(component);
  }

  function renameComponent(componentId, name) {
    const component = components.find(c => c.id === Number(componentId));
    if (!component) return fail(404, 'Not found.');
    if (!Logic.canManageComponents(myRole(component.project))) {
      return fail(403, "You don't have permission to manage components.");
    }
    if (!name || !name.trim()) return fail(400, 'This field may not be blank.');
    component.name = name.trim();
    return wait(component);
  }

  function deleteComponent(componentId) {
    const component = components.find(c => c.id === Number(componentId));
    if (!component) return fail(404, 'Not found.');
    if (!Logic.canManageComponents(myRole(component.project))) {
      return fail(403, "You don't have permission to manage components.");
    }
    components = components.filter(c => c.id !== component.id);
    workItems.forEach(w => { w.component_ids = w.component_ids.filter(cid => cid !== component.id); });
    return wait(null);
  }

  /* ---- work item links ("relates to") ---- */

  function decorateLink(link) {
    const a = workItems.find(w => w.id === link.item_a);
    const b = workItems.find(w => w.id === link.item_b);
    return Object.assign({}, link, {
      item_a_detail: a && { id: a.id, key: a.key, title: a.title, item_type: a.item_type },
      item_b_detail: b && { id: b.id, key: b.key, title: b.title, item_type: b.item_type },
    });
  }

  function listLinks(itemId) {
    const item = workItems.find(w => w.id === Number(itemId));
    if (!item) return fail(404, 'Not found.');
    try { requireMember(boardProjectId(item.board)); } catch (err) { return Promise.reject(err); }
    return wait(links.filter(l => l.item_a === item.id || l.item_b === item.id).map(decorateLink));
  }

  function createLink(itemAId, itemBId) {
    itemAId = Number(itemAId); itemBId = Number(itemBId);
    if (itemAId === itemBId) return fail(400, "An item can't be linked to itself.");
    const a = workItems.find(w => w.id === itemAId);
    const b = workItems.find(w => w.id === itemBId);
    if (!a || !b) return fail(404, 'Not found.');
    try { requireMember(boardProjectId(a.board)); } catch (err) { return Promise.reject(err); }

    if (a.parent === b.id || b.parent === a.id) {
      return fail(400, 'These items are already parent and child.');
    }
    const [lo, hi] = itemAId < itemBId ? [itemAId, itemBId] : [itemBId, itemAId];
    if (links.some(l => l.item_a === lo && l.item_b === hi)) {
      return fail(400, 'These items are already linked.');
    }
    const link = { id: id(), item_a: lo, item_b: hi, created_by: me.id, created_at: new Date().toISOString() };
    links.push(link);
    return wait(decorateLink(link));
  }

  function deleteLink(linkId) {
    const link = links.find(l => l.id === Number(linkId));
    if (!link) return fail(404, 'Not found.');
    links = links.filter(l => l.id !== link.id);
    return wait(null);
  }

  const listUsers = () => wait(users);

  return {
    login, logout, getMe,
    listMyProjects, getProject, createProject, deleteProject,
    listMembers, removeMember, leaveProject, changeRole, transferOwnership,
    listMyInvitations, listProjectInvitations, listInvitableUsers,
    inviteMember, acceptInvitation, declineInvitation,
    listBoards, createBoard, getBoard,
    listBoardWorkItems, getWorkItem, createWorkItem, updateWorkItem, deleteWorkItem,
    listComponents, createComponent, renameComponent, deleteComponent,
    listLinks, createLink, deleteLink,
    listUsers,
  };
})();
