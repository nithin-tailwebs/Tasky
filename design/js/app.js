/* Tasky — Projects & Membership design prototype (sub-project 1 of 7).
   Mock-only: no backend, no build step. Role rules live in logic.js;
   store.js enforces them the same way the real API will. Views, routing
   and the interaction polish (skeletons, staggered rows, animated modal
   and toast lifecycle) live here. */

const root = document.getElementById('root');
const tpl = (id) => document.getElementById(id).content.cloneNode(true);
const esc = (s) => String(s == null ? '' : s);
const outlet = () => root.querySelector('[data-main]');

let me = null;

/* Toast ------------------------------------------------------------------ */

let toastTimer = null;
function toast(message, bad) {
  document.querySelectorAll('.toast').forEach(t => t.remove());
  const t = document.createElement('div');
  t.className = 'toast' + (bad ? ' bad' : '');
  t.textContent = message;
  t.setAttribute('role', 'status');
  document.body.appendChild(t);
  requestAnimationFrame(() => t.classList.add('is-open'));

  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    t.classList.remove('is-open');
    setTimeout(() => t.remove(), 180);
  }, 2600);
}

function errorText(err) {
  return (err && err.message) || 'Something went wrong.';
}

function handle(err) { toast(errorText(err), true); }

/* Skeletons -------------------------------------------------------------- */

function skeletonList(count) {
  return `<ul class="skeleton-list">${
    Array.from({ length: count }, () => '<li class="skeleton-row"></li>').join('')
  }</ul>`;
}

/* Staggers a NodeList's entrance so rows settle in rather than popping in
   as one block — capped so a long list doesn't feel sluggish to arrive. */
function stagger(nodes) {
  nodes.forEach((el, i) => { el.style.animationDelay = `${Math.min(i, 8) * 28}ms`; });
}

/* Boot --------------------------------------------------------------------*/

async function boot() {
  try {
    me = await Store.getMe();
    renderShell();
  } catch {
    renderLogin();
  }
}

/* Login ------------------------------------------------------------------ */

function renderLogin() {
  root.replaceChildren(tpl('tpl-login'));
  const form = root.querySelector('form');
  const errorEl = form.querySelector('[data-error]');

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button');
    btn.disabled = true;
    errorEl.hidden = true;
    try {
      me = await Store.login(form.username.value, form.password.value);
      renderShell();
    } catch (err) {
      errorEl.textContent = errorText(err);
      errorEl.hidden = false;
      btn.disabled = false;
    }
  });
}

/* Shell + routing ---------------------------------------------------------*/

function renderShell() {
  root.replaceChildren(tpl('tpl-shell'));
  root.querySelector('[data-who]').textContent = me.display_name || me.username;
  root.querySelector('[data-signout]').addEventListener('click', async () => {
    await Store.logout();
    me = null;
    location.hash = '';
    renderLogin();
  });
  route();
}

function route() {
  if (!me) return;
  const hash = location.hash.replace(/^#/, '') || '/projects';
  const boardMatch = hash.match(/^\/projects\/(\d+)\/boards\/(\d+)$/);
  if (boardMatch) return viewBoard(Number(boardMatch[1]), Number(boardMatch[2]));
  const m = hash.match(/^\/projects\/(\d+)$/);
  if (m) return viewProject(Number(m[1]));
  viewProjects();
}
window.addEventListener('hashchange', route);

/* Projects list ------------------------------------------------------------*/

async function viewProjects() {
  const main = outlet();
  main.replaceChildren(tpl('tpl-projects'));

  const invSection = main.querySelector('[data-invitations]');
  const invList = main.querySelector('[data-invite-list]');
  const list = main.querySelector('[data-list]');
  list.innerHTML = skeletonList(3);

  main.querySelector('[data-create-project]').addEventListener('submit', async (e) => {
    e.preventDefault();
    const errorEl = main.querySelector('[data-create-error]');
    errorEl.hidden = true;
    const name = e.target.querySelector('[name=name]').value;
    const key = e.target.querySelector('[name=key]').value;
    try {
      const project = await Store.createProject({ name, key });
      toast('Project created');
      location.hash = `#/projects/${project.id}`;
    } catch (err) {
      errorEl.textContent = errorText(err);
      errorEl.hidden = false;
    }
  });

  try {
    const [invitations, projects] = await Promise.all([
      Store.listMyInvitations(),
      Store.listMyProjects(),
    ]);

    if (invitations.length) {
      invSection.hidden = false;
      const rows = invitations.map(invitationRow);
      invList.replaceChildren(...rows);
      stagger(rows);
    }

    if (!projects.length) {
      list.innerHTML = '<li class="empty">No projects yet. Create one above, or wait for an invitation.</li>';
      return;
    }
    const rows = projects.map(projectRow);
    list.replaceChildren(...rows);
    stagger(rows);
  } catch (err) {
    list.innerHTML = '';
    handle(err);
  }
}

function invitationRow(invite) {
  const li = document.createElement('li');
  li.className = 'invite-row';
  li.innerHTML =
    `<span class="who">${esc(invite.project_detail.name)} <span class="key-pill">${esc(invite.project_detail.key)}</span></span>` +
    `<span class="sub">Invited by ${esc(invite.invited_by_detail.display_name)}</span>` +
    `<span class="actions">` +
      `<button class="btn btn-primary" data-accept>Accept</button>` +
      `<button class="btn btn-quiet" data-decline>Decline</button>` +
    `</span>`;
  li.querySelector('[data-accept]').addEventListener('click', async () => {
    try {
      await Store.acceptInvitation(invite.id);
      toast('Invitation accepted');
      viewProjects();
    } catch (err) { handle(err); }
  });
  li.querySelector('[data-decline]').addEventListener('click', async () => {
    try {
      await Store.declineInvitation(invite.id);
      toast('Invitation declined');
      viewProjects();
    } catch (err) { handle(err); }
  });
  return li;
}

function projectRow(project) {
  const li = document.createElement('li');
  const a = document.createElement('a');
  a.className = 'project-row';
  a.href = `#/projects/${project.id}`;
  a.innerHTML =
    `<span class="name">${esc(project.name)}</span>` +
    `<span class="key-pill">${esc(project.key)}</span>` +
    `<span class="desc">${esc(project.description)}</span>` +
    `<span class="role-badge role-${project.my_role}">${Logic.ROLE_LABEL[project.my_role]}</span>` +
    `<span class="tally mono">${project.member_count} member${project.member_count === 1 ? '' : 's'}</span>`;
  li.appendChild(a);
  return li;
}

/* Project detail ------------------------------------------------------------*/

async function viewProject(projectId) {
  const main = outlet();
  main.replaceChildren(tpl('tpl-project'));
  main.querySelector('[data-members]').innerHTML = skeletonList(3);

  try {
    const [project, myProjects] = await Promise.all([
      Store.getProject(projectId),
      Store.listMyProjects(),
    ]);

    main.querySelector('[data-project-name]').textContent = project.name;
    main.querySelector('[data-project-key]').textContent = project.key;
    const desc = main.querySelector('[data-project-desc]');
    if (project.description) desc.textContent = project.description; else desc.remove();

    const roleBadge = main.querySelector('[data-my-role]');
    roleBadge.textContent = Logic.ROLE_LABEL[project.my_role];
    roleBadge.classList.add(`role-${project.my_role}`);

    const switcher = main.querySelector('[data-switcher]');
    switcher.replaceChildren(...myProjects.map(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = `${p.name} (${p.key})`;
      if (p.id === projectId) opt.selected = true;
      return opt;
    }));
    switcher.addEventListener('change', () => { location.hash = `#/projects/${switcher.value}`; });

    renderProjectActions(main, project);
    await renderBoards(main, projectId);
    await renderComponents(main, projectId, project.my_role);
    await renderMembers(main, projectId, project.my_role);
    await renderPendingInvites(main, projectId, project.my_role);
  } catch (err) {
    handle(err);
    location.hash = '#/projects';
  }
}

/* Boards ---------------------------------------------------------------- */

async function renderBoards(main, projectId) {
  const list = main.querySelector('[data-boards]');
  list.innerHTML = skeletonList(2);

  main.querySelector('[data-create-board]').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = e.target.querySelector('[name=name]');
    if (!input.value.trim()) return;
    try {
      const board = await Store.createBoard(projectId, input.value);
      location.hash = `#/projects/${projectId}/boards/${board.id}`;
    } catch (err) { handle(err); }
  });

  try {
    const boards = await Store.listBoards(projectId);
    if (!boards.length) {
      list.innerHTML = '<li class="empty">No boards yet. Name one above to get started.</li>';
      return;
    }
    const rows = boards.map(b => {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.className = 'board-row';
      a.href = `#/projects/${projectId}/boards/${b.id}`;
      a.innerHTML = `<span class="name">${esc(b.name)}</span>`;
      li.appendChild(a);
      return li;
    });
    list.replaceChildren(...rows);
    stagger(rows);
  } catch (err) {
    list.innerHTML = '';
    handle(err);
  }
}

/* Components -------------------------------------------------------------- */

async function renderComponents(main, projectId, myRole) {
  const list = main.querySelector('[data-components]');
  const form = main.querySelector('[data-create-component]');
  const canManage = Logic.canManageComponents(myRole);
  form.hidden = !canManage;
  list.innerHTML = skeletonList(1);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = e.target.querySelector('[name=name]');
    if (!input.value.trim()) return;
    try {
      await Store.createComponent(projectId, input.value);
      input.value = '';
      await renderComponents(main, projectId, myRole);
    } catch (err) { handle(err); }
  });

  try {
    const items = await Store.listComponents(projectId);
    if (!items.length) {
      list.innerHTML = '<li class="empty">No components yet.</li>';
      return;
    }
    const rows = items.map(c => componentRow(c, projectId, myRole));
    list.replaceChildren(...rows);
    stagger(rows);
  } catch (err) {
    list.innerHTML = '';
    handle(err);
  }
}

function componentRow(component, projectId, myRole) {
  const li = document.createElement('li');
  li.className = 'component-row';
  const canManage = Logic.canManageComponents(myRole);
  li.innerHTML =
    `<span class="who" ${canManage ? 'contenteditable="true" data-rename' : ''}>${esc(component.name)}</span>` +
    (canManage ? `<span class="actions"><button class="btn btn-danger" data-remove>Delete</button></span>` : '');

  const nameEl = li.querySelector('[data-rename]');
  if (nameEl) {
    nameEl.addEventListener('blur', async () => {
      const value = nameEl.textContent.trim();
      if (!value || value === component.name) { nameEl.textContent = component.name; return; }
      try {
        await Store.renameComponent(component.id, value);
        component.name = value;
        toast('Component renamed');
      } catch (err) {
        nameEl.textContent = component.name;
        handle(err);
      }
    });
    nameEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); nameEl.blur(); }
    });
  }
  const removeBtn = li.querySelector('[data-remove]');
  if (removeBtn) {
    removeBtn.addEventListener('click', async () => {
      try {
        await Store.deleteComponent(component.id);
        toast('Component deleted');
        await renderComponents(outlet(), projectId, myRole);
      } catch (err) { handle(err); }
    });
  }
  return li;
}

function renderProjectActions(main, project) {
  const actions = main.querySelector('[data-actions]');
  actions.innerHTML = '';
  const role = project.my_role;

  if (Logic.canInvite(role)) {
    const btn = document.createElement('button');
    btn.className = 'btn';
    btn.textContent = 'Invite';
    btn.addEventListener('click', () => openInviteModal(project));
    actions.appendChild(btn);
  }
  if (Logic.canTransferOwnership(role)) {
    const btn = document.createElement('button');
    btn.className = 'btn';
    btn.textContent = 'Transfer ownership';
    btn.addEventListener('click', () => openTransferModal(project));
    actions.appendChild(btn);
  }
  if (Logic.canLeave(role)) {
    const btn = document.createElement('button');
    btn.className = 'btn btn-quiet';
    btn.textContent = 'Leave project';
    btn.addEventListener('click', async () => {
      try {
        await Store.leaveProject(project.id);
        toast('You left the project');
        location.hash = '#/projects';
      } catch (err) { handle(err); }
    });
    actions.appendChild(btn);
  }
  if (Logic.canDeleteProject(role)) {
    const btn = document.createElement('button');
    btn.className = 'btn btn-danger';
    btn.textContent = 'Delete project';
    btn.addEventListener('click', async () => {
      try {
        await Store.deleteProject(project.id);
        toast('Project deleted');
        location.hash = '#/projects';
      } catch (err) { handle(err); }
    });
    actions.appendChild(btn);
  }
}

async function renderMembers(main, projectId, myRole) {
  const list = main.querySelector('[data-members]');
  try {
    const members = await Store.listMembers(projectId);
    const rows = members.map(m => memberRow(m, projectId, myRole));
    list.replaceChildren(...rows);
    stagger(rows);
  } catch (err) {
    list.innerHTML = '';
    handle(err);
  }
}

function memberRow(member, projectId, myRole) {
  const li = document.createElement('li');
  li.className = 'member-row';
  const isMe = me && member.user_detail.id === me.id;

  let controls = '';
  if (Logic.canChangeRole(myRole) && member.role !== 'owner') {
    controls +=
      `<select class="role-select" data-role-select>` +
        `<option value="member" ${member.role === 'member' ? 'selected' : ''}>Member</option>` +
        `<option value="admin" ${member.role === 'admin' ? 'selected' : ''}>Admin</option>` +
      `</select>`;
  }
  if (Logic.canRemove(myRole, member.role) && !isMe) {
    controls += `<button class="btn btn-danger" data-remove>Remove</button>`;
  }

  li.innerHTML =
    `<span class="who">${esc(member.user_detail.display_name)}${isMe ? ' (you)' : ''} <span class="sub">@${esc(member.user_detail.username)}</span></span>` +
    `<span class="role-badge role-${member.role}">${Logic.ROLE_LABEL[member.role]}</span>` +
    `<span class="actions">${controls}</span>`;

  const roleSelect = li.querySelector('[data-role-select]');
  if (roleSelect) {
    roleSelect.addEventListener('change', async () => {
      try {
        await Store.changeRole(projectId, member.user_detail.id, roleSelect.value);
        toast('Role updated');
        await renderMembers(outlet(), projectId, myRole);
      } catch (err) { handle(err); }
    });
  }
  const removeBtn = li.querySelector('[data-remove]');
  if (removeBtn) {
    removeBtn.addEventListener('click', async () => {
      try {
        await Store.removeMember(projectId, member.user_detail.id);
        toast('Member removed');
        await renderMembers(outlet(), projectId, myRole);
      } catch (err) { handle(err); }
    });
  }

  return li;
}

async function renderPendingInvites(main, projectId, myRole) {
  if (!Logic.canInvite(myRole)) return; // only Owner/Admin see outgoing invites
  const section = main.querySelector('[data-pending-section]');
  const list = main.querySelector('[data-pending-invites]');
  try {
    const invites = await Store.listProjectInvitations(projectId);
    if (!invites.length) return;
    section.hidden = false;
    const rows = invites.map(inv => {
      const li = document.createElement('li');
      li.className = 'invite-row';
      li.innerHTML =
        `<span class="who">${esc(inv.invited_user_detail.display_name)}</span>` +
        `<span class="sub">Invited by ${esc(inv.invited_by_detail.display_name)} · awaiting response</span>`;
      return li;
    });
    list.replaceChildren(...rows);
    stagger(rows);
  } catch (err) { handle(err); }
}

/* Modals — a shared open/close lifecycle so every dialog animates the
   same way and Escape/backdrop-click always work the same way. Modals can
   nest (the work item modal opens a link picker on top of itself), so
   Escape only ever closes the topmost one. -------------------------- */

const modalStack = [];

function openModal(bodyHtml) {
  const scrim = document.createElement('div');
  scrim.className = 'scrim';

  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.innerHTML = bodyHtml;

  scrim.appendChild(modal);
  document.body.appendChild(scrim);
  requestAnimationFrame(() => scrim.classList.add('is-open'));

  function close() {
    scrim.classList.remove('is-open');
    document.removeEventListener('keydown', onKey);
    setTimeout(() => scrim.remove(), 180);
    const idx = modalStack.indexOf(close);
    if (idx !== -1) modalStack.splice(idx, 1);
  }
  function onKey(e) {
    if (e.key === 'Escape' && modalStack[modalStack.length - 1] === close) close();
  }

  scrim.addEventListener('click', (e) => { if (e.target === scrim) close(); });
  document.addEventListener('keydown', onKey);
  modal.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', close));

  modalStack.push(close);
  return { modal, close };
}

async function openInviteModal(project) {
  let invitable;
  try { invitable = await Store.listInvitableUsers(project.id); }
  catch (err) { return handle(err); }

  const body = !invitable.length
    ? `<div class="modal-head"><p class="eyebrow">Invite to ${esc(project.key)}</p><button class="btn btn-quiet" data-close>Close</button></div>
       <p class="empty">Everyone with an account is already a member or already invited.</p>`
    : `<div class="modal-head"><p class="eyebrow">Invite to ${esc(project.key)}</p><button class="btn btn-quiet" data-close>Close</button></div>
       <label class="field"><span>Person</span><select name="user">${
         invitable.map(u => `<option value="${u.id}">${esc(u.display_name)} (@${esc(u.username)})</option>`).join('')
       }</select></label>
       <p class="form-error" data-error hidden></p>
       <div class="modal-actions"><button class="btn btn-primary" data-send>Send invite</button><button class="btn" data-close>Cancel</button></div>`;

  const { modal, close } = openModal(body);
  const sendBtn = modal.querySelector('[data-send]');
  if (!sendBtn) return;

  sendBtn.addEventListener('click', async () => {
    const errorEl = modal.querySelector('[data-error]');
    const userId = modal.querySelector('[name=user]').value;
    try {
      await Store.inviteMember(project.id, Number(userId));
      close();
      toast('Invitation sent');
      await renderPendingInvites(outlet(), project.id, project.my_role);
    } catch (err) {
      errorEl.textContent = errorText(err);
      errorEl.hidden = false;
    }
  });
}

async function openTransferModal(project) {
  let admins;
  try { admins = (await Store.listMembers(project.id)).filter(m => m.role === 'admin'); }
  catch (err) { return handle(err); }

  const body = !admins.length
    ? `<div class="modal-head"><p class="eyebrow">Transfer ownership</p><button class="btn btn-quiet" data-close>Close</button></div>
       <p class="empty">There's no Admin to transfer to yet. Promote a member to Admin first.</p>`
    : `<div class="modal-head"><p class="eyebrow">Transfer ownership</p><button class="btn btn-quiet" data-close>Close</button></div>
       <p class="page-sub" style="margin-bottom:12px">You'll become an Admin. This can't be undone from here.</p>
       <label class="field"><span>New owner</span><select name="user">${
         admins.map(m => `<option value="${m.user_detail.id}">${esc(m.user_detail.display_name)} (@${esc(m.user_detail.username)})</option>`).join('')
       }</select></label>
       <p class="form-error" data-error hidden></p>
       <div class="modal-actions"><button class="btn btn-primary" data-send>Transfer</button><button class="btn" data-close>Cancel</button></div>`;

  const { modal, close } = openModal(body);
  const sendBtn = modal.querySelector('[data-send]');
  if (!sendBtn) return;

  sendBtn.addEventListener('click', async () => {
    const errorEl = modal.querySelector('[data-error]');
    const userId = modal.querySelector('[name=user]').value;
    try {
      await Store.transferOwnership(project.id, Number(userId));
      close();
      toast('Ownership transferred');
      viewProject(project.id);
    } catch (err) {
      errorEl.textContent = errorText(err);
      errorEl.hidden = false;
    }
  });
}

/* Board — work items (sub-project 2a) ------------------------------------ */

let boardState = { projectId: null, boardId: null, buckets: null };

function groupByStatus(items) {
  const buckets = {};
  Logic.STATUSES.forEach(s => { buckets[s] = []; });
  items.forEach(item => { (buckets[item.status] || (buckets[item.status] = [])).push(item); });
  return buckets;
}

async function viewBoard(projectId, boardId) {
  const main = outlet();
  main.replaceChildren(tpl('tpl-board'));
  boardState.projectId = projectId;
  boardState.boardId = boardId;

  main.querySelector('[data-back-link]').href = `#/projects/${projectId}`;
  main.querySelector('[data-type-legend]').innerHTML = Logic.ITEM_TYPES.map(t =>
    `<span class="legend-item"><i class="type-dot type-${t}"></i>${Logic.ITEM_TYPE_LABEL[t]}</span>`
  ).join('');

  const columnsEl = main.querySelector('[data-columns]');
  columnsEl.innerHTML = '<p class="loading">Loading board…</p>';

  try {
    const [board, items] = await Promise.all([
      Store.getBoard(boardId),
      Store.listBoardWorkItems(boardId),
    ]);
    main.querySelector('[data-board-name]').textContent = board.name;

    boardState.buckets = groupByStatus(items);
    paintColumns();
  } catch (err) {
    columnsEl.innerHTML = '';
    handle(err);
    location.hash = `#/projects/${projectId}`;
  }
}

async function reloadBoard() {
  const items = await Store.listBoardWorkItems(boardState.boardId);
  boardState.buckets = groupByStatus(items);
  paintColumns();
}

function paintColumns() {
  const columnsEl = root.querySelector('[data-columns]');
  if (!columnsEl) return;
  columnsEl.replaceChildren(...Logic.STATUSES.map(s => columnEl(s, boardState.buckets[s] || [])));
}

function columnEl(status, items) {
  const col = document.createElement('section');
  col.className = 'column';
  if (status === 'in_progress') col.classList.add('column-active');
  if (status === 'done') col.classList.add('column-done');

  const head = document.createElement('div');
  head.className = 'column-head';
  head.innerHTML =
    `<span class="dot"></span>` +
    `<span class="label">${Logic.STATUS_LABELS[status]}</span>` +
    `<span class="count">${items.length}</span>`;
  col.appendChild(head);

  const stack = document.createElement('div');
  stack.className = 'stack';
  items.forEach(item => stack.appendChild(workItemCard(item)));
  col.appendChild(stack);

  col.appendChild(addWorkItemControl(status));
  return col;
}

function workItemCard(item) {
  const el = document.createElement('article');
  el.className = `wi-card p${item.priority || 2}`;
  el.tabIndex = 0;

  const parentChip = item.parent_detail
    ? `<span class="parent-chip">${esc(item.parent_detail.key)}</span>` : '';
  const who = item.assignee_detail
    ? `<span class="who-chip">${esc(item.assignee_detail.display_name)}</span>` : '';

  el.innerHTML =
    `<div class="wi-top">` +
      `<span class="key-pill">${esc(item.key)}</span>` +
      `<span class="type-badge type-${item.item_type}">${Logic.ITEM_TYPE_LABEL[item.item_type]}</span>` +
    `</div>` +
    `<p class="card-title">${esc(item.title)}</p>` +
    `<div class="card-meta">${parentChip}${who}</div>`;

  el.addEventListener('click', () => openWorkItemModal(item.id));
  el.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openWorkItemModal(item.id); }
  });
  return el;
}

function addWorkItemControl(status) {
  const wrap = document.createElement('div');
  const btn = document.createElement('button');
  btn.className = 'add-card';
  btn.type = 'button';
  btn.textContent = '+ Add work item';
  wrap.appendChild(btn);

  btn.addEventListener('click', () => {
    const form = document.createElement('form');
    form.className = 'add-wi-form';
    form.innerHTML =
      `<select name="item_type" aria-label="Type">${
        Logic.ITEM_TYPES.map(t => `<option value="${t}">${Logic.ITEM_TYPE_LABEL[t]}</option>`).join('')
      }</select>` +
      `<input name="title" placeholder="What needs doing?" aria-label="Title">` +
      `<select name="parent" aria-label="Parent"><option value="">No parent</option></select>` +
      `<p class="form-error" data-error hidden></p>`;
    wrap.replaceChildren(form);

    const typeSelect = form.querySelector('[name=item_type]');
    const parentSelect = form.querySelector('[name=parent]');
    const titleInput = form.querySelector('[name=title]');
    titleInput.focus();

    function refreshParentOptions() {
      const type = typeSelect.value;
      parentSelect.innerHTML = '<option value="">No parent</option>';
      if (!Logic.canHaveParent(type)) { parentSelect.disabled = true; return; }
      parentSelect.disabled = false;
      const items = boardState.buckets ? Object.values(boardState.buckets).flat() : [];
      const candidates = items.filter(i => Logic.VALID_PARENT_TYPES[type].includes(i.item_type));
      candidates.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = `${c.key} — ${c.title}`;
        parentSelect.appendChild(opt);
      });
      if (Logic.requiresParent(type) && candidates.length) parentSelect.value = candidates[0].id;
    }
    typeSelect.addEventListener('change', refreshParentOptions);
    refreshParentOptions();

    const cancel = () => { if (!titleInput.value.trim()) wrap.replaceChildren(btn); };
    titleInput.addEventListener('blur', () => setTimeout(cancel, 150));

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!titleInput.value.trim()) return;
      const errorEl = form.querySelector('[data-error]');
      errorEl.hidden = true;
      try {
        await Store.createWorkItem({
          board: boardState.boardId, item_type: typeSelect.value, title: titleInput.value,
          parent: parentSelect.value || null, status,
        });
        await reloadBoard();
      } catch (err) {
        errorEl.textContent = errorText(err);
        errorEl.hidden = false;
      }
    });
  });

  return wrap;
}

/* Work item detail modal -------------------------------------------------- */

async function openWorkItemModal(itemId) {
  let item, users, projectComponents, boardItems;
  try {
    [item, users, projectComponents, boardItems] = await Promise.all([
      Store.getWorkItem(itemId),
      Store.listUsers(),
      Store.listComponents(boardState.projectId),
      Store.listBoardWorkItems(boardState.boardId),
    ]);
  } catch (err) { return handle(err); }

  const assigneeOptions = users.map(u =>
    `<option value="${u.id}" ${item.assignee === u.id ? 'selected' : ''}>${esc(u.display_name)}</option>`
  ).join('');

  const componentChips = projectComponents.map(c => {
    const checked = item.component_ids.includes(c.id);
    return `<label class="chip-check ${checked ? 'is-checked' : ''}">` +
      `<input type="checkbox" value="${c.id}" ${checked ? 'checked' : ''}>${esc(c.name)}</label>`;
  }).join('');

  const childrenHtml = item.children.length
    ? `<ul class="children-list">${item.children.map(c =>
        `<li><a href="#" data-open-item="${c.id}"><span class="key-pill">${esc(c.key)}</span> ${esc(c.title)}</a>` +
        `<span class="status-tag">${Logic.STATUS_LABELS[c.status]}</span></li>`
      ).join('')}</ul>`
    : `<p class="empty-inline">No children yet.</p>`;

  const showParentField = Logic.canHaveParent(item.item_type);
  const parentOptions = showParentField
    ? boardItems
        .filter(i => i.id !== item.id && Logic.VALID_PARENT_TYPES[item.item_type].includes(i.item_type))
        .map(i => `<option value="${i.id}" ${item.parent === i.id ? 'selected' : ''}>${esc(i.key)} — ${esc(i.title)}</option>`)
        .join('')
    : '';

  const body = `
    <div class="modal-head">
      <p class="eyebrow">${esc(item.key)} · <span class="type-badge type-${item.item_type}">${Logic.ITEM_TYPE_LABEL[item.item_type]}</span></p>
      <button class="btn btn-quiet" data-close>Close</button>
    </div>
    <input class="modal-title" name="title" value="${esc(item.title)}" aria-label="Title">
    <label class="field">
      <span>Description</span>
      <textarea name="description" placeholder="What does done look like?">${esc(item.description)}</textarea>
    </label>
    <div class="grid-3">
      <label class="field">
        <span>Status</span>
        <select name="status">${Logic.STATUSES.map(s =>
          `<option value="${s}" ${item.status === s ? 'selected' : ''}>${Logic.STATUS_LABELS[s]}</option>`).join('')}</select>
      </label>
      <label class="field">
        <span>Priority</span>
        <select name="priority">
          <option value="1" ${item.priority === 1 ? 'selected' : ''}>Low</option>
          <option value="2" ${item.priority === 2 ? 'selected' : ''}>Medium</option>
          <option value="3" ${item.priority === 3 ? 'selected' : ''}>High</option>
        </select>
      </label>
      <label class="field">
        <span>Assignee</span>
        <select name="assignee"><option value="">Unassigned</option>${assigneeOptions}</select>
      </label>
    </div>
    <div class="grid-2">
      <label class="field">
        <span>Due</span>
        <input type="date" name="due_date" value="${item.due_date || ''}">
      </label>
      ${showParentField ? `
      <label class="field">
        <span>Parent ${Logic.requiresParent(item.item_type) ? '(required)' : ''}</span>
        <select name="parent"><option value="">No parent</option>${parentOptions}</select>
      </label>` : '<div></div>'}
    </div>
    <p class="form-error" data-error hidden></p>
    <div class="modal-actions">
      <button class="btn btn-primary" data-save>Save changes</button>
      <button class="btn" data-close>Cancel</button>
      <button class="btn btn-danger" data-delete>Delete</button>
    </div>

    <div class="components-block">
      <h2>Components</h2>
      <div class="chip-check-list">${componentChips || '<p class="empty-inline">No components on this project yet.</p>'}</div>
    </div>

    <div class="children-block">
      <h2>Children</h2>
      ${childrenHtml}
    </div>

    <div class="links-block">
      <h2>Related items</h2>
      <ul class="link-list" data-links><li class="loading">Loading…</li></ul>
      <button class="btn" type="button" data-add-link>+ Link an item</button>
    </div>`;

  const { modal, close } = openModal(body);
  const errorEl = modal.querySelector('[data-error]');

  modal.querySelectorAll('.chip-check').forEach(chip => {
    const input = chip.querySelector('input');
    input.addEventListener('change', () => chip.classList.toggle('is-checked', input.checked));
  });

  modal.querySelectorAll('[data-open-item]').forEach(a => {
    a.addEventListener('click', (e) => {
      e.preventDefault();
      const childId = Number(a.dataset.openItem);
      close();
      openWorkItemModal(childId);
    });
  });

  modal.querySelector('[data-save]').addEventListener('click', async () => {
    errorEl.hidden = true;
    const componentIds = Array.from(modal.querySelectorAll('.chip-check input:checked')).map(i => Number(i.value));
    const parentSelect = modal.querySelector('[name=parent]');
    const fields = {
      title: modal.querySelector('[name=title]').value,
      description: modal.querySelector('[name=description]').value,
      status: modal.querySelector('[name=status]').value,
      priority: Number(modal.querySelector('[name=priority]').value),
      due_date: modal.querySelector('[name=due_date]').value || null,
      assignee: modal.querySelector('[name=assignee]').value || null,
      component_ids: componentIds,
    };
    if (parentSelect) fields.parent = parentSelect.value || null;
    try {
      await Store.updateWorkItem(item.id, fields);
      close();
      await reloadBoard();
      toast('Saved');
    } catch (err) {
      errorEl.textContent = errorText(err);
      errorEl.hidden = false;
    }
  });

  modal.querySelector('[data-delete]').addEventListener('click', async () => {
    try {
      await Store.deleteWorkItem(item.id);
      close();
      await reloadBoard();
      toast('Deleted — any children were kept, just unlinked from it');
    } catch (err) { handle(err); }
  });

  loadLinks(item, modal);
  modal.querySelector('[data-add-link]').addEventListener('click', () => openLinkModal(item, modal));
}

async function loadLinks(item, modal) {
  const list = modal.querySelector('[data-links]');
  try {
    const links = await Store.listLinks(item.id);
    if (!links.length) {
      list.innerHTML = '<li class="empty-inline">No related items yet.</li>';
      return;
    }
    const rows = links.map(link => {
      const other = link.item_a === item.id ? link.item_b_detail : link.item_a_detail;
      const li = document.createElement('li');
      li.className = 'link-row';
      li.innerHTML =
        `<span class="key-pill">${esc(other.key)}</span>` +
        `<span class="link-title">${esc(other.title)}</span>` +
        `<button class="btn btn-danger" data-unlink>Remove</button>`;
      li.querySelector('[data-unlink]').addEventListener('click', async () => {
        try {
          await Store.deleteLink(link.id);
          loadLinks(item, modal);
        } catch (err) { handle(err); }
      });
      return li;
    });
    list.replaceChildren(...rows);
  } catch (err) {
    list.innerHTML = '';
    handle(err);
  }
}

async function openLinkModal(item, parentModal) {
  let candidates;
  try {
    const boardItems = await Store.listBoardWorkItems(item.board);
    candidates = boardItems.filter(i => i.id !== item.id);
  } catch (err) { return handle(err); }

  const body = !candidates.length
    ? `<div class="modal-head"><p class="eyebrow">Link ${esc(item.key)}</p><button class="btn btn-quiet" data-close>Close</button></div>
       <p class="empty">No other items on this board to link to yet.</p>`
    : `<div class="modal-head"><p class="eyebrow">Link ${esc(item.key)}</p><button class="btn btn-quiet" data-close>Close</button></div>
       <label class="field"><span>Item</span><select name="target">${
         candidates.map(c => `<option value="${c.id}">${esc(c.key)} — ${esc(c.title)}</option>`).join('')
       }</select></label>
       <p class="form-error" data-error hidden></p>
       <div class="modal-actions"><button class="btn btn-primary" data-send>Link</button><button class="btn" data-close>Cancel</button></div>`;

  const { modal, close } = openModal(body);
  const sendBtn = modal.querySelector('[data-send]');
  if (!sendBtn) return;

  sendBtn.addEventListener('click', async () => {
    const errorEl = modal.querySelector('[data-error]');
    const targetId = modal.querySelector('[name=target]').value;
    try {
      await Store.createLink(item.id, Number(targetId));
      close();
      toast('Linked');
      loadLinks(item, parentModal);
    } catch (err) {
      errorEl.textContent = errorText(err);
      errorEl.hidden = false;
    }
  });
}

boot();
