"""Verify evidence and compute the rule-based Fit score for one packet.

Input:  output/RXX/RXX.json        (criteria check, see CONTRACT.md)
        output/RXX/RXX.pages.json  (transcript the quotes must come from)
Output: output/RXX/RXX.scored.json (same data + verified flags, blockers, fit score)

The score is deliberately simple so every point can be explained:
  start 100
  verified blocker (exclusion applies / must-rule failed)  -> score capped at 15
  unverified possible blocker                              -> -15, "check by hand"
  conditional arrangement missing (not_met / unknown)      -> -10 / -4
  key rule unknown or can't tell                           -> -8
  other must/exclude rule unknown                          -> -2
  form vs chart conflict                                   -> -5 (max 4 counted)
  required document missing                                -> -3
Bands: 70+ likely fit, 40-69 needs info, under 40 likely not a fit.
Weights were set by hand, not fitted; 11 packets are too few to fit them.
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CRITERIA = REPO / "challenges/1-referral-intake/criteria/admission-criteria.json"

KEY_RULES = {"ADL-1", "ADL-2", "ADL-3", "MOB-1", "MOB-3", "MOB-4", "MH-1", "MH-2", "MH-3",
             "COG-1", "COG-2", "OTH-1", "OTH-4"}
DOC_SKIP = {"DOC-5", "DOC-9", "DOC-10"}  # "if needed" or not checkable from the packet

SHORT = {
    "GEN-1": "Unhoused and too ill to recover", "GEN-2": "Lives alone, no supports",
    "GEN-3": "Re-hospitalization risk", "ADL-1": "Independent ADLs", "ADL-2": "Independent hygiene",
    "ADL-3": "Independent toileting", "MOB-1": "Uses DME independently", "MOB-2": "PT/OT notes sent",
    "MOB-3": "Walks 100 ft", "MOB-4": "Transfers independently", "MH-1": "Mentally stable on meds",
    "MH-2": "No suicidal ideation", "MH-3": "No command hallucinations", "MH-4": "72h hold after alcohol",
    "MH-5": "No conservatorship/FSP", "COG-1": "Self-administers meds", "COG-2": "AOx4",
    "OTH-1": "Not aggressive", "OTH-2": "Sex offender case by case", "OTH-3": "IV access + home health",
    "OTH-4": "Not on isolation", "EOL-1": "Hospice arranged", "INF-1": "MRSA swab negative",
    "INF-2": "COVID swab within 24h", "DM-1": "5 glucose readings", "DM-2": "ED: glucose controlled",
    "DM-3": "Insulin started 24h+ ago", "DM-4": "Poor control: plan in place", "DM-5": "Uses glucometer",
    "DM-6": "Gives own insulin", "ID-1": "Last 5 vitals sent", "ID-2": "Takes oral antibiotics",
    "ID-3": "IV abx: home health ordered", "RESP-1": "Chest imaging sent", "RESP-2": "Last 5 vitals sent",
    "RESP-3": "O2 ordered + tank ready", "RESP-4": "RT notes sent", "CARD-1": "Vitals, BP stable on PO",
    "CARD-2": "3 troponins sent", "CARD-3": "EKG sent", "CARD-4": "AFib rate controlled",
    "CARD-5": "EF 25% or higher", "CARD-6": "No IV BP meds",
    "FORM-X1": "Not cognitively impaired", "FORM-X2": "Can do ADLs", "FORM-X4": "No uncleared MRSA/TB/C-diff",
    "FORM-X5": "Not refusing detox", "FORM-X7": "Not aggressive (form)",
}


def load_rules() -> dict:
    d = json.loads(CRITERIA.read_text())
    rules = {}
    for r in d["general"]["any_of"]:
        rules[r["id"]] = {"kind": "general", "section": "General", "text": r["text"]}
    for r in d["rules"]:
        rules[r["id"]] = {"kind": r["kind"], "section": r["section"], "text": r["text"]}
    for s in d["by_system"]:
        for r in s.get("eligible", []):
            rules[r["id"]] = {"kind": r.get("kind", "eligible"), "section": s["system"], "text": r["text"]}
        for r in s.get("ineligible", []):
            rules[r["id"]] = {"kind": "exclude", "section": s["system"], "text": r["text"]}
    form = d["referral_form_screen"]
    for r in form["must_meet_all"]:
        rules[r["id"]] = {"kind": "must", "section": "Referral form", "text": r["text"],
                          "superseded_by": r.get("superseded_by")}
    for r in form["not_eligible_if"]:
        rules[r["id"]] = {"kind": "exclude", "section": "Referral form", "text": r["text"],
                          "superseded_by": r.get("superseded_by")}
    for rid, r in rules.items():
        r["short"] = SHORT.get(rid) or (r["text"][:38].rstrip() + ("..." if len(r["text"]) > 38 else ""))
    return rules


def norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def verify(ev: dict, page_text: dict) -> bool:
    q = norm(ev.get("quote", ""))
    return bool(q) and q in page_text.get(ev.get("page"), "")


def score_packet(check: dict, pages: dict, rules: dict) -> dict:
    page_text = {p["page"]: norm(p["text"]) for p in pages["pages"]}
    out = dict(check)
    out["pages"] = len(pages["pages"])

    # verify every quote
    for r in out["rules"]:
        for ev in r.get("evidence", []):
            ev["verified"] = verify(ev, page_text)
        r["verified"] = bool(r.get("evidence")) and all(ev["verified"] for ev in r["evidence"])
        meta = rules.get(r["rule_id"], {"kind": "unknown", "section": "Other", "text": "", "short": r["rule_id"]})
        r.update(kind=meta["kind"], section=meta["section"], text=meta["text"], short=meta["short"],
                 superseded_by=meta.get("superseded_by"))
    for f in out.get("key_facts", []):
        f["verified"] = verify({"page": f.get("quote_page"), "quote": f.get("quote", "")}, page_text)
    for c in out.get("conflicts", []):
        for s in c.get("sources", []):
            s["verified"] = verify(s, page_text)

    score, reasons, blockers, possible = 100, [], [], []

    def hit(points, why):
        nonlocal score
        score -= points
        reasons.append({"points": -points, "why": why})

    for r in out["rules"]:
        rid, kind, st = r["rule_id"], r["kind"], r["status"]
        if r.get("superseded_by"):
            continue
        if st == "not_met" and kind in ("must", "exclude"):
            (blockers if r["verified"] else possible).append(rid)
        elif kind == "conditional" and st == "not_met":
            hit(10, f"{rid} arrangement not in place")
        elif kind == "conditional" and st == "unknown":
            hit(4, f"{rid} arrangement not confirmed")
        elif st in ("unknown", "cant_tell") and rid in KEY_RULES:
            hit(8, f"{rid} {'unknown' if st == 'unknown' else 'can not tell (redacted)'}")
        elif st in ("unknown", "cant_tell") and kind in ("must", "exclude"):
            hit(2, f"{rid} unknown")

    gen = [r for r in out["rules"] if r["kind"] == "general"]
    if gen and all(r["status"] == "not_met" and r["verified"] for r in gen):
        blockers.append("GEN")

    for rid in possible:
        hit(15, f"{rid} may fail, evidence not verified")
    for c in out.get("conflicts", [])[:4]:
        hit(5, f"form vs chart: {c.get('topic', '')}")
    for d in out.get("documents", []):
        if d["present"] == "no" and d["doc_id"] not in DOC_SKIP:
            hit(3, f"{d['doc_id']} missing")

    score = max(0, min(100, score))
    if blockers:
        score = min(score, 15)
    band = "fit" if score >= 70 else "info" if score >= 40 else "nofit"
    out["fit"] = {
        "score": score,
        "band": band,
        "label": {"fit": "Likely fit", "info": "Needs info", "nofit": "Likely not a fit"}[band],
        "blockers": blockers,
        "possible_blockers": possible,
        "reasons": reasons,
    }
    total_ev = [ev for r in out["rules"] for ev in r.get("evidence", [])]
    out["verification"] = {"quotes": len(total_ev), "verified": sum(ev["verified"] for ev in total_ev)}
    return out


def main(argv: list[str]) -> None:
    out_root = Path(argv[1]) if len(argv) > 1 else REPO / "output"
    rules = load_rules()
    for f in sorted(out_root.glob("R??/R??.json")):
        pid = f.stem
        pages = json.loads((f.parent / f"{pid}.pages.json").read_text())
        scored = score_packet(json.loads(f.read_text()), pages, rules)
        (f.parent / f"{pid}.scored.json").write_text(json.dumps(scored, indent=2))
        v = scored["verification"]
        print(f"{pid}: fit {scored['fit']['score']:3d} {scored['fit']['label']:<17} "
              f"blockers={scored['fit']['blockers']} quotes {v['verified']}/{v['quotes']} verified")


if __name__ == "__main__":
    main(sys.argv)
