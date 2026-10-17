/* Referral Desk. Reads window.APP (written by src/build_app.py) and renders:
   #/            inbox with 2-hour countdowns
   #/D01         review: summary, criteria, evidence panel, decision + reply draft
   Decisions live only in this browser (localStorage). Nothing is ever sent. */
(function () {
  const APP = window.APP || { packets: [], meta: {} };
  const P = APP.packets;
  const byId = Object.fromEntries(P.map(p => [p.id, p]));
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const ICON = { met: "✓", not_met: "✕", unknown: "?", cant_tell: "⌛" };
  const BAND = { fit: "var(--ok)", info: "var(--warn)", nofit: "var(--bad)" };
  const SLA = 120; // IHH answers hospitals within 2 hours
  const LOADED = Date.now();

  const store = {
    get() { try { return JSON.parse(localStorage.getItem("referral-desk") || "{}") } catch (e) { return {} } },
    set(v) { try { localStorage.setItem("referral-desk", JSON.stringify(v)) } catch (e) { /* private mode: keep in memory */ } mem = v },
  };
  let mem = store.get();
  const decisions = () => mem;

  const ui = { filter: "all", sort: "deadline", q: "", showIhh: false, panel: null, drawer: null };

  // who is reviewing: kept in this browser only, stamped on every saved decision and reply
  const ROLES = ["Referral coordinator", "RN", "LVN", "Medical director", "Case manager"];
  // Demo sign-in. The check runs in the browser, so it keeps casual viewers out and nothing more.
  // A real deployment would use IHH's own sign-in. Passwords are stored as salted SHA-256, not in plain text.
  const ACCOUNTS = [{ email: "cornel@ocmeed.com", name: "Dr Cornel Manole", role: "Referral coordinator", salt: "ihh-desk-demo-1",
    hash: "039022d0783fe2c200f58e8038fbaffd1c648700f25a35290d6af7f2b20ed5e0" }];
  let session = null;
  try { session = JSON.parse(sessionStorage.getItem("referral-desk-session") || "null") } catch (e) { /* not signed in */ }
  let who = session ? { name: session.name, role: session.role } : { name: "", role: "Referral coordinator" };
  try { if (session) who = { ...who, ...JSON.parse(localStorage.getItem("referral-desk-user:" + session.email) || "{}") } } catch (e) { /* keep account default */ }
  async function sha256(s) { const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s)); return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join("") }
  function loginView() {
    return `<section class="login"><div class="login-card">
      <p class="eyebrow">Referral Desk · Illumination Health + Home</p><h1>Sign in</h1>
      <form id="login" autocomplete="on">
        <label>Email<input id="l-email" type="email" autocomplete="username" required></label>
        <label>Password<input id="l-pass" type="password" autocomplete="current-password" required></label>
        ${ui.loginError ? `<p class="l-err" role="alert">${esc(ui.loginError)}</p>` : ""}
        <button class="btn primary" type="submit">Sign in</button></form>
      <p class="lbl">Demo sign-in for the prototype: it runs in this browser and is not real security. A real deployment would use IHH’s own sign-in. Judges: the demo account is in the project README.</p></div></section>`;
  }
  document.addEventListener("submit", async e => {
    if (e.target.id !== "login") return; e.preventDefault();
    const email = $("#l-email").value.trim().toLowerCase(), pass = $("#l-pass").value;
    const a = ACCOUNTS.find(x => x.email === email);
    let ok = false; try { ok = !!a && await sha256(a.salt + ":" + pass) === a.hash } catch (err) { ui.loginError = "This browser cannot check the password here. Open the page over https or localhost."; return render() }
    if (!ok) { ui.loginError = "Email or password not recognized."; return render() }
    session = { email: a.email, name: a.name, role: a.role };
    try { sessionStorage.setItem("referral-desk-session", JSON.stringify(session)) } catch (err) { /* keep in memory */ }
    who = { name: a.name, role: a.role };
    try { who = { ...who, ...JSON.parse(localStorage.getItem("referral-desk-user:" + a.email) || "{}") } } catch (err) { /* keep */ }
    ui.loginError = null; render();
  });
  const sign = () => `${who.name}, ${who.role}\nIllumination Health + Home`;
  function whoBar() {
    if (!ui.editWho) return `<p class="eyebrow who">Welcome back, ${esc(who.name)} · ${esc(who.role)} <button class="who-edit" data-who>Change</button><button class="who-edit" data-signout>Sign out</button></p>`;
    return `<div class="who-form"><input id="who-name" value="${esc(who.name)}" aria-label="Your name" placeholder="Your name">
      <select id="who-role" aria-label="Your role">${ROLES.map(r => `<option ${r === who.role ? "selected" : ""}>${r}</option>`).join("")}</select>
      <button class="btn primary" data-whosave>Save</button></div>`;
  }

  // ---------- helpers ----------
  function minsLeft(p) { return SLA - p.received_min - (Date.now() - LOADED) / 60000 }
  function clock(p) {
    const d = decisions()[p.id];
    if (d) return `<span class="done ${d.decision}">${{ approve: "Approved", info: "Asked for info", deny: "Denied" }[d.decision]}</span>`;
    const m = minsLeft(p), a = Math.abs(m), h = Math.floor(a / 60), mm = Math.floor(a % 60);
    const txt = m < 0 ? `overdue ${h ? h + "h " : ""}${mm}m` : `${h}h ${String(mm).padStart(2, "0")}m left`;
    return `<span class="clock ${m < 0 ? "over" : m < 30 ? "soon" : ""}" title="${p.uploaded ? "Time since upload" : "Simulated arrival time"}"><i></i>${txt}</span>`;
  }
  const SRC = { upload: "Upload", fax: "Fax", folder: "Folder", email: "Email", portal: "Portal" };
  const srcTag = p => p.uploaded ? `<span class="src ${esc(p.uploaded.source || "upload")}" title="How this referral arrived">${SRC[p.uploaded.source] || "Upload"}</span>` : "";
  function arrival(p) {
    const u = p.uploaded; if (!u) return "";
    const bits = [`Arrived by <b>${SRC[u.source] || "Upload"}</b>`];
    if (u.hospital) bits.push(`from ${esc(u.hospital)}`);
    if (u.from) bits.push(`sender ${esc(u.from)}`);
    if (u.contact) bits.push(`callback ${esc(u.contact)}`);
    if (u.subject) bits.push(`“${esc(u.subject)}”`);
    if (u.attachment) bits.push(`attachment ${esc(u.attachment)} of that email`);
    if (u.source === "portal") bits.push(u.declared_docs && u.declared_docs.length ? `hospital says it attached ${u.declared_docs.map(esc).join(", ")}` : "hospital ticked no documents");
    if (u.dry_run) bits.push("dry run");
    return `<div class="meta arrival">${bits.join(" · ")}</div>`;
  }
  const pill = p => `<span class="pill ${p.fit.band}">${p.fit.score}</span>`;
  const pg = (page, quote, label) => page == null ? "" :
    `<button class="pg" data-page="${page}" data-quote="${esc(quote || "")}" title="Open page ${page}">${label || "p" + page}</button>`;
  const vmark = v => v == null ? "" : v ? '<span class="vf" title="Quote found on this page">✓</span>' : '<span class="ck" title="Quote not found on this page, read it">check</span>';

  function arc(r, from, to, color, w, cap) {
    const c = 2 * Math.PI * r;
    return `<circle cx="80" cy="80" r="${r}" fill="none" stroke="${color}" stroke-width="${w}"${cap ? ' stroke-linecap="round"' : ""}
      stroke-dasharray="${(c * (to - from)).toFixed(1)} ${c.toFixed(1)}" transform="rotate(${-90 + from * 360} 80 80)"/>`;
  }
  function ring(score, band, size = 176) {
    const s = Math.max(0.001, score / 100);
    return `<svg class="gauge" width="${size}" height="${size}" viewBox="0 0 160 160" role="img" aria-label="Fit score ${score} of 100, ${band}">
      ${arc(73, 0, 0.395, "var(--bad)", 3.5)}${arc(73, 0.405, 0.695, "var(--warn)", 3.5)}${arc(73, 0.705, 1, "var(--ok)", 3.5)}
      ${arc(60, 0, 1, "var(--track)", 13)}${arc(60, 0, s, BAND[band], 13, true)}
      <text x="80" y="84" text-anchor="middle" font-size="44" font-weight="600" fill="var(--ink)" font-family="IBM Plex Mono, monospace">${score}</text>
      <text x="80" y="104" text-anchor="middle" font-size="10" letter-spacing="1.5" fill="var(--mute)" font-family="Montserrat, sans-serif">FIT SCORE</text></svg>`;
  }
  function dial(score, band) {
    const r = 21, c = 2 * Math.PI * r;
    return `<svg class="dial" width="52" height="52" viewBox="0 0 52 52" aria-hidden="true">
      <circle cx="26" cy="26" r="${r}" fill="none" stroke="var(--track)" stroke-width="5"/>
      <circle cx="26" cy="26" r="${r}" fill="none" stroke="${BAND[band]}" stroke-width="5" stroke-linecap="round" stroke-dasharray="${(c * Math.max(.01, score / 100)).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 26 26)"/>
      <text x="26" y="31" text-anchor="middle" font-size="14" font-weight="600" fill="var(--ink)" font-family="IBM Plex Mono, monospace">${score}</text></svg>`;
  }

  // ---------- inbox ----------
  const LANES = [["nofit", "Not a fit", "Verified hard stop found"], ["info", "Needs info", "No hard stop; open questions"], ["fit", "Likely fit", "Rules met with evidence"]];
  function card(p) {
    const d = decisions()[p.id], m = minsLeft(p);
    const used = Math.min(1, Math.max(0, (SLA - m) / SLA));
    const bl = p.fit.blockers;
    return `<button class="card2 ${p.fit.band} ${d ? "decided" : ""}" data-open="${p.id}">
      <span class="c-top"><span class="id">${p.id}</span>${srcTag(p)}${clock(p)}</span>
      <span class="c-main">${dial(p.fit.score, p.fit.band)}<span class="c-who"><b>${esc(p.patient.summary)}</b><small>${esc(p.patient.admit_reason || "")}</small></span></span>
      <span class="c-bl">${bl.length ? bl.slice(0, 3).map(x => `<span class="tagx">${esc(x)}</span>`).join("") + (bl.length > 3 ? `<span class="tagx more">+${bl.length - 3}</span>` : "") : `<span class="calm">No hard stop</span>`}</span>
      <span class="c-foot"><span class="sla ${m < 0 ? "over" : m < 30 ? "soon" : ""}" title="Share of the 2-hour window used"><i style="width:${(used * 100).toFixed(0)}%"></i></span>
        <span class="num lbl">${p.pages} pp${ui.showIhh && p.ihh ? ` · IHH ${p.ihh}` : ""}</span></span>
    </button>`;
  }
  function recap() {
    const d = decisions(), open_ = P.filter(p => !d[p.id]);
    const n = k => open_.filter(p => p.fit.band === k).length;
    const soon = open_.filter(p => minsLeft(p) < 30).length;
    if (!open_.length) return `<h1>All caught up.</h1><p class="lede">Every referral has a decision. New ones appear here as they arrive.</p>`;
    const go = (k, num, label) => `<button class="rc ${k}" data-filter="${k}"><span class="num">${num}</span>${label}</button>`;
    return `<h1>${open_.length} ${open_.length === 1 ? "referral needs" : "referrals need"} your review.</h1>
      <div class="recap">${go("fit", n("fit"), "look like a fit")}${go("nofit", n("nofit"), "do not fit")}${go("info", n("info"), "need more info or your call")}</div>
      <p class="lede">${soon ? `<b class="soon">${soon} under 30 minutes left on the 2-hour reply.</b> ` : ""}Each finding links to the page it came from. You decide; nothing is sent from here.</p>`;
  }
  function inbox() {
    const d = decisions();
    let list = P.filter(p => ui.filter === "all" || ui.filter === "open" ? (ui.filter !== "open" || !d[p.id]) : p.fit.band === ui.filter);
    if (ui.q) { const q = ui.q.toLowerCase(); list = list.filter(p => (p.id + " " + p.patient.summary + " " + (p.patient.admit_reason || "") + " " + p.fit.blockers.join(" ")).toLowerCase().includes(q)) }
    const sorters = { deadline: (a, b) => (d[a.id] ? 1 : 0) - (d[b.id] ? 1 : 0) || minsLeft(a) - minsLeft(b), score: (a, b) => a.fit.score - b.fit.score, id: (a, b) => a.id.localeCompare(b.id) };
    list.sort(sorters[ui.sort]);
    const pages = P.reduce((s, p) => s + p.pages, 0);
    const decided = Object.keys(d).filter(k => byId[k]).length;
    const urgent = P.filter(p => !d[p.id] && minsLeft(p) < 30).length;
    const lanes = LANES.filter(([k]) => ["all", "open"].includes(ui.filter) || ui.filter === k).map(([k, name, sub]) => {
      const items = list.filter(p => p.fit.band === k);
      return `<section class="lane ${k}"><header><i></i><div><b>${name}</b><small>${sub}</small></div><span class="num">${items.length}</span></header>
        <div class="cards">${items.map(card).join("") || `<div class="empty">Nothing here</div>`}</div></section>`;
    }).join("");
    return `<section class="hero2">
        <div class="h-copy">${whoBar()}
          ${recap()}</div>
        <div class="pipe">
          <div><small class="step">[01] Read</small><span class="num">${pages}</span><small>faxed pages</small></div>
          <div><small class="step">[02] Check</small><span class="num">${P.length}</span><small>one-page reviews</small></div>
          <div class="hot"><small class="step">[03] Decide</small><span class="num">${decided}<em>/${P.length}</em></span><small>${urgent} under 30 min left</small></div>
        </div></section>
      <div class="tools">
        <div class="seg" role="tablist">${[["all", "All"], ["open", "Open"], ["nofit", "Not a fit"], ["info", "Needs info"], ["fit", "Likely fit"]].map(([k, l]) => `<button data-filter="${k}" class="${ui.filter === k ? "on" : ""}">${l}</button>`).join("")}</div>
        <input class="search" id="q" type="search" placeholder="Search patient, diagnosis or rule ID" value="${esc(ui.q)}" aria-label="Search">
        <select class="sort" id="sort" aria-label="Sort">${[["deadline", "Sort: deadline"], ["score", "Sort: lowest score"], ["id", "Sort: packet ID"]].map(([k, l]) => `<option value="${k}" ${ui.sort === k ? "selected" : ""}>${l}</option>`).join("")}</select>
        ${APP.meta.real ? `<label class="toggle"><input type="checkbox" id="ihh" ${ui.showIhh ? "checked" : ""}> show IHH decision</label>` : ""}
      </div>
      ${dropzone()}
      <div class="board">${lanes}</div>
      <p class="foot">Countdowns use simulated arrival times. Fit score is rule-based: a verified blocker caps it at 15; unknowns lower it. Weights were hand-tuned on IHH’s 11 past decisions, so it guides the coordinator and does not decide. ${esc(APP.meta.note || "")}</p>`;
  }

  // ---------- intake (only with src/desk_server.py running on this computer) ----------
  const STEP_NAMES = { fix: "Straighten pages", transcribe: "Read every page", check: "Check IHH rules", score: "Verify quotes, score", build: "Add to inbox" };
  function dropzone() {
    const s = ui.server; if (!s) return "";
    const jobs = (ui.jobs || []).slice().reverse().map(j => {
      const at = j.steps.indexOf(j.stage);
      return `<div class="job ${j.state}"><div class="j-top"><b>${esc(j.id)}</b><span class="src">${esc(j.source)}</span><span>${esc(j.name)}</span>${j.dry_run ? `<span class="tagx">dry run</span>` : ""}
          ${j.state === "done" ? `<button class="btn" data-open="${j.id}">Open ${j.id}</button>` : ""}</div>
        <ol class="j-steps">${j.steps.map((k, i) => `<li class="${j.state === "done" || i < at ? "ok" : i === at ? (j.state === "error" ? "bad" : "now") : ""}">${STEP_NAMES[k]}</li>`).join("")}</ol>
        <p class="lbl">${esc(j.msg || "")}</p></div>`;
    }).join("");
    return `<section class="intake"><label class="drop" id="drop"><input type="file" id="file" accept="application/pdf,.pdf,.docx,image/jpeg,image/png,.jpg,.jpeg,.png" multiple hidden>
        <b>Drop referrals here: PDF, Word or photos</b><small>or click to choose. Each PDF or Word file becomes a referral; photos dropped together become one referral, one page per photo. It is processed on this computer and saved in output/, which is never committed.${s.dry_run ? " DRY RUN: only the fictional F01 to F09 PDFs, with prepared results." : ""}</small></label>
      <p class="lbl channels">Also arriving here: <b>Fax</b> (fax service webhook) · <b>Email</b> to ${esc(s.email || "the intake address")} · <b>Folder</b> (files saved in the intake folder) · <b>Hospital portal</b> <a href="/portal" target="_blank" rel="noopener">open /portal</a></p>
      ${s.key ? "" : `<p class="lbl warn">No API key: start the server with ANTHROPIC_API_KEY set.</p>`}
      ${ui.uploadError ? `<p class="lbl warn">${esc(ui.uploadError)}</p>` : ""}${jobs}</section>`;
  }
  async function upload(list) {
    const files = [...(list || [])], errs = [];
    ui.uploadError = null;
    if (!files.length) return;
    const photos = files.filter(f => /\.(jpe?g|png)$/i.test(f.name));
    if (photos.length) {
      try {
        const b64 = f => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result.split(",")[1]); r.onerror = no; r.readAsDataURL(f) });
        const r = await fetch("/api/upload/photos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ files: await Promise.all(photos.map(async f => ({ name: f.name, b64: await b64(f) }))) }) });
        const j = await r.json(); if (!r.ok) errs.push(`photos: ${j.error || "upload failed"}`);
      } catch (e) { errs.push("The local server is not answering.") }
    }
    for (const file of files.filter(f => !photos.includes(f))) {
      if (!/\.(pdf|docx)$/i.test(file.name)) { errs.push(`${file.name}: not a PDF, Word file or photo`); continue }
      try {
        const r = await fetch("/api/upload", { method: "POST", headers: { "Content-Type": "application/pdf", "X-Filename": encodeURIComponent(file.name) }, body: file });
        const j = await r.json(); if (!r.ok) errs.push(`${file.name}: ${j.error || "upload failed"}`);
      } catch (e) { errs.push("The local server is not answering."); break }
    }
    ui.uploadError = errs.join(" · ") || null;
    if (errs.length) render();
    poll();
  }
  async function poll() {
    try { ui.jobs = await (await fetch("/api/jobs", { cache: "no-store" })).json() } catch (e) { return }
    const fresh = ui.jobs.find(j => j.state === "done" && !byId[j.id]);
    const busy = ui.jobs.some(j => j.state === "running");
    if (fresh && !busy) { location.hash = "#/" + fresh.id; return location.reload() }  // new packets are in the rebuilt page
    if (!route()) { const y = scrollY; render(); scrollTo(0, y) }
    if (ui.jobs.some(j => j.state === "running")) setTimeout(poll, 1500);
  }
  if (!APP.meta.artifact && location.protocol.startsWith("http") && APP.meta.real) {
    fetch("/api/ping", { cache: "no-store" }).then(r => r.ok ? r.json() : null).then(j => { if (j && j.ok) { ui.server = j; poll() } }).catch(() => {});
  }
  document.addEventListener("dragover", e => { const d = e.target.closest && e.target.closest("#drop"); if (d) { e.preventDefault(); d.classList.add("over") } });
  document.addEventListener("dragleave", e => { const d = e.target.closest && e.target.closest("#drop"); if (d) d.classList.remove("over") });
  document.addEventListener("drop", e => { const d = e.target.closest && e.target.closest("#drop"); if (d) { e.preventDefault(); upload(e.dataTransfer.files) } });

  // ---------- review ----------
  function chip(r) {
    const e = (r.evidence || [])[0];
    const pages = [...new Set((r.evidence || []).map(x => x.page))].map(x => "p" + x).join(" ");
    return `<button class="chip ${r.status}" data-rule="${r.rule_id}" title="${esc(r.rule_id + ": " + r.text + "\n\n" + (r.finding || ""))}">${ICON[r.status] || ""} <span class="rid">${r.rule_id}</span>${esc(r.short)}${pages ? ` <span class="num" style="opacity:.7">${pages}</span>` : ""}${(r.evidence || []).length && !r.verified ? ' <span class="ck">check</span>' : ""}</button>`;
  }
  function sbar(rs) {
    const n = rs.length, w = k => (100 * rs.filter(r => r.status === k).length / n).toFixed(1);
    return `<span class="sbar" aria-hidden="true"><i class="met" style="width:${w("met")}%"></i><i class="unknown" style="width:${(+w("unknown") + +w("cant_tell")).toFixed(1)}%"></i><i class="not_met" style="width:${w("not_met")}%"></i></span>`;
  }
  function criteria(p) {
    const shown = p.rules.filter(r => r.status !== "not_applicable" && !r.superseded_by);
    const order = ["General", "ADLs", "Mobility", "Mental Health", "Cognition", "Other Factors", "End of life care", "Infection Control", "Infection", "Diabetes", "Respiratory Illness", "Cardiac"];
    const g = {}; shown.forEach(r => (g[r.section] = g[r.section] || []).push(r));
    const secs = [...order.filter(s => g[s]), ...Object.keys(g).filter(s => !order.includes(s)).sort()];
    const rank = { not_met: 0, unknown: 1, cant_tell: 2, met: 3 };
    const c = k => shown.filter(r => r.status === k).length;
    return `<div class="card crit"><h2>Criteria check <span class="legend">✓ ${c("met")} met · ✕ ${c("not_met")} not met · ? ${c("unknown")} unknown · ⌛ ${c("cant_tell")} can't tell · ${p.rules.length - shown.length} not applicable hidden</span></h2>
      ${secs.map(s => `<div class="sec"><div class="n">${esc(s)}${sbar(g[s])}</div><div class="chips">${g[s].sort((a, b) => rank[a.status] - rank[b.status]).map(chip).join("")}</div></div>`).join("")}</div>`;
  }
  function review(p) {
    const rules = Object.fromEntries(p.rules.map(r => [r.rule_id, r]));
    const facts = (p.key_facts || []).map(f => `<li><span class="k">${esc(f.label)}</span><span>${esc(f.text)} ${(f.pages || []).map(x => pg(x, x === f.quote_page ? f.quote : "")).join(" ")}${vmark(f.verified)}</span></li>`).join("");
    let blocks = p.fit.blockers.map(id => {
      const r = rules[id] || { short: "No general eligibility criterion met", finding: "", evidence: [] };
      const e = (r.evidence || [])[0];
      return `<div class="block"><b>⛔ ${esc(id)} · ${esc(r.short)}</b><div>${esc(r.finding)}</div>${e ? `<div><span class="q">"${esc(e.quote)}"</span> ${pg(e.page, e.quote)}${vmark(e.verified)}</div>` : ""}</div>`;
    }).join("");
    blocks += p.fit.possible_blockers.map(id => `<div class="block maybe"><b>⚠ Possible: ${esc(id)} · ${esc(rules[id].short)}</b><div>${esc(rules[id].finding)}</div><div class="ck">evidence not verified, read the page</div></div>`).join("");
    if (!blocks) blocks = `<div class="clear">No verified blockers found</div>`;
    const confs = (p.conflicts || []).map(c => `<div class="conf"><b>${esc(c.topic)}</b> · ${esc(c.note)} ${(c.sources || []).map(s => pg(s.page, s.quote) + vmark(s.verified)).join(" ")}</div>`).join("") || `<div class="lbl">None found</div>`;
    const missing = (p.documents || []).filter(d => d.present === "no").map(d => `<span>${esc(d.name || d.doc_id)}</span>`).join("") || `<span class="lbl" style="background:none">Nothing from the checklist</span>`;
    const cf = p.claude_fit || {};
    const reasons = (p.fit.reasons || []).map(r => `<li>${r.points} ${esc(r.why)}</li>`).join("");
    return `<div class="title band-${p.fit.band}"><div><p class="eyebrow">${esc(p.id)} · ${p.pages} faxed pages · ${esc(p.fit.label)}</p><h1>${esc(p.id)} · ${esc(p.patient.summary)}</h1>
        <div class="meta">${p.pages} pages · ${esc(p.patient.insurance || "")} · Housing: ${esc(p.patient.housing || "")} · Admitted for: ${esc(p.patient.admit_reason || "")} ${(p.patient.pages || []).map(x => pg(x)).join(" ")}</div>${arrival(p)}</div>
        <div class="meta">${clock(p)} ${ui.showIhh && p.ihh ? `<span class="ihh">· IHH decided: ${p.ihh}</span>` : ""}</div></div>
      <div class="grid3">
        <div class="card"><h2>Key facts <small>click a page to see it</small></h2><ul class="facts">${facts}</ul></div>
        <div class="card ringbox">${ring(p.fit.score, p.fit.band)}<div class="band" style="color:${BAND[p.fit.band]}">${esc(p.fit.label)}</div>${proof(p)}
          <div class="second">Claude's read: <b>${esc(cf.score ?? "–")}/100 · ${esc(String(cf.recommendation || "").replace("_", " "))}</b><br>${esc(cf.reason || "")}</div>
          ${reasons ? `<details class="why"><summary>How the score was built</summary><ul><li>start 100</li>${reasons}${p.fit.blockers.length ? "<li>verified blocker: capped at 15</li>" : "<li>no blocker: floor 40</li>"}</ul></details>` : ""}</div>
        <div class="card"><h2>Blockers</h2>${blocks}<h2 style="margin-top:12px">Form vs chart</h2>${confs}</div>
      </div>
      <div class="stack">${criteria(p)}</div>
      <div class="two"><div class="card"><h2>Missing from packet</h2><div class="miss">${missing}</div></div>
        <div class="card"><h2>Ask the hospital <small>${(p.questions || []).length} questions</small></h2><ol class="qs">${(p.questions || []).map(q => `<li>${esc(q)}</li>`).join("") || "<li>No open questions</li>"}</ol></div></div>
      <p class="foot">✓ next to a page means the quote was found on that page (${p.verification.verified}/${p.verification.quotes} criteria quotes verified). "check" means read the page yourself. Transcripts are AI-made from the scans.</p>`;
  }

  function proof(p) {
    const v = p.verification, files = !APP.meta.artifact;
    const link = (href, name, sub) => href && files ? `<a class="pf" href="${href}" target="_blank" rel="noopener"><b>${name}</b><small>${sub}</small></a>` : "";
    return `<div class="proof"><p class="eyebrow">Proof behind the score</p>
      <div class="pf-row"><button class="pf here" data-page="1"><b>View original here</b><small>page by page, beside this summary</small></button>${link(p.pdf, "Original PDF", `${p.pages} pages as faxed`)}${link(p.readable, "Readable PDF", "each page beside its transcript")}${link(p.fitlist, "Fit checklist", "every IHH rule, status and page")}${link(p.criteria, "IHH criteria", "IHH’s own admission rules")}</div>
      ${files ? "" : `<p class="lbl">The files open in the GitHub Pages or local version of this app.</p>`}
      <p class="pf-check"><span class="vf">✓</span> ${v.verified}/${v.quotes} quotes found on the page they cite</p></div>`;
  }

  // ---------- evidence panel ----------
  function panel(p) {
    const s = ui.panel; if (!s) return "";
    const pageObj = p.page_list.find(x => x.page === s.page) || p.page_list[0];
    const i = p.page_list.indexOf(pageObj);
    let text = esc(pageObj.text);
    if (s.quote) {
      const q = esc(s.quote).replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
      text = text.replace(new RegExp(q, "i"), m => `<mark id="hit">${m}</mark>`);
    }
    text = text.replace(/^## (.*)$/gm, "<b>$1</b>").replace(/^- /gm, "• ");
    const img = p.imgs ? p.imgs[pageObj.page - 1] : p.img ? p.img.replace("{nn}", String(pageObj.page).padStart(2, "0")) : null;
    const pdf = p.pdf && !APP.meta.artifact ? p.pdf : null;
    const tabs = [pdf && ["pdf", "Original PDF"], img && ["scan", "Original page"], ["text", "Transcript"]].filter(Boolean);
    const tab = s.tab && tabs.some(t => t[0] === s.tab) ? s.tab : tabs[0][0];
    const r = s.rule ? p.rules.find(x => x.rule_id === s.rule) : null;
    return `<aside class="panel" aria-label="Evidence">
      <div class="ph"><b>Page ${pageObj.page} of ${p.pages}</b><span class="lbl">${esc(pageObj.title)}</span><span class="sp"></span>
        <button data-nav="-1" ${i <= 0 ? "disabled" : ""} aria-label="Previous page">◀</button><button data-nav="1" ${i >= p.page_list.length - 1 ? "disabled" : ""} aria-label="Next page">▶</button>
        <button data-close aria-label="Close">✕</button></div>
      ${r ? `<div class="rulebox"><span class="chip ${r.status}">${ICON[r.status] || ""} <span class="rid">${r.rule_id}</span>${esc(r.short)}</span><div class="t">${esc(r.finding)}</div><div class="t" style="font-size:11.5px">Rule: ${esc(r.text)}</div></div>` : ""}
      <div class="body">${tabs.length > 1 ? `<div class="tabs">${tabs.map(([k, l]) => `<button data-tab="${k}" class="${tab === k ? "on" : ""}">${l}</button>`).join("")}</div>` : `<div class="lbl" style="margin-bottom:8px">Transcript of the packet page.</div>`}
        ${tab === "pdf" ? `<iframe class="pdfv" src="${pdf}#page=${pageObj.page}&view=FitH" title="Original PDF, page ${pageObj.page}"></iframe>${s.quote ? `<p class="lbl">Looking for: <mark>${esc(s.quote)}</mark></p>` : ""}`
          : tab === "scan" ? `<img src="${img}" alt="Original scan of page ${pageObj.page}">${s.quote ? `<p class="lbl">Looking for: <mark>${esc(s.quote)}</mark></p>` : ""}` : `<pre>${text}</pre>`}</div></aside>`;
  }

  // ---------- decision ----------
  function draft(p, kind) {
    const rules = Object.fromEntries(p.rules.map(r => [r.rule_id, r]));
    const head = `Re: recuperative care referral ${p.id} (${p.patient.summary})\n\nThank you for the referral. Illumination Health + Home has reviewed the packet.\n\n`;
    const qs = (p.questions || []).map((q, i) => `${i + 1}. ${q}`).join("\n");
    if (kind === "deny") return head + "We are not able to accept this patient at this time, based on:\n" +
      (p.fit.blockers.filter((id, _, all) => !(id.startsWith("FORM-") && all.some(x => !x.startsWith("FORM-")))).map(id => `- ${(rules[id] || {}).short || id}${(rules[id] && rules[id].evidence[0]) ? ` (packet p${rules[id].evidence[0].page})` : ""}`).join("\n") || "- [reason]") +
      "\n\nIf the patient's status has changed, please send updated notes and we will review again.\n\n" + sign();
    if (kind === "info") return head + "To finish our review we need the following:\n" + (qs || "1. [question]") + "\n\nWe will reply as soon as we receive them.\n\n" + sign();
    return head + "We can accept this patient for recuperative care." + (qs ? "\n\nBefore discharge, please confirm:\n" + qs : "") + "\n\nPlease call to arrange transport and arrival time.\n\n" + sign();
  }
  function decideBar(p) {
    const d = decisions()[p.id], k = ui.drawer || (d && d.decision);
    const text = ui.drawer ? (ui.draftText ?? draft(p, ui.drawer)) : d ? d.text : "";
    return `<div class="decide"><div class="decide-in gutter">
        <span class="lead">${d ? `Decided: <b>${{ approve: "Approve", info: "Ask for info", deny: "Deny" }[d.decision]}</b> · ${new Date(d.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}${d.by ? ` · by ${esc(d.by)}` : ""}` :"Your decision drafts the reply to the hospital. Nothing is sent from here."}</span>
        <button class="btn approve ${k === "approve" ? "on" : ""}" data-decide="approve">Approve</button>
        <button class="btn info ${k === "info" ? "on" : ""}" data-decide="info">Ask for info</button>
        <button class="btn deny ${k === "deny" ? "on" : ""}" data-decide="deny">Deny</button>
        <button class="btn" data-next>Next ▸</button></div>
      ${ui.drawer ? `<div class="drawer gutter"><textarea id="reply" aria-label="Reply to hospital">${esc(text)}</textarea>
        <div class="row2"><span class="hint">Edit as needed, then copy it into your fax or email system.</span>
          <button class="btn" data-copy>Copy reply</button><button class="btn primary" data-save>Save decision</button><button class="btn" data-cancel>Cancel</button></div></div>` : ""}</div>`;
  }

  // ---------- render + routing ----------
  function route() { const m = location.hash.match(/^#\/?([A-Z]\d\d)?$/); return m && m[1] && byId[m[1]] ? m[1] : null }
  function render() {
    if (!session) { $("#crumb").innerHTML = ""; $("#main").innerHTML = loginView(); $("#dock").innerHTML = ""; return }
    const id = route(), p = id && byId[id];
    $("#crumb").innerHTML = p ? `<a href="#/">Inbox</a> <span>›</span> <span>${p.id}</span>` : `<span>Inbox</span>`;
    const main = $("#main");
    if (!p) { main.innerHTML = inbox(); $("#dock").innerHTML = ""; return }
    main.innerHTML = `<div class="review ${ui.panel ? "withpanel" : ""}"><div>${review(p)}</div>${panel(p)}</div>`;
    $("#dock").innerHTML = decideBar(p);
    const hit = document.getElementById("hit"); if (hit) hit.scrollIntoView({ block: "center" });
  }
  function open(id) { ui.panel = null; ui.drawer = null; ui.draftText = null; location.hash = "#/" + id }

  document.addEventListener("click", e => {
    const t = e.target.closest("button, [data-open]"); if (!t) return;
    const p = byId[route()];
    if (t.dataset.open) return open(t.dataset.open);
    if (t.dataset.filter) { ui.filter = t.dataset.filter; return render() }
    if (t.dataset.page) { ui.panel = { page: +t.dataset.page, quote: t.dataset.quote, tab: null }; return render() }
    if (t.dataset.rule && p) {
      const r = p.rules.find(x => x.rule_id === t.dataset.rule), ev = (r.evidence || [])[0];
      ui.panel = { page: ev ? ev.page : (ui.panel ? ui.panel.page : p.page_list[0].page), quote: ev ? ev.quote : "", rule: r.rule_id }; return render();
    }
    if (t.dataset.nav && p) { const i = p.page_list.findIndex(x => x.page === ui.panel.page) + +t.dataset.nav; ui.panel = { page: p.page_list[i].page, tab: ui.panel.tab }; return render() }
    if (t.dataset.tab) { ui.panel.tab = t.dataset.tab; return render() }
    if ("close" in t.dataset) { ui.panel = null; return render() }
    if (t.dataset.decide && p) { ui.drawer = t.dataset.decide; ui.draftText = null; render(); const ta = $("#reply"); if (ta) ta.focus(); return }
    if ("cancel" in t.dataset) { ui.drawer = null; return render() }
    if ("copy" in t.dataset) {
      const ta = $("#reply");
      const done = () => { t.textContent = "Copied"; setTimeout(() => (t.textContent = "Copy reply"), 1500) };
      try { navigator.clipboard.writeText(ta.value).then(done, () => { ta.select(); t.textContent = "Press Ctrl+C" }) } catch (err) { ta.select(); t.textContent = "Press Ctrl+C" }
      return;
    }
    if ("save" in t.dataset && p) { const v = { ...decisions() }; v[p.id] = { decision: ui.drawer, text: $("#reply").value, at: Date.now(), by: `${who.name} (${who.role})` }; store.set(v); ui.drawer = null; return render() }
    if ("next" in t.dataset && p) {
      const d = decisions(), open_ = P.filter(x => !d[x.id] && x.id !== p.id).sort((a, b) => minsLeft(a) - minsLeft(b));
      return open_.length ? open(open_[0].id) : (location.hash = "#/");
    }
    if ("theme" in t.dataset) { const r = document.documentElement, cur = r.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); r.dataset.theme = cur === "dark" ? "light" : "dark"; return }
    if ("reset" in t.dataset) { store.set({}); return render() }
    if ("who" in t.dataset) { ui.editWho = true; render(); const n = $("#who-name"); if (n) n.focus(); return }
    if ("whosave" in t.dataset) {
      who = { name: ($("#who-name").value.trim() || "Staff").slice(0, 60), role: $("#who-role").value };
      try { localStorage.setItem("referral-desk-user:" + session.email, JSON.stringify(who)) } catch (e) { /* private mode: keep in memory */ }
      ui.editWho = false; return render();
    }
    if ("signout" in t.dataset) { session = null; try { sessionStorage.removeItem("referral-desk-session") } catch (e) { /* ok */ } location.hash = "#/"; return render() }
  });
  document.addEventListener("input", e => {
    if (e.target.id === "q") { ui.q = e.target.value; const pos = e.target.selectionStart; render(); const q = $("#q"); q.focus(); q.setSelectionRange(pos, pos) }
    if (e.target.id === "reply") ui.draftText = e.target.value;
  });
  document.addEventListener("change", e => {
    if (e.target.id === "sort") { ui.sort = e.target.value; render() }
    if (e.target.id === "ihh") { ui.showIhh = e.target.checked; render() }
    if (e.target.id === "file") { upload(e.target.files); e.target.value = "" }
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { if (ui.drawer) ui.drawer = null; else if (ui.panel) ui.panel = null; else if (route()) location.hash = "#/"; render() }
  });
  addEventListener("hashchange", () => { ui.panel = null; ui.drawer = null; render(); scrollTo(0, 0) });
  setInterval(() => { if (!document.activeElement || !["q", "reply", "l-email", "l-pass", "who-name"].includes(document.activeElement.id)) { const y = scrollY; render(); scrollTo(0, y) } }, 30000);
  render();
})();
