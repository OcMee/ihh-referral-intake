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

  // ---------- helpers ----------
  function minsLeft(p) { return SLA - p.received_min - (Date.now() - LOADED) / 60000 }
  function clock(p) {
    const d = decisions()[p.id];
    if (d) return `<span class="done ${d.decision}">${{ approve: "Approved", info: "Asked for info", deny: "Denied" }[d.decision]}</span>`;
    const m = minsLeft(p), a = Math.abs(m), h = Math.floor(a / 60), mm = Math.floor(a % 60);
    const txt = m < 0 ? `overdue ${h ? h + "h " : ""}${mm}m` : `${h}h ${String(mm).padStart(2, "0")}m left`;
    return `<span class="clock ${m < 0 ? "over" : m < 30 ? "soon" : ""}" title="Simulated arrival time"><i></i>${txt}</span>`;
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
      <span class="c-top"><span class="id">${p.id}</span>${clock(p)}</span>
      <span class="c-main">${dial(p.fit.score, p.fit.band)}<span class="c-who"><b>${esc(p.patient.summary)}</b><small>${esc(p.patient.admit_reason || "")}</small></span></span>
      <span class="c-bl">${bl.length ? bl.slice(0, 3).map(x => `<span class="tagx">${esc(x)}</span>`).join("") + (bl.length > 3 ? `<span class="tagx more">+${bl.length - 3}</span>` : "") : `<span class="calm">No hard stop</span>`}</span>
      <span class="c-foot"><span class="sla ${m < 0 ? "over" : m < 30 ? "soon" : ""}" title="Share of the 2-hour window used"><i style="width:${(used * 100).toFixed(0)}%"></i></span>
        <span class="num lbl">${p.pages} pp${ui.showIhh && p.ihh ? ` · IHH ${p.ihh}` : ""}</span></span>
    </button>`;
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
        <div class="h-copy"><p class="eyebrow">Referral Desk · Illumination Health + Home</p>
          <h1>Every referral on one page, answered inside two hours.</h1>
          <p class="lede">Faxed packets are read page by page and checked against IHH’s admission rules. Each finding links to the page it came from.</p></div>
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
      <div class="board">${lanes}</div>
      <p class="foot">Countdowns use simulated arrival times. Fit score is rule-based: a verified blocker caps it at 15; unknowns lower it. Weights were hand-tuned on IHH’s 11 past decisions, so it guides the coordinator and does not decide. ${esc(APP.meta.note || "")}</p>`;
  }

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
        <div class="meta">${p.pages} pages · ${esc(p.patient.insurance || "")} · Housing: ${esc(p.patient.housing || "")} · Admitted for: ${esc(p.patient.admit_reason || "")} ${(p.patient.pages || []).map(x => pg(x)).join(" ")}</div></div>
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
      <div class="pf-row">${link(p.pdf, "Original PDF", `${p.pages} pages as faxed`)}${link(p.readable, "Readable PDF", "each page beside its transcript")}${link(p.docx, "Word copy", "compact, in the form styles")}</div>
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
    const img = p.img ? p.img.replace("{nn}", String(pageObj.page).padStart(2, "0")) : null;
    const pdf = p.pdf && !APP.meta.artifact ? p.pdf : null;
    const tabs = [pdf && ["pdf", "Original PDF"], img && ["scan", "Scan image"], ["text", "Transcript"]].filter(Boolean);
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
      "\n\nIf the patient's status has changed, please send updated notes and we will review again.\n\nIHH Referral Coordinator";
    if (kind === "info") return head + "To finish our review we need the following:\n" + (qs || "1. [question]") + "\n\nWe will reply as soon as we receive them.\n\nIHH Referral Coordinator";
    return head + "We can accept this patient for recuperative care." + (qs ? "\n\nBefore discharge, please confirm:\n" + qs : "") + "\n\nPlease call to arrange transport and arrival time.\n\nIHH Referral Coordinator";
  }
  function decideBar(p) {
    const d = decisions()[p.id], k = ui.drawer || (d && d.decision);
    const text = ui.drawer ? (ui.draftText ?? draft(p, ui.drawer)) : d ? d.text : "";
    return `<div class="decide"><div class="decide-in gutter">
        <span class="lead">${d ? `Decided: <b>${{ approve: "Approve", info: "Ask for info", deny: "Deny" }[d.decision]}</b> · ${new Date(d.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}` : "Your decision drafts the reply to the hospital. Nothing is sent from here."}</span>
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
    if ("save" in t.dataset && p) { const v = { ...decisions() }; v[p.id] = { decision: ui.drawer, text: $("#reply").value, at: Date.now() }; store.set(v); ui.drawer = null; return render() }
    if ("next" in t.dataset && p) {
      const d = decisions(), open_ = P.filter(x => !d[x.id] && x.id !== p.id).sort((a, b) => minsLeft(a) - minsLeft(b));
      return open_.length ? open(open_[0].id) : (location.hash = "#/");
    }
    if ("theme" in t.dataset) { const r = document.documentElement, cur = r.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); r.dataset.theme = cur === "dark" ? "light" : "dark"; return }
    if ("reset" in t.dataset) { store.set({}); return render() }
  });
  document.addEventListener("input", e => {
    if (e.target.id === "q") { ui.q = e.target.value; const pos = e.target.selectionStart; render(); const q = $("#q"); q.focus(); q.setSelectionRange(pos, pos) }
    if (e.target.id === "reply") ui.draftText = e.target.value;
  });
  document.addEventListener("change", e => {
    if (e.target.id === "sort") { ui.sort = e.target.value; render() }
    if (e.target.id === "ihh") { ui.showIhh = e.target.checked; render() }
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") { if (ui.drawer) ui.drawer = null; else if (ui.panel) ui.panel = null; else if (route()) location.hash = "#/"; render() }
  });
  addEventListener("hashchange", () => { ui.panel = null; ui.drawer = null; render(); scrollTo(0, 0) });
  setInterval(() => { if (!document.activeElement || !["q", "reply"].includes(document.activeElement.id)) { const y = scrollY; render(); scrollTo(0, y) } }, 30000);
  render();
})();
