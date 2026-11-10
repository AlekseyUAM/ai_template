/* auth.js — токен доступа AgentMon.
 *
 * Токен приходит один раз в URL (?token=...), сохраняется в localStorage и
 * подставляется во все fetch-запросы заголовком X-Agentmon-Token. Для
 * WebSocket есть agentmonUrl(), добавляющий ?token= к адресу.
 */
(function () {
  var KEY = 'agentmon_token';

  try {
    var u = new URL(location.href);
    var t = u.searchParams.get('token');
    if (t) {
      localStorage.setItem(KEY, t);
      u.searchParams.delete('token');
      history.replaceState(null, '', u.pathname + u.search + (u.hash || ''));
    }
  } catch (_) { /* старый браузер — работаем без токена */ }

  function token() {
    try { return localStorage.getItem(KEY) || ''; } catch (_) { return ''; }
  }

  var originalFetch = window.fetch ? window.fetch.bind(window) : null;
  if (originalFetch) {
    window.fetch = function (input, init) {
      init = init ? Object.assign({}, init) : {};
      var headers = new Headers(
        init.headers || (input instanceof Request ? input.headers : undefined)
      );
      var t = token();
      if (t) headers.set('X-Agentmon-Token', t);
      init.headers = headers;
      return originalFetch(input, init);
    };
  }

  window.agentmonUrl = function (path) {
    var t = token();
    if (!t) return path;
    return path + (path.indexOf('?') >= 0 ? '&' : '?') + 'token=' +
      encodeURIComponent(t);
  };
})();
