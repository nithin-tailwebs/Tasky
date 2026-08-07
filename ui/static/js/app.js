/* Tasky — design prototype.
   Views, routing and wiring. All business rules live in logic.js; all data
   access goes through one interface, so swapping the mock store for the real
   API is a one-line change. */

/* Data source. The live API by default; append ?data=store to any URL to run
   the seeded mock instead, which is how the design is reviewed without a
   database. `boot` falls back to the mock automatically if the API cannot be
   reached at all, so opening this file off a bare static server still works. */
const FORCED = new URLSearchParams(location.search).get('data');
let data = FORCED === 'store' ? Store : Api;
const usingMock = () => data === Store;

const root = document.getElementById('root');
const tpl = (id) => document.getElementById(id).content.cloneNode(true);
const esc = (s) => String(s == null ? '' : s);

let me = null;
let usersCache = null;

/* Toast ---------------------------------------------------------------- */

let toastTimer = null;
function toast(message, bad) {
  document.querySelectorAll('.toast').forEach(t => t.remove());
  const t = document.createElement('div');
  t.className = 'toast' + (bad ? ' bad' : '');
  t.textContent = message;
  t.setAttribute('role', 'status');
  document.body.appendChild(t);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.remove(), 2600);
}

function errorText(err) {
  if (!err) return 'Something went wrong.';
  if (err.data && typeof err.data === 'object') {
    const first = Object.values(err.data)[0];
    return Array.isArray(first) ? first[0] : String(first);
  }
  return err.message || 'Something went wrong.';
}

/* Handles a failure uniformly: an expired session sends you back to sign in,
   anything else is reported where you are. */
function handle(err) {
  if (err && err.sessionExpired) {
    me = null;
    toast('Your session expired. Sign in again.', true);
    renderLogin();
    return;
  }
  toast(errorText(err), true);
}

/* Boot ----------------------------------------------------------------- */

function showMockBadge() {
  const b = document.createElement('div');
  b.className = 'mock-badge';
  b.textContent = 'Mock data';
  b.title = 'No backend reachable — running on the seeded store.';
  document.body.appendChild(b);
}

async function boot() {
  try {
    await data.getCsrf();
  } catch (err) {
    /* An HTTP status means the API answered, so keep using it. No status at
       all means the request never reached a server — fall back to the mock so
       the UI stays reviewable instead of showing a dead screen. */
    if (!err || err.status === undefined) {
      data = Store;
      await data.getCsrf();
    }
  }
  if (usingMock()) showMockBadge();

  try {
    me = await data.getMe();
    renderShell();
  } catch {
    renderLogin();                                  // 403 means "not signed in"
  }
}

/* Login ---------------------------------------------------------------- */

function renderLogin() {
  root.replaceChildren(tpl('tpl-login'));
  const form = root.querySelector('form');
  const errorEl = form.querySelector('[data-error]');

  // The demo credentials only exist in the mock store.
  if (!usingMock()) form.querySelector('.login-hint').remove();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = form.querySelector('button');
    btn.disabled = true;
    errorEl.hidden = true;
    try {
      me = await data.login(form.username.value, form.password.value);
      renderShell();
    } catch (err) {
      errorEl.textContent = errorText(err);
      errorEl.hidden = false;
      btn.disabled = false;
    }
  });
}

/* Shell + routing ------------------------------------------------------ */

function renderShell() {
  root.replaceChildren(tpl('tpl-shell'));
  root.querySelector('[data-who]').textContent = me.display_name || me.username;
  root.querySelector('[data-signout]').addEventListener('click', async () => {
    await data.logout();
    me = null;
    location.hash = '';
    renderLogin();
  });
  route();
}

function outlet() { return root.querySelector('[data-main]'); }

function setActiveNav(name) {
  root.querySelectorAll('[data-nav]').forEach(a => {
    a.classList.toggle('is-active', a.dataset.nav === name);
  });
}

function route() {
  if (!me) return;
  const hash = location.hash.replace(/^#/, '') || '/boards';
  const boardMatch = hash.match(/^\/boards\/(\d+)$/);

  if (boardMatch) { setActiveNav('boards'); return viewBoard(boardMatch[1]); }
  if (hash === '/my-tasks') { setActiveNav('my-tasks'); return viewMyTasks(); }
  setActiveNav('boards');
  viewBoards();
}

window.addEventListener('hashchange', route);

/* Boards --------------------------------------------------------------- */

async function viewBoards() {
  const main = outlet();
  main.replaceChildren(tpl('tpl-boards'));
  const list = main.querySelector('[data-list]');
  list.innerHTML = '<li class="loading">Loading boards…</li>';

  main.querySelector('[data-create-board]').addEventListener('submit', async (e) => {
    e.preventDefault();
    // Explicit lookup: form.name would return the form's own name attribute.
    const input = e.target.querySelector('[name=name]');
    if (!input.value.trim()) return;
    try {
      await data.createBoard({ name: input.value });
      input.value = '';
      viewBoards();
    } catch (err) { handle(err); }
  });

  try {
    const boards = await data.listBoards();
    if (!boards.length) {
      list.innerHTML = '<li class="empty">No boards yet. Name one above to get started.</li>';
      return;
    }
    const counts = await Promise.all(boards.map(b => data.getBoardCards(b.id)));
    list.replaceChildren(...boards.map((b, i) => boardRow(b, counts[i])));
  } catch (err) {
    list.innerHTML = '';
    handle(err);
  }
}

function boardRow(board, cards) {
  const open = cards.filter(c => c.status !== 'done').length;
  const li = document.createElement('li');
  const a = document.createElement('a');
  a.className = 'board-row';
  a.href = `#/boards/${board.id}`;
  a.innerHTML =
    `<span class="name">${esc(board.name)}</span>` +
    `<span class="desc">${esc(board.description)}</span>` +
    `<span class="tally mono">${open} open · ${cards.length} total</span>`;
  li.appendChild(a);
  return li;
}

/* Board ---------------------------------------------------------------- */

let boardState = { id: null, buckets: null };

async function viewBoard(boardId) {
  const main = outlet();
  main.replaceChildren(tpl('tpl-board'));
  boardState.id = Number(boardId);

  const columnsEl = main.querySelector('[data-columns]');
  columnsEl.innerHTML = '<p class="loading">Loading board…</p>';

  try {
    const [board, cards] = await Promise.all([
      data.getBoard(boardId),
      data.getBoardCards(boardId),
    ]);
    main.querySelector('[data-board-name]').textContent = board.name;
    const desc = main.querySelector('[data-board-desc]');
    if (board.description) desc.textContent = board.description; else desc.remove();

    boardState.buckets = Logic.groupByStatus(cards);
    paintColumns();
  } catch (err) {
    columnsEl.innerHTML = '';
    handle(err);
  }
}

async function reloadBoard() {
  const cards = await data.getBoardCards(boardState.id);
  boardState.buckets = Logic.groupByStatus(cards);
  paintColumns();
}

function paintColumns(buckets) {
  if (buckets) boardState.buckets = buckets;
  const columnsEl = root.querySelector('[data-columns]');
  if (!columnsEl) return;
  columnsEl.replaceChildren(...Logic.STATUSES.map(s => columnEl(s, boardState.buckets[s])));
}

function columnEl(status, cards) {
  const col = document.createElement('section');
  col.className = 'column';
  if (status === 'in_progress') col.classList.add('column-active');
  if (status === 'done') col.classList.add('column-done');
  col.dataset.status = status;

  const head = document.createElement('div');
  head.className = 'column-head';
  head.innerHTML =
    `<span class="dot"></span>` +
    `<span class="label">${Logic.STATUS_LABELS[status]}</span>` +
    `<span class="count">${cards.length}</span>`;
  col.appendChild(head);

  const stack = document.createElement('div');
  stack.className = 'stack';
  stack.dataset.stack = '';
  cards.forEach(c => stack.appendChild(cardEl(c)));
  col.appendChild(stack);

  col.appendChild(addCardControl(status));
  wireDrop(col, stack, status);
  return col;
}

function cardEl(card) {
  const el = document.createElement('article');
  el.className = `card p${card.priority || 2}`;
  if (Logic.isOverdue(card)) el.classList.add('is-overdue');
  el.draggable = true;
  el.tabIndex = 0;
  el.dataset.id = card.id;

  const due = card.due_date
    ? `<time class="${Logic.isOverdue(card) ? 'late' : ''}" datetime="${card.due_date}">${Logic.dueLabel(card.due_date)}</time>`
    : '';
  const who = card.assignee_detail
    ? `<span class="who-chip">${esc(card.assignee_detail.display_name || card.assignee_detail.username)}</span>`
    : '';

  el.innerHTML =
    `<p class="card-title">${esc(card.title)}</p>` +
    (due || who ? `<div class="card-meta">${due}${who}</div>` : '');

  el.addEventListener('click', () => openCard(card.id));
  el.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openCard(card.id); }
  });

  el.addEventListener('dragstart', (e) => {
    e.dataTransfer.setData('text/plain', String(card.id));
    e.dataTransfer.effectAllowed = 'move';
    requestAnimationFrame(() => el.classList.add('is-dragging'));
  });
  el.addEventListener('dragend', () => el.classList.remove('is-dragging'));

  return el;
}

function addCardControl(status) {
  const wrap = document.createElement('div');
  const btn = document.createElement('button');
  btn.className = 'add-card';
  btn.type = 'button';
  btn.textContent = '+ Add a card';
  wrap.appendChild(btn);

  btn.addEventListener('click', () => {
    const form = document.createElement('form');
    form.className = 'add-form';
    form.innerHTML = '<input name="title" placeholder="What needs doing?" aria-label="Card title">';
    wrap.replaceChildren(form);
    // Explicit lookup: form.title would return the element's title attribute.
    const input = form.querySelector('[name=title]');
    input.focus();

    const cancel = () => { if (!input.value.trim()) wrap.replaceChildren(btn); };
    input.addEventListener('blur', cancel);

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!input.value.trim()) return;
      try {
        await data.createCard({ board: boardState.id, title: input.value, status });
        await reloadBoard();
      } catch (err) { handle(err); }
    });
  });

  return wrap;
}

/* Drag and drop -------------------------------------------------------- */

/* The destination index among the cards that will remain after the dragged
   card is removed — which is exactly what applyMove expects. */
function indexAtY(stack, y, draggedId) {
  const others = Array.from(stack.querySelectorAll('.card'))
    .filter(el => Number(el.dataset.id) !== draggedId);
  let index = 0;
  for (const el of others) {
    const box = el.getBoundingClientRect();
    if (y > box.top + box.height / 2) index++;
  }
  return index;
}

function wireDrop(col, stack, status) {
  col.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    col.classList.add('is-over');
  });
  col.addEventListener('dragleave', (e) => {
    if (!col.contains(e.relatedTarget)) col.classList.remove('is-over');
  });
  col.addEventListener('drop', async (e) => {
    e.preventDefault();
    col.classList.remove('is-over');
    const cardId = Number(e.dataTransfer.getData('text/plain'));
    if (!cardId) return;

    try {
      await Logic.moveCard({
        buckets: boardState.buckets,
        cardId,
        toStatus: status,
        toIndex: indexAtY(stack, e.clientY, cardId),
        render: paintColumns,
        commit: data.postMove,
        reload: reloadBoard,
      });
    } catch (err) {
      handle(err);
    }
  });
}

/* Card modal ----------------------------------------------------------- */

function closeModal() {
  document.querySelectorAll('.scrim').forEach(s => s.remove());
  document.removeEventListener('keydown', onModalKey);
}

function onModalKey(e) { if (e.key === 'Escape') closeModal(); }

async function openCard(cardId) {
  const all = Logic.STATUSES.flatMap(s => boardState.buckets ? boardState.buckets[s] : []);
  const card = all.find(c => c.id === cardId);
  if (!card) return;

  if (!usersCache) {
    try { usersCache = await data.listUsers(); } catch { usersCache = []; }
  }

  const scrim = document.createElement('div');
  scrim.className = 'scrim';
  scrim.addEventListener('click', (e) => { if (e.target === scrim) closeModal(); });

  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');

  const options = usersCache.map(u =>
    `<option value="${u.id}" ${Number(card.assignee) === u.id ? 'selected' : ''}>${esc(u.display_name || u.username)}</option>`
  ).join('');

  modal.innerHTML = `
    <div class="modal-head">
      <p class="eyebrow">${Logic.STATUS_LABELS[card.status]} · card ${card.id}</p>
      <button class="btn btn-quiet" data-close>Close</button>
    </div>
    <input class="modal-title" name="title" value="${esc(card.title)}" aria-label="Card title">
    <label class="field">
      <span>Description</span>
      <textarea name="description" placeholder="What does done look like?">${esc(card.description)}</textarea>
    </label>
    <div class="grid-3">
      <label class="field">
        <span>Priority</span>
        <select name="priority">
          <option value="1" ${card.priority === 1 ? 'selected' : ''}>Low</option>
          <option value="2" ${card.priority === 2 ? 'selected' : ''}>Medium</option>
          <option value="3" ${card.priority === 3 ? 'selected' : ''}>High</option>
        </select>
      </label>
      <label class="field">
        <span>Due</span>
        <input type="date" name="due_date" value="${card.due_date || ''}">
      </label>
      <label class="field">
        <span>Assignee</span>
        <select name="assignee"><option value="">Unassigned</option>${options}</select>
      </label>
    </div>
    <p class="form-error" data-error hidden></p>
    <div class="modal-actions">
      <button class="btn btn-primary" data-save>Save changes</button>
      <button class="btn" data-close>Cancel</button>
      <button class="btn btn-danger" data-delete>Delete card</button>
    </div>
    <div class="comments-block">
      <h2>Comments</h2>
      <ul class="comment-list" data-comments><li class="loading">Loading…</li></ul>
      <form class="comment-form" data-comment-form>
        <input name="body" placeholder="Add a comment" aria-label="Comment">
        <button class="btn" type="submit">Post</button>
      </form>
    </div>`;

  scrim.appendChild(modal);
  document.body.appendChild(scrim);
  document.addEventListener('keydown', onModalKey);
  modal.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', closeModal));

  const errorEl = modal.querySelector('[data-error]');

  modal.querySelector('[data-save]').addEventListener('click', async () => {
    errorEl.hidden = true;
    const form = {
      title: modal.querySelector('[name=title]').value,
      description: modal.querySelector('[name=description]').value,
      priority: modal.querySelector('[name=priority]').value,
      due_date: modal.querySelector('[name=due_date]').value,
      assignee: modal.querySelector('[name=assignee]').value,
    };
    try {
      await data.updateCard(card.id, Logic.editableCardFields(form));
      closeModal();
      await reloadBoard();
      toast('Card saved');
    } catch (err) {
      errorEl.textContent = errorText(err);
      errorEl.hidden = false;
    }
  });

  modal.querySelector('[data-delete]').addEventListener('click', async () => {
    try {
      await data.deleteCard(card.id);
      closeModal();
      await reloadBoard();
      toast('Card deleted');
    } catch (err) { handle(err); }
  });

  loadComments(card.id, modal);
  modal.querySelector('[data-comment-form]').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = e.target.querySelector('[name=body]');
    if (!input.value.trim()) return;
    try {
      await data.createComment(card.id, input.value);
      input.value = '';
      loadComments(card.id, modal);
    } catch (err) { handle(err); }
  });
}

async function loadComments(cardId, modal) {
  const list = modal.querySelector('[data-comments]');
  try {
    const comments = await data.listComments(cardId);
    if (!comments.length) {
      list.innerHTML = '<li class="empty">No comments yet. Explain the tricky part here.</li>';
      return;
    }
    list.replaceChildren(...comments.map(c => commentEl(c, cardId, modal)));
  } catch (err) {
    list.innerHTML = '';
    handle(err);
  }
}

function commentEl(comment, cardId, modal) {
  const li = document.createElement('li');
  li.className = 'comment';
  const author = comment.author
    ? esc(comment.author.display_name || comment.author.username)
    : 'Deleted user';
  const mine = !comment.author || (me && comment.author.id === me.id);

  li.innerHTML =
    `<div class="comment-head">` +
      `<span class="author">${author}</span>` +
      `<time datetime="${comment.created_at}">${comment.created_at.slice(0, 10)}</time>` +
      (mine ? `<button class="btn btn-danger" data-del>Delete</button>` : '') +
    `</div>` +
    `<p class="comment-body">${esc(comment.body)}</p>`;

  const del = li.querySelector('[data-del]');
  if (del) del.addEventListener('click', async () => {
    try {
      await data.deleteComment(comment.id);
      loadComments(cardId, modal);
    } catch (err) { handle(err); }
  });

  return li;
}

/* My tasks ------------------------------------------------------------- */

async function viewMyTasks() {
  const main = outlet();
  main.replaceChildren(tpl('tpl-my-tasks'));
  const list = main.querySelector('[data-list]');
  list.innerHTML = '<li class="loading">Loading…</li>';

  try {
    const cards = await data.myTasks();
    if (!cards.length) {
      list.innerHTML = '<li class="empty">Nothing assigned to you. Enjoy it while it lasts.</li>';
      return;
    }
    list.replaceChildren(...cards.map(taskRow));
  } catch (err) {
    list.innerHTML = '';
    handle(err);
  }
}

function taskRow(card) {
  const li = document.createElement('li');
  li.className = `task-row p${card.priority || 2}`;
  if (Logic.isOverdue(card)) li.classList.add('is-overdue');

  const due = card.due_date
    ? `<time class="${Logic.isOverdue(card) ? 'late' : ''}" datetime="${card.due_date}">${Logic.dueLabel(card.due_date)}</time>`
    : '<span class="where">No due date</span>';

  li.innerHTML =
    `<span class="t">${esc(card.title)}</span>` +
    due +
    `<span class="state ${card.status === 'in_progress' ? 'active' : ''}">${Logic.STATUS_LABELS[card.status]}</span>`;

  li.addEventListener('click', () => { location.hash = `#/boards/${card.board}`; });
  return li;
}

boot();
