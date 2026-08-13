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
    await renderMembers(main, projectId, project.my_role);
    await renderPendingInvites(main, projectId, project.my_role);
  } catch (err) {
    handle(err);
    location.hash = '#/projects';
  }
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
   same way and Escape/backdrop-click always work the same way. -------- */

let closeActiveModal = null;

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
    closeActiveModal = null;
  }
  function onKey(e) { if (e.key === 'Escape') close(); }

  scrim.addEventListener('click', (e) => { if (e.target === scrim) close(); });
  document.addEventListener('keydown', onKey);
  modal.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', close));

  closeActiveModal = close;
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

boot();
