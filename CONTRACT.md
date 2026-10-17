# Engine to UI contract

One JSON file per packet. The engine writes it, the UI reads it. Neither side changes the shape
without telling the other.

- Engine writes: `output/R01.json` ... `output/R11.json` (git ignored, real packet output)
- UI develops against: `ui/sample_output.json` (fake, safe to commit)

## Shape

```json
{
  "packet_id": "R01",
  "pages": 34,
  "generated_at": "2026-10-17T12:30:00-07:00",
  "recommendation": "approve | deny | needs_info",
  "confidence": "high | medium | low",
  "summary": "Two or three plain sentences a coordinator reads first.",
  "blockers": ["MH-2"],
  "rules": [
    {
      "rule_id": "MOB-3",
      "status": "met | not_met | unknown | cant_tell | not_applicable",
      "finding": "One sentence: what the chart says about this rule.",
      "evidence": [
        { "page": 12, "doc_type": "pt_eval", "quote": "exact words copied from the page" }
      ],
      "verified": true,
      "verify_note": "Second pass found the quote on page 12."
    }
  ],
  "documents": [
    { "doc_id": "DOC-1", "present": "yes | no | unknown", "pages": [2] }
  ],
  "conflicts": [
    {
      "topic": "Mobility",
      "rule_ids": ["MOB-3"],
      "sources": [
        { "page": 2, "doc_type": "referral_form", "quote": "..." },
        { "page": 12, "doc_type": "pt_eval", "quote": "..." }
      ],
      "note": "Form says X, PT eval says Y. Chart wins."
    }
  ],
  "questions_for_hospital": ["Short questions the coordinator can paste into a reply."],
  "page_map": [
    { "page": 1, "doc_type": "fax_cover", "orientation": "normal | sideways | upside_down" }
  ]
}
```

## Field rules

**recommendation**
- `deny`: at least one `exclude` rule is `not_met` (the exclusion applies) or a `must` rule is
  `not_met`, with verified evidence. `blockers` lists those rule IDs.
- `needs_info`: no verified blocker, but key rules are `unknown`. Ask the hospital.
- `approve`: no blockers and nothing critical unknown.
- The tool recommends. The coordinator decides. The UI must never say "approved".

**status**
- `met`: the chart shows the patient meets the rule.
- `not_met`: the chart shows the patient fails the rule. For an `exclude` rule, `not_met` means
  the exclusion applies (e.g. suicidal ideation is present).
- `unknown`: the packet does not say. Not the same as normal.
- `cant_tell`: the packet has the fact but the date or time needed was blacked out.
- `not_applicable`: rule does not apply (e.g. diabetes rules for a non-diabetic patient).

**evidence**
- `quote` is copied from the page, not paraphrased. `page` is the 1-based PDF page.
- A `met` or `not_met` status with no evidence is a bug.
- Black boxes are redactions. Never cite one as a missing document.

**verified**
- Set by a second pass that re-reads the cited page and checks the quote is there and supports
  the status. `false` means the UI shows the rule as "check by hand".

**rule_id** values come from `challenges/1-referral-intake/criteria/admission-criteria.json`
(`ADL-*`, `MOB-*`, `MH-*`, `COG-*`, `OTH-*`, `EOL-*`, `INF-*`, `DM-*`, `ID-*`, `RESP-*`, `CARD-*`,
`INT-*` and other `by_system` IDs, `FORM-*`). `doc_id` values are `DOC-1` to `DOC-10` from
`referral_checklist`.

**Precedence:** when a `FORM-*` rule and an outline rule disagree, the outline wins (see
`precedence` in the criteria JSON). Show both in `conflicts`.

## doc_type values

`fax_cover`, `referral_form`, `calaim_auth`, `face_sheet`, `h_and_p`, `progress_note`,
`nursing_note`, `pt_eval`, `ot_eval`, `labs`, `imaging`, `ecg`, `med_list`, `med_record`,
`social_work`, `psych_consult`, `wound_note`, `vitals`, `orders`, `other`, `blank`.
