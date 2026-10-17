"""Build three FICTIONAL referral packets and run them through the real scoring and one-pager code.

Nothing here comes from a real packet. Names, ages, findings and pages are invented so the
app can be shared publicly. Output: demo/site/index.html (one file, all three summaries).

  python demo/make_demo.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "src"))
import onepager  # noqa: E402
import score  # noqa: E402

BANNER = ("Fictional demo cases. These patients are invented to show how the tool works. "
          "No real patient data is on this page.")


def page(n, doc_type, title, text):
    return {"page": n, "doc_type": doc_type, "title": title, "orientation": "normal",
            "legibility": "good", "text": text, "notes": ""}


def ev(pages, n, quote):
    assert quote in pages[n - 1]["text"], (n, quote)
    return {"page": n, "quote": quote}


def rule(pages, rid, status, finding, *cites):
    return {"rule_id": rid, "status": status, "finding": finding,
            "evidence": [ev(pages, n, q) for n, q in cites]}


def fact(pages, label, text, n, quote, extra=()):
    ev(pages, n, quote)
    return {"label": label, "text": text, "pages": [n, *extra], "quote": quote, "quote_page": n}


def docs(present):
    return [{"doc_id": f"DOC-{i}", "present": present.get(i, "yes"), "pages": []} for i in range(1, 11)]


# ---------- D01: likely fit ----------
p1 = [
    page(1, "referral_form", "IHH Referral Form",
         "Housing: Currently unhoused [X]\nChief complaint: Cellulitis right forearm\nAmbulatory: Yes  Assistive device: No\n"
         "Self administer all meds: Yes\nAny wounds? Yes, right forearm, home health ordered for dressing changes\nMental health: None"),
    page(2, "h_and_p", "History and Physical",
         "52 y.o. male, unhoused, admitted with right forearm cellulitis. Started IV cefazolin, improving.\n"
         "Plan: transition to oral cephalexin 500 mg four times daily for 7 days at discharge.\n"
         "Neuro: Alert and oriented x4. Psych: Calm, cooperative, denies SI/HI, no hallucinations."),
    page(3, "pt_eval", "PT Evaluation",
         "Independent with bed mobility and transfers.\nAmbulated 300 ft independently, no assistive device.\n"
         "Independent with ADLs including showering. No skilled PT needs."),
    page(4, "labs", "Labs and swabs",
         "MRSA nares PCR: Negative\nSARS-CoV-2 rapid antigen: Negative\nWound culture: MSSA, sensitive to cefazolin"),
    page(5, "orders", "Discharge orders",
         "Home health RN referral accepted for dressing changes three times weekly.\n30 day supply of medications sent to bedside."),
]
c1 = {
    "packet_id": "D01",
    "patient": {"summary": "52M (fictional), right forearm cellulitis, finishing on oral antibiotics, unhoused",
                "age": "52", "sex": "M", "insurance": "Medi-Cal (fictional)", "housing": "Currently unhoused",
                "admit_reason": "Right forearm cellulitis", "pages": [1, 2]},
    "key_facts": [
        fact(p1, "Infection", "Switching to oral cephalexin for 7 days at discharge.", 2, "transition to oral cephalexin 500 mg"),
        fact(p1, "Mobility", "Walks 300 ft independently, no device.", 3, "Ambulated 300 ft independently"),
        fact(p1, "Cognition", "Alert and oriented x4.", 2, "Alert and oriented x4"),
        fact(p1, "Wounds", "Forearm wound; home health RN accepted for dressing changes.", 5, "Home health RN referral accepted"),
        fact(p1, "Infection", "MRSA and COVID swabs negative.", 4, "MRSA nares PCR: Negative"),
    ],
    "rules": [
        rule(p1, "GEN-1", "met", "Unhoused and recovering from cellulitis.", (1, "Currently unhoused [X]")),
        rule(p1, "ADL-1", "met", "Independent with ADLs per PT.", (3, "Independent with ADLs including showering")),
        rule(p1, "MOB-2", "met", "PT evaluation sent.", (3, "Independent with bed mobility and transfers")),
        rule(p1, "MOB-3", "met", "Walks 300 ft.", (3, "Ambulated 300 ft independently")),
        rule(p1, "MH-2", "met", "Denies SI.", (2, "denies SI/HI")),
        rule(p1, "MH-3", "met", "No hallucinations.", (2, "no hallucinations")),
        rule(p1, "COG-1", "met", "Self-administers meds per form.", (1, "Self administer all meds: Yes")),
        rule(p1, "COG-2", "met", "AOx4 in H&P.", (2, "Alert and oriented x4")),
        rule(p1, "OTH-1", "met", "Calm and cooperative.", (2, "Calm, cooperative")),
        rule(p1, "INF-1", "met", "MRSA negative.", (4, "MRSA nares PCR: Negative")),
        rule(p1, "INF-2", "cant_tell", "COVID negative; test date not shown on the page.", (4, "SARS-CoV-2 rapid antigen: Negative")),
        rule(p1, "INT-E2", "met", "Wound care arranged with home health.", (5, "dressing changes three times weekly")),
        rule(p1, "ID-2", "met", "Oral antibiotic plan at discharge.", (2, "oral cephalexin 500 mg four times daily")),
    ],
    "documents": docs({}),
    "conflicts": [],
    "questions_for_hospital": ["Please confirm the COVID test was within 24 hours of discharge."],
    "claude_fit": {"score": 85, "recommendation": "approve",
                   "reason": "Meets housing, mobility, cognition and ADL rules with documents; wound care is arranged. Only the COVID test timing needs confirming."},
}

# ---------- D02: needs info ----------
p2 = [
    page(1, "referral_form", "IHH Referral Form",
         "Housing: Currently unhoused [X]\nChief complaint: Pneumonia\nRequires O2? No\nAmbulatory: Yes  Assistive device: walker\nWounds: No"),
    page(2, "h_and_p", "History and Physical",
         "68 y.o. female, unhoused, admitted with community acquired pneumonia.\nOn IV ceftriaxone, plan to reassess for oral step-down.\n"
         "Currently on 2L nasal cannula, weaning as tolerated.\nNeuro: Alert and oriented x4."),
    page(3, "progress_note", "Progress Note",
         "Patient pleasant. Still on 2L O2 at rest. PT evaluation ordered, pending.\nHome oxygen needs to be assessed before discharge."),
    page(4, "labs", "Labs",
         "WBC 11.2\nChest X-ray: right lower lobe infiltrate\nSARS-CoV-2 PCR: Negative"),
]
c2 = {
    "packet_id": "D02",
    "patient": {"summary": "68F (fictional), pneumonia on IV antibiotics and 2L oxygen, unhoused",
                "age": "68", "sex": "F", "insurance": "Medi-Cal (fictional)", "housing": "Currently unhoused",
                "admit_reason": "Community acquired pneumonia", "pages": [1, 2]},
    "key_facts": [
        fact(p2, "Meds/IV/O2", "Still on 2L oxygen; form says no oxygen.", 3, "Still on 2L O2 at rest", extra=(1,)),
        fact(p2, "Infection", "IV ceftriaxone; oral step-down not decided.", 2, "plan to reassess for oral step-down"),
        fact(p2, "Mobility", "PT evaluation still pending.", 3, "PT evaluation ordered, pending"),
        fact(p2, "Cognition", "Alert and oriented x4.", 2, "Alert and oriented x4"),
    ],
    "rules": [
        rule(p2, "GEN-1", "met", "Unhoused and recovering from pneumonia.", (1, "Currently unhoused [X]")),
        rule(p2, "COG-2", "met", "AOx4.", (2, "Alert and oriented x4")),
        rule(p2, "MOB-2", "not_met", "PT/OT notes not sent; PT pending.", (3, "PT evaluation ordered, pending")),
        rule(p2, "MOB-3", "unknown", "Walking distance not documented."),
        rule(p2, "MOB-1", "unknown", "Uses a walker per form; independence with it not documented."),
        rule(p2, "ADL-1", "unknown", "ADLs not documented."),
        rule(p2, "MH-2", "unknown", "No suicide screen in packet."),
        rule(p2, "ADL-3", "unknown", "Toileting not documented."),
        rule(p2, "COG-1", "unknown", "Not stated whether she manages her own meds."),
        rule(p2, "MH-1", "unknown", "Mental health not documented."),
        rule(p2, "OTH-4", "unknown", "Isolation status not stated."),
        rule(p2, "RESP-3", "unknown", "On 2L O2; home oxygen order not arranged yet.", (3, "Home oxygen needs to be assessed")),
        rule(p2, "ID-3", "unknown", "IV antibiotics; home health or oral switch not confirmed.", (2, "On IV ceftriaxone")),
        rule(p2, "INF-1", "not_met", "No MRSA swab in packet."),
        rule(p2, "INF-2", "met", "COVID PCR negative.", (4, "SARS-CoV-2 PCR: Negative")),
        rule(p2, "RESP-1", "met", "Chest X-ray sent.", (4, "Chest X-ray: right lower lobe infiltrate")),
    ],
    "documents": docs({8: "no"}),
    "conflicts": [{"topic": "Oxygen", "rule_ids": ["RESP-3"],
                   "sources": [ev(p2, 1, "Requires O2? No"), ev(p2, 3, "Still on 2L O2 at rest")],
                   "note": "Form says no oxygen, progress note says 2L at rest. Chart wins."}],
    "questions_for_hospital": [
        "Will she go home on oxygen? If so, please send the order and confirm a tank will come with her.",
        "Will she switch to oral antibiotics before discharge, or is home health arranged for IV?",
        "Please send the PT evaluation when done, including walking distance with her walker.",
        "Please send an MRSA swab result.",
    ],
    "claude_fit": {"score": 55, "recommendation": "needs_info",
                   "reason": "No hard stop, but oxygen and IV plans (RESP-3, ID-3) and PT (MOB-2) are open. Approvable if the hospital answers."},
}

# ---------- D03: likely not a fit ----------
p3 = [
    page(1, "referral_form", "IHH Referral Form",
         "Housing: Currently unhoused [X]\nChief complaint: Hip fracture s/p repair\nAmbulatory: Yes\nCognitive impairment: [ ]"),
    page(2, "h_and_p", "History and Physical",
         "81 y.o. male, unhoused, fall with left hip fracture, s/p surgical repair.\nNeuro: Oriented to self only. Confused, follows simple commands."),
    page(3, "pt_eval", "PT Evaluation",
         "Transfers: moderate assist x2.\nAmbulation: 10 ft with front wheeled walker and moderate assist.\n"
         "Needs moderate assist with lower body dressing and toileting.\nRecommend skilled nursing facility."),
]
c3 = {
    "packet_id": "D03",
    "patient": {"summary": "81M (fictional), hip fracture after a fall, confused, unhoused",
                "age": "81", "sex": "M", "insurance": "Medicare (fictional)", "housing": "Currently unhoused",
                "admit_reason": "Left hip fracture, surgically repaired", "pages": [1, 2]},
    "key_facts": [
        fact(p3, "Cognition", "Oriented to self only; form leaves cognitive impairment unchecked.", 2, "Oriented to self only", extra=(1,)),
        fact(p3, "Mobility", "Needs moderate assist of 2 for transfers; walks 10 ft.", 3, "Transfers: moderate assist x2"),
        fact(p3, "Other", "PT recommends a skilled nursing facility.", 3, "Recommend skilled nursing facility"),
    ],
    "rules": [
        rule(p3, "GEN-1", "met", "Unhoused, recovering from surgery.", (1, "Currently unhoused [X]")),
        rule(p3, "MOB-4", "not_met", "Cannot transfer independently.", (3, "Transfers: moderate assist x2")),
        rule(p3, "MOB-3", "not_met", "Walks 10 ft with assist, not 100 ft.", (3, "Ambulation: 10 ft with front wheeled walker")),
        rule(p3, "ADL-3", "not_met", "Needs assist with toileting.", (3, "Needs moderate assist with lower body dressing and toileting")),
        rule(p3, "COG-2", "not_met", "Oriented to self only.", (2, "Oriented to self only")),
        rule(p3, "FORM-X1", "not_met", "Chart shows confusion; form leaves cognitive impairment unchecked.", (2, "Confused, follows simple commands")),
        rule(p3, "MH-2", "unknown", "No suicide screen in packet."),
        rule(p3, "INF-1", "not_met", "No MRSA swab in packet."),
    ],
    "documents": docs({7: "no", 6: "no"}),
    "conflicts": [{"topic": "Cognition", "rule_ids": ["FORM-X1", "COG-2"],
                   "sources": [ev(p3, 1, "Cognitive impairment: [ ]"), ev(p3, 2, "Oriented to self only")],
                   "note": "Form leaves cognitive impairment unchecked; H&P says oriented to self only. Chart wins."}],
    "questions_for_hospital": ["Has a skilled nursing facility been considered, as PT recommends?"],
    "claude_fit": {"score": 10, "recommendation": "deny",
                   "reason": "Needs hands-on help with transfers and toileting (MOB-4, ADL-3) and is not oriented (COG-2). PT recommends a skilled nursing facility."},
}


def main() -> None:
    rules = score.load_rules()
    checklist = {x["id"]: x["text"] for x in json.loads(onepager.CRITERIA.read_text())["referral_checklist"]["items"]}
    scored = []
    for check, pages in ((c1, p1), (c2, p2), (c3, p3)):
        d = score.score_packet(check, {"pages": pages}, rules)
        scored.append(d)
        print(d["packet_id"], d["fit"]["score"], d["fit"]["label"], d["fit"]["blockers"])
    site = ROOT / "site"
    site.mkdir(exist_ok=True)
    (site / "index.html").write_text(onepager.bundle(scored, {}, checklist, artifact=True, banner=BANNER), encoding="utf-8")
    print("->", site / "index.html")


if __name__ == "__main__":
    main()
