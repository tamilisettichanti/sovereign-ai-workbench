// Documents: upload, then run the pipeline Upload -> OCR -> Understanding -> Knowledge Base.
(function () {
  const STAGES = [['upload', 'File Upload', 'upload'], ['ocr', 'OCR / Text Extraction', 'scan'],
                  ['understand', 'AI Understanding', 'spark'], ['kb', 'Knowledge Base', 'db']];
  let selected = null, busy = false;

  async function loadFiles(el) {
    const f = await api('/api/files');
    const all = [...f.uploads, ...f.samples];
    $('#doc-list', el).innerHTML = all.length ? all.map((x) => `
      <div class="pick ${selected && selected.name === x.name ? 'active' : ''}" data-name="${esc(x.name)}" data-area="${x.area}">
        ${icon(extIcon(x.name))}<div class="grow"><b>${esc(x.name)}</b><small>${x.ext.toUpperCase()} &middot; ${x.size_kb} KB &middot; ${x.area === 'samples' ? 'sample' : 'uploaded'}</small></div>
      </div>`).join('') : '<div class="empty">No files yet. Upload one above.</div>';
    return all;
  }

  function showPreview(el) {
    const v = $('#doc-preview', el);
    if (!selected) { v.innerHTML = '<span class="muted">Select a file to preview it.</span>'; return; }
    const url = fileUrl(selected.area, selected.name);
    if (selected.is_image) v.innerHTML = `<img src="${url}" alt="">`;
    else if (selected.ext === 'pdf') v.innerHTML = `<iframe src="${url}" style="width:100%;height:420px;border:0"></iframe>`;
    else v.innerHTML = `<div class="muted">${icon('doc', 'width:34px;height:34px')}<br>${esc(selected.name)}</div>`;
  }

  function resetPipeline(el) {
    $('#doc-pipe', el).innerHTML = STAGES.map((s) => `<div class="pstage" data-stage="${s[0]}"><div class="circle">${icon(s[2])}</div><b>${s[1]}</b><span>waiting</span></div>`).join('');
    $('#doc-text', el).textContent = '';
    $('#doc-summary', el).innerHTML = '<span class="muted">The summary appears here after processing.</span>';
  }

  async function process(el) {
    if (!selected || busy) return;
    busy = true;
    const btn = $('#doc-run', el);
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span> Processing...';
    resetPipeline(el);
    let summary = '';
    try {
      await stream('/api/documents/process', {name: selected.name, save_kb: $('#doc-kb', el).checked}, (ev) => {
        if (ev.type === 'stage') {
          const s = $(`[data-stage="${ev.name}"]`, el);
          s.className = 'pstage ' + ev.status;
          $('.circle', s).innerHTML = ev.status === 'running' ? '<span class="spin"></span>' : icon(ev.status === 'done' ? 'check' : STAGES.find((x) => x[0] === ev.name)[2]);
          $('span', s).textContent = ev.detail || ev.status;
        } else if (ev.type === 'text') {
          $('#doc-text', el).textContent = ev.text || '(no text found)';
        } else if (ev.type === 'token') {
          summary += ev.text;
          $('#doc-summary', el).innerHTML = md(summary);
        } else if (ev.type === 'error') {
          toast(ev.message, true);
        }
      });
    } catch (e) { toast(e.message, true); }
    busy = false;
    btn.disabled = false;
    btn.innerHTML = `${icon('spark')}Start Analysis`;
  }

  Pages.documents = {
    title: 'Documents',
    async render(el) {
      el.innerHTML = `
        <div class="page-head"><div><h1>Document Processing</h1><p>Extract and understand documents with on-device OCR and local models. Scanned pages are read by Tesseract on this machine.</p></div></div>
        <div class="grid" style="grid-template-columns: 340px minmax(0,1fr)">
          <div>
            <div class="drop"><div>${icon('upload', 'width:26px;height:26px;color:var(--blue)')}</div>
              <p style="margin:8px 0"><b>Upload documents</b><br><span class="muted small">PDF, scanned images, Word or text files</span></p>
              <button class="btn primary" id="doc-choose">Choose Files</button><input type="file" id="doc-file" multiple hidden></div>
            <div class="card mt"><h3>Files</h3><div id="doc-list"></div></div>
          </div>
          <div>
            <div class="card"><h3>Processing Pipeline
              <span class="right row"><label class="check small"><input type="checkbox" id="doc-kb"> Add to knowledge base</label>
              <button class="btn primary" id="doc-run" disabled>${icon('spark')}Start Analysis</button></span></h3>
              <div class="pipeline" id="doc-pipe"></div></div>
            <div class="grid cols-2 mt">
              <div class="card"><h3>Preview</h3><div class="viewer" id="doc-preview"></div></div>
              <div class="card"><div class="tabs"><button class="active" data-tab="summary">AI Summary</button><button data-tab="text">Extracted Text</button></div>
                <div id="doc-summary" class="md"></div><pre class="plain" id="doc-text" hidden></pre></div>
            </div>
          </div>
        </div>`;
      resetPipeline(el);
      showPreview(el);
      // Wire the controls first, then load data: a slow first load must not leave dead buttons.
      let files = [];
      loadFiles(el).then((f) => { files = f; }).catch((e) => toast(e.message, true));

      $('#doc-choose', el).onclick = () => $('#doc-file', el).click();
      $('#doc-file', el).onchange = async (e) => {
        if (!e.target.files.length) return;
        try {
          const r = await uploadFiles(e.target.files);
          files = await loadFiles(el);
          selected = files.find((x) => x.name === r.files[0]) || null;
          files = await loadFiles(el);
          showPreview(el);
          $('#doc-run', el).disabled = !selected;
          toast(`${r.files.length} file(s) uploaded`);
        } catch (err) { toast(err.message, true); }
      };
      $('#doc-list', el).onclick = (e) => {
        const p = e.target.closest('.pick');
        if (!p || busy) return;
        selected = files.find((x) => x.name === p.dataset.name && x.area === p.dataset.area);
        $$('.pick', el).forEach((x) => x.classList.toggle('active', x === p));
        showPreview(el);
        resetPipeline(el);
        $('#doc-run', el).disabled = false;
      };
      $('#doc-run', el).disabled = !selected;
      $('#doc-run', el).onclick = () => process(el);
      $$('.tabs button', el).forEach((b) => b.onclick = () => {
        $$('.tabs button', el).forEach((x) => x.classList.toggle('active', x === b));
        $('#doc-summary', el).hidden = b.dataset.tab !== 'summary';
        $('#doc-text', el).hidden = b.dataset.tab !== 'text';
      });
    },
  };
})();
