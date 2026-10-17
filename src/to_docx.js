// Turn a transcript (RXX.pages.json) into a compact Word document that keeps the look of
// each form, so a coordinator recognizes the referral form, face sheet, H&P, PT note.
//
//   node src/to_docx.js output/R05/R05.pages.json            -> output/R05/R05.docx
//   node src/to_docx.js demo/fictional/F01/F01.pages.json    -> demo/fictional/F01/F01.docx
//
// Real packets are de-identified patient data: their .docx stays in output/ (git ignored).

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, AlignmentType, LevelFormat, Footer, PageNumber, TabStopType,
} = require("docx");

const BRAND = { black: "1A1A1A", orange: "FF8710", white: "FFFFFF" }; // OCMEE styleguide 2024, p7
const W = 11520; // content width in DXA: letter 8.5in minus 0.5in margins
const FONT = "Arial";
const SERIF = "Georgia";

// Header style per document type: [band label, band fill, text color, title font]
const STYLE = {
  referral_form: ["ILLUMINATION  Recuperative Care Referral Form", "FFFFFF", "1A1A1A", SERIF],
  calaim_auth: ["CalOptima Health  ·  CalAIM Community Supports", "E8EEF6", "1F3B57", FONT],
  face_sheet: ["Face Sheet", "D9D9D9", "1A1A1A", FONT],
  fax_cover: ["Fax Cover Sheet", "F2F2F2", "1A1A1A", FONT],
  h_and_p: ["History and Physical", "E7EEF5", "1F3B57", FONT],
  progress_note: ["Progress Note", "E7EEF5", "1F3B57", FONT],
  nursing_note: ["Nursing Note", "E7EEF5", "1F3B57", FONT],
  pt_eval: ["Physical Therapy", "E6F2EA", "1B5E3B", FONT],
  ot_eval: ["Occupational Therapy", "E6F2EA", "1B5E3B", FONT],
  social_work: ["Social Work / Case Management", "F3ECF7", "4B2C5E", FONT],
  psych_consult: ["Psychiatry", "F3ECF7", "4B2C5E", FONT],
  labs: ["Labs", "F2F2F2", "333333", FONT],
  vitals: ["Flowsheet: Vitals", "F2F2F2", "333333", FONT],
  imaging: ["Imaging", "F2F2F2", "333333", FONT],
  ecg: ["ECG", "F2F2F2", "333333", FONT],
  med_list: ["Medication List", "FBF1E3", "7A4A00", FONT],
  med_record: ["Medication Administration Record", "FBF1E3", "7A4A00", FONT],
  wound_note: ["Wound Care", "FBE9E7", "8A1C12", FONT],
  orders: ["Physician Orders", "F2F2F2", "333333", FONT],
};
const DEFAULT_STYLE = ["Document", "F2F2F2", "333333", FONT];

const thin = { style: BorderStyle.SINGLE, size: 2, color: "BFBFBF" };
const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const cellBorders = { top: thin, bottom: thin, left: thin, right: thin };

// --- inline runs: checkboxes, redactions, illegible, uncertain marks ---
function runs(text, opts = {}) {
  const out = [];
  const parts = text.split(/(\[REDACTED\]|\[X\]|\[ \]|\[\?\]|\[illegible\]|\[POSSIBLE MISSED REDACTION\])/g);
  for (const p of parts) {
    if (!p) continue;
    const base = { font: FONT, size: opts.size || 17, bold: opts.bold, color: opts.color, italics: opts.italics };
    if (p === "[REDACTED]") out.push(new TextRun({ ...base, text: " redacted ", color: "FFFFFF", size: 13, shading: { type: ShadingType.CLEAR, fill: "111111", color: "auto" } }));
    else if (p === "[X]") out.push(new TextRun({ ...base, text: "☒", font: "Segoe UI Symbol" }));
    else if (p === "[ ]") out.push(new TextRun({ ...base, text: "☐", font: "Segoe UI Symbol" }));
    else if (p === "[?]") out.push(new TextRun({ ...base, text: "☐?", bold: true, color: "C0392B", font: "Segoe UI Symbol" }));
    else if (p === "[illegible]") out.push(new TextRun({ ...base, text: "[illegible]", italics: true, color: "888888" }));
    else if (p === "[POSSIBLE MISSED REDACTION]") out.push(new TextRun({ ...base, text: "[possible missed redaction]", bold: true, color: "C0392B" }));
    else out.push(new TextRun({ ...base, text: p }));
  }
  return out;
}

const para = (children, o = {}) => new Paragraph({ children, spacing: { before: 0, after: o.after ?? 20, line: 250 }, ...o });

function band(label, fill, color, font, pages, title) {
  const pg = pages.length > 1 ? `pp. ${pages[0]}–${pages[pages.length - 1]}` : `p. ${pages[0]}`;
  const isForm = label.startsWith("ILLUMINATION");
  return new Table({
    width: { size: W, type: WidthType.DXA },
    columnWidths: [W - 1700, 1700],
    rows: [new TableRow({
      cantSplit: true,
      children: [
        new TableCell({
          width: { size: W - 1700, type: WidthType.DXA },
          shading: { type: ShadingType.CLEAR, fill, color: "auto" },
          borders: isForm ? { top: none, left: none, right: none, bottom: { style: BorderStyle.SINGLE, size: 12, color: "1A1A1A" } } : cellBorders,
          margins: { top: 50, bottom: 50, left: 100, right: 100 },
          children: [para([
            new TextRun({ text: label, font, bold: true, size: isForm ? 26 : 20, color }),
            ...(title && !isForm ? [new TextRun({ text: `   ${title}`, font: FONT, size: 15, color: "666666" })] : []),
          ], { after: 0, keepNext: true })],
        }),
        new TableCell({
          width: { size: 1700, type: WidthType.DXA },
          shading: { type: ShadingType.CLEAR, fill, color: "auto" },
          borders: isForm ? { top: none, left: none, right: none, bottom: { style: BorderStyle.SINGLE, size: 12, color: "1A1A1A" } } : cellBorders,
          margins: { top: 50, bottom: 50, left: 100, right: 100 },
          children: [para([new TextRun({ text: pg, font: FONT, size: 15, color: "666666" })], { alignment: AlignmentType.RIGHT, after: 0 })],
        }),
      ],
    })],
  });
}

function sectionHead(text, font, color) {
  return para([new TextRun({ text, font, bold: true, size: font === SERIF ? 19 : 17, color })], {
    keepNext: true, after: 20, spacing: { before: 60, after: 20 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF", space: 1 } },
  });
}

// label/value lines packed into a grid: 4 columns when values are short, else 2
function kvTable(pairs) {
  const short = pairs.every(([, v]) => v.length <= 34);
  const cols = short ? [1500, W / 2 - 1500, 1500, W / 2 - 1500] : [2400, W - 2400];
  const per = short ? 2 : 1;
  const rows = [];
  for (let i = 0; i < pairs.length; i += per) {
    const cells = [];
    for (let j = 0; j < per; j++) {
      const pr = pairs[i + j] || ["", ""];
      cells.push(new TableCell({
        width: { size: cols[j * 2], type: WidthType.DXA }, borders: cellBorders,
        shading: { type: ShadingType.CLEAR, fill: "F7F7F7", color: "auto" },
        margins: { top: 20, bottom: 20, left: 70, right: 70 },
        children: [para(runs(pr[0], { size: 15, bold: true, color: "555555" }), { after: 0 })],
      }));
      cells.push(new TableCell({
        width: { size: cols[j * 2 + 1], type: WidthType.DXA }, borders: cellBorders,
        margins: { top: 20, bottom: 20, left: 70, right: 70 },
        children: [para(runs(pr[1]), { after: 0 })],
      }));
    }
    rows.push(new TableRow({ cantSplit: true, children: cells }));
  }
  return new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: cols, rows });
}

const KV = /^([A-Za-z][A-Za-z0-9 /&().#'%+-]{0,38}):\s+(.+)$/;

function renderText(text, font, color, type) {
  const formLike = type === "referral_form" || type === "calaim_auth";
  const out = [];
  let pairs = [];
  const flush = () => { if (pairs.length) { out.push(kvTable(pairs)); out.push(para([], { after: 20 })); pairs = []; } };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) { flush(); continue; }
    if (line.startsWith("## ")) { flush(); out.push(sectionHead(line.slice(3), font, color)); continue; }
    // Only a single plain answer ("O2: No", "Any wounds? No [X]", "Diabetes: No (meds blank)") becomes
    // the form's Yes/No boxes. Lines that already carry several boxes are shown exactly as transcribed.
    const yn = formLike && line.replace(/^- /, "").match(/^([^[\]:?]+)([:?])\s*(Yes|No)(?:\s*\[X\])?(?:\s*\(([^()[\]]*)\))?$/i);
    if (yn) {
      const yes = /^yes$/i.test(yn[3]);
      pairs.push([yn[1].trim() + (yn[2] === "?" ? "?" : ""), `${yes ? "[X]" : "[ ]"} Yes  ${yes ? "[ ]" : "[X]"} No${yn[4] ? `  (${yn[4]})` : ""}`]);
      continue;
    }
    if (line.startsWith("- ")) { flush(); out.push(new Paragraph({ numbering: { reference: "dots", level: 0 }, children: runs(line.slice(2)), spacing: { after: 10, line: 240 } })); continue; }
    const m = line.length < 140 && line.match(KV);
    if (m && !/^https?$/i.test(m[1])) { pairs.push([m[1], m[2]]); continue; }
    flush();
    out.push(para(runs(line)));
  }
  flush();
  return out;
}

function groupDocs(pages) {
  const docs = [];
  for (const p of pages) {
    const last = docs[docs.length - 1];
    if (last && last.type === p.doc_type) last.pages.push(p);
    else docs.push({ type: p.doc_type, pages: [p] });
  }
  return docs;
}

function build(data, srcName) {
  const fictional = !!data.fictional;
  const pages = data.pages;
  const docs = groupDocs(pages);
  const body = [];

  // OCMEE Design brand band (styleguide: #1A1A1A, #FF8710, #FFFFFF)
  const bc = (children, w, align) => new TableCell({ width: { size: w, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: BRAND.black, color: "auto" },
    borders: { top: none, left: none, right: none, bottom: { style: BorderStyle.SINGLE, size: 24, color: BRAND.orange } },
    margins: { top: 70, bottom: 70, left: 140, right: 140 }, children: [para(children, { after: 0, alignment: align })] });
  body.push(new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: [5200, W - 5200], rows: [new TableRow({ children: [
    bc([new TextRun({ text: "OCMEE", font: FONT, bold: true, size: 24, color: BRAND.orange }), new TextRun({ text: " DESIGN", font: FONT, bold: true, size: 24, color: BRAND.white }),
        new TextRun({ text: "   Empowering Engineering Designs", font: FONT, size: 14, color: "BBBBBB" })], 5200),
    bc([new TextRun({ text: "Referral intake  ·  prepared for Illumination Health + Home", font: FONT, size: 15, color: BRAND.white })], W - 5200, AlignmentType.RIGHT),
  ] })] }));
  body.push(para([], { after: 60 }));
  body.push(para([new TextRun({ text: `Referral packet ${data.packet_id}`, font: SERIF, bold: true, size: 30 })], { after: 20 }));
  body.push(para([new TextRun({
    text: fictional ? `FICTIONAL demo packet · ${pages.length} pages · invented patient, no real data`
      : `${pages.length} pages · from ${srcName} · De-identified packet data: do not share, upload or commit. Black bars are privacy redactions.`,
    font: FONT, size: 15, color: fictional ? "1B5E3B" : "8A1C12", bold: true,
  })], { after: 60 }));

  // contents: one compact table
  const cols = [700, 4300, 1300, 700, 4300, 220];
  const half = Math.ceil(docs.length / 2);
  const rows = [];
  const label = d => (STYLE[d.type] || DEFAULT_STYLE)[0].replace("ILLUMINATION  ", "IHH ");
  const rng = d => d.pages.length > 1 ? `${d.pages[0].page}–${d.pages[d.pages.length - 1].page}` : `${d.pages[0].page}`;
  for (let i = 0; i < half; i++) {
    const a = docs[i], b = docs[i + half];
    const c = (txt, w, bold) => new TableCell({ width: { size: w, type: WidthType.DXA }, borders: { top: none, left: none, right: none, bottom: thin },
      margins: { top: 10, bottom: 10, left: 60, right: 60 }, children: [para([new TextRun({ text: txt, font: FONT, size: 15, bold, color: bold ? "333333" : "555555" })], { after: 0 })] });
    rows.push(new TableRow({ children: [c(a ? `p${rng(a)}` : "", cols[0], true), c(a ? label(a) : "", cols[1]), c("", cols[2]),
      c(b ? `p${rng(b)}` : "", cols[3], true), c(b ? label(b) : "", cols[4]), c("", cols[5])] }));
  }
  body.push(new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: cols, rows }));
  body.push(para([], { after: 80 }));

  for (const d of docs) {
    const [lab, fill, color, font] = STYLE[d.type] || DEFAULT_STYLE;
    const title = d.pages[0].title.replace(/,?\s*page \d+( of \d+)?/i, "");
    body.push(band(lab, fill, color, font, d.pages.map(p => p.page), title));
    for (const p of d.pages) {
      body.push(para([
        new TextRun({ text: `Page ${p.page}`, font: FONT, size: 13, bold: true, color: "999999" }),
        ...(p.orientation !== "normal" ? [new TextRun({ text: `  · scanned ${p.orientation.replace("_", " ")}`, font: FONT, size: 13, color: "999999" })] : []),
        ...(p.legibility !== "good" ? [new TextRun({ text: `  · legibility ${p.legibility}`, font: FONT, size: 13, color: "A86400" })] : []),
      ], { spacing: { before: 50, after: 10 }, keepNext: true }));
      body.push(...renderText(p.text, font, color, d.type));
      if (p.notes) body.push(para(runs(`Check the original: ${p.notes}`, { size: 15, italics: true, color: "A86400" })));
    }
    body.push(para([], { after: 100 }));
  }

  return new Document({
    creator: "ihh-referral-intake",
    title: `${data.packet_id} referral packet`,
    styles: { default: { document: { run: { font: FONT, size: 17 } } } },
    numbering: { config: [{ reference: "dots", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 300, hanging: 180 } } } }] }] },
    sections: [{
      properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 720, bottom: 720, left: 360, right: 360 } } },
      footers: { default: new Footer({ children: [para([
        new TextRun({ text: "OCMEE DESIGN  ", font: FONT, size: 13, bold: true, color: BRAND.orange }),
        new TextRun({ text: `${data.packet_id} · ${fictional ? "fictional demo packet" : "de-identified packet data, do not share"} · transcript is AI-made, check the original scan`, font: FONT, size: 13, color: "999999" }),
        new TextRun({ children: ["\tsheet ", PageNumber.CURRENT], font: FONT, size: 13, color: "999999" }),
      ], { tabStops: [{ type: TabStopType.RIGHT, position: W }], after: 0 })] }) },
      children: body,
    }],
  });
}

async function main() {
  const files = process.argv.slice(2);
  if (!files.length) { console.error("usage: node src/to_docx.js <RXX.pages.json> [...]"); process.exit(1); }
  for (const f of files) {
    const data = JSON.parse(fs.readFileSync(f, "utf8"));
    const out = path.join(path.dirname(f), `${data.packet_id}.docx`);
    fs.writeFileSync(out, await Packer.toBuffer(build(data, `${data.packet_id}.pdf`)));
    console.log(`${data.packet_id}: ${data.pages.length} pages -> ${out}`);
  }
}

main();
