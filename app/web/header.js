(function () {
  var style = `
body { padding-top: 0 !important; overflow-x: hidden; }
.appheader {
  position: relative;
  width: 100vw;
  left: 50%;
  margin-left: -50vw;
  margin-right: -50vw;
  margin-bottom: 16px;
  padding: 10px 24px;
  background: var(--bg-inset, #010409);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid var(--border, #30363d);
  flex-shrink: 0;
  box-sizing: border-box;
}
.appheader .appheader-title {
  font-size: 15px;
  color: var(--fg, #e6edf3);
}
.appheader .appheader-ver {
  font-weight: 400;
  font-size: 12px;
  color: var(--fg-muted, #8b949e);
  margin-left: 4px;
}
.appnav {
  margin-left: auto;
  display: flex;
  gap: 4px;
}
.appnav a {
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 400;
  color: var(--fg-muted, #8b949e);
  text-decoration: none;
  transition: background 0.15s;
}
.appnav a:hover {
  background: var(--bg-subtle, #161b22);
  color: var(--fg, #e6edf3);
  text-decoration: none;
}
.appnav a.active {
  background: var(--bg-subtle, #161b22);
  color: var(--accent, #58a6ff);
}
`;

  var styleEl = document.createElement('style');
  styleEl.textContent = style;
  document.head.appendChild(styleEl);

  var nav = [
    { label: 'Монитор', href: '/' },
    { label: 'Проекты', href: '/projects' },
    { label: 'Задачи', href: '/tasks' },
    { label: 'MCP', href: '/mcp' }
  ];

  var path = location.pathname;

  function matchActive(href) {
    if (href === '/') return path === '/';
    return path === href || path.startsWith(href + '/');
  }

  var navHtml = nav.map(function (item) {
    var cls = matchActive(item.href) ? ' class="active"' : '';
    return '<a href="' + item.href + '"' + cls + '>' + item.label + '</a>';
  }).join('');

  var html = '<header class="appheader">'
    + '<span class="appheader-title">Agent Monitor <span class="appheader-ver" id="appheader-ver"></span></span>'
    + '<nav class="appnav">' + navHtml + '</nav>'
    + '</header>';

  document.body.insertAdjacentHTML('afterbegin', html);

  fetch('/api/env/version')
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) {
      if (data && data.version) {
        var el = document.getElementById('appheader-ver');
        if (el) el.textContent = 'v' + data.version;
        document.title = 'Agent Monitor v' + data.version;
      }
    })
    .catch(function () {});
})();
