// Models: the registry, on/off switches, the routing diagram and a live router test.
(function () {
  const TASKS = [['agent', 'Document Processing', 'PDF, DOCX, OCR, multi-step work'], ['vision', 'Visual Understanding', 'Images, diagrams, drawings'],
                 ['code', 'Coding', 'Generation and debugging'], ['chat', 'General Questions', 'Short Q&A']];
  const EXAMPLES = [['Summarise this inspection report and draft an approval note', 'report.pdf'], ['Explain this P&ID drawing', 'drawing.png'],
                    ['Write a Python script to compute pressure drop', ''], ['What is a heat exchanger?', '']];

  function cards(models) {
    return models.map((m) => `
      <div class="card model-card">
        <div class="row"><div class="grow"><h4>${esc(m.label)}</h4><span class="muted small">${esc(m.family)} &middot; ${esc(m.params)} parameters</span></div>
          <label class="switch" title="${m.installed ? 'Enable or disable' : 'Not downloaded'}"><input type="checkbox" data-model="${esc(m.name)}" ${m.enabled ? 'checked' : ''} ${m.installed ? '' : 'disabled'}><span></span></label></div>
        <div style="margin:10px 0 6px">${m.capabilities.map((c) => `<span class="tag">${esc(c)}</span>`).join('')}</div>
        <p class="muted small" style="margin:0 0 10px;min-height:34px">${esc(m.description)}</p>
        <div class="row small"><span class="mono muted grow">${esc(m.name)}</span>
          ${m.installed ? `<span class="muted">${m.size_gb} GB on disk</span>` : ''}
          <span class="pill ${!m.installed ? 'amber' : m.enabled ? 'green' : ''}">${!m.installed ? 'Not downloaded' : m.enabled ? 'Active' : 'Disabled'}</span></div>
      </div>`).join('');
  }

  function pickFor(models, fallbacks, cap) {
    const usable = (c) => models.find((m) => m.capabilities.includes(c) && m.enabled && m.installed);
    let m = usable(cap);
    if (!m) for (const c of (fallbacks[cap] || [])) { m = usable(c); if (m) break; }
    return m;
  }

  function diagram(d, highlight) {
    return `<div class="route-diagram">
      <div class="route-col"><h5>User Task</h5>${TASKS.map((t) => `<div class="route-item ${highlight === t[0] ? 'hl' : ''}"><b>${t[1]}</b><small>${t[2]}</small></div>`).join('')}</div>
      <div class="arrow-big">${icon('arrow', 'width:24px;height:24px')}</div>
      <div class="route-col mid"><h5>Model Router</h5>
        ${['Analyse the task type', 'Check attached file types', 'Match model capabilities', 'Skip disabled or missing models', 'Route to the best local model']
          .map((s) => `<div class="row small" style="margin-bottom:7px">${icon('checkc', 'color:var(--green);width:15px;height:15px')}${s}</div>`).join('')}
        <div class="pill green" style="margin-top:4px">${icon('shield')}Local routing, no external APIs</div></div>
      <div class="arrow-big">${icon('arrow', 'width:24px;height:24px')}</div>
      <div class="route-col"><h5>Best Local Model</h5>${TASKS.map((t) => { const m = pickFor(d.models, d.fallbacks, d.task_capability[t[0]]);
        return `<div class="route-item ${highlight === t[0] ? 'hl' : ''}"><b>${m ? esc(m.label) : 'No model available'}</b><small>needs "${esc(d.task_capability[t[0]])}"</small></div>`; }).join('')}</div>
    </div>`;
  }

  async function loadActivity(el) {
    const r = await api('/api/routing');
    $('#md-activity', el).innerHTML = r.activity.length ? `<table class="tbl"><tr><th>Time</th><th>Request</th><th>Task</th><th>Routed to</th></tr>
      ${r.activity.map((a) => `<tr><td class="muted">${fmtTime(a.ts)}</td><td>${esc((a.request || '').slice(0, 60))}</td><td><span class="pill">${esc(a.task)}</span></td>
        <td><b>${esc(a.model_label || '-')}</b></td></tr>`).join('')}</table>` : '<div class="empty">No routing decisions yet.</div>';
  }

  Pages.models = {
    title: 'Models',
    async render(el) {
      let d = await api('/api/models');
      el.innerHTML = `
        <div class="page-head"><div><h1>Local AI Models</h1><p>Open-weight models served by Ollama on this machine. New models are added by one entry in <span class="mono">workbench/models.yaml</span>.</p></div></div>
        <div class="grid cols-4" id="md-cards">${cards(d.models)}</div>
        <div class="card mt"><h3>Intelligent Model Routing</h3><div id="md-diagram">${diagram(d)}</div></div>
        <div class="grid mt" style="grid-template-columns: minmax(0,1fr) minmax(0,1.2fr)">
          <div class="card"><h3>${icon('route', 'color:var(--blue)')}Test the Router</h3>
            <input type="text" id="md-msg" placeholder="Type a request to see which model it is routed to">
            <div class="row mt"><select id="md-att"><option value="">No attachment</option><option value="drawing.png">With an image attached</option><option value="report.pdf">With a document attached</option></select>
              <button class="btn primary" id="md-test">${icon('route')}Test Router</button></div>
            <div class="chips">${EXAMPLES.map((e, i) => `<button class="chip" data-ex="${i}">${esc(e[0])}</button>`).join('')}</div>
            <div id="md-result" class="mt"></div></div>
          <div class="card"><h3>Recent Routing Activity</h3><div id="md-activity" class="tbl-scroll"></div></div>
        </div>`;
      loadActivity(el).catch(() => {});

      const test = async () => {
        const message = $('#md-msg', el).value.trim();
        if (!message) return;
        const att = $('#md-att', el).value;
        const r = await api('/api/route/test', {json: {message, attachments: att ? [att] : []}});
        $('#md-result', el).innerHTML = `<div class="plan"><b>Decision</b>
          <div class="kv"><span>Task type</span><span>${esc(r.task_label)}</span></div>
          <div class="kv"><span>Capability needed</span><span>${esc(r.capability)}</span></div>
          <div class="kv"><span>Routed to</span><span>${esc(r.model_label || 'no model available')}</span></div>
          <div class="small" style="margin-top:5px">Why: ${esc(r.reason)}${r.fallback ? '. ' + esc(r.fallback) : ''}</div></div>`;
        $('#md-diagram', el).innerHTML = diagram(d, r.task);
        loadActivity(el);
      };
      $('#md-test', el).onclick = test;
      $('#md-msg', el).onkeydown = (e) => { if (e.key === 'Enter') test(); };
      $$('[data-ex]', el).forEach((c) => c.onclick = () => { const ex = EXAMPLES[+c.dataset.ex]; $('#md-msg', el).value = ex[0]; $('#md-att', el).value = ex[1]; test(); });
      $('#md-cards', el).onchange = async (e) => {
        const box = e.target.closest('[data-model]');
        if (!box) return;
        const r = await api('/api/models/toggle', {json: {name: box.dataset.model, enabled: box.checked}});
        d = {...d, models: r.models};
        $('#md-cards', el).innerHTML = cards(d.models);
        $('#md-diagram', el).innerHTML = diagram(d);
        toast(`${box.dataset.model} ${box.checked ? 'enabled' : 'disabled'}. Routing updated.`);
      };
    },
  };
})();
