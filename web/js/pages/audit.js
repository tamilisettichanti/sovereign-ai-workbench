// Audit Logs: live network monitor (the proof of no external calls) and the audit trail.
(function () {
  let timer = null;
  const KINDS = [['', 'All events'], ['model_call', 'Model calls'], ['tool_call', 'Tool calls'], ['route', 'Routing decisions'],
                 ['task_done', 'Completed tasks'], ['network_blocked', 'Blocked connections'], ['login,logout,login_failed', 'Sign-ins'],
                 ['kb_ingest,kb_search,kb_delete', 'Knowledge base']];

  const describe = (r) => {
    switch (r.kind) {
      case 'model_call': return `<b>${esc(r.model)}</b> &middot; ${esc(r.purpose)} &middot; ${r.prompt_tokens ?? '-'} in / ${r.output_tokens ?? '-'} out tokens &middot; ${((r.duration_ms || 0) / 1000).toFixed(1)} s${r.error ? ` <span class="pill red">error</span>` : ''}`;
      case 'tool_call': return `<b>${esc(r.tool)}</b> ${r.ok ? '<span class="pill green">ok</span>' : '<span class="pill red">failed</span>'} ${r.file ? '&rarr; ' + esc(r.file) : ''} <span class="muted">${esc(Object.entries(r.args || {}).map(([k, v]) => `${k}=${String(v).slice(0, 50)}`).join(', '))}</span>`;
      case 'route': return `${esc(r.task_label || r.task)} &rarr; <b>${esc(r.model_label || 'none')}</b> <span class="muted">${esc((r.request || '').slice(0, 70))}</span>`;
      case 'task_start': return `Started ${esc(r.task)} task: <span class="muted">${esc((r.request || '').slice(0, 80))}</span>`;
      case 'task_done': return `Finished ${esc(r.task)} task in ${r.duration_s} s <span class="pill ${r.status === 'failed' ? 'red' : 'green'}">${esc(r.status)}</span>`;
      case 'network_blocked': return `<span class="pill red">blocked</span> outbound attempt to <b>${esc(r.dest)}</b> (${esc(r.via)})`;
      case 'kb_search': return `Searched "${esc(r.query)}" <span class="muted">${(r.hits || []).length} passages</span>`;
      case 'kb_ingest': return `Indexed <b>${esc(r.source)}</b> (${r.chunks} passages)`;
      default: return esc(Object.entries(r).filter(([k]) => !['ts', 'kind', 'user'].includes(k)).map(([k, v]) => `${k}: ${v}`).join(', '));
    }
  };

  async function loadNetwork(el) {
    if (!$('#au-net', el)) return;
    const n = await api('/api/network');
    const ok = n.external_count === 0;
    $('#au-cards', el).innerHTML = `
      <div class="card stat"><div class="icon ${ok ? 'green' : 'red'}">${icon('net')}</div><div><b>${n.external_count}</b><span>External connections right now</span></div></div>
      <div class="card stat"><div class="icon">${icon('cpu')}</div><div><b>${n.model_calls}</b><span>Model calls, all to ${esc(n.endpoints.join(', ') || '127.0.0.1')}</span></div></div>
      <div class="card stat"><div class="icon amber">${icon('shield')}</div><div><b>${n.blocked.length}</b><span>Outbound attempts blocked</span></div></div>
      <div class="card stat"><div class="icon purple">${icon('list')}</div><div><b>${n.connections.length}</b><span>Live sockets inspected</span></div></div>`;
    $('#au-verdict', el).innerHTML = ok
      ? `<span class="pill green">${icon('checkc')}No connection leaves this machine</span>`
      : `<span class="pill red">${icon('xc')}${n.external_count} external connection(s) detected</span>`;
    $('#au-checked', el).textContent = 'checked ' + fmtTime(n.checked_at) + ', refreshes every 3 s';
    $('#au-net', el).innerHTML = `<table class="tbl"><tr><th>Process</th><th>PID</th><th>Local address</th><th>Remote address</th><th>State</th><th>Scope</th></tr>
      ${n.connections.map((c) => `<tr><td><b>${esc(c.process)}</b></td><td class="mono">${c.pid}</td><td class="mono">${esc(c.local)}</td>
        <td class="mono">${esc(c.remote || '-')}</td><td class="muted">${esc(c.status)}</td>
        <td><span class="pill ${c.external ? 'red' : 'green'}">${c.external ? 'EXTERNAL' : 'this machine'}</span></td></tr>`).join('')}</table>`;
  }

  async function loadAudit(el) {
    const kind = $('#au-kind', el).value;
    const r = await api('/api/audit?limit=300' + (kind ? '&kind=' + kind : ''));
    $('#au-count', el).textContent = `${r.records.length} most recent`;
    $('#au-log', el).innerHTML = r.records.length ? `<table class="tbl"><tr><th>Time</th><th>User</th><th>Event</th><th>Details</th><th>Endpoint</th></tr>
      ${r.records.map((x) => `<tr><td class="muted" style="white-space:nowrap">${fmtDateTime(x.ts)}</td><td>${esc(x.user)}</td>
        <td><span class="pill ${x.kind === 'network_blocked' ? 'red' : x.kind === 'model_call' ? 'blue' : ''}">${esc(x.kind)}</span></td>
        <td>${describe(x)}</td><td class="mono muted">${esc(x.endpoint || '')}</td></tr>`).join('')}</table>` : '<div class="empty">No events.</div>';
  }

  Pages.audit = {
    title: 'Audit Logs',
    async render(el) {
      el.innerHTML = `
        <div class="page-head"><div><h1>Audit Logs and Network Monitor</h1><p>The proof of the sovereign claim: every model and tool call is recorded, and the live sockets of this app and the model server are shown below.</p></div>
          <div class="actions"><button class="btn" id="au-test">${icon('shield')}Test the outbound guard</button></div></div>
        <div class="grid cols-4" id="au-cards"></div>
        <div class="card mt"><h3>${icon('net', 'color:var(--blue)')}Live Network Connections <span id="au-verdict"></span><span class="right small muted" id="au-checked"></span></h3>
          <div class="tbl-scroll" id="au-net" style="max-height:260px"></div>
          <p class="small muted" style="margin:10px 0 0">Shows sockets held by this web server and by Ollama. A listening socket has no remote address. For the strongest proof, switch Wi-Fi off and run any task.</p></div>
        <div class="card mt"><h3>Audit Trail <span class="muted small" id="au-count"></span>
          <span class="right row"><select id="au-kind" style="width:200px">${KINDS.map((k) => `<option value="${k[0]}">${k[1]}</option>`).join('')}</select>
          <button class="btn sm" id="au-refresh">${icon('refresh')}Refresh</button></span></h3>
          <div class="tbl-scroll" id="au-log" style="max-height:480px"></div></div>`;
      loadNetwork(el).catch(() => {});
      loadAudit(el).catch(() => {});
      clearInterval(timer);
      timer = setInterval(() => loadNetwork(el).catch(() => {}), 3000);
      $('#au-kind', el).onchange = () => loadAudit(el);
      $('#au-refresh', el).onclick = () => loadAudit(el);
      $('#au-test', el).onclick = async () => {
        const r = await api('/api/network/selftest', {method: 'POST'});
        toast(r.blocked ? `Blocked as expected: ${r.detail}` : `NOT blocked: ${r.detail}`, !r.blocked);
        await Promise.all([loadNetwork(el), loadAudit(el)]);
      };
    },
    leave() { clearInterval(timer); },
  };
})();
