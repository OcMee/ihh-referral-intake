"""Build one local HTML page to explore every transcribed packet.

Reads output/R??/R??.pages.json (made by clean.py), writes output/explorer.html.
The page is packet data: open it locally, do not publish, upload or commit it.

  python src/explore.py
  python src/explore.py --out C:\\ihh-private\\output
"""

import argparse
import json
import os
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CRITERIA = REPO / "challenges/1-referral-intake/criteria/admission-criteria.json"
DECISIONS = REPO / "challenges/1-referral-intake/eval/decisions.json"

# Which page doc_types satisfy each checklist item. None = can't tell from doc_type alone.
DOC_MAP = {
    "DOC-1": ["referral_form"],
    "DOC-2": ["face_sheet"],
    "DOC-3": ["calaim_auth"],
    "DOC-4": ["h_and_p"],
    "DOC-5": ["progress_note"],
    "DOC-6": ["vitals"],
    "DOC-7": ["med_list", "med_record"],
    "DOC-8": ["pt_eval", "ot_eval", "nursing_note"],
    "DOC-9": ["labs"],
    "DOC-10": None,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path,
                    default=Path(os.environ.get("IHH_OUTPUT", REPO / "output")))
    args = ap.parse_args()

    packets = []
    for f in sorted(args.out.glob("R??/R??.pages.json")):
        packets.append(json.loads(f.read_text(encoding="utf-8")))
    if not packets:
        raise SystemExit(f"no R??.pages.json under {args.out}. Run clean.py --transcribe first.")

    checklist = json.loads(CRITERIA.read_text())["referral_checklist"]["items"]
    decisions = {p["packet_id"]: p for p in json.loads(DECISIONS.read_text())["packets"]}

    data = {"packets": packets, "checklist": checklist, "doc_map": DOC_MAP,
            "decisions": decisions}
    html = TEMPLATE.replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
    dest = args.out / "explorer.html"
    dest.write_text(html, encoding="utf-8")
    print(f"{len(packets)} packet(s) -> {dest}")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Referral Packet Explorer</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1d2430;--mute:#667085;--line:#e3e7ec;--accent:#1f5f9e;
--ok:#1e7b4a;--okbg:#e6f4ec;--bad:#b42318;--badbg:#fdecea;--unk:#8a6a00;--unkbg:#fff6d6;--hl:#ffe58a}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#12161c;--card:#1a2029;--ink:#e6e9ee;
--mute:#98a2b3;--line:#2c3440;--accent:#7bb3ee;--ok:#6fd39c;--okbg:#173326;--bad:#ff8a80;--badbg:#3a1d1b;
--unk:#f1cf6b;--unkbg:#3a3116;--hl:#6b5a12}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:14px 16px;border-bottom:1px solid var(--line);background:var(--card);position:sticky;top:0;z-index:2}
h1{font-size:18px;margin:0 0 4px}.sub{color:var(--mute);font-size:12px}
nav{display:flex;gap:6px;margin-top:10px;flex-wrap:wrap}
nav button,select,input{font:inherit;color:var(--ink);background:var(--bg);border:1px solid var(--line);
border-radius:6px;padding:6px 10px}
nav button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
main{padding:16px;max-width:1200px;margin:0 auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px;margin-bottom:14px;overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid var(--line);
padding:6px 8px;text-align:left;vertical-align:top}th{color:var(--mute);font-weight:600;white-space:nowrap}
.pill{display:inline-block;padding:1px 7px;border-radius:10px;font-size:12px;font-weight:600}
.yes{background:var(--okbg);color:var(--ok)}.no{background:var(--badbg);color:var(--bad)}
.unk{background:var(--unkbg);color:var(--unk)}
a{color:var(--accent);cursor:pointer;text-decoration:none}
.page{border-top:1px solid var(--line);padding:10px 0}.page h3{margin:0 0 4px;font-size:14px}
pre{white-space:pre-wrap;font:13px/1.5 ui-monospace,Consolas,monospace;margin:6px 0 0}
.note{color:var(--unk);font-size:12px;margin-top:4px}mark{background:var(--hl);color:inherit}
.hit{border-top:1px solid var(--line);padding:8px 0}.muted{color:var(--mute)}
ul{margin:6px 0;padding-left:20px}.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
</style></head><body>
<header><h1>Referral Packet Explorer</h1>
<div class="sub">De-identified packet data. Local only: do not publish, upload or commit.
Transcripts are AI-made; check the original page before relying on a fact.</div>
<nav><button data-v="overview" class="on">Overview</button><button data-v="packet">Packet</button>
<button data-v="search">Search all</button>
<label class="sub" style="margin-left:auto"><input type="checkbox" id="showDec"> show IHH decision</label></nav>
</header><main id="app"></main>
<script>
const D = __DATA__;
const P = D.packets, app = document.getElementById('app');
let view = 'overview', cur = P[0].packet_id;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const showDec = () => document.getElementById('showDec').checked;

function docStatus(p, id) {
  const types = D.doc_map[id];
  if (!types) return ['unk', "can't tell", []];
  const pages = p.pages.filter(x => types.includes(x.doc_type)).map(x => x.page);
  return pages.length ? ['yes', 'p' + pages.join(', '), pages] : ['no', 'not found', []];
}

function overview() {
  let h = `<div class="card"><h2 style="margin:0 0 8px;font-size:16px">${P.length} packet(s) transcribed</h2>
  <table><tr><th>Packet</th><th>Pages</th>${showDec() ? '<th>IHH decision</th>' : ''}
  <th>Check by hand</th>${D.checklist.map(c => `<th title="${esc(c.text)}">${c.id}</th>`).join('')}</tr>`;
  for (const p of P) {
    const dec = D.decisions[p.packet_id]?.decision ?? '?';
    const flags = p.pages.filter(x => x.notes).length;
    h += `<tr><td><a onclick="openPacket('${p.packet_id}')">${p.packet_id}</a></td><td>${p.pages.length}</td>
    ${showDec() ? `<td><span class="pill ${dec === 'approve' ? 'yes' : 'no'}">${dec}</span></td>` : ''}
    <td>${flags ? `<span class="pill unk">${flags} page(s)</span>` : ''}</td>
    ${D.checklist.map(c => { const [k, t] = docStatus(p, c.id); return `<td><span class="pill ${k}">${esc(t)}</span></td>`; }).join('')}</tr>`;
  }
  h += `</table><p class="sub">Document columns follow the IHH referral checklist. Hover a column for its name.
  "not found" means no page of that type was identified, so check the page map before calling it missing.</p></div>`;
  const legend = D.checklist.map(c => `<li><b>${c.id}</b> ${esc(c.text)}</li>`).join('');
  return h + `<div class="card"><b>Checklist</b><ul>${legend}</ul></div>`;
}

function packet() {
  const p = P.find(x => x.packet_id === cur);
  let h = `<div class="card"><div class="row"><select onchange="cur=this.value;render()">
  ${P.map(x => `<option ${x.packet_id === cur ? 'selected' : ''}>${x.packet_id}</option>`).join('')}</select>
  <b>${p.packet_id}</b><span class="muted">${p.pages.length} pages</span>
  ${showDec() ? `<span class="pill ${D.decisions[cur]?.decision === 'approve' ? 'yes' : 'no'}">IHH: ${D.decisions[cur]?.decision}</span>` : ''}</div>`;
  if (p.highlights?.length) h += `<h3 style="font-size:14px;margin:12px 0 4px">What stands out</h3><ul>${p.highlights.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`;
  h += `<h3 style="font-size:14px;margin:12px 0 4px">Page map</h3><table><tr><th>Page</th><th>Document</th><th>Type</th><th>Legibility</th><th>Check by hand</th></tr>
  ${p.pages.map(x => `<tr><td><a href="#pg${x.page}">${x.page}</a></td><td>${esc(x.title)}</td><td>${x.doc_type}</td><td>${x.legibility}</td><td class="note">${esc(x.notes)}</td></tr>`).join('')}</table></div>
  <div class="card"><h3 style="font-size:14px;margin:0">Transcripts</h3>
  ${p.pages.map(x => `<div class="page" id="pg${x.page}"><h3>Page ${x.page}: ${esc(x.title)}</h3>
  <div class="sub">${x.doc_type} | ${x.orientation} | legibility ${x.legibility}</div><pre>${esc(x.text)}</pre>
  ${x.notes ? `<div class="note">Check by hand: ${esc(x.notes)}</div>` : ''}</div>`).join('')}</div>`;
  return h;
}

let q = '';
function search() {
  let h = `<div class="card"><div class="row"><input id="q" placeholder="Search every page, e.g. 5150, insulin, wound, walker"
  value="${esc(q)}" style="flex:1;min-width:220px"><span class="muted" id="cnt"></span></div><div id="hits"></div></div>`;
  setTimeout(() => { const i = document.getElementById('q'); i.focus(); i.oninput = e => { q = e.target.value; runSearch(); }; runSearch(); });
  return h;
}
function runSearch() {
  const out = document.getElementById('hits'), cnt = document.getElementById('cnt');
  if (q.trim().length < 2) { out.innerHTML = '<p class="muted">Type at least 2 characters.</p>'; cnt.textContent = ''; return; }
  const re = new RegExp(q.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  let hits = [], packetsHit = new Set();
  for (const p of P) for (const x of p.pages) for (const line of x.text.split('\n')) {
    re.lastIndex = 0;
    if (re.test(line)) { hits.push([p.packet_id, x, line]); packetsHit.add(p.packet_id); }
  }
  cnt.textContent = `${hits.length} line(s) in ${packetsHit.size} of ${P.length} packet(s)`;
  out.innerHTML = hits.slice(0, 400).map(([id, x, line]) => `<div class="hit"><a onclick="openPacket('${id}',${x.page})">${id} p${x.page}</a>
  <span class="muted">${esc(x.title)}</span><div>${esc(line).replace(new RegExp(re.source, 'gi'), m => `<mark>${m}</mark>`)}</div></div>`).join('')
  || '<p class="muted">No matches. Not found in the transcripts is not the same as not in the packet.</p>';
}

function openPacket(id, page) {
  cur = id; view = 'packet'; render();
  if (page) setTimeout(() => document.getElementById('pg' + page)?.scrollIntoView({block: 'start'}));
}
function render() {
  document.querySelectorAll('nav button').forEach(b => b.classList.toggle('on', b.dataset.v === view));
  app.innerHTML = {overview, packet, search}[view]();
}
document.querySelectorAll('nav button').forEach(b => b.onclick = () => { view = b.dataset.v; render(); });
document.getElementById('showDec').onchange = render;
render();
</script></body></html>
"""

if __name__ == "__main__":
    main()
