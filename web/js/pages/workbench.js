// AI Workbench: chat with live routing, plan, tool steps, answer and generated files.
(function () {
  const TOOLS = [
    ['read_document', 'scan', 'OCR'],
    ['search_knowledge_base', 'db', 'Knowledge Base'],
    ['describe_image', 'eye', 'Vision Model'],
    ['run_python', 'code', 'Code Sandbox'],
    ['create_word', 'doc', 'Word'],
    ['create_excel', 'table', 'Excel'],
    ['create_presentation', 'slides', 'PowerPoint'],
  ];
  const SUGGESTIONS = [
    {label: 'Approval note from scanned report', files: ['inspection_report_E204.png'],
     text: 'Read the scanned inspection report, pull out the key findings, check them against our SOP limits, and draft an approval note as a Word file.'},
    {label: 'Explain this P&ID', files: ['pid_crude_preheat.png'],
     text: 'Explain what this diagram shows and list the equipment tags.'},
    {label: 'Write and verify code', files: [],
     text: 'Write a Python function remaining_life(nominal, measured, minimum, years_in_service) for a vessel wall. Corrosion rate = (nominal - measured) / years_in_service. Remaining life = (measured - minimum) / corrosion rate. Return both. Test it with nominal 12.0, measured 9.2, minimum 8.5 and 10 years: assert the corrosion rate is 0.28 mm/year and the remaining life is 2.5 years (use round to 2 decimals), then print both.'},
    {label: 'Ask about a procedure', files: [],
     text: 'What are the vibration limits for centrifugal pumps as per our SOP, and what action is needed above the alert level?'},
    {label: 'Findings to Excel', files: ['inspection_report_E204.pdf'],
     text: 'Read the inspection report and create an Excel sheet listing each finding, the measured value, the SOP limit and whether it is acceptable.'},
    {label: 'Quick question', files: [], text: 'In two sentences, what is a shell and tube heat exchanger?'},
  ];

  const state = {root: null, attachments: [], busy: false};

  const build = () => {
    const root = document.createElement('div');
    root.className = 'wb';
    root.innerHTML = `
      <div class="card chat-card">
        <div class="chat-head">
          <div><h1>AI Workbench</h1><span class="muted small">Your on-premise assistant for confidential industrial knowledge work.</span></div>
          <div class="grow"></div>
          <button class="btn primary" data-act="new">${icon('plus')}New Chat</button>
        </div>
        <div class="chat-body" data-el="body"></div>
        <div class="composer">
          <div class="line">
            <button class="btn" data-act="attach" title="Attach files">${icon('clip')}</button>
            <input type="file" data-el="file" multiple hidden>
            <textarea data-el="input" placeholder="Type your message here. Press Enter to send."></textarea>
            <button class="btn primary" data-act="send">${icon('send')}Send</button>
          </div>
          <div class="chips" data-el="chips"></div>
        </div>
      </div>
      <div class="side-col">
        <div class="card"><h3>Current Task <span class="right" data-el="status"><span class="pill">Idle</span></span></h3>
          <div data-el="task" class="muted small">No task yet. Send a message or pick a suggestion.</div></div>
        <div class="card"><h3>Attached Files</h3>
          <div data-el="atts"></div>
          <select data-el="pick" class="small"></select></div>
        <div class="card"><h3>Output</h3><div data-el="outputs" class="muted small">Generated files appear here.</div></div>
        <div class="card"><h3>Tools in Use</h3><div class="tool-grid" data-el="tools"></div></div>
      </div>`;
    const el = (n) => root.querySelector(`[data-el="${n}"]`);
    state.el = el;

    el('chips').innerHTML = SUGGESTIONS.map((s, i) => `<button class="chip" data-s="${i}">${esc(s.label)}</button>`).join('');
    el('tools').innerHTML = TOOLS.map((t) => `<div class="tool" data-tool="${t[0]}">${icon(t[1])}${t[2]}</div>`).join('');
    welcome();

    root.addEventListener('click', (e) => {
      const chip = e.target.closest('.chip');
      if (chip) {
        const s = SUGGESTIONS[+chip.dataset.s];
        el('input').value = s.text;
        state.attachments = [...s.files];
        renderAtts();
        el('input').focus();
        return;
      }
      const rm = e.target.closest('[data-rm]');
      if (rm) { state.attachments = state.attachments.filter((a) => a !== rm.dataset.rm); renderAtts(); return; }
      const act = e.target.closest('[data-act]');
      if (!act) return;
      if (act.dataset.act === 'send') send();
      if (act.dataset.act === 'attach') el('file').click();
      if (act.dataset.act === 'new' && !state.busy) { welcome(); state.attachments = []; renderAtts(); resetSide(); }
    });
    el('input').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
    el('file').addEventListener('change', async (e) => {
      if (!e.target.files.length) return;
      try {
        const r = await uploadFiles(e.target.files);
        r.files.forEach((f) => { if (!state.attachments.includes(f)) state.attachments.push(f); });
        renderAtts(); loadPicker();
      } catch (err) { toast(err.message, true); }
      e.target.value = '';
    });
    el('pick').addEventListener('change', (e) => {
      const v = e.target.value;
      if (v && !state.attachments.includes(v)) { state.attachments.push(v); renderAtts(); }
      e.target.value = '';
    });
    renderAtts();
    return root;
  };

  function welcome() {
    state.el('body').innerHTML = `<div class="empty">${icon('spark', 'width:30px;height:30px;color:var(--blue)')}
      <p><b>Ask a question, attach a document or image, or pick a suggestion below.</b></p>
      <p class="small">The router picks a local model for each request. Everything runs on this machine.</p></div>`;
  }

  function resetSide() {
    state.el('status').innerHTML = '<span class="pill">Idle</span>';
    state.el('task').innerHTML = 'No task yet. Send a message or pick a suggestion.';
    state.el('task').className = 'muted small';
    state.el('outputs').innerHTML = 'Generated files appear here.';
    state.el('outputs').className = 'muted small';
    $$('.tool', state.root).forEach((t) => t.classList.remove('on'));
  }

  function renderAtts() {
    state.el('atts').innerHTML = state.attachments.length
      ? state.attachments.map((a) => `<div class="file-row">${icon(extIcon(a))}<span class="grow" style="overflow:hidden;text-overflow:ellipsis">${esc(a)}</span><button class="x" data-rm="${esc(a)}">${icon('x')}</button></div>`).join('')
      : '<div class="muted small" style="margin-bottom:8px">No files attached.</div>';
  }

  async function loadPicker() {
    try {
      const f = await api('/api/files');
      const opts = (label, list) => list.length ? `<optgroup label="${label}">${list.map((x) => `<option>${esc(x.name)}</option>`).join('')}</optgroup>` : '';
      state.el('pick').innerHTML = '<option value="">+ Attach a sample or uploaded file</option>' + opts('Samples', f.samples) + opts('Uploaded', f.uploads);
    } catch (e) { /* the picker is optional */ }
  }

  const STEP_ICON = {running: '<span class="spin"></span>', done: icon('checkc'), failed: icon('xc')};

  async function send() {
    const input = state.el('input');
    const text = input.value.trim();
    if (!text || state.busy) return;
    state.busy = true;
    const atts = [...state.attachments];
    input.value = '';
    const body = state.el('body');
    if (body.querySelector('.empty')) body.innerHTML = '';

    const user = document.createElement('div');
    user.className = 'msg-user';
    user.innerHTML = esc(text) + (atts.length ? `<span class="att">${icon('clip', 'width:13px;height:13px;vertical-align:-2px')} ${esc(atts.join(', '))}</span>` : '');
    body.appendChild(user);

    const ai = document.createElement('div');
    ai.className = 'msg-ai';
    ai.innerHTML = `<div class="route-line"><span class="spin"></span> Choosing a model...</div>
      <div class="plan" hidden></div><div class="steps"></div><div class="answer md"></div><div class="files"></div><div class="meta-line"></div>`;
    body.appendChild(ai);
    const part = (c) => ai.querySelector('.' + c);
    const scroll = () => { body.scrollTop = body.scrollHeight; };
    scroll();

    resetSide();
    state.el('status').innerHTML = '<span class="pill blue"><span class="spin"></span> In Progress</span>';
    const started = new Date();
    let answer = '', files = [];
    const steps = {};

    const onEvent = (ev) => {
      if (ev.type === 'route') {
        part('route-line').innerHTML = `${icon('route')}<span>Routed to</span><span class="pill blue">${esc(ev.model_label || 'no model')}</span>
          <span class="pill">${esc(ev.task_label)}</span><span>${esc(ev.reason)}${ev.fallback ? ' (' + esc(ev.fallback) + ')' : ''}</span>`;
        state.el('task').className = '';
        state.el('task').innerHTML = `<div style="margin-bottom:8px">${esc(text.length > 150 ? text.slice(0, 150) + '...' : text)}</div>
          <div class="kv"><span>Model</span><span>${esc(ev.model_label || '-')}</span></div>
          <div class="kv"><span>Type</span><span>${esc(ev.task_label)}</span></div>
          <div class="kv"><span>Started</span><span>${started.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}</span></div>
          <div class="kv"><span>Duration</span><span data-el="dur">running</span></div>`;
      } else if (ev.type === 'plan' && ev.steps.length) {
        const p = part('plan');
        p.hidden = false;
        p.innerHTML = `<b>Plan</b><ol>${ev.steps.map((s) => `<li>${esc(s)}</li>`).join('')}</ol>`;
      } else if (ev.type === 'step') {
        let s = steps[ev.id];
        if (!s) { s = steps[ev.id] = document.createElement('div'); part('steps').appendChild(s); }
        s.className = 'step ' + ev.status;
        const detail = ev.detail && ev.detail.length > 60
          ? `<details><summary>Show result</summary><pre>${esc(ev.detail)}</pre></details>`
          : (ev.detail ? ` <span class="muted small">${esc(ev.detail)}</span>` : '');
        s.innerHTML = `<span class="st">${STEP_ICON[ev.status] || ''}</span><div class="grow"><b>${esc(ev.title)}</b>${detail}</div>`;
        if (ev.tool) { const t = state.root.querySelector(`[data-tool="${ev.tool}"]`); if (t) t.classList.add('on'); }
      } else if (ev.type === 'token') {
        answer += ev.text;
        part('answer').innerHTML = md(answer);
      } else if (ev.type === 'answer_reset') {
        answer = '';
        part('answer').innerHTML = '';
      } else if (ev.type === 'file') {
        files.push(ev.name);
        part('files').innerHTML = files.map((f) => `<a class="file-chip" href="${fileUrl('outputs', f, 1)}">${icon(extIcon(f))}${esc(f)}${icon('download')}</a>`).join('');
        state.el('outputs').className = '';
        state.el('outputs').innerHTML = files.map((f) => `<a class="file-row" href="${fileUrl('outputs', f, 1)}">${icon(extIcon(f))}<span class="grow">${esc(f)}</span>${icon('download')}</a>`).join('');
      } else if (ev.type === 'error') {
        part('answer').innerHTML += `<p style="color:var(--red)"><b>Error:</b> ${esc(ev.message)}</p>`;
      } else if (ev.type === 'done') {
        const ok = ev.status !== 'failed';
        part('meta-line').textContent = `Completed in ${ev.duration_s} s, fully on this machine.`;
        state.el('status').innerHTML = ok ? '<span class="pill green">Completed</span>' : '<span class="pill red">Failed</span>';
        const d = state.root.querySelector('[data-el="dur"]');
        if (d) d.textContent = ev.duration_s + ' s';
      }
      scroll();
    };

    try {
      await stream('/api/chat', {message: text, attachments: atts}, onEvent);
    } catch (e) {
      part('answer').innerHTML += `<p style="color:var(--red)"><b>Error:</b> ${esc(e.message)}</p>`;
      state.el('status').innerHTML = '<span class="pill red">Failed</span>';
    }
    if (part('route-line').querySelector('.spin')) part('route-line').textContent = '';
    state.busy = false;
    state.attachments = [];
    renderAtts();
  }

  Pages.workbench = {
    title: 'AI Workbench',
    render(el) {
      if (!state.root) state.root = build();
      el.appendChild(state.root);
      loadPicker();
      const body = state.el('body');
      body.scrollTop = body.scrollHeight;
    },
  };
})();
