"""Fill IHH's real blank referral form (public, in criteria/source/) with a FICTIONAL patient's answers.

The values come from the fictional packet's referral-form transcript, so the "original" shows IHH's
actual form layout while every entry is invented. The form's checkboxes all share one internal name,
so marks are drawn at each box's position instead of toggling form fields.
"""

import re
from pathlib import Path

import pymupdf

REPO = Path(__file__).resolve().parent.parent
FORM = REPO / "challenges/1-referral-intake/criteria/source/ihh-recuperative-care-referral-form.pdf"
INK = (0.08, 0.16, 0.45)  # blue-black pen

# label in the transcript -> form text field
TEXT = {"hospital": "Referring Hospital", "department/floor": "DeptFloor", "social worker/case manager/nurse": "SWCMRN",
        "phone": "PhonePager", "email": "Email", "nursing station": "Nursing Station", "authorized by": "Authorized by",
        "name": "Patient Name", "mrn": "MRN", "birth date": "Date6_af_date", "ethnicity": "Ethnicity",
        "ssn (last 4)": "Text4", "insurance": "Insurance", "preferred language": "Preferred Language",
        "chief complaint/admitting diagnosis": "Cheif Complaint Admitting Diagnosis", "chief complaint": "Cheif Complaint Admitting Diagnosis",
        "admit date": "Date7_af_date", "number/location/size/stage": "Admit Date 2", "days": "Length of Stay Authorized in Recupertive Care"}
# Yes/No rows: transcript label -> (yes box x, no box x, y) in PDF points, from the form's own boxes
YESNO = {"o2": (203, 241, 411), "self administer all meds": (203, 241, 440), "continent of bowel & bladder": (203, 241, 455),
         "colostomy/ileostomy": (202, 240, 470), "foley catheter": (202, 240, 485), "diabetes": (202, 241, 500),
         "insulin": (202, 240, 515), "diabetes oral meds": (203, 240, 530), "active infection": (481, 517, 410),
         "ambulatory": (480, 516, 440), "assistive device": (480, 516, 455), "hospice": (480, 517, 485),
         "car": (481, 517, 515), "service animal": (480, 517, 529)}
RADIO = {"any wounds": ((377, 297), (429, 297)), "independent with wound care": ((215, 342), (267, 342)),
         "home health ordered": ((503, 342), (540, 342)), "ppd/tb test or chest x-ray": ((289, 357), (324, 357))}
SINGLE = {"mental health dx": (35, 581), "non-compliant": (35, 594), "forgetful": (311, 594),
          "cognitive impairment": (35, 608), "registered sex offender": (311, 608)}
GENDER = {"m": (110, 204), "male": (110, 204), "f": (179, 204), "female": (179, 204)}


def parse(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = re.match(r"\s*([^:\[]{2,60}?):\s*(.*)$", line)
        if m:
            out.setdefault(m.group(1).strip().lower(), m.group(2).strip())
    out["_unhoused"] = bool(re.search(r"currently unhoused\s*\[X\]", text, re.I)) or "unhoused" in out.get("housing", "").lower()
    out["_episodes"] = bool(re.search(r"4\+ episodes[^\n]*\[X\]", text, re.I))
    return out


def yes(v: str):
    if re.search(r"yes\s*\[X\]", v, re.I):
        return True
    if re.search(r"no\s*\[X\]", v, re.I):
        return False
    if re.match(r"\s*yes\b", v, re.I):
        return True
    if re.match(r"\s*no\b|\s*none\b", v, re.I):
        return False
    return None


def tick(page, x, y, size=12):
    r = pymupdf.Rect(x + 1.5, y + 1.5, x + size - 1.5, y + size - 1.5)
    page.draw_line(r.tl, r.br, color=INK, width=1.6)
    page.draw_line(r.tr, r.bl, color=INK, width=1.6)


def fill(text: str) -> bytes:
    """One filled page (IHH form page 2) as PDF bytes."""
    src = pymupdf.open(FORM)
    rects = {w.field_name: w.rect for w in src[1].widgets()}
    out = pymupdf.open()
    out.insert_pdf(src, from_page=1, to_page=1)
    page = out[0]
    for w in list(page.widgets()):
        page.delete_widget(w)
    v = parse(text)

    def put(field, value, fs=8.5):
        value = re.sub(r"\s*\[[ X?]\]\s*", " ", value).strip()
        if field in rects and value:
            r = rects[field]
            while fs > 5 and pymupdf.get_text_length(value, "helv", fs) > r.width - 3:
                fs -= 0.5
            page.insert_text((r.x0 + 2, r.y1 - 3), value, fontsize=fs, fontname="helv", color=INK)

    for label, field in TEXT.items():
        if label in v:
            put(field, v[label])
    if "ppd/tb test or chest x-ray" in v:
        m = re.search(r"date:\s*([\d/]+).*?result:\s*(.*)$", v["ppd/tb test or chest x-ray"], re.I)
        if m:
            tick(page, 289, 357)
            put("Date8_af_date", m.group(1), 8)
            put("Results", m.group(2), 7.5)
    g = GENDER.get(v.get("gender", "").strip().lower().split(" ")[0] if v.get("gender") else "")
    if g:
        tick(page, *g, size=13)
    if v["_unhoused"]:
        tick(page, 143, 234, size=13)
    if v["_episodes"]:
        tick(page, 323, 234, size=13)
    for label, (yx, nx) in RADIO.items():
        if label in v and label != "ppd/tb test or chest x-ray":
            a = yes(v[label])
            if a is not None:
                tick(page, *(yx if a else nx), size=13)
    for label, (x_yes, x_no, y) in YESNO.items():
        if label in v:
            a = yes(v[label])
            if a is not None:
                tick(page, x_yes if a else x_no, y)
            note = re.sub(r"^\s*yes\s*\[.\]\s*no\s*\[.\]\s*", "", v[label], flags=re.I).strip()
            if note and label == "o2":
                put("Explain", note, 7.5)
            if note and label == "active infection":
                put("Explain_2", note, 7.5)
            if note and label == "assistive device":
                put("Explain_3", note, 7.5)
            if note and label == "hospice":
                put("Explain_4", note, 7.5)
    lim = v.get("any limitations or challenges", "")
    a = None if not lim else (False if re.search(r"no\s*\[X\]", lim, re.I) else True if re.search(r"yes\s*\[X\]", lim, re.I) else None)
    if a is not None:
        tick(page, *((491, 564) if a else (420, 564)))
    for label, xy in SINGLE.items():
        if label in v and yes(v[label]):
            tick(page, *xy)
    t = re.search(r"type:\s*(.+)$", v.get("mental health dx", ""), re.I)
    if t and t.group(1).strip():
        put("If checked what type", t.group(1))
    if v.get("other", "").strip():
        put("Explain_5", v["other"])
    return out.tobytes()
