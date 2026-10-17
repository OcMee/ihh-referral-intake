"""Criteria check through the Claude API: one transcript in, one check JSON out (shape in CONTRACT.md).

Reads   output/<ID>/<ID>.pages.json  (from clean.py --transcribe)
Writes  output/<ID>/<ID>.json        (then score.py verifies quotes and scores it)

Check and correct: after the first pass, every quote that is not on the page it cites goes back to
Claude once with that page's text. Anything still not found stays and shows as "check" in the app.
Claude never sees IHH's past decisions (eval/ is not read here).

  python src/check.py output/U01/U01.pages.json
"""

import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
import score  # noqa: E402
from clean import MODEL, client as api_client  # noqa: E402

CRIT = REPO / "challenges/1-referral-intake/criteria"


class Evidence(BaseModel):
    page: int
    quote: str


class Rule(BaseModel):
    rule_id: str
    status: Literal["met", "not_met", "unknown", "cant_tell", "not_applicable"]
    finding: str
    evidence: list[Evidence]


class Document(BaseModel):
    doc_id: str
    present: Literal["yes", "no", "unknown"]
    pages: list[int]


class Conflict(BaseModel):
    topic: str
    rule_ids: list[str]
    sources: list[Evidence]
    note: str


class KeyFact(BaseModel):
    label: str
    text: str
    pages: list[int]
    quote: str
    quote_page: int


class Patient(BaseModel):
    summary: str
    age: str
    sex: str
    insurance: str
    housing: str
    admit_reason: str
    pages: list[int]


class ClaudeFit(BaseModel):
    score: int
    recommendation: Literal["approve", "deny", "needs_info"]
    reason: str


class Check(BaseModel):
    packet_id: str
    patient: Patient
    key_facts: list[KeyFact]
    rules: list[Rule]
    documents: list[Document]
    conflicts: list[Conflict]
    questions_for_hospital: list[str]
    claude_fit: ClaudeFit


PROMPT = """You are checking one de-identified recuperative-care referral against Illumination Health + Home \
(IHH) admission criteria. A coordinator reads your output on a one-page summary and decides. Being wrong \
with confidence is the worst outcome. "unknown" is a fine answer.

Hard rules
- Never invent facts, values, quotes or page numbers.
- [REDACTED] / black boxes are privacy removals, not missing documents.
- Rules needing a date or hour count (24h on insulin, 72h after alcohol, swab within 24h) are "cant_tell" when dates are redacted.
- The chart beats the referral form. When they disagree, record a conflict and decide from the chart.
- Precedence: when FORM-* and outline rules disagree, the outline wins (see "precedence" in the criteria JSON).

Status means "does the patient PASS this rule"
- met: the packet shows the patient passes. For an "exclude" rule, met = the exclusion does NOT apply.
- not_met: the patient fails. For an "exclude" rule, not_met = the exclusion APPLIES. For "document" rules, not_met = the document is missing.
- unknown: the packet does not say. Absence of a mention is unknown, not met.
- cant_tell: the fact exists but a redacted date/time blocks the check.
- not_applicable: the rule does not apply (e.g. diabetes rules for a non-diabetic).
- "conditional" rules: met = arrangement confirmed, not_met = packet says NOT arranged, unknown = not stated.
- "ask" and "note" rules: answer in finding; status met/unknown/not_applicable only.

Which rules
- Every item in "general" (GEN-1..3), every item in "rules", every item in referral_form_screen.not_eligible_if (FORM-X*).
- From "by_system": only systems the patient actually has.
- referral_checklist DOC-1..DOC-10 go in "documents" (all 10), not "rules".

Evidence
- Each met/not_met rule needs 1-2 evidence items {{page, quote}}.
- quote MUST be copied character-for-character from that page's "text", 3 to 20 words, no "..." and no added words. \
A script checks it is a substring of that page's text; non-matching quotes are shown as unverified.
- unknown / cant_tell / not_applicable: evidence may be empty; finding says why.

Other fields
- patient.summary: one line, e.g. "57M, trauma admit after bike fall, unhoused". Unknown fields are "unknown".
- key_facts: 5 to 8 facts that matter most for this decision; label is one of Mobility, Cognition, Mental health, \
Substance use, Infection, Wounds, Meds/IV/O2, Cardiac, Diabetes, Home health, Other. quote is an exact substring of quote_page.
- questions_for_hospital: short, specific, polite; one per unknown that matters.
- claude_fit: your overall read as an experienced coordinator, 0-100, reason in 2 sentences naming the deciding rule IDs.

packet_id: {pid}

<criteria_json>
{criteria_json}
</criteria_json>

<criteria_text>
{criteria_md}
</criteria_text>

<transcript>
{transcript}
</transcript>"""

FIX = """Some quotes in your check are not exact substrings of the page they cite. For each one below, either \
copy a corrected quote character-for-character from that page's text (3 to 20 words), cite the page where it \
actually appears, or drop that evidence item and set the status to "unknown" if nothing on the page supports it. \
Change nothing else. Return the full corrected check.

<failing_quotes>
{failing}
</failing_quotes>

<your_check>
{check}
</your_check>"""


def call(client, content: str) -> dict:
    resp = client.messages.parse(
        model=MODEL, max_tokens=32000, output_config={"effort": "high"},
        messages=[{"role": "user", "content": content}], output_format=Check,
        extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"}, extra_body={"fallbacks": "default"},
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RuntimeError(f"criteria check returned no result ({resp.stop_reason})")
    return resp.parsed_output.model_dump()


def failing(check: dict, pages: dict) -> list:
    text = {p["page"]: score.norm(p["text"]) for p in pages["pages"]}
    raw = {p["page"]: p["text"] for p in pages["pages"]}
    bad = []
    items = [(f"rule {r['rule_id']}", e) for r in check["rules"] for e in r["evidence"]]
    items += [(f"key fact {f['label']}", {"page": f["quote_page"], "quote": f["quote"]}) for f in check["key_facts"]]
    items += [(f"conflict {c['topic']}", s) for c in check["conflicts"] for s in c["sources"]]
    for where, e in items:
        if not score.verify(e, text):
            bad.append({"where": where, "page": e["page"], "quote": e["quote"], "page_text": raw.get(e["page"], "(no such page)")})
    return bad


def run(pages_json: Path, log=print) -> Path:
    client = api_client()
    pages = json.loads(pages_json.read_text())
    pid = pages["packet_id"]
    log(f"checking {pid} against IHH criteria with {MODEL}")
    check = call(client, PROMPT.format(pid=pid, criteria_json=(CRIT / "admission-criteria.json").read_text(),
                                       criteria_md=(CRIT / "admission-criteria.md").read_text(),
                                       transcript=json.dumps(pages["pages"], indent=1)))
    bad = failing(check, pages)
    if bad:
        log(f"{len(bad)} quotes not found on their page, asking Claude to correct them once")
        check = call(client, FIX.format(failing=json.dumps(bad, indent=1), check=json.dumps(check, indent=1)))
        log(f"{len(failing(check, pages))} quotes still not found; they show as 'check' in the app")
    check["packet_id"] = pid
    dest = pages_json.with_name(f"{pid}.json")
    dest.write_text(json.dumps(check, indent=2))
    return dest


if __name__ == "__main__":
    print(run(Path(sys.argv[1])))
