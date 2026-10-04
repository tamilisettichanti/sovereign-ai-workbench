// App shell: icons, API helpers, streaming reader, markdown, and the page router.
// Each file in js/pages registers itself as Pages.<name> = { title, render(el) }.

const Pages = {};

const ICON_PATHS = {
  shield: '<path d="M12 3l7 3v6c0 4.5-3 7.6-7 9-4-1.4-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5L18 18M18 6l-2.5 2.5M8.5 15.5L6 18"/>',
  doc: '<path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M21 16l-5-5-8 8"/>',
  db: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
  users: '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M16 5.2a3.2 3.2 0 010 5.6M21 20c0-2.6-1.6-4.8-4-5.6"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 00-.1-1.3l2-1.5-2-3.4-2.3.9a7 7 0 00-2.2-1.3L14 3h-4l-.4 2.4a7 7 0 00-2.2 1.3l-2.3-.9-2 3.4 2 1.5A7 7 0 005 12c0 .4 0 .9.1 1.3l-2 1.5 2 3.4 2.3-.9c.7.6 1.4 1 2.2 1.3L10 21h4l.4-2.4c.8-.3 1.5-.7 2.2-1.3l2.3.9 2-3.4-2-1.5c.1-.4.1-.9.1-1.3z"/>',
  send: '<path d="M21 3L10 14M21 3l-7 18-4-7-7-4z"/>',
  clip: '<path d="M20 11.5l-8.5 8.5a5 5 0 01-7-7L13 4.5a3.3 3.3 0 014.7 4.7L9.5 17.5a1.7 1.7 0 01-2.4-2.4L14.5 8"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="M5 12l5 5L20 7"/>',
  checkc: '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
  xc: '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M4 21h16"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5M4 21h16"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  code: '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/>',
  scan: '<path d="M4 8V5a1 1 0 011-1h3M16 4h3a1 1 0 011 1v3M20 16v3a1 1 0 01-1 1h-3M8 20H5a1 1 0 01-1-1v-3M4 12h16"/>',
  eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  route: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="12" cy="18" r="2.5"/><path d="M6 8.5v2a3 3 0 003 3h6a3 3 0 003-3v-2M12 13.5v2"/>',
  net: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 3 2.5 15 0 18M12 3c-2.5 3-2.5 15 0 18"/>',
  trash: '<path d="M4 7h16M10 7V4h4v3M6 7l1 13h10l1-13M10 11v6M14 11v6"/>',
  refresh: '<path d="M20 11a8 8 0 10-2.3 5.7M20 4v7h-7"/>',
  table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 4v16"/>',
  slides: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M12 16v4M8 20h8"/>',
  bot: '<rect x="4" y="8" width="16" height="11" rx="3"/><path d="M12 4v4M9 13h.01M15 13h.01M9.5 16h5"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};
const icon = (name, style = '') => `<svg class="ic" viewBox="0 0 24 24" style="${style}">${ICON_PATHS[name] || ''}</svg>`;

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const fmtTime = (iso) => iso ? new Date(iso).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) : '';
const fmtDateTime = (iso) => iso ? new Date(iso).toLocaleString([], {day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit'}) : '';
const fileUrl = (area, name, download) => `/api/file/${area}/${encodeURIComponent(name)}${download ? '?download=1' : ''}`;
const extIcon = (name) => {
  const e = (name.split('.').pop() || '').toLowerCase();
  if (['png', 'jpg', 'jpeg', 'bmp', 'tif', 'tiff', 'webp'].includes(e)) return 'image';
  if (e === 'xlsx' || e === 'csv') return 'table';
  if (e === 'pptx') return 'slides';
  if (e === 'py') return 'code';
  return 'doc';
};

function toast(message, isError) {
  const t = document.createElement('div');
  t.className = 'toast' + (isError ? ' err' : '');
  t.textContent = message;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4200);
}

async function api(path, options = {}) {
  if (options.json !== undefined) {
    options.method = options.method || 'POST';
    options.headers = {'Content-Type': 'application/json'};
    options.body = JSON.stringify(options.json);
  }
  const res = await fetch(path, options);
  if (res.status === 401) { location.href = '/login'; throw new Error('Not signed in'); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || `Request failed (${res.status})`);
  return data;
}

// POST a request and read the reply as a stream of JSON events.
// The server runs the work as a background task. If the connection drops part-way
// (tasks can take minutes), this reconnects to the task and resumes where it stopped.
async function stream(path, body, onEvent) {
  let taskId = null, received = 0, ended = false;

  const read = async (res) => {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      let cut;
      while ((cut = buffer.indexOf('\n\n')) >= 0) {
        const line = buffer.slice(0, cut).trim();
        buffer = buffer.slice(cut + 2);
        if (!line.startsWith('data:')) continue;
        let ev;
        try { ev = JSON.parse(line.slice(5)); } catch (e) { continue; }
        if (ev.type === 'task') { taskId = ev.id; continue; }
        if (ev.type === 'ping') continue;
        if (ev.type === 'end') { ended = true; continue; }
        received++;
        try { onEvent(ev); } catch (e) { console.error(e); }
      }
    }
  };

  let res = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  if (res.status === 401) { location.href = '/login'; return; }
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  for (let attempt = 0; ; attempt++) {
    try { await read(res); } catch (e) { if (!taskId) throw e; }
    if (ended || !taskId) return;
    if (attempt >= 30) throw new Error('Lost the connection to the server and could not rejoin the task.');
    await new Promise((r) => setTimeout(r, 1000));
    try {
      res = await fetch(`/api/task/${taskId}?start=${received}`);
      if (res.status === 404) throw new Error('The server was restarted while this task was running.');
    } catch (e) {
      if (String(e.message).includes('restarted')) throw e;
      res = {body: {getReader: () => ({read: async () => ({done: true})})}};  // server unreachable: wait and retry
    }
  }
}

async function uploadFiles(fileList, path = '/api/upload') {
  const form = new FormData();
  for (const f of fileList) form.append('files', f);
  return api(path, {method: 'POST', body: form});
}

// Small markdown renderer: code fences, headings, lists, tables, bold, inline code.
function md(text) {
  const inline = (s) => esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
  const out = [];
  const lines = String(text || '').split('\n');
  let i = 0, list = null;
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim().startsWith('```')) {
      closeList();
      const code = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) code.push(lines[i++]);
      i++;
      out.push(`<pre><code>${esc(code.join('\n'))}</code></pre>`);
      continue;
    }
    if (line.trim().startsWith('|')) {
      closeList();
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) rows.push(lines[i++]);
      const cells = rows.map((r) => r.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim()))
        .filter((r) => !r.every((c) => /^:?-{2,}:?$/.test(c)));
      out.push('<table>' + cells.map((r, n) => '<tr>' + r.map((c) => n ? `<td>${inline(c)}</td>` : `<th>${inline(c)}</th>`).join('') + '</tr>').join('') + '</table>');
      continue;
    }
    let m;
    if ((m = line.match(/^\s*#{1,4}\s+(.*)/))) { closeList(); out.push(`<h4>${inline(m[1])}</h4>`); }
    else if ((m = line.match(/^\s*[-*•]\s+(.*)/))) { if (list !== 'ul') { closeList(); out.push('<ul>'); list = 'ul'; } out.push(`<li>${inline(m[1])}</li>`); }
    else if ((m = line.match(/^\s*\d+[.)]\s+(.*)/))) { if (list !== 'ol') { closeList(); out.push('<ol>'); list = 'ol'; } out.push(`<li>${inline(m[1])}</li>`); }
    else if (line.trim() === '---') { closeList(); out.push('<hr>'); }
    else if (line.trim() === '') { closeList(); }
    else { closeList(); out.push(`<p>${inline(line)}</p>`); }
    i++;
  }
  closeList();
  return out.join('');
}

const App = {
  user: null,
  nav: [
    ['dashboard', 'Dashboard', 'grid'],
    ['workbench', 'AI Workbench', 'spark'],
    ['documents', 'Documents', 'doc'],
    ['multimodal', 'Multimodal Analysis', 'image'],
    ['knowledge', 'Knowledge Base', 'db'],
    ['models', 'Models', 'cpu'],
    null,
    ['agents', 'Agents', 'bot'],
    ['reports', 'Reports', 'chart'],
    ['audit', 'Audit Logs', 'list'],
    ['settings', 'Settings', 'gear'],
  ],
  current: null,

  async start() {
    this.user = await api('/api/me');
    $('#brand').innerHTML = `${icon('shield')}<div><b>Sovereign AI Workbench</b><small>On-Premise &middot; Secure &middot; Trusted</small></div>`;
    $('#nav').innerHTML = this.nav.map((n) => n ? `<a href="#${n[0]}" data-page="${n[0]}">${icon(n[2])}${n[1]}</a>` : '<div class="sep"></div>').join('');
    $('#onprem').innerHTML = `${icon('shield')}<span>On-Premise AI<small>No External API Calls</small></span>`;
    $('#avatar').textContent = this.user.name[0].toUpperCase();
    $('#user-name').textContent = this.user.name;
    $('#user-role').textContent = this.user.role;
    $('#logout').onclick = async () => { await api('/api/logout', {method: 'POST'}); location.href = '/login'; };
    const tick = () => { $('#clock').textContent = new Date().toLocaleString([], {weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit'}); };
    tick(); setInterval(tick, 30000);
    window.addEventListener('hashchange', () => this.go());
    this.go();
  },

  go() {
    const name = (location.hash.slice(1) || 'dashboard').split('?')[0];
    const page = Pages[name] || Pages.dashboard;
    if (this.current && this.current.leave) this.current.leave();
    this.current = page;
    $$('#nav a').forEach((a) => a.classList.toggle('active', a.dataset.page === name));
    $('#page-title').textContent = page.title;
    // Each visit draws into its own container, so a slow page that finishes loading
    // after the user has moved on cannot overwrite the page now on screen.
    const host = $('#page');
    const el = document.createElement('div');
    host.replaceChildren(el);
    host.scrollTop = 0;
    Promise.resolve(page.render(el)).catch((e) => { el.innerHTML = `<div class="card empty">${esc(e.message)}</div>`; });
  },
};
