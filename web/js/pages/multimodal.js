// Multimodal Analysis: pick an image, the vision model and OCR describe it.
(function () {
  let selected = null, busy = false, analysis = '';

  async function loadImages(el) {
    const f = await api('/api/files');
    const imgs = [...f.uploads, ...f.samples].filter((x) => x.is_image);
    $('#mm-list', el).innerHTML = imgs.length ? imgs.map((x) => `
      <div class="pick ${selected && selected.name === x.name ? 'active' : ''}" data-name="${esc(x.name)}" data-area="${x.area}">
        ${icon('image')}<div class="grow"><b>${esc(x.name)}</b><small>${x.size_kb} KB &middot; ${x.area === 'samples' ? 'sample' : 'uploaded'}</small></div>
      </div>`).join('') : '<div class="empty">No images yet.</div>';
    return imgs;
  }

  function show(el) {
    $('#mm-view', el).innerHTML = selected ? `<img src="${fileUrl(selected.area, selected.name)}" alt="">` : '<span class="muted">Select an image.</span>';
    $('#mm-name', el).textContent = selected ? selected.name : '';
    $('#mm-run', el).disabled = !selected;
  }

  async function analyse(el) {
    if (!selected || busy) return;
    busy = true;
    analysis = '';
    const btn = $('#mm-run', el);
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span> Analysing...';
    $('#mm-report', el).disabled = true;
    $('#mm-steps', el).innerHTML = '';
    $('#mm-out', el).innerHTML = '';
    $('#mm-status', el).innerHTML = '<span class="pill blue"><span class="spin"></span> Running locally</span>';
    const steps = {};
    try {
      await stream('/api/vision/analyze', {name: selected.name, question: $('#mm-q', el).value}, (ev) => {
        if (ev.type === 'route') {
          $('#mm-model', el).innerHTML = `<span class="pill blue">${esc(ev.model_label || 'no vision model')}</span>`;
        } else if (ev.type === 'step') {
          let s = steps[ev.id];
          if (!s) { s = steps[ev.id] = document.createElement('div'); $('#mm-steps', el).appendChild(s); }
          s.className = 'step ' + ev.status;
          s.innerHTML = `<span class="st">${ev.status === 'running' ? '<span class="spin"></span>' : icon(ev.status === 'done' ? 'checkc' : 'xc')}</span>
            <div><b>${esc(ev.title)}</b> <span class="muted small">${esc(ev.detail || '')}</span></div>`;
        } else if (ev.type === 'token') {
          analysis += ev.text;
          $('#mm-out', el).innerHTML = md(analysis);
        } else if (ev.type === 'error') {
          $('#mm-out', el).innerHTML = `<p style="color:var(--red)">${esc(ev.message)}</p>`;
        } else if (ev.type === 'done') {
          $('#mm-status', el).innerHTML = ev.status === 'failed' ? '<span class="pill red">Failed</span>'
            : `<span class="pill green">${icon('shield')}Processed locally in ${ev.duration_s} s</span>`;
        }
      });
    } catch (e) { toast(e.message, true); }
    busy = false;
    btn.disabled = false;
    btn.innerHTML = `${icon('eye')}Analyse Image`;
    $('#mm-report', el).disabled = !analysis;
  }

  Pages.multimodal = {
    title: 'Multimodal Analysis',
    async render(el) {
      el.innerHTML = `
        <div class="page-head"><div><h1>Multimodal Analysis</h1><p>Understand engineering drawings, photographs and scanned pages with the local vision model and on-device OCR.</p></div></div>
        <div class="grid" style="grid-template-columns: 270px minmax(0,1.25fr) minmax(0,1fr)">
          <div class="card"><h3>Images <button class="btn sm right" id="mm-up">${icon('upload')}Upload</button><input type="file" id="mm-file" accept="image/*" multiple hidden></h3>
            <div id="mm-list"></div></div>
          <div class="card"><h3>Image Viewer <span class="right small muted" id="mm-name"></span></h3>
            <div class="viewer" id="mm-view"></div>
            <div class="row mt"><input type="text" id="mm-q" placeholder="Optional: ask a specific question about the image">
              <button class="btn primary" id="mm-run" disabled>${icon('eye')}Analyse Image</button></div></div>
          <div class="card"><h3>AI Analysis Results <span class="right" id="mm-status"></span></h3>
            <div class="row small muted" style="margin-bottom:8px">Model: <span id="mm-model">chosen by the router</span></div>
            <div class="steps" id="mm-steps"></div>
            <div class="md" id="mm-out"><span class="muted">Select an image and press Analyse Image. On this CPU a drawing takes one to two minutes.</span></div>
            <button class="btn mt" id="mm-report" disabled>${icon('doc')}Generate Word Report</button></div>
        </div>`;
      // Wire the controls first, then load data: a slow first load must not leave dead buttons.
      let imgs = [];
      loadImages(el).then(async (list) => {
        imgs = list;
        if (!selected && imgs.length) selected = imgs.find((x) => x.name.startsWith('pid')) || imgs[0];
        imgs = await loadImages(el);
        show(el);
      }).catch((e) => toast(e.message, true));
      show(el);

      $('#mm-up', el).onclick = () => $('#mm-file', el).click();
      $('#mm-file', el).onchange = async (e) => {
        if (!e.target.files.length) return;
        try {
          const r = await uploadFiles(e.target.files);
          imgs = await loadImages(el);
          selected = imgs.find((x) => x.name === r.files[0]) || selected;
          imgs = await loadImages(el);
          show(el);
        } catch (err) { toast(err.message, true); }
      };
      $('#mm-list', el).onclick = (e) => {
        const p = e.target.closest('.pick');
        if (!p || busy) return;
        selected = imgs.find((x) => x.name === p.dataset.name && x.area === p.dataset.area);
        $$('.pick', el).forEach((x) => x.classList.toggle('active', x === p));
        show(el);
      };
      $('#mm-run', el).onclick = () => analyse(el);
      $('#mm-report', el).onclick = async () => {
        try {
          const r = await api('/api/vision/report', {json: {name: selected.name, analysis}});
          toast(`Created ${r.file}`);
          location.href = fileUrl('outputs', r.file, 1);
        } catch (err) { toast(err.message, true); }
      };
    },
  };
})();
