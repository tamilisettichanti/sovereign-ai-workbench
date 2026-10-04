// Knowledge Base (RAG): search, grounded answers with sources, and document management.
(function () {
  const FLOW = [['1. Ingest', 'Read the file, OCR if scanned'], ['2. Chunk', 'Split into overlapping passages'],
                ['3. Embed', 'nomic-embed-text, run locally'], ['4. Store', 'ChromaDB folder on this disk'],
                ['5. Retrieve', 'Closest passages to the question'], ['6. Ground', 'Answer only from those passages']];
  let busy = false;

  async function loadDocs(el) {
    const d = await api('/api/kb/documents');
    $('#kb-count', el).textContent = `${d.stats.documents} documents, ${d.stats.chunks} passages`;
    $('#kb-docs', el).innerHTML = d.documents.length ? `<table class="tbl"><tr><th>Document</th><th>Category</th><th>Passages</th><th>Size</th><th>Indexed</th><th></th></tr>
      ${d.documents.map((x) => `<tr><td>${icon(extIcon(x.source), 'vertical-align:-4px;color:var(--blue)')} <a href="${fileUrl('kb', x.source)}" target="_blank">${esc(x.source)}</a></td>
        <td><span class="tag">${esc(x.category)}</span></td><td>${x.chunks}</td><td class="muted">${x.size_kb} KB</td><td class="muted">${fmtDateTime(x.added)}</td>
        <td><button class="btn sm danger" data-del="${esc(x.source)}" title="Remove">${icon('trash')}</button></td></tr>`).join('')}</table>`
      : '<div class="empty">The knowledge base is empty. Add documents to begin.</div>';
  }

  const hitHtml = (h) => `<div class="hit"><div class="top">${icon('doc', 'color:var(--blue)')}<b class="grow">${esc(h.source)}</b>
    <span class="tag">${esc(h.category)}</span><span class="pill green">${h.match}% match</span></div><p>${esc(h.text)}</p></div>`;

  async function search(el) {
    const q = $('#kb-q', el).value.trim();
    if (!q) return;
    $('#kb-results', el).innerHTML = '<div class="empty"><span class="spin"></span> Searching...</div>';
    try {
      const r = await api('/api/kb/search?q=' + encodeURIComponent(q));
      $('#kb-results', el).innerHTML = r.hits.length ? r.hits.map(hitHtml).join('') : '<div class="empty">No matching passages.</div>';
      $('#kb-rcount', el).textContent = `(${r.hits.length})`;
    } catch (e) { toast(e.message, true); }
  }

  async function ask(el) {
    const q = $('#kb-q', el).value.trim();
    if (!q || busy) return;
    busy = true;
    $('#kb-ask', el).disabled = true;
    search(el);
    let answer = '';
    $('#kb-answer', el).innerHTML = '<span class="spin"></span> Retrieving passages and writing a grounded answer...';
    $('#kb-sources', el).innerHTML = '';
    try {
      await stream('/api/kb/ask', {query: q}, (ev) => {
        if (ev.sources) {
          $('#kb-sources', el).innerHTML = ev.sources.length ? '<h4 style="font-size:12.5px;margin:12px 0 7px">Retrieved Sources</h4>' +
            ev.sources.map((s, i) => `<div class="file-row"><span class="pill">${i + 1}</span><span class="grow">${esc(s.source)}</span><span class="pill green">${s.match}%</span></div>`).join('') : '';
        } else if (ev.model) {
          $('#kb-model', el).textContent = ev.model;
        } else if (ev.token) {
          answer += ev.token;
          $('#kb-answer', el).innerHTML = md(answer);
        } else if (ev.type === 'error') {
          $('#kb-answer', el).innerHTML = `<p style="color:var(--red)">${esc(ev.message)}</p>`;
        }
      });
    } catch (e) { toast(e.message, true); }
    busy = false;
    $('#kb-ask', el).disabled = false;
  }

  Pages.knowledge = {
    title: 'Knowledge Base',
    async render(el) {
      el.innerHTML = `
        <div class="page-head"><div><h1>Knowledge Base</h1><p>Search and ask questions over your organisation's SOPs, manuals and reports. Retrieval and answers run entirely on this machine.</p></div>
          <div class="actions"><button class="btn" id="kb-reindex">${icon('refresh')}Re-index All</button>
          <button class="btn primary" id="kb-add">${icon('plus')}Add Documents</button><input type="file" id="kb-file" multiple hidden></div></div>
        <div class="card"><h3>How retrieval works (RAG pipeline)</h3>
          <div class="rag-flow">${FLOW.map((f, i) => `${i ? `<span class="arrow">${icon('arrow')}</span>` : ''}<div><b>${f[0]}</b>${f[1]}</div>`).join('')}</div></div>
        <div class="card mt"><div class="row">
          <input type="text" id="kb-q" placeholder="e.g. tube plugging limit for heat exchangers" value="">
          <button class="btn" id="kb-search">${icon('search')}Search</button>
          <button class="btn primary" id="kb-ask">${icon('spark')}Ask AI from Knowledge Base</button></div>
          <div class="chips">${['What is the tube plugging limit for a heat exchanger?', 'Who approves a repair costing Rs 4.8 lakh?', 'Pump vibration limits and actions', 'Lockout-tagout steps before maintenance']
            .map((q) => `<button class="chip" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div></div>
        <div class="grid mt" style="grid-template-columns: minmax(0,1.2fr) minmax(0,1fr)">
          <div class="card"><h3>Search Results <span id="kb-rcount" class="muted"></span></h3>
            <div id="kb-results"><div class="empty">Results show the passages closest in meaning to your query, with a match score.</div></div></div>
          <div class="card"><h3>${icon('spark', 'color:var(--blue)')}AI Assistant (Knowledge Base) <span class="right small muted" id="kb-model"></span></h3>
            <div id="kb-answer" class="md"><span class="muted">Click "Ask AI from Knowledge Base" for an answer built only from your indexed documents, with its sources.</span></div>
            <div id="kb-sources"></div>
            <div class="pill green mt">${icon('shield')}Searches and answers use local models only</div></div>
        </div>
        <div class="card mt"><h3>Indexed Documents <span class="right small muted" id="kb-count"></span></h3><div id="kb-docs"></div></div>`;
      // Wire the controls first, then load data: a slow first load must not leave dead buttons.
      loadDocs(el).catch((e) => toast(e.message, true));

      $('#kb-search', el).onclick = () => search(el);
      $('#kb-ask', el).onclick = () => ask(el);
      $('#kb-q', el).onkeydown = (e) => { if (e.key === 'Enter') search(el); };
      $$('.chip', el).forEach((c) => c.onclick = () => { $('#kb-q', el).value = c.dataset.q; search(el); });
      $('#kb-add', el).onclick = () => $('#kb-file', el).click();
      $('#kb-file', el).onchange = async (e) => {
        if (!e.target.files.length) return;
        toast('Indexing documents...');
        try {
          const r = await uploadFiles(e.target.files, '/api/kb/upload');
          const bad = r.results.filter((x) => x.error);
          toast(bad.length ? `Could not index: ${bad.map((x) => x.source).join(', ')}` : `${r.results.length} document(s) indexed`, bad.length > 0);
          await loadDocs(el);
        } catch (err) { toast(err.message, true); }
        e.target.value = '';
      };
      $('#kb-reindex', el).onclick = async () => {
        toast('Re-indexing the knowledge base...');
        try { const r = await api('/api/kb/reindex', {method: 'POST'}); toast(`${r.results.length} document(s) re-indexed`); await loadDocs(el); }
        catch (err) { toast(err.message, true); }
      };
      $('#kb-docs', el).onclick = async (e) => {
        const b = e.target.closest('[data-del]');
        if (!b || !confirm(`Remove "${b.dataset.del}" from the knowledge base?`)) return;
        try { await api('/api/kb/documents/' + encodeURIComponent(b.dataset.del), {method: 'DELETE'}); await loadDocs(el); }
        catch (err) { toast(err.message, true); }
      };
    },
  };
})();
