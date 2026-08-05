/* Real data source — the same interface as Store, against the live Django API.
   Switch to it by setting DATA_SOURCE = 'api' at the top of app.js, and serve
   this directory from the same origin as Django so the session cookie works. */

const Api = (() => {

  function getCookie(name) {
    const match = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
    return match ? decodeURIComponent(match[2]) : null;
  }

  async function parseBody(res) {
    try { return await res.json(); } catch { return null; }
  }

  async function request(path, { method = 'GET', body } = {}) {
    const headers = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (method !== 'GET') {
      const token = getCookie('csrftoken');
      if (token) headers['X-CSRFToken'] = token;
    }

    const res = await fetch(path, {
      method, headers,
      credentials: 'same-origin',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    if (res.status === 204) return null;
    if (res.ok) return parseBody(res);

    const data = await parseBody(res);

    /* 403 is ambiguous: an expired session, or a legitimate permission denial
       such as deleting someone else's comment. Treating every 403 as a logout
       would eject the user for clicking the wrong delete button. Raw fetch for
       the recheck — going back through request() would recurse forever once
       the session is genuinely gone. */
    if (res.status === 403) {
      const me = await fetch('/api/auth/me/', { credentials: 'same-origin' });
      const err = Object.assign(new Error('Forbidden'), { status: 403, data });
      err.sessionExpired = (me.status === 403);
      throw err;
    }

    throw Object.assign(new Error('API ' + res.status), { status: res.status, data });
  }

  return {
    getCsrf:  ()               => request('/api/auth/csrf/'),
    login:    (username, password) => request('/api/auth/login/', { method: 'POST', body: { username, password } }),
    logout:   ()               => request('/api/auth/logout/', { method: 'POST' }),
    getMe:    ()               => request('/api/auth/me/'),

    listBoards:    ()          => request('/api/boards/'),
    getBoard:      (id)        => request(`/api/boards/${id}/`),
    createBoard:   (fields)    => request('/api/boards/', { method: 'POST', body: fields }),
    getBoardCards: (id)        => request(`/api/boards/${id}/cards/`),

    createCard: (fields)       => request('/api/cards/', { method: 'POST', body: fields }),
    // No `status`, no `board` — the API rejects a change to either with 400.
    updateCard: (id, fields)   => request(`/api/cards/${id}/`, { method: 'PATCH', body: fields }),
    deleteCard: (id)           => request(`/api/cards/${id}/`, { method: 'DELETE' }),
    postMove:   (id, payload)  => request(`/api/cards/${id}/move/`, { method: 'POST', body: payload }),

    listComments:  (cardId)    => request(`/api/cards/${cardId}/comments/`),
    createComment: (cardId, body) => request(`/api/cards/${cardId}/comments/`, { method: 'POST', body: { body } }),
    deleteComment: (id)        => request(`/api/comments/${id}/`, { method: 'DELETE' }),

    listUsers: ()              => request('/api/users/'),
    myTasks:   ()              => request('/api/me/tasks/'),
  };
})();
