"""Render the one-page coordinator summary for every scored packet, plus an index.

Reads output/RXX/RXX.scored.json (from score.py). Writes:
  output/RXX/RXX.summary.html   one page per packet (screen + prints on one letter sheet)
  output/index.html             all packets at a glance
Packet data: open locally, do not publish or commit.

  python src/score.py && python src/onepager.py
"""

import html
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CRITERIA = REPO / "challenges/1-referral-intake/criteria/admission-criteria.json"
DECISIONS = REPO / "challenges/1-referral-intake/eval/decisions.json"

SECTION_ORDER = ["General", "ADLs", "Mobility", "Mental Health", "Cognition", "Other Factors",
                 "End of life care", "Infection Control", "Infection", "Diabetes",
                 "Respiratory Illness", "Cardiac"]
ICON = {"met": "✓", "not_met": "✕", "unknown": "?", "cant_tell": "⌛", "not_applicable": "–"}
BAND_COLOR = {"fit": "var(--ok)", "info": "var(--warn)", "nofit": "var(--bad)"}

CSS = """
:root{--bg:#f4f5f7;--card:#fff;--ink:#17202b;--mute:#5f6b7a;--line:#e2e6eb;--soft:#f7f8fa;
--ok:#1b7a47;--okbg:#e5f3eb;--warn:#a86400;--warnbg:#fdf1dc;--bad:#b42318;--badbg:#fbe9e7;
--gray:#6b7280;--graybg:#eef0f3;--accent:#1f5f9e}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1318;--card:#171c23;--ink:#e7eaee;
--mute:#9aa4b1;--line:#29313b;--soft:#1d232b;--ok:#5fd08f;--okbg:#14301f;--warn:#f0b54a;--warnbg:#33270f;
--bad:#ff8577;--badbg:#3a1a17;--gray:#a0a8b3;--graybg:#232a33;--accent:#7db4ee}}
*{box-sizing:border-box}html{background:var(--bg)}
body{margin:0;color:var(--ink);background:var(--bg);font:13px/1.42 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:16px}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.top h1{font-size:20px;margin:0}.top .sub{color:var(--mute)}
.links a{margin-left:12px;font-size:12px}
.grid{display:grid;grid-template-columns:1fr 250px 1fr;gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.card h2{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin:0 0 8px}
.ringbox{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
.ring text{font-family:inherit}
.band{font-weight:700;font-size:15px;margin-top:4px}
.claude{margin-top:10px;padding-top:10px;border-top:1px dashed var(--line);width:100%;font-size:12px;color:var(--mute)}
.claude b{color:var(--ink)}
.facts{list-style:none;margin:0;padding:0}.facts li{padding:5px 0;border-bottom:1px solid var(--line)}
.facts li:last-child{border:0}.facts .lab{display:inline-block;min-width:92px;color:var(--mute);font-size:11px;font-weight:600}
.pg{font-size:11px;white-space:nowrap}.chk{font-size:10px;color:var(--warn);font-weight:700;margin-left:3px}
.vf{font-size:10px;color:var(--ok);margin-left:2px}
.block{background:var(--badbg);border:1px solid var(--bad);border-radius:8px;padding:8px 10px;margin-bottom:8px}
.block b{color:var(--bad)}.possible{background:var(--warnbg);border-color:var(--warn)}.possible b{color:var(--warn)}
.none{color:var(--ok);font-weight:600}
.conf{padding:6px 0;border-bottom:1px solid var(--line)}.conf:last-child{border:0}
.conf .t{font-weight:600}.q{color:var(--mute);font-style:italic}
.crit{margin-top:12px}.legend{float:right;font-size:11px;color:var(--mute);text-transform:none;letter-spacing:0}
.sec{display:grid;grid-template-columns:120px 1fr;gap:6px;padding:5px 0;border-top:1px solid var(--line)}
.sec .n{color:var(--mute);font-size:11px;font-weight:600;padding-top:3px}
.chips{display:flex;flex-wrap:wrap;gap:4px}
.chip{display:inline-flex;align-items:center;gap:4px;padding:2px 7px;border-radius:12px;font-size:11.5px;border:1px solid transparent;cursor:default}
.chip .id{font-weight:700;font-size:10.5px;opacity:.85}
.s-met{background:var(--okbg);color:var(--ok)}.s-not_met{background:var(--badbg);color:var(--bad);border-color:var(--bad)}
.s-unknown{background:var(--warnbg);color:var(--warn)}.s-cant_tell{background:var(--graybg);color:var(--gray)}
.bottom{display:grid;grid-template-columns:1fr 1.4fr;gap:12px;margin-top:12px}
.miss span{display:inline-block;background:var(--graybg);border-radius:6px;padding:2px 7px;margin:0 4px 4px 0;font-size:12px}
ol{margin:0;padding-left:18px}ol li{margin-bottom:3px}
button{font:inherit;font-size:11px;border:1px solid var(--line);background:var(--soft);color:var(--ink);border-radius:6px;padding:3px 8px;cursor:pointer;float:right}
.foot{color:var(--mute);font-size:11px;margin-top:10px}
@media screen and (max-width:900px){.grid,.bottom{grid-template-columns:1fr}.sec{grid-template-columns:1fr}}
@page{size:letter;margin:8mm}
.printnote{display:none}
@media print{html,body{background:#fff}.wrap{padding:0;max-width:none;zoom:.8}.links,button{display:none}
body{font-size:9.5px;line-height:1.3}.card{padding:6px 8px;border-radius:6px;break-inside:avoid}
.grid{grid-template-columns:1fr 150px 1fr;gap:6px}.bottom{gap:6px;margin-top:6px}.crit{margin-top:6px}
.top{margin-bottom:6px}.top h1{font-size:14px}.ring{width:120px;height:120px}.band{font-size:12px}
.claude .why{display:none}.facts li{padding:2px 0}.facts li:nth-child(n+7){display:none}
.confs .conf:nth-child(n+4){display:none}.block{padding:4px 6px;margin-bottom:4px}.block .q{display:none}
.chip{font-size:8.5px;padding:0 5px}.s-met{display:none}.sec{padding:2px 0}.sec:not(:has(.chip:not(.s-met))){display:none}
#qs li:nth-child(n+7){display:none}.printnote{display:block}.foot{font-size:8.5px;margin-top:4px}}
"""


def e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def pages_link(pages, verified=None) -> str:
    if not pages:
        return ""
    links = ", ".join(f'<a href="pages/p-{int(p):02d}.png" target="_blank">p{int(p)}</a>' for p in pages)
    mark = "" if verified is None else ('<span class="vf" title="quote found on cited page">✓</span>' if verified
                                       else '<span class="chk" title="quote not found on cited page">check</span>')
    return f'<span class="pg">{links}{mark}</span>'


def ring(score: int, band: str, size: int = 170) -> str:
    r, c = 62, 2 * 3.14159 * 62
    return f"""<svg class="ring" width="{size}" height="{size}" viewBox="0 0 160 160" role="img" aria-label="Fit score {score} of 100">
<circle cx="80" cy="80" r="{r}" fill="none" stroke="var(--line)" stroke-width="14"/>
<circle cx="80" cy="80" r="{r}" fill="none" stroke="{BAND_COLOR[band]}" stroke-width="14" stroke-linecap="round"
 stroke-dasharray="{c * score / 100:.1f} {c:.1f}" transform="rotate(-90 80 80)"/>
<text x="80" y="84" text-anchor="middle" font-size="40" font-weight="700" fill="var(--ink)">{score}</text>
<text x="80" y="106" text-anchor="middle" font-size="12" fill="var(--mute)">fit score / 100</text></svg>"""


def chip(r: dict) -> str:
    ev = r.get("evidence", [])
    pg = sorted({x["page"] for x in ev})
    unverified = ev and not r.get("verified")
    tip = f'{r["rule_id"]}: {r["text"]}\n\n{r.get("finding", "")}'
    pages = "".join(f' p{p}' for p in pg)
    return (f'<span class="chip s-{r["status"]}" title="{e(tip)}">{ICON[r["status"]]} '
            f'<span class="id">{e(r["rule_id"])}</span>{e(r["short"])}'
            f'<span class="pg">{pages}</span>{"<span class=chk>check</span>" if unverified else ""}</span>')


def criteria_block(rules: list) -> str:
    shown = [r for r in rules if r["status"] != "not_applicable" and not r.get("superseded_by")]
    na = len(rules) - len(shown)
    groups = {}
    for r in shown:
        groups.setdefault(r["section"], []).append(r)
    order = [s for s in SECTION_ORDER if s in groups] + sorted(s for s in groups if s not in SECTION_ORDER)
    status_rank = {"not_met": 0, "unknown": 1, "cant_tell": 2, "met": 3}
    rows = []
    for s in order:
        items = sorted(groups[s], key=lambda r: status_rank.get(r["status"], 9))
        rows.append(f'<div class="sec"><div class="n">{e(s)}</div><div class="chips">{"".join(chip(r) for r in items)}</div></div>')
    counts = {k: sum(r["status"] == k for r in shown) for k in ("met", "not_met", "unknown", "cant_tell")}
    return f"""<div class="card crit"><h2>Criteria check
<span class="legend">✓ met {counts['met']} · ✕ not met {counts['not_met']} · ? unknown {counts['unknown']} · ⌛ can't tell (redacted) {counts['cant_tell']} · {na} not applicable hidden · hover a chip for the finding</span></h2>
{''.join(rows)}</div>"""


def render(d: dict, checklist: dict) -> str:
    fit, pt = d["fit"], d.get("patient", {})
    rules = {r["rule_id"]: r for r in d["rules"]}

    facts = "".join(
        f'<li><span class="lab">{e(f["label"])}</span>{e(f["text"])} {pages_link(f.get("pages"), f.get("verified"))}</li>'
        for f in d.get("key_facts", []))

    blocks = ""
    for rid in fit["blockers"]:
        r = rules.get(rid, {"short": "No general eligibility met", "finding": "", "evidence": []})
        q = r["evidence"][0] if r.get("evidence") else None
        blocks += (f'<div class="block"><b>⛔ {e(rid)} · {e(r["short"])}</b><br>{e(r.get("finding"))}'
                   + (f'<br><span class="q">"{e(q["quote"])}"</span> {pages_link([q["page"]], q["verified"])}' if q else "")
                   + "</div>")
    for rid in fit["possible_blockers"]:
        r = rules[rid]
        blocks += (f'<div class="block possible"><b>⚠ Possible: {e(rid)} · {e(r["short"])}</b><br>'
                   f'{e(r.get("finding"))}<br><span class="chk">evidence not verified, check by hand</span></div>')
    if not blocks:
        blocks = '<div class="none">No verified blockers found</div>'

    confs = "".join(
        f'<div class="conf"><span class="t">{e(c.get("topic"))}</span> · {e(c.get("note"))} '
        + " ".join(pages_link([s["page"]], s.get("verified")) for s in c.get("sources", [])) + "</div>"
        for c in d.get("conflicts", [])) or '<div class="muted">None found</div>'

    missing = "".join(f'<span>{e(checklist.get(x["doc_id"], x["doc_id"]))}</span>'
                      for x in d.get("documents", []) if x["present"] == "no")
    qs = d.get("questions_for_hospital", [])
    qtext = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(qs))
    cf = d.get("claude_fit", {})
    v = d["verification"]

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{e(d['packet_id'])} Referral Summary</title>
<style>{CSS}</style></head><body><div class="wrap">
<div class="top"><div><h1>{e(d['packet_id'])} · {e(pt.get('summary'))}</h1>
<div class="sub">{d['pages']} pages · {e(pt.get('insurance'))} · Housing: {e(pt.get('housing'))} · Admitted for: {e(pt.get('admit_reason'))} {pages_link(pt.get('pages'))}</div></div>
<div class="links"><a href="../index.html">All referrals</a><a href="{e(d['packet_id'])}.readable.pdf" target="_blank">Readable packet</a></div></div>

<div class="grid">
<div class="card"><h2>Key facts</h2><ul class="facts">{facts}</ul></div>
<div class="card ringbox">{ring(fit['score'], fit['band'])}
<div class="band" style="color:{BAND_COLOR[fit['band']]}">{e(fit['label'])}</div>
<div class="claude">Claude's read: <b>{e(cf.get('score', '–'))}/100 · {e(str(cf.get('recommendation', '')).replace('_', ' '))}</b><br><span class="why">{e(cf.get('reason'))}</span></div></div>
<div class="card"><h2>Blockers</h2>{blocks}<h2 style="margin-top:10px">Form vs chart</h2><div class="confs">{confs}</div></div>
</div>

{criteria_block(d['rules'])}

<div class="bottom">
<div class="card"><h2>Missing from packet</h2><div class="miss">{missing or '<span class="none">Nothing from the checklist</span>'}</div></div>
<div class="card"><h2>Ask the hospital <button onclick="navigator.clipboard.writeText(document.getElementById('qs').innerText)">Copy</button></h2>
<ol id="qs">{''.join(f'<li>{e(q)}</li>' for q in qs) or '<li>No questions</li>'}</ol></div>
</div>

<div class="foot"><span class="printnote">Printed view is trimmed: met criteria, extra facts, conflicts and questions are on the screen version.</span>AI-prepared summary for a coordinator. The coordinator decides. Ring = rule-based score (hand-set weights, not fitted; see score.py).
✓ = quote found on the cited page ({v['verified']}/{v['quotes']} criteria quotes verified). "check" = not found, read the page. Page links open the original scan.</div>
</div></body></html>"""


def index(scored: list, decisions: dict) -> str:
    rows = ""
    for d in scored:
        f, cf = d["fit"], d.get("claude_fit", {})
        dec = decisions.get(d["packet_id"], "?")
        rows += f"""<tr><td><a href="{d['packet_id']}/{d['packet_id']}.summary.html"><b>{d['packet_id']}</b></a></td>
<td>{e(d.get('patient', {}).get('summary'))}</td><td>{d['pages']}</td>
<td><span class="pill" style="background:{BAND_COLOR[f['band']]}">{f['score']}</span> {e(f['label'])}</td>
<td>{e(cf.get('score'))} · {e(str(cf.get('recommendation', '')).replace('_', ' '))}</td>
<td>{e(', '.join(f['blockers']) or '–')}</td><td class="dec">{e(dec)}</td></tr>"""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Referral Intake Summaries</title><style>{CSS}
table{{width:100%;border-collapse:collapse;background:var(--card)}}th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{color:var(--mute);font-size:11px;text-transform:uppercase;letter-spacing:.05em}}
.pill{{display:inline-block;min-width:34px;text-align:center;color:#fff;border-radius:12px;padding:1px 8px;font-weight:700}}
.dec{{display:none}}body.show .dec{{display:table-cell}}.card{{overflow-x:auto}}</style></head><body><div class="wrap">
<div class="top"><div><h1>Referral intake</h1><div class="sub">{len(scored)} referrals · packet data, local only</div></div>
<label class="sub"><input type="checkbox" onchange="document.body.classList.toggle('show',this.checked)"> show IHH decision</label></div>
<div class="card"><table><tr><th>Packet</th><th>Patient</th><th>Pages</th><th>Fit score</th><th>Claude's read</th><th>Blockers</th><th class="dec">IHH decision</th></tr>{rows}</table></div>
<div class="foot">Fit score is rule-based with hand-set weights. The coordinator decides.</div></div></body></html>"""


def main(argv: list[str]) -> None:
    out_root = Path(argv[1]) if len(argv) > 1 else REPO / "output"
    checklist = {x["id"]: x["text"] for x in json.loads(CRITERIA.read_text())["referral_checklist"]["items"]}
    decisions = {p["packet_id"]: p["decision"] for p in json.loads(DECISIONS.read_text())["packets"]}
    scored = []
    for f in sorted(out_root.glob("R??/R??.scored.json")):
        d = json.loads(f.read_text())
        (f.parent / f"{d['packet_id']}.summary.html").write_text(render(d, checklist), encoding="utf-8")
        scored.append(d)
    (out_root / "index.html").write_text(index(scored, decisions), encoding="utf-8")
    print(f"{len(scored)} summaries -> {out_root}/index.html")


if __name__ == "__main__":
    main(sys.argv)
