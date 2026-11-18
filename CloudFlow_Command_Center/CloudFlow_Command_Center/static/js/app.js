/* CloudFlow front-end: tiny hash-router single page app (no build step). */
const view = document.getElementById("view");
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

let csrfToken = null;
async function api(path, opts = {}) {
  opts.headers = { ...(opts.headers || {}) };
  if (opts.method && opts.method !== "GET" && csrfToken) opts.headers["X-CSRF-Token"] = csrfToken;
  const res = await fetch("/api" + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), 3000);
}

const badge = (s) => `<span class="badge ${s}">${cap(s)}</span>`;
const jobRow = (j) => `
  <a class="job" href="#/jobs/${j.id}">
    <div class="main"><div class="name">${esc(j.name)}</div><div class="id">#${j.id}</div></div>
    ${badge(j.status)}<span class="chev">›</span>
  </a>`;

function fmtTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}
function fmtClock(iso) {
  return new Date(iso).toLocaleTimeString([], { hour12: false });
}
function fmtDur(s) {
  if (s == null) return "—";
  return s < 60 ? `${Math.round(s)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

/* ---------------------------------------------------------------- pages */
const pages = {};

pages.dashboard = {
  async render() {
    const [s, workers, stats] = await Promise.all([api("/summary"), api("/workers"), api("/stats")]);
    const workerTiles = workers.map((w, i) => `
      <div class="worker-tile">
        <div class="worker-symbol">${["✣","☁","▦","◈","⌘","✧"][i % 6]}</div>
        <strong>${esc(w.name)}</strong>
        <small>${w.cpu_total} CPU · ${w.ram_total} GB RAM · ${w.gpu_total} GPU</small>
        <div class="worker-state ${w.status === "busy" ? "busy" : ""}"><i></i>${w.status === "busy" ? `Busy · ${w.running_jobs} running` : "Ready · Idle"}</div>
      </div>`).join("");
    const recent = s.recent.length ? `<div class="mission-list">${s.recent.map(j => `
      <a class="mission-row" href="#/jobs/${j.id}">
        <span class="mission-name">${esc(j.name)}<small>Job #${j.id} · ${j.progress || 0}% progress</small></span>
        ${badge(j.status)}<span class="chev">›</span>
      </a>`).join("")}</div>` : `<div class="mission-empty"><div class="empty-symbol">⚑</div><strong>No active mission</strong><span>Start a new job to monitor its progress here.</span></div>`;
    view.innerHTML = `
      <section class="command-banner">
        <div class="command-mark">✦</div>
        <div class="command-copy"><h1>CloudFlow Intelligence Command Center</h1><p>JOB ORCHESTRATION PLATFORM&nbsp; • &nbsp;RESOURCE INTELLIGENCE&nbsp; • &nbsp;SIMULATED COMPUTE OPERATIONS</p></div>
        <div class="command-actions"><span class="live-pill">● LOCAL SYSTEM</span><a class="primary-action" href="#/new">＋ New Job</a></div>
      </section>
      <div class="system-strip">
        <span class="system-title">SYSTEM HEALTH</span>
        <span class="system-item"><i></i> Scheduler <em>Ready</em></span>
        <span class="system-item"><i></i> Flask API <em>Connected</em></span>
        <span class="system-item"><i></i> SQLite Database <em>Ready</em></span>
        <span class="system-item"><i></i> Resource Monitor <em>Active</em></span>
        <span class="system-item"><i></i> Intelligence Lab <em>Local rules</em></span>
      </div>
      <div class="metrics-grid">
        <div class="metric-card"><div class="metric-icon">▦</div><div><div class="metric-value">${s.total}</div><div class="metric-label">Total Jobs</div><div class="metric-sub">${s.completed} completed</div></div></div>
        <div class="metric-card"><div class="metric-icon green">◉</div><div><div class="metric-value">${s.running}</div><div class="metric-label">Running Jobs</div><div class="metric-sub">${s.pending} waiting in queue</div></div></div>
        <div class="metric-card"><div class="metric-icon cyan">◎</div><div><div class="metric-value">${stats.success_rate == null ? "—" : stats.success_rate + "%"}</div><div class="metric-label">Success Rate</div><div class="metric-sub">Completed vs failed jobs</div></div></div>
        <div class="metric-card"><div class="metric-icon amber">⌘</div><div><div class="metric-value">${workers.length}</div><div class="metric-label">Compute Workers</div><div class="metric-sub">${workers.filter(w => w.status === "busy").length} currently busy</div></div></div>
      </div>
      <div class="dashboard-grid">
        <section class="panel">
          <div class="panel-head"><div class="panel-title"><span class="p-icon">⚑</span> Active Missions</div><a href="#/jobs">View all jobs →</a></div>
          <div class="mission-content">${recent}<a class="launch-btn" href="#/new">▶&nbsp; Launch New Job</a></div>
        </section>
        <section class="panel">
          <div class="panel-head"><div class="panel-title"><span class="p-icon">✣</span> Worker Fleet</div><a href="#/workers">${workers.length} Nodes →</a></div>
          <div class="worker-grid">${workerTiles || '<div class="empty">No workers configured.</div>'}</div>
        </section>
      </div>
      <section class="module-section">
        <div class="section-head"><h2>Intelligence Modules</h2><a href="#/lab">Open AI Command Center →</a></div>
        <div class="module-grid">
          <a class="module-card" href="#/lab"><span class="module-icon">✧</span><span><strong>AI Job Optimizer</strong><small>Resource recommendations</small></span></a>
          <a class="module-card" href="#/lab"><span class="module-icon">◉</span><span><strong>Failure Prediction</strong><small>Risk analysis</small></span></a>
          <a class="module-card" href="#/lab"><span class="module-icon">⌘</span><span><strong>Workflow Studio</strong><small>Multi-step pipelines</small></span></a>
          <a class="module-card" href="#/lab"><span class="module-icon">♧</span><span><strong>Carbon Intelligence</strong><small>Energy estimates</small></span></a>
        </div>
      </section>`;
  },
};

pages.jobs = {
  state: { status: "", q: "" },
  async render(params) {
    if (params.has("status")) {
      this.state.status = params.get("status");
      history.replaceState(null, "", "#/jobs"); // consume the one-shot filter so chips stay in control
    }
    if (params.has("q")) this.state.q = params.get("q");
    const st = this.state;
    const result = await api(`/jobs?status=${encodeURIComponent(st.status)}&q=${encodeURIComponent(st.q)}&limit=100`);
    const jobs = result.items || [];
    const filters = ["", "running", "pending", "completed", "failed", "cancelled"];
    // keep the search box focused across auto-refresh
    const hadFocus = document.activeElement && document.activeElement.id === "q";
    view.innerHTML = `
      <div class="section-head" style="margin-top:0"><h1 style="margin:0">Jobs</h1><a href="#/new">+ New job</a></div>
      <div class="toolbar">
        <input id="q" type="search" placeholder="Search by name or #id" value="${esc(st.q)}">
        <div class="chips">${filters.map((f) => `<span class="chip ${st.status === f ? "active" : ""}" data-f="${f}">${f ? cap(f) : "All"}</span>`).join("")}</div>
      </div>
      <div class="list">${jobs.length ? jobs.map(jobRow).join("") : '<div class="card empty">No jobs match.</div>'}</div>`;
    const q = $("#q");
    if (hadFocus) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
    q.addEventListener("input", () => { st.q = q.value; clearTimeout(this._d); this._d = setTimeout(() => route(), 250); });
    view.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => { st.status = c.dataset.f; route(); }));
  },
};

pages.detail = {
  async render(_p, id) {
    const j = await api(`/jobs/${id}`);
    const active = j.status === "pending" || j.status === "running";
    const logs = j.logs.map((l) => `<span class="t">[${fmtClock(l.ts)}]</span> ${/error/i.test(l.line) ? `<span class="err">${esc(l.line)}</span>` : esc(l.line)}`).join("\n");
    view.innerHTML = `
      <a class="back" href="#/jobs">‹ All jobs</a>
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
          <div><h2>${esc(j.name)}</h2><div class="muted">#${j.id} · ${esc(j.type)}</div></div>${badge(j.status)}
        </div>
        <div style="margin-top:16px">
          <div class="row" style="display:flex;justify-content:space-between;font-size:14px;margin-bottom:6px"><span class="muted">Progress</span><strong>${j.progress}%</strong></div>
          <div class="bar ${j.status === "running" ? "green" : ""}"><i style="width:${j.progress}%"></i></div>
        </div>
        <dl class="kv">
          <div><dt>Worker</dt><dd>${esc(j.worker || "Not assigned")}</dd></div>
          <div><dt>Priority</dt><dd>${cap(j.priority)}</dd></div>
          <div><dt>CPU cores</dt><dd>${j.cpu}</dd></div>
          <div><dt>RAM</dt><dd>${j.ram} GB</dd></div>
          <div><dt>GPUs</dt><dd>${j.gpu}</dd></div>
          <div><dt>Submitted</dt><dd>${fmtTime(j.created_at)}</dd></div>
          <div><dt>Started</dt><dd>${fmtTime(j.started_at)}</dd></div>
          <div><dt>Finished</dt><dd>${fmtTime(j.finished_at)}</dd></div>
          <div><dt>Automatic retries</dt><dd>${j.auto_retry ? `On · ${j.retry_count}/${j.max_retries} used` : "Off"}</dd></div>
        </dl>
        ${j.command ? `<div style="margin-top:14px"><div class="muted" style="font-size:13px">Command</div><code>${esc(j.command)}</code></div>` : ""}
      </div>
      <div class="section-head"><h2>Execution log</h2></div>
      <pre class="logs">${logs || "No log output yet."}</pre>
      ${active ? '<div style="margin-top:16px"><button class="btn secondary" id="cancel">Cancel job</button></div>' : '<div style="margin-top:16px"><button class="btn" id="rerun">Re-run job</button></div>'}`;
    const rerun = $("#rerun");
    if (rerun) rerun.addEventListener("click", async () => {
      rerun.disabled = true;
      try { const copy = await api(`/jobs/${id}/retry`, { method: "POST" }); toast(`Re-run submitted as #${copy.id}`); location.hash = `#/jobs/${copy.id}`; }
      catch (e) { toast(e.message); rerun.disabled = false; }
    });
    const btn = $("#cancel");
    if (btn) btn.addEventListener("click", async () => {
      if (!confirm("Cancel this job?")) return;
      try { await api(`/jobs/${id}/cancel`, { method: "POST" }); toast("Job cancelled"); route(); }
      catch (e) { toast(e.message); }
    });
  },
};

pages.new = {
  manual: true, // no auto-refresh while typing
  async render() {
    view.innerHTML = `
      <a class="back" href="#/">‹ Back</a>
      <h1>Submit a New Job</h1>
      <p class="muted">Describe the computing task and the resources it needs.</p>
      <form class="card" id="form" style="margin-top:16px">
        <div id="err"></div>
        <div class="field"><label for="name">Job name</label><input id="name" required maxlength="80" placeholder="e.g. ResNet training run"></div>
        <div class="field"><label for="type">Job type</label>
          <select id="type">${["Model Training", "Data Processing", "Image Analysis", "Simulation", "Batch Inference", "Custom"].map((t) => `<option>${t}</option>`).join("")}</select></div>
        <div class="grid three">
          <div class="field"><label for="cpu">CPU cores</label><input id="cpu" type="number" min="1" max="64" value="4"></div>
          <div class="field"><label for="ram">RAM (GB)</label><input id="ram" type="number" min="1" max="256" value="8"></div>
          <div class="field"><label for="gpu">GPUs</label><input id="gpu" type="number" min="0" max="4" value="0"></div>
        </div>
        <div class="field"><label for="priority">Priority</label>
          <select id="priority"><option value="low">Low</option><option value="normal" selected>Normal</option><option value="high">High</option></select></div>
        <div class="field"><label for="command">Command <span class="muted">(optional; stored only, never executed)</span></label>
          <textarea id="command" rows="2" placeholder="python train.py --epochs 10"></textarea></div>
        <label class="checkline"><input id="auto_retry" type="checkbox"> Automatically retry simulated failures (up to 3 attempts)</label>
        <div class="button-row"><button class="btn secondary" id="optimize" type="button">Optimize resources</button><button class="btn secondary" id="predict" type="button">Check failure risk</button></div>
        <div id="smart-result" class="hint"></div>
        <button class="btn" id="submit" type="submit">Submit job</button>
      </form>`;
    $("#optimize").addEventListener("click", async () => {
      try { const r = await api("/optimizer/recommend", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({type:$("#type").value,cpu:$("#cpu").value,ram:$("#ram").value,gpu:$("#gpu").value})});
        $("#cpu").value=r.recommended.cpu; $("#ram").value=r.recommended.ram; $("#gpu").value=r.recommended.gpu; $("#smart-result").textContent=`Suggested resources applied. ${r.explanation}`;
      } catch(e) { $("#smart-result").textContent=e.message; }
    });
    $("#predict").addEventListener("click", async () => {
      try { const r = await api("/prediction/risk", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({type:$("#type").value,cpu:$("#cpu").value,ram:$("#ram").value,gpu:$("#gpu").value})});
        $("#smart-result").textContent=`Estimated risk: ${r.score}% (${r.band}). ${r.reasons.join("; ")} — ${r.method}`;
      } catch(e) { $("#smart-result").textContent=e.message; }
    });
    $("#form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = $("#submit"); btn.disabled = true;
      const body = Object.fromEntries(["name", "type", "cpu", "ram", "gpu", "priority", "command"].map((k) => [k, $("#" + k).value]));
      body.auto_retry = $("#auto_retry").checked; body.max_retries = 3;
      try {
        const job = await api("/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        toast(`Job #${job.id} submitted`);
        location.hash = `#/jobs/${job.id}`;
      } catch (err) {
        $("#err").innerHTML = `<div class="error">${esc(err.message)}</div>`;
        btn.disabled = false;
      }
    });
  },
};

pages.notifications = {
  async render() {
    const n = await api("/notifications");
    view.innerHTML = `<h1>Notifications</h1><p class="muted">Updates when your jobs finish or fail.</p><div class="list" style="margin-top:16px">${n.items.length ? n.items.map(x => `<div class="card"><strong>${esc(x.message)}</strong><div class="muted" style="margin-top:6px">${fmtTime(x.created_at)} · <a href="#/jobs/${x.job_id}">Open job #${x.job_id}</a></div></div>`).join("") : '<div class="card empty">No notifications yet.</div>'}</div>`;
    if (n.unread) await api("/notifications/read", {method:"POST"});
  },
};

pages.lab = {
  manual: true,
  async render() {
    const workflows = await api('/workflows');
    view.innerHTML = `
      <h1>CloudFlow Intelligence Lab</h1><p class="muted">Decision-support tools, workflow orchestration and transparent simulations.</p>
      <div class="section-head"><h2>AI Job Optimizer & Failure Risk</h2></div>
      <div class="card"><p class="muted">Enter a proposed workload. Recommendations use transparent rules, not a trained model.</p>
        <div class="grid three"><div class="field"><label>Job type</label><select id="lab-type"><option>Model Training</option><option>Data Processing</option><option>Image Analysis</option><option>Simulation</option><option>Batch Inference</option><option>Custom</option></select></div><div class="field"><label>CPU</label><input id="lab-cpu" type="number" min="1" max="64" value="8"></div><div class="field"><label>RAM GB</label><input id="lab-ram" type="number" min="1" max="256" value="16"></div></div>
        <div class="field"><label>GPU count</label><input id="lab-gpu" type="number" min="0" max="4" value="1"></div>
        <div class="button-row"><button class="btn" id="lab-opt">Recommend resources</button><button class="btn secondary" id="lab-risk">Predict risk</button></div><div id="lab-ai-result" class="result-panel">Results will appear here.</div>
      </div>
      <div class="section-head"><h2>What-if Worker Simulator</h2></div>
      <div class="card"><p class="muted">Model extra worker capacity without changing your real worker pool.</p><div class="grid two"><div class="field"><label>Additional workers</label><input id="wf-count" type="number" min="0" max="10" value="2"></div><div class="field"><label>CPU per worker</label><input id="wf-cpu" type="number" min="1" max="256" value="32"></div><div class="field"><label>RAM per worker (GB)</label><input id="wf-ram" type="number" min="1" max="1024" value="128"></div><div class="field"><label>GPU per worker</label><input id="wf-gpu" type="number" min="0" max="16" value="2"></div></div><button class="btn" id="run-whatif">Run what-if simulation</button><div id="whatif-result" class="result-panel">Simulation results will appear here.</div></div>
      <div class="section-head"><h2>Workflow Builder</h2></div>
      <div class="card"><p class="muted">Create a simple sequential pipeline. Each step waits for the previous step to complete.</p><div class="field"><label>Workflow name</label><input id="flow-name" maxlength="80" value="ML training pipeline"></div><div class="grid three"><div class="field"><label>Step 1</label><input id="step1" value="Prepare data"></div><div class="field"><label>Step 2</label><input id="step2" value="Train model"></div><div class="field"><label>Step 3</label><input id="step3" value="Evaluate model"></div></div><button class="btn" id="create-flow">Create workflow</button><div id="flow-result" class="result-panel"></div>
        <h3 style="margin-top:20px">Your workflows</h3><div class="list">${workflows.items.length ? workflows.items.map(w=>`<div class="workflow-card"><strong>${esc(w.name)}</strong><div class="workflow-steps">${w.steps.map((st,i)=>`<a href="#/jobs/${st.id}" class="workflow-step"><span>${i+1}. ${esc(st.name)}</span>${badge(st.status)}</a>`).join('<div class="flow-arrow">↓</div>')}</div></div>`).join('') : '<div class="empty">No workflows created yet.</div>'}</div>
      </div>
      <div class="section-head"><h2>Carbon Footprint Estimator</h2></div>
      <div class="card"><p class="muted">Illustrative energy estimate. Enter a verified local grid intensity for reporting.</p><div class="grid two"><div class="field"><label>Runtime (hours)</label><input id="carbon-hours" type="number" min="0.01" step="0.1" value="2"></div><div class="field"><label>Current grid intensity (gCO₂/kWh)</label><input id="carbon-intensity" type="number" min="10" max="1200" value="400"></div><div class="field"><label>Optional later-window intensity</label><input id="carbon-future" type="number" min="10" max="1200" value="180"></div><div class="field"><label>CPU cores</label><input id="carbon-cpu" type="number" value="8"></div><div class="field"><label>RAM GB</label><input id="carbon-ram" type="number" value="16"></div><div class="field"><label>GPUs</label><input id="carbon-gpu" type="number" value="1"></div></div><button class="btn" id="carbon-run">Estimate footprint</button><div id="carbon-result" class="result-panel"></div></div>
      <div class="section-head"><h2>CloudFlow Assistant</h2></div>
      <div class="card"><p class="muted">Ask about your own jobs or workers. This local assistant uses simple intent rules and does not send data to an external AI provider.</p><div class="field"><label for="assistant-prompt">Your question</label><input id="assistant-prompt" placeholder="Show my failed jobs"></div><button class="btn" id="ask-assistant">Ask CloudFlow</button><div id="assistant-result" class="result-panel"></div></div>`;

    const readResources = (prefix='lab-') => ({type:$("#"+prefix+"type").value,cpu:$("#"+prefix+"cpu").value,ram:$("#"+prefix+"ram").value,gpu:$("#"+prefix+"gpu").value});
    $("#lab-opt").onclick = async () => { try { const r=await api('/optimizer/recommend',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(readResources())}); $("#lab-ai-result").textContent=`Recommended: ${r.recommended.cpu} CPU · ${r.recommended.ram} GB RAM · ${r.recommended.gpu} GPU. ${r.explanation}`; } catch(e){ $("#lab-ai-result").textContent=e.message; } };
    $("#lab-risk").onclick = async () => { try { const r=await api('/prediction/risk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(readResources())}); $("#lab-ai-result").textContent=`Risk ${r.score}% (${r.band}). ${r.reasons.join('; ')}. ${r.method}`; } catch(e){ $("#lab-ai-result").textContent=e.message; } };
    $("#run-whatif").onclick = async () => { try { const d={extra_workers:$("#wf-count").value,cpu:$("#wf-cpu").value,ram:$("#wf-ram").value,gpu:$("#wf-gpu").value}; const r=await api('/simulate/whatif',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)}); $("#whatif-result").textContent=`Pending jobs: ${r.pending_jobs}. Jobs fitting now: ${r.currently_fit}; with added workers: ${r.fit_with_extra_workers}. Additional supported: ${r.additional_jobs_supported}. CPU capacity: ${r.cpu_capacity_now} → ${r.cpu_capacity_after}. ${r.assumptions}`; } catch(e){ $("#whatif-result").textContent=e.message; } };
    $("#create-flow").onclick = async () => { try { const names=[1,2,3].map(i=>$("#step"+i).value.trim()); if(names.some(x=>!x)) throw new Error('Give every workflow step a name'); const steps=names.map((name,i)=>({name,type:i===1?'Model Training':i===0?'Data Processing':'Batch Inference',cpu:i===1?8:4,ram:i===1?16:8,gpu:i===1?1:0})); const r=await api('/workflows',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$("#flow-name").value,steps})}); $("#flow-result").textContent=`Workflow created. Job IDs: ${r.job_ids.join(' → ')}. Refresh this page to see the pipeline.`; } catch(e){ $("#flow-result").textContent=e.message; } };
    $("#carbon-run").onclick = async () => { try { const d={runtime_hours:$("#carbon-hours").value,grid_intensity:$("#carbon-intensity").value,future_grid_intensity:$("#carbon-future").value,cpu:$("#carbon-cpu").value,ram:$("#carbon-ram").value,gpu:$("#carbon-gpu").value}; const r=await api('/carbon/estimate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)}); $("#carbon-result").textContent=`Estimated energy: ${r.energy_kwh} kWh · Carbon now: ${r.carbon_grams} gCO₂ (${r.carbon_kg} kg). Later-window estimate: ${r.future_carbon_grams} gCO₂; potential saving: ${r.estimated_saving_grams} g. ${r.green_window_recommended?'The supplied later-window intensity is lower; consider delaying flexible work.':'No carbon saving from the supplied later window.'} ${r.assumptions}`; } catch(e){ $("#carbon-result").textContent=e.message; } };
    $("#ask-assistant").onclick = async () => { try { const r=await api('/assistant',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:$("#assistant-prompt").value})}); $("#assistant-result").innerHTML=`<p>${esc(r.answer)}</p>${r.items.length?`<div class="list">${r.items.map(x=>x.status?`<a class="job" href="#/jobs/${x.id}"><span>${esc(x.name)}</span>${badge(x.status)}</a>`:`<div class="job"><div class="main"><strong>${esc(x.name)}</strong><div class="muted">${esc([x.cpu_total!=null?x.cpu_total+' CPU cores':'',x.ram_total!=null?x.ram_total+' GB RAM':'',x.gpu_total!=null?x.gpu_total+' GPUs':''].filter(Boolean).join(' · '))}</div></div></div>`).join('')}</div>`:''}<p class="hint">${esc(r.notice)}</p>`; } catch(e){ $("#assistant-result").textContent=e.message; } };
  }
};

/* ------- charts (hand-rolled SVG, no dependencies) ------- */
const COLORS = { cpu: "#1e3a6e", ram: "#0ea5a4", gpu: "#d97706" };
function lineChart(samples) {
  const W = 600, H = 220, L = 34, R = 10, T = 10, B = 22;
  if (samples.length < 2) return '<div class="empty">Collecting data…</div>';
  const x = (i) => L + (i * (W - L - R)) / (samples.length - 1);
  const y = (v) => T + (1 - v / 100) * (H - T - B);
  const grid = [0, 25, 50, 75, 100].map((v) => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#e3e8f2"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="#5b6b8a">${v}%</text>`).join("");
  const lines = ["cpu", "ram", "gpu"].map((k) => `<polyline fill="none" stroke="${COLORS[k]}" stroke-width="2.4" stroke-linejoin="round" points="${samples.map((s, i) => `${x(i)},${y(s[k])}`).join(" ")}"/>`).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Resource utilization over time">${grid}${lines}</svg>
    <div class="legend">${["cpu", "ram", "gpu"].map((k) => `<span><i style="background:${COLORS[k]}"></i>${k.toUpperCase()} ${samples[samples.length - 1][k]}%</span>`).join("")}</div>`;
}
function hbars(obj, colorFor) {
  const entries = Object.entries(obj);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  if (!entries.length) return '<div class="empty">No data yet.</div>';
  return entries.map(([k, v]) => `<div class="hbar"><span>${esc(cap(k))}</span><div class="bar"><i style="width:${(100 * v) / max}%;background:${colorFor(k)}"></i></div><strong>${v}</strong></div>`).join("");
}
const STATUS_COLOR = (s) => ({ running: "#16a34a", completed: "#1d4ed8", pending: "#d97706", failed: "#dc2626", cancelled: "#9ca3af" }[s] || "#1e3a6e");

pages.stats = {
  async render() {
    const s = await api("/stats");
    const done = s.by_status.completed || 0, failed = s.by_status.failed || 0;
    view.innerHTML = `
      <h1>Statistics</h1>
      <p class="muted">Job counts and resource usage across all workers.</p>
      <div class="grid three" style="margin-top:16px">
        <div class="card stat"><div class="label">Total jobs</div><div class="value">${s.total}</div></div>
        <div class="card stat"><div class="label">Success rate</div><div class="value green">${s.success_rate == null ? "—" : s.success_rate + "%"}</div></div>
        <div class="card stat"><div class="label">Avg. runtime</div><div class="value" style="font-size:30px">${fmtDur(s.avg_duration)}</div></div>
      </div>
      <div class="section-head"><h2>Resource utilization</h2></div>
      <div class="card">${lineChart(s.utilization)}</div>
      <div class="section-head"><h2>Completed vs failed</h2></div>
      <div class="card">${hbars({ completed: done, failed }, STATUS_COLOR)}</div>
      <div class="section-head"><h2>Jobs by status</h2></div>
      <div class="card">${hbars(s.by_status, STATUS_COLOR)}</div>
      <div class="section-head"><h2>Jobs by type</h2></div>
      <div class="card">${hbars(s.by_type, () => "#1e3a6e")}</div>`;
  },
};

pages.workers = {
  async render() {
    const ws = await api("/workers");
    const res = (label, used, total, unit) => total === 0
      ? `<div class="res"><div class="row"><span class="muted">${label}</span><span class="muted">None</span></div></div>`
      : `<div class="res"><div class="row"><span>${label}</span><strong>${used} / ${total}${unit}</strong></div><div class="bar ${used / total > .8 ? "" : "green"}"><i style="width:${(100 * used) / total}%"></i></div></div>`;
    view.innerHTML = `
      <h1>Workers</h1>
      <p class="muted">Status and available resources of each compute node.</p>
      <div class="list" style="margin-top:16px">${ws.map((w) => `
        <div class="card worker">
          <h2>${esc(w.name)} ${w.status === "busy" ? '<span class="badge running">Busy</span>' : '<span class="badge cancelled">Idle</span>'}</h2>
          <div class="muted">${w.running_jobs} running job${w.running_jobs === 1 ? "" : "s"}</div>
          ${res("CPU cores", w.cpu_used, w.cpu_total, "")}
          ${res("RAM", w.ram_used, w.ram_total, " GB")}
          ${res("GPUs", w.gpu_used, w.gpu_total, "")}
        </div>`).join("")}</div>`;
  },
};

/* --------------------------------------------------------------- authentication */
async function showAuth() {
  view.innerHTML = `<div class="card" style="max-width:430px;margin:8vh auto"><h1>Welcome to CloudFlow</h1><p class="muted">Sign in to manage your private jobs, or create an account.</p><div class="field"><label for="auth-user">Username</label><input id="auth-user" autocomplete="username" minlength="3" maxlength="32"></div><div class="field"><label for="auth-pass">Password</label><input id="auth-pass" type="password" autocomplete="current-password"></div><div id="auth-error"></div><div style="display:flex;gap:10px;margin-top:14px"><button class="btn" id="sign-in">Sign in</button><button class="btn secondary" id="sign-up">Create account</button></div></div>`;
  async function submit(mode) {
    const b = mode === "login" ? $("#sign-in") : $("#sign-up"); b.disabled = true;
    try { const r = await api(`/auth/${mode}`, {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username:$("#auth-user").value,password:$("#auth-pass").value})}); csrfToken=r.csrf_token; location.hash="#/"; await route(); }
    catch(e) { $("#auth-error").innerHTML=`<div class="error">${esc(e.message)}</div>`; b.disabled=false; }
  }
  $("#sign-in").addEventListener("click",()=>submit("login")); $("#sign-up").addEventListener("click",()=>submit("register"));
}

/* --------------------------------------------------------------- router */
let current = null;
let authChecked = false;
async function route() {
  if (!authChecked) {
    try { const me = await api("/auth/me"); authChecked = true; if (!me.authenticated) { await showAuth(); return; } csrfToken = me.csrf_token;
      const userName = $("#user-name"); if (userName) userName.textContent = me.username || "CloudFlow User";
      const logout = $("#logout"); if (logout) logout.onclick = async () => { try { await api("/auth/logout", {method:"POST"}); csrfToken=null; authChecked=false; await showAuth(); } catch(e) { toast(e.message); } };
    }
    catch (_) { await showAuth(); return; }
  }
  const raw = location.hash.slice(1) || "/";
  const [path, qs] = raw.split("?");
  const params = new URLSearchParams(qs || "");
  let name = "dashboard", arg;
  const m = path.match(/^\/jobs\/(\d+)$/);
  if (m) { name = "detail"; arg = m[1]; }
  else if (path === "/jobs") name = "jobs";
  else if (path === "/new") name = "new";
  else if (path === "/stats") name = "stats";
  else if (path === "/workers") name = "workers";
  else if (path === "/lab") name = "lab";
  else if (path === "/notifications") name = "notifications";
  current = name;
  const tab = name === "detail" || name === "new" ? (name === "new" ? "dashboard" : "jobs") : name === "notifications" ? "dashboard" : name;
  document.querySelectorAll("[data-route]").forEach((a) => a.classList.toggle("active", a.dataset.route === tab));
  try { await pages[name].render(params, arg); }
  catch (e) { view.innerHTML = `<div class="card empty">Couldn't load this page.<br>${esc(e.message)}</div>`; }
  if (!pages[name].manual && path !== "/jobs") window.scrollTo(0, window.scrollY);
}

async function refreshBell() {
  try { const n = await api("/notifications"); $("#bell-dot").hidden = n.unread === 0; } catch (_) {}
}

const globalSearch = $("#global-search");
if (globalSearch) {
  globalSearch.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && globalSearch.value.trim()) {
      pages.jobs.state.q = globalSearch.value.trim();
      pages.jobs.state.status = "";
      location.hash = "#/jobs?q=" + encodeURIComponent(globalSearch.value.trim());
      globalSearch.blur();
    }
  });
}
window.addEventListener("hashchange", () => { window.scrollTo(0, 0); route(); refreshBell(); });
setInterval(() => { if (current && !pages[current].manual && !document.hidden) route(); refreshBell(); }, 4000);
route();
refreshBell();
