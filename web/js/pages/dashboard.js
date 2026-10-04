// Dashboard: live counts, quick actions, recent activity and system status.
(function () {
  const QUICK = [
    ['documents', 'upload', 'Upload Document', 'Process and analyse your files', 'background:#eaf1ff;color:#2563eb'],
    ['workbench', 'spark', 'Ask a Question', 'Get help from the local assistant', 'background:#e7f6ec;color:#15803d'],
    ['multimodal', 'image', 'Analyse Image', 'Understand drawings and scans', 'background:#f1e9ff;color:#7c3aed'],
    ['knowledge', 'db', 'Search Knowledge', 'SOPs, manuals and reports', 'background:#fef3c7;color:#b45309'],
    ['audit', 'net', 'Network Monitor', 'Proof of no external calls', 'background:#fee2e2;color:#b91c1c'],
  ];

  const activityText = (r) => {
    if (r.kind === 'task_done') return [r.request || '', r.model || '', r.status === 'failed' ? 'red' : 'green', r.status || 'completed'];
    if (r.kind === 'kb_ingest') return [`Indexed ${r.source} into the knowledge base`, 'nomic-embed-text', 'green', 'indexed'];
    return [`Removed ${r.source} from the knowledge base`, '', 'amber', 'removed'];
  };

  Pages.dashboard = {
    title: 'Dashboard',
    async render(el) {
      const d = await api('/api/dashboard');
      const c = d.cards;
      el.innerHTML = `
        <div class="grid cols-4">
          <div class="card stat"><div class="icon">${icon('checkc')}</div><div><b>${c.tasks}</b><span>Tasks completed</span></div></div>
          <div class="card stat"><div class="icon amber">${icon('db')}</div><div><b>${c.kb_documents}</b><span>Knowledge base documents</span></div></div>
          <div class="card stat"><div class="icon purple">${icon('cpu')}</div><div><b>${c.models_active}</b><span>Local models active</span></div></div>
          <div class="card stat"><div class="icon green">${icon('doc')}</div><div><b>${c.files_generated}</b><span>Files generated</span></div></div>
        </div>
        <h3 class="mt" style="margin-bottom:10px">Quick Actions</h3>
        <div class="quick">${QUICK.map((q) => `<a href="#${q[0]}"><div class="icon" style="${q[4]}">${icon(q[1])}</div><b>${q[2]}</b><span>${q[3]}</span></a>`).join('')}</div>
        <div class="grid mt" style="grid-template-columns: 1.6fr 1fr">
          <div class="card"><h3>Recent Activity <a class="right small" href="#audit">View all</a></h3>
            ${d.activity.length ? `<table class="tbl"><tr><th>Time</th><th>User</th><th>Activity</th><th>Model</th><th>Status</th></tr>
              ${d.activity.map((r) => { const a = activityText(r); return `<tr><td class="muted">${fmtTime(r.ts)}</td><td>${esc(r.user)}</td>
                <td>${esc(a[0].length > 70 ? a[0].slice(0, 70) + '...' : a[0])}</td><td class="muted">${esc(a[1])}</td>
                <td><span class="pill ${a[2]}">${esc(a[3])}</span></td></tr>`; }).join('')}</table>`
              : '<div class="empty">No activity yet. Open the AI Workbench to run your first task.</div>'}
          </div>
          <div class="card"><h3>System Status <span class="right small muted">checked live</span></h3>
            ${d.status.map((s) => `<div class="status-row">${icon(s.ok ? 'checkc' : 'xc', `color:${s.ok ? 'var(--green)' : 'var(--red)'}`)}
              <div class="grow"><b>${esc(s.name)}</b><small>${esc(s.detail)}</small></div>
              <span class="pill ${s.ok ? 'green' : 'red'}">${s.ok ? 'Running' : 'Check'}</span></div>`).join('')}
          </div>
        </div>
        <div class="card mt" style="background:var(--navy);color:#fff;border:none;display:flex;gap:12px;align-items:center">
          ${icon('shield', 'width:26px;height:26px;color:#60a5fa')}
          <div><b>Built for secure and sovereign AI adoption</b><div class="small" style="color:#cbd5e1">All models, documents, embeddings and logs stay on this machine. Open the Audit Logs page for the live proof.</div></div>
        </div>`;
    },
  };
})();
