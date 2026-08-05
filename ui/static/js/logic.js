/* Business logic — pure, no DOM, no network.
   Everything here is the real logic the product needs, written against the
   contract in docs/api.md. It is deliberately independent of where the data
   comes from, so the same code runs on the mock store and the real API. */

const Logic = (() => {

  const STATUSES = ['todo', 'in_progress', 'done'];

  const STATUS_LABELS = {
    todo: 'To Do',
    in_progress: 'In Progress',
    done: 'Done',
  };

  const PRIORITY_LABELS = { 1: 'Low', 2: 'Medium', 3: 'High' };

  /* The API returns every card on a board in ONE position-ordered list that
     interleaves all three statuses, so two cards in different columns share a
     position. Grouping is the client's job. */
  function groupByStatus(cards) {
    const buckets = { todo: [], in_progress: [], done: [] };
    for (const card of cards || []) {
      if (buckets[card.status]) buckets[card.status].push(card);
    }
    return buckets;
  }

  function findCard(buckets, cardId) {
    for (const status of STATUSES) {
      const card = buckets[status].find(c => c.id === cardId);
      if (card) return { card, from: status };
    }
    return { card: null, from: null };
  }

  function removeCard(buckets, cardId) {
    const next = {};
    for (const status of STATUSES) {
      next[status] = buckets[status].filter(c => c.id !== cardId);
    }
    return next;
  }

  /* Remove from the source column BEFORE inserting into the destination.
     The other order is off by one whenever a card moves down within its own
     column. Returns new objects; never mutates the input. */
  function applyMove(buckets, cardId, toStatus, toIndex) {
    const { card } = findCard(buckets, cardId);
    if (!card) return buckets;

    const next = removeCard(buckets, cardId);
    const moved = Object.assign({}, card, { status: toStatus });
    const target = next[toStatus].slice();
    target.splice(toIndex, 0, moved);
    next[toStatus] = target;
    return next;
  }

  /* Optimistic move with rollback.
     `commit` performs the write and `reload` re-reads the board. */
  async function moveCard(opts) {
    const { buckets, cardId, toStatus, toIndex, render, commit, reload } = opts;
    const snapshot = buckets;

    render(applyMove(buckets, cardId, toStatus, toIndex));

    try {
      await commit(cardId, { status: toStatus, position: toIndex });
      /* The server renumbers the whole column in a transaction. If a teammate
         dragged at the same time our local guess is wrong, so reconcile. */
      await reload();
    } catch (err) {
      if (err && err.status === 404) {
        /* Deleted before the move landed — drop it rather than resurrect it. */
        render(removeCard(snapshot, cardId));
        await reload();
        return;
      }
      render(snapshot);
      throw err;
    }
  }

  /* Dates are compared as plain YYYY-MM-DD strings, which is what the API
     returns. No timezone maths, no Date parsing surprises. */
  function today() {
    const d = new Date();
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  }

  function isOverdue(card) {
    return Boolean(card.due_date) && card.status !== 'done' && card.due_date < today();
  }

  function dueLabel(dateStr) {
    if (!dateStr) return '';
    const days = Math.round((new Date(dateStr) - new Date(today())) / 86400000);
    if (days === 0) return 'Today';
    if (days === 1) return 'Tomorrow';
    if (days === -1) return 'Yesterday';
    if (days < 0) return `${Math.abs(days)}d late`;
    if (days <= 7) return `${days}d`;
    return dateStr.slice(5);            // MM-DD
  }

  /* Fields the card PATCH endpoint accepts. `status` and `board` are absent
     on purpose: the API rejects a change to either with 400, and column moves
     go only through the move endpoint. */
  function editableCardFields(form) {
    return {
      title: form.title,
      description: form.description,
      priority: Number(form.priority),
      due_date: form.due_date || null,
      assignee: form.assignee === '' ? null : Number(form.assignee),
    };
  }

  return {
    STATUSES, STATUS_LABELS, PRIORITY_LABELS,
    groupByStatus, applyMove, removeCard, moveCard,
    isOverdue, dueLabel, today, editableCardFields,
  };
})();
