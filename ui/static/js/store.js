/* Mock data source.
   Implements exactly the interface Api does, so the prototype runs standalone
   with no backend. It deliberately enforces the same server-side rules the
   real API enforces — a rejected PATCH, an author-only comment delete, column
   renumbering on move — so the prototype is an honest model of the product
   rather than a picture of it. */

const Store = (() => {

  const LATENCY = 140;   // enough to see optimistic updates land

  let nextId = 100;
  const id = () => ++nextId;

  // Deliberately the same people the real `seed_demo` command creates, so the
  // mock and a seeded local database do not contradict each other.
  const users = [
    { id: 1, username: 'asha',  display_name: 'Asha Rao' },
    { id: 2, username: 'kabir', display_name: 'Kabir Menon' },
    { id: 3, username: 'lena',  display_name: 'Lena Fischer' },
  ];

  let me = null;

  const boards = [
    { id: 1, name: 'Tasky v1', description: 'Ship the internal board', created_by: users[0] },
    { id: 2, name: 'Website refresh', description: '', created_by: users[1] },
  ];

  const day = offset => {
    const d = new Date();
    d.setDate(d.getDate() + offset);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  };

  const card = (o) => Object.assign({
    description: '', due_date: null, assignee: null, priority: 2,
    created_by: users[0],
  }, o, {
    assignee_detail: o.assignee ? users.find(u => u.id === o.assignee) : null,
    priority_label: { 1: 'Low', 2: 'Medium', 3: 'High' }[o.priority || 2],
  });

  let cards = [
    card({ id: 11, board: 1, title: 'Drag ordering keeps a gap when two people drag at once',
           status: 'in_progress', position: 0, priority: 3, due_date: day(-2), assignee: 1,
           description: 'Reading the old column before taking the row lock lets a concurrent move leave the board permanently out of order.' }),
    card({ id: 12, board: 1, title: 'Card comments', status: 'done', position: 0, priority: 2, assignee: 2 }),
    card({ id: 13, board: 1, title: 'Assignee dropdown needs a users endpoint', status: 'todo', position: 0, priority: 1, assignee: 3 }),
    card({ id: 14, board: 1, title: 'Decide what happens to cards on a deleted board',
           status: 'todo', position: 1, priority: 2, due_date: day(3) }),
    card({ id: 15, board: 1, title: 'Rotate the dev superuser before anything is reachable',
           status: 'todo', position: 2, priority: 3, due_date: day(0), assignee: 1 }),
    card({ id: 16, board: 1, title: 'Apache reverse proxy in front of the container',
           status: 'in_progress', position: 1, priority: 2, due_date: day(6), assignee: 2 }),
    card({ id: 17, board: 1, title: 'Session auth, same origin', status: 'done', position: 1, priority: 2, assignee: 1 }),
    card({ id: 18, board: 1, title: 'Seed command for local demo data', status: 'done', position: 2, priority: 1, assignee: 3 }),
    card({ id: 21, board: 2, title: 'Rewrite the pricing page', status: 'todo', position: 0, priority: 2, assignee: 2 }),
    card({ id: 22, board: 2, title: 'Compress the hero image', status: 'in_progress', position: 0, priority: 1, due_date: day(-5), assignee: 1 }),
  ];

  let comments = [
    { id: 31, card: 11, author: users[1], body: 'Reproduced it — two browsers, same card. The gap survives a refresh.',
      created_at: day(-3) + 'T09:12:00Z' },
    { id: 32, card: 11, author: users[0], body: 'Fix is to take the lock first, then read. Adding two regression tests.',
      created_at: day(-2) + 'T14:40:00Z' },
  ];

  /* ---- plumbing ---- */

  const wait = (v) => new Promise(res => setTimeout(() => res(clone(v)), LATENCY));
  const clone = (v) => (v === null || v === undefined) ? v : JSON.parse(JSON.stringify(v));

  function fail(status, data) {
    return Promise.reject(Object.assign(new Error('Mock API ' + status), { status, data }));
  }

  function renumber(boardId, status) {
    cards
      .filter(c => c.board === boardId && c.status === status)
      .sort((a, b) => a.position - b.position || a.id - b.id)
      .forEach((c, i) => { c.position = i; });
  }

  /* ---- auth ---- */

  const getCsrf = () => wait(null);

  function login(username, password) {
    const user = users.find(u => u.username === username.trim().toLowerCase());
    if (!user || !password) {
      // Identical for an unknown username and a wrong password, exactly as the
      // real backend does — a different message would let anyone enumerate
      // who works here.
      return fail(400, { detail: 'Incorrect username or password.' });
    }
    me = user;
    return wait(user);
  }

  function logout() { me = null; return wait(null); }
  function getMe() { return me ? wait(me) : fail(403, { detail: 'Authentication credentials were not provided.' }); }

  /* ---- boards ---- */

  const listBoards = () => wait(boards);
  const getBoard = (bid) => {
    const b = boards.find(x => x.id === Number(bid));
    return b ? wait(b) : fail(404, null);
  };

  function createBoard(fields) {
    if (!fields.name || !fields.name.trim()) return fail(400, { name: 'This field may not be blank.' });
    const b = { id: id(), name: fields.name.trim(), description: fields.description || '', created_by: me };
    boards.push(b);
    return wait(b);
  }

  /* Returns every card on the board in ONE position-ordered list across all
     three statuses — interleaved, exactly like the real endpoint. */
  const getBoardCards = (bid) => wait(
    cards.filter(c => c.board === Number(bid))
         .sort((a, b) => a.position - b.position || a.id - b.id)
  );

  /* ---- cards ---- */

  function createCard(fields) {
    if (!fields.title || !fields.title.trim()) return fail(400, { title: 'This field may not be blank.' });
    const status = fields.status || 'todo';
    const siblings = cards.filter(c => c.board === fields.board && c.status === status);
    const c = card({
      id: id(), board: Number(fields.board), title: fields.title.trim(),
      status, position: siblings.length, priority: fields.priority || 2,
      due_date: fields.due_date || null, assignee: fields.assignee || null,
    });
    c.created_by = me;
    cards.push(c);
    return wait(c);
  }

  function updateCard(cardId, fields) {
    const c = cards.find(x => x.id === Number(cardId));
    if (!c) return fail(404, null);

    if ('status' in fields && fields.status !== c.status) {
      return fail(400, { status: 'Status cannot be changed here — POST to /api/cards/{id}/move/ instead.' });
    }
    if ('board' in fields && Number(fields.board) !== c.board) {
      return fail(400, { board: 'Cards cannot be moved between boards.' });
    }

    Object.assign(c, fields);
    c.assignee_detail = c.assignee ? users.find(u => u.id === Number(c.assignee)) : null;
    c.assignee = c.assignee ? Number(c.assignee) : null;
    c.priority_label = { 1: 'Low', 2: 'Medium', 3: 'High' }[c.priority];
    return wait(c);
  }

  function deleteCard(cardId) {
    const c = cards.find(x => x.id === Number(cardId));
    if (!c) return fail(404, null);
    cards = cards.filter(x => x.id !== Number(cardId));
    comments = comments.filter(x => x.card !== Number(cardId));
    // Deliberately no renumber: gaps are normal and harmless.
    return wait(null);
  }

  function postMove(cardId, { status, position }) {
    const c = cards.find(x => x.id === Number(cardId));
    if (!c) return fail(404, { detail: 'Not found.' });

    const from = c.status;
    c.status = status;
    c.position = position - 0.5;      // slot in between, then renumber to integers
    renumber(c.board, status);
    if (from !== status) renumber(c.board, from);
    return wait(c);
  }

  /* ---- comments ---- */

  const listComments = (cardId) => wait(
    comments.filter(x => x.card === Number(cardId))
            .sort((a, b) => a.created_at.localeCompare(b.created_at))
  );

  function createComment(cardId, body) {
    if (!body || !body.trim()) return fail(400, { body: 'A comment cannot be empty.' });
    const c = { id: id(), card: Number(cardId), author: me, body: body.trim(), created_at: new Date().toISOString() };
    comments.push(c);
    return wait(c);
  }

  function deleteComment(commentId) {
    const c = comments.find(x => x.id === Number(commentId));
    if (!c) return fail(404, null);
    // Author-only, exactly like the real endpoint. A comment whose author was
    // deleted (author === null) can be removed by anyone signed in.
    if (c.author && me && c.author.id !== me.id) {
      return fail(403, { detail: 'You can only delete your own comments.' });
    }
    comments = comments.filter(x => x.id !== Number(commentId));
    return wait(null);
  }

  /* ---- me ---- */

  const listUsers = () => wait(users);

  const myTasks = () => wait(
    cards.filter(c => me && c.assignee === me.id && c.status !== 'done')
         .sort((a, b) => {
           if (!a.due_date && !b.due_date) return a.id - b.id;
           if (!a.due_date) return 1;
           if (!b.due_date) return -1;
           return a.due_date.localeCompare(b.due_date);
         })
  );

  return {
    getCsrf, login, logout, getMe,
    listBoards, getBoard, createBoard, getBoardCards,
    createCard, updateCard, deleteCard, postMove,
    listComments, createComment, deleteComment,
    listUsers, myTasks,
  };
})();
