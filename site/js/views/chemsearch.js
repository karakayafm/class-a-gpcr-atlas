// Chemistry search: the structural-similarity query and the pair comparison it opens.
//
// This was written inside the structures view, where it was the chemistry rail's entry point.
// The ligand explorer asks the same question as its opening move, and a second copy of a
// fingerprint search is not something to keep in step by hand, so it lives here and both views
// call it. Nothing in it is specific to either: it loads its own payloads, draws with the
// vendored RDKit build, and returns a node.
import { t, getLang } from "../core/i18n.js";
import { el, clear, debounce } from "../components/dom.js";
import { downloadBlob, toCSV, download } from "../components/csv.js";
import { downloadXLSX } from "../components/xlsx.js";
import * as L from "../data/loader.js";
import { buildHash } from "../core/router.js";
import { plainName, familyDisplayName } from "./names.js";

/* Structural-similarity search. It sits above the chemistry filters because it is the entry
   point a reader arrives with a molecule for, and it is answered differently from everything
   else here: the corpus is fingerprinted in the pipeline and shipped, the query is fingerprinted
   by the vendored RDKit build in the reader's own browser, and Tanimoto is a bit operation. A
   structure someone has drawn but not published therefore never leaves their machine. */
let rdkit = null, rdkitLoading = null, fingerprints = null;
/* Shared so the ligand explorer can draw its cards with the same build rather than loading a
   second copy of a seven-megabyte wasm module. */
export function getRdkit() {
  if (rdkit) return Promise.resolve(rdkit);
  if (rdkitLoading) return rdkitLoading;
  rdkitLoading = new Promise((resolve, reject) => {
    const tag = document.createElement("script");
    tag.src = "vendor/rdkit/RDKit_minimal.js";
    tag.onerror = () => reject(new Error("rdkit"));
    tag.onload = () => window.initRDKitModule({ locateFile: () => "vendor/rdkit/RDKit_minimal.wasm" })
      .then(mod => { rdkit = mod; resolve(mod); }).catch(reject);
    document.head.appendChild(tag);
  });
  return rdkitLoading;
}
const POPCOUNT = new Uint8Array(256);
for (let i = 0; i < 256; i++) POPCOUNT[i] = (i & 1) + POPCOUNT[i >> 1];
function unpack(b64) {
  const raw = atob(b64), out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}
function tanimoto(a, b) {
  let both = 0, either = 0;
  for (let i = 0; i < a.length; i++) { both += POPCOUNT[a[i] & b[i]]; either += POPCOUNT[a[i] | b[i]]; }
  return either === 0 ? 0 : both / either;
}

/* Tab fills an empty field with a worked example. It does not run it: the example is there to be
   read and edited, and a query that starts on its own turns a keystroke meant to show the format
   into one that produces a result the reader did not ask for. Focus stays in the field, so Enter
   runs it and a second Tab moves on.

   The gesture is only bound while the field is empty, so Tab goes back to moving focus the moment
   there is anything to move on from, and each field says it offers this rather than leaving it to
   be discovered. */
function exampleOnTab(field, example) {
  field.addEventListener("keydown", event => {
    if (event.key !== "Tab" || event.shiftKey || event.altKey || event.ctrlKey || event.metaKey) return;
    if (field.value.trim()) return;
    event.preventDefault();
    field.value = example;
    field.setSelectionRange(field.value.length, field.value.length);
  });
}

/* A Bemis-Murcko scaffold matched back into the molecule it came from should always match, and
   for 33 of this release's 497 scaffolds it did not. Stripping the side chains changes the
   hydrogen count on whatever they were attached to — an N-methyl becomes N-H, a quaternary
   ammonium becomes [NH2+] — and as a SMARTS query [nH] demands exactly one hydrogen, so
   caffeine's own scaffold failed against caffeine. The count is an artefact of the stripping, not
   a fact about the framework, so it is dropped from bracketed atoms while element, charge and
   aromaticity are kept; stereocentres are left alone, their @ marks not matching the pattern.

   Measured over 3,600 scaffold-molecule pairs this changes exactly one verdict, and that one is a
   molecule matching its own scaffold. Nothing that matched before stops matching. */
function scaffoldQuery(mod, smiles) {
  if (!smiles) return null;
  const relaxed = smiles.replace(/\[([a-zA-Z][a-z]?)H\d*([+-]\d*)?\]/g,
    (whole, element, charge) => charge ? "[" + element + charge + "]" : element);
  return mod.get_qmol(relaxed);
}

/* ---------------------------------------------------------------- several queries at once */
/* One query answers on the page. A set of them is a different job: the reader wants the table,
   not the browsing, and wants to keep it. The work is the same fingerprint comparison, plus the
   part the single-query view draws — what a query and a hit have in common — written out instead.
 *
 * The catalogue patterns each molecule carries are computed once per molecule and intersected,
 * rather than matched again for every pair: a hundred pairs over thirty-nine patterns would be
 * seven thousand substructure searches for an answer that only needs each molecule read once.
 */
function parseQueries(text) {
  const out = [];
  for (const raw of String(text || "").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    // SMILES cannot contain whitespace, so anything after the first token is a label.
    const space = line.search(/\s/);
    const smiles = space < 0 ? line : line.slice(0, space);
    const label = space < 0 ? "" : line.slice(space + 1).trim();
    out.push({ smiles, label: label || smiles });
  }
  return out;
}

export async function runBatch({ text, limit = 20, onProgress }) {
  const queries = parseQueries(text);
  if (!queries.length) return { rows: [], queries: [], failed: [] };
  const mod = await getRdkit();
  const payloadFp = fingerprints || (fingerprints = await L.loadLigandFingerprints());
  const catalog = await L.loadChemistryCatalog().catch(() => ({ patterns: {} }));

  const specs = Object.entries(catalog.patterns || {})
    .filter(([, spec]) => spec.smarts)
    .map(([key, spec]) => ({ key, spec, qmol: mod.get_qmol(spec.smarts) }))
    .filter(p => p.qmol);
  const label = spec => spec["label_" + getLang()] || spec.label_en;
  const patternsOf = mol => {
    const found = [];
    for (const p of specs) {
      try {
        const hit = JSON.parse(mol.get_substruct_match(p.qmol));
        if (hit && (hit.atoms || []).length) found.push(p);
      } catch (e) { /* a pattern that will not match is simply absent */ }
    }
    // Parents of a matched child add nothing, exactly as in the single-pair view.
    const parents = new Set(found.map(p => p.spec.parent).filter(Boolean));
    return found.filter(p => !parents.has(p.key));
  };

  const hitPatterns = new Map();
  const rows = [], failed = [];
  let done = 0;
  for (const query of queries) {
    if (onProgress) onProgress(done, queries.length, query.label);
    const qmol = mod.get_mol(query.smiles);
    if (!qmol || !qmol.is_valid || !qmol.is_valid()) {
      if (qmol) qmol.delete();
      failed.push(query); done += 1; continue;
    }
    const bits = qmol.get_morgan_fp_as_uint8array(
      JSON.stringify({ radius: payloadFp.radius, nBits: payloadFp.bits }));
    const queryPatterns = new Set(patternsOf(qmol).map(p => p.key));
    const queryScaffoldSource = qmol;
    const scored = (payloadFp.records || [])
      .map(r => ({ rec: r, score: tanimoto(bits, unpack(r.fp)) }))
      .filter(r => r.score > 0 && (r.rec.seen_in || []).length)
      .sort((a, b) => b.score - a.score).slice(0, limit);

    for (const [rank, hit] of scored.entries()) {
      const rec = hit.rec;
      if (!hitPatterns.has(rec.ccd)) {
        const mol = rec.smiles ? mod.get_mol(rec.smiles) : null;
        if (mol && mol.is_valid && mol.is_valid()) {
          hitPatterns.set(rec.ccd, patternsOf(mol));
          mol.delete();
        } else { if (mol) mol.delete(); hitPatterns.set(rec.ccd, []); }
      }
      const shared = hitPatterns.get(rec.ccd).filter(p => queryPatterns.has(p.key));
      const groups = shared.filter(p => p.spec.facet === "functional_group").map(p => label(p.spec));
      const rings = shared.filter(p => p.spec.facet === "ring_system").map(p => label(p.spec));
      // Does the hit's Bemis-Murcko scaffold embed in the query? The same test the pair view runs.
      let sharedScaffold = false;
      if (rec.scaffold) {
        const pattern = scaffoldQuery(mod, rec.scaffold);
        if (pattern) {
          try {
            const m = JSON.parse(queryScaffoldSource.get_substruct_match(pattern));
            sharedScaffold = !!(m && (m.atoms || []).length);
          } catch (e) { sharedScaffold = false; }
          pattern.delete();
        }
      }
      const place = (rec.seen_in || [])[0] || {};
      rows.push({
        rec, query_label: query.label, query_smiles: query.smiles, rank: rank + 1,
        ccd: rec.ccd, name: plainName(rec.name || ""), similarity: hit.score,
        shared_scaffold: sharedScaffold, hit_scaffold: rec.scaffold || "",
        shared_functional_groups: groups, shared_ring_systems: rings,
        shared_pattern_count: shared.length,
        structures: (rec.seen_in || []).reduce((n, x) => n + (x.structures || 0), 0),
        families: (rec.seen_in || []).length, example_pdb: place.pdb_id || "",
      });
    }
    qmol.delete();
    done += 1;
  }
  for (const p of specs) p.qmol.delete();
  if (onProgress) onProgress(done, queries.length, "");
  return { rows, queries, failed };
}

/* A compound can be hit by several of the queries. The card shows the best of them and compares
   against that one, because "compare with the query" has no answer otherwise. */
function bestPerHit(result) {
  const best = new Map();
  for (const row of result.rows) {
    const held = best.get(row.ccd);
    if (!held || row.similarity > held.score)
      best.set(row.ccd, { ccd: row.ccd, score: row.similarity, rec: row.rec,
                          queryLabel: row.query_label, querySmiles: row.query_smiles });
  }
  return [...best.values()].sort((a, b) => b.score - a.score);
}

export const batchColumns = () => [
  { key: "query_label", label: t("col_query") },
  { key: "query_smiles", label: t("col_query_smiles") },
  { key: "rank", label: t("col_rank") },
  { key: "ccd", label: t("col_component") },
  { key: "name", label: t("col_component_name") },
  { key: "similarity", label: t("col_tanimoto"), get: r => r.similarity.toFixed(4) },
  { key: "shared_scaffold", label: t("col_shares_hit_scaffold"), get: r => r.shared_scaffold ? "yes" : "no" },
  { key: "hit_scaffold", label: t("col_hit_scaffold") },
  { key: "shared_functional_groups", label: t("col_shared_functional_groups"),
    get: r => r.shared_functional_groups.join("; ") },
  { key: "shared_ring_systems", label: t("col_shared_ring_systems"),
    get: r => r.shared_ring_systems.join("; ") },
  { key: "shared_pattern_count", label: t("col_shared_pattern_count") },
  { key: "structures", label: t("col_structures") },
  { key: "families", label: t("col_families") },
  { key: "example_pdb", label: t("col_example_pdb") },
];

/* `onResults` lets a view take the hits over and render them itself. The panel keeps the query
   controls and the status line; the caller gets each hit with the function that opens its
   comparison, so the RDKit work stays here and only the presentation moves. Without the option
   the panel renders its own list, which is what the structure view still wants. */
export function createSimilarityPanel(options) {
  const onResults = options && options.onResults;
  const box = el("details", { class: "sim-panel", open: true });
  box.appendChild(el("summary", {}, [el("span", { text: t("sim_title") })]));
  const body = el("div", { class: "sim-body" });
  const input = el("input", { type: "text", class: "sim-input", spellcheck: "false",
    placeholder: t("sim_placeholder") });
  const pdbInput = el("input", { type: "text", class: "sim-pdb", spellcheck: "false",
    maxlength: "4", placeholder: t("sim_pdb_placeholder") });
  const status = el("p", { class: "sim-status muted small" });
  const alternatives = el("div", { class: "sim-alt" });
  const results = el("div", { class: "sim-results" });

  /* Pull the ligand out of a deposition the reader names, so a structure can be the query
     without them having to find its SMILES first. An entry often holds more than one component
     with a structure here — 5T1A holds two — and taking the first silently made the panel look
     as though the entry had one ligand. The rest are offered as buttons: the reader can see
     there was a choice and make it differently. The component code names each one, and the
     chemical name on hover comes from the PDB chemical component dictionary, which is where
     every name in this atlas comes from. */
  async function fromPdb() {
    const code = pdbInput.value.trim().toUpperCase();
    clear(results); clear(alternatives);
    if (!/^[0-9A-Z]{4}$/.test(code)) { status.textContent = t("sim_pdb_invalid"); return; }
    status.textContent = t("sim_working");
    try {
      const payloadFp = fingerprints || (fingerprints = await L.loadLigandFingerprints());
      const chemistry = await L.loadLigandChemistry();
      const smilesOf = new Map((chemistry.records || []).map(r => [r.ccd, r.raw_smiles]));
      const nameOf = new Map((chemistry.records || []).map(r => [r.ccd, plainName(r.name || "")]));
      const codes = ((payloadFp.by_structure || {})[code] || []).filter(c => smilesOf.get(c));
      if (!codes.length) { status.textContent = t("sim_pdb_no_ligand", { pdb: code }); return; }
      await take(code, codes, codes[0], smilesOf, nameOf);
    } catch (error) { status.textContent = t("sim_pdb_failed", { pdb: code }); }
  }
  async function take(code, codes, chosen, smilesOf, nameOf) {
    clear(alternatives);
    input.value = smilesOf.get(chosen);
    const message = t("sim_pdb_taken", { pdb: code, ccd: chosen });
    status.textContent = message;
    const others = codes.filter(c => c !== chosen);
    if (others.length) {
      alternatives.appendChild(el("span", { class: "muted small",
        text: others.length === 1 ? t("sim_pdb_others_one") : t("sim_pdb_others", { n: others.length }) }));
      for (const other of others)
        alternatives.appendChild(el("button", { class: "sim-alt-pick", type: "button",
          text: other, title: nameOf.get(other) || other,
          onclick: () => take(code, codes, other, smilesOf, nameOf) }));
    }
    await run(message + " ");
  }

    /* The one RDKit instance, held where the comparison machinery can reach it: getRdkit caches a
     singleton, and both the single query and a batch resolve to the same object. */
  let mod = null;

  /* What the two molecules have in common, drawn rather than asserted. The hit's
       Bemis-Murcko scaffold is matched into both structures and those atoms are highlighted:
       it is the shared ring system, not a maximum common substructure, and the caption says
       so. Where the scaffold does not match the query the pair is still drawn, unmarked. */
    function drawPair(rec, width, height, qSmiles) {
      const pattern = rec.scaffold ? scaffoldQuery(mod, rec.scaffold) : null;
      const prepared = [[qSmiles, t("sim_compare_query")], [rec.smiles, rec.ccd]]
        .map(([smiles, label]) => {
          const m = mod.get_mol(smiles);
          if (!m || !m.is_valid || !m.is_valid()) { if (m) m.delete(); return null; }
          let found = { atoms: [], bonds: [] };
          if (pattern) { try { found = JSON.parse(m.get_substruct_match(pattern)) || found; }
                         catch (e) { found = { atoms: [], bonds: [] }; } }
          return { mol: m, label, found, matched: (found.atoms || []).length > 0 };
        });
      /* The pattern is the hit's own Bemis-Murcko scaffold, so it always covers most of the
         hit — that is what a scaffold is. Marking it there while the query carries no match
         painted four fifths of one molecule green and none of the other, which reads as a
         similarity map and is not one: the score comes from the whole-molecule fingerprint,
         not from the marked atoms. The highlight means "this is what the two share", so it is
         drawn only when both actually carry it, and otherwise the pair is drawn plain and the
         caption says why. */
      const shared = prepared.every(p => p && p.matched);
      /* The enlarged pair is redrawn rather than scaled up: RDKit lays a molecule out for the
         box it is given, and stretching the 200px drawing would thin the bonds and leave the
         labels at thumbnail proportions. Stereo annotation stays off in both, so the large
         drawing is the small one, only bigger. */
      const parts = prepared.map(p => {
        if (!p) return null;
        const svg = p.mol.get_svg_with_highlights(JSON.stringify({
          width, height, bondLineWidth: width > 300 ? 2 : 1, addStereoAnnotation: false,
          atoms: shared ? p.found.atoms || [] : [], bonds: shared ? p.found.bonds || [] : [],
          highlightColour: [0.62, 0.85, 0.72] }));
        p.mol.delete();
        return { svg, label: p.label };
      });
      if (pattern) pattern.delete();
      return { parts, shared };
    }
    /* One image holding both molecules, so what leaves the browser is the comparison and not
       two drawings the reader has to put side by side again. RDKit hands back a complete SVG
       document each time; nesting them keeps each one's own coordinate system intact. */
    function pairSvg(parts, width, height) {
      const pad = 14, cap = 22;
      const w = width * parts.length + pad * (parts.length + 1);
      const h = height + cap + pad * 2;
      const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
                                .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
      let body = "";
      parts.forEach((part, i) => {
        const x = pad + i * (width + pad);
        body += part.svg.replace(/^[\s\S]*?(?=<svg)/, "").replace("<svg", `<svg x="${x}" y="${pad}"`);
        body += `<text x="${x + width / 2}" y="${pad + height + 15}" text-anchor="middle" `
              + `font-family="system-ui,sans-serif" font-size="13" fill="#444">${esc(part.label)}</text>`;
      });
      return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" `
           + `viewBox="0 0 ${w} ${h}"><rect width="100%" height="100%" fill="#ffffff"/>`
           + body + `</svg>`;
    }
    function downloadPairSvg(parts, name, width, height) {
      downloadBlob(name + ".svg",
        new Blob([pairSvg(parts, width, height)], { type: "image/svg+xml;charset=utf-8" }));
    }
    // Rasterised at three times the drawing size, matching the viewer's own snapshot factor,
    // so the image is usable in a figure rather than only on screen.
    function downloadPairPng(parts, name, width, height) {
      const url = URL.createObjectURL(
        new Blob([pairSvg(parts, width, height)], { type: "image/svg+xml;charset=utf-8" }));
      const image = new Image();
      image.onload = () => {
        const canvas = el("canvas");
        canvas.width = image.width * 3; canvas.height = image.height * 3;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);
        canvas.toBlob(blob => blob && downloadBlob(name + ".png", blob), "image/png");
      };
      image.onerror = () => URL.revokeObjectURL(url);
      image.src = url;
    }
    /* Selecting either drawing opens both at a size worth reading, with the pair downloadable
       as one image. The thumbnails are 200px because the rail is narrow; that is enough to see
       that two molecules differ and not enough to see how. */
    async function openCompare(rec, qSmiles) {
      const width = 430, height = 350;
      const catalog = await L.loadChemistryCatalog().catch(() => null);
      const mols = [[qSmiles, t("sim_compare_query")], [rec.smiles, rec.ccd]].map(([smiles, label]) => {
        const mol = mod.get_mol(smiles);
        if (!mol || !mol.is_valid || !mol.is_valid()) { if (mol) mol.delete(); return null; }
        return { mol, label };
      });
      if (mols.some(m => !m)) { for (const m of mols) if (m) m.mol.delete(); return; }
      const marks = sharedMarks(rec, mols, catalog);
      let chosen = 0;

      const name = "compare_" + rec.ccd;
      const opener = document.activeElement;
      const overlay = el("div", { class: "sim-lightbox", role: "dialog", "aria-modal": "true",
        "aria-label": t("sim_compare_open") });
      const close = () => {
        document.removeEventListener("keydown", onKey);
        overlay.remove();
        document.body.classList.remove("modal-open");
        for (const m of mols) m.mol.delete();
        if (opener && opener.focus) opener.focus();
      };
      const onKey = e => { if (e.key === "Escape") { e.preventDefault(); close(); } };
      const closeButton = el("button", { class: "btn close", type: "button",
        "aria-label": t("sim_compare_close"), text: "✕", onclick: close });
      const figures = el("div", { class: "sim-lightbox-figures" });
      const chips = el("div", { class: "sim-marks" });

      const parts = () => renderMarked(mols, marks[chosen], width, height);
      function paint() {
        clear(figures);
        for (const part of parts()) {
          const cell = el("figure", { class: "sim-lightbox-figure" });
          cell.innerHTML = part.svg;
          cell.appendChild(el("figcaption", { text: part.label }));
          figures.appendChild(cell);
        }
        for (const button of chips.querySelectorAll(".sim-mark")) {
          const on = Number(button.dataset.mark) === chosen;
          button.classList.toggle("active", on);
          button.setAttribute("aria-pressed", on ? "true" : "false");
        }
      }
      /* What the two molecules actually have in common, named and markable one at a time.
         Before this the panel marked a shared ring system or nothing at all, which left a
         reader looking at a 20% score with no way to see where the 20% was. */
      if (marks.length) {
        chips.appendChild(el("span", { class: "muted small", text: t("sim_marks_title") }));
        marks.forEach((mark, i) => {
          chips.appendChild(el("button", { class: "sim-mark", type: "button", "data-mark": String(i),
            text: mark.label, onclick: () => { chosen = i; paint(); } }));
        });
      } else {
        chips.appendChild(el("span", { class: "muted small", text: t("sim_marks_empty") }));
      }
      overlay.appendChild(el("div", { class: "sim-lightbox-inner" }, [
        el("header", { class: "sim-lightbox-head" }, [
          el("h2", { text: t("sim_compare_open") + " — " + rec.ccd }),
          el("button", { class: "btn small", type: "button", text: t("sim_compare_png"),
            onclick: () => downloadPairPng(parts(), name, width, height) }),
          el("button", { class: "btn small", type: "button", text: t("sim_compare_svg"),
            onclick: () => downloadPairSvg(parts(), name, width, height) }),
          closeButton ]),
        figures, chips,
        /* Not the thumbnail's caption: that one says what the green is, and here the green
           is whatever chip is selected. What stays true is what the scaffold option means,
           or why there is not one. */
        el("p", { class: "sim-lightbox-note", text: marks.some(m => m.key === "scaffold")
          ? t("sim_scaffold_present") : t("sim_scaffold_absent") }),
        el("p", { class: "sim-lightbox-note", text: t("sim_marks_note") })]));
      paint();
      overlay.addEventListener("click", e => { if (e.target === overlay) close(); });
      document.addEventListener("keydown", onKey);
      document.body.classList.add("modal-open");
      document.body.appendChild(overlay);
      closeButton.focus();
    }
    function renderMarked(mols, mark, width, height) {
      return mols.map((m, i) => ({
        label: m.label,
        svg: m.mol.get_svg_with_highlights(JSON.stringify({
          width, height, bondLineWidth: width > 300 ? 2 : 1, addStereoAnnotation: false,
          atoms: (mark && mark.atoms[i]) || [], bonds: (mark && mark.bonds[i]) || [],
          highlightColour: [0.62, 0.85, 0.72] })) }));
    }
    /* The pieces both molecules carry, from the atlas's own SMARTS catalogue — the same 39
       patterns the chemistry filters are built on, so what is marked here is what the facet
       lists elsewhere already name. A pattern is kept only when it matches both molecules,
       and dropped when a more specific child of it also matches, so an amide is not also
       reported as a carbonyl. */
    function sharedMarks(rec, mols, catalog) {
      const union = qmol => mols.map(m => {
        let out = { atoms: [], bonds: [] };
        try {
          for (const hit of JSON.parse(m.mol.get_substruct_matches(qmol)) || []) {
            out.atoms = out.atoms.concat(hit.atoms || []);
            out.bonds = out.bonds.concat(hit.bonds || []);
          }
        } catch (e) { /* an unmatchable pattern is simply not shared */ }
        return out;
      });
      const found = [];
      // The scaffold first: it is the largest single thing the two can share.
      if (rec.scaffold) {
        const qmol = scaffoldQuery(mod, rec.scaffold);
        if (qmol) {
          const per = union(qmol); qmol.delete();
          if (per.every(p => p.atoms.length))
            found.push({ key: "scaffold", label: t("sim_marks_scaffold"),
                         atoms: per.map(p => p.atoms), bonds: per.map(p => p.bonds) });
        }
      }
      const patterns = (catalog && catalog.patterns) || {};
      const shared = [];
      for (const [key, spec] of Object.entries(patterns)) {
        if (!spec.smarts) continue;
        const qmol = mod.get_qmol(spec.smarts);
        if (!qmol) continue;
        const per = union(qmol); qmol.delete();
        if (per.every(p => p.atoms.length))
          shared.push({ key, spec, atoms: per.map(p => p.atoms), bonds: per.map(p => p.bonds) });
      }
      const parents = new Set(shared.map(s => s.spec.parent).filter(Boolean));
      for (const s of shared) {
        if (parents.has(s.key)) continue;
        found.push({ key: s.key, atoms: s.atoms, bonds: s.bonds,
          label: s.spec["label_" + getLang()] || s.spec.label_en || s.key });
      }
      /* One shared pattern needs no "All" beside it — it is all of it. Returning a nameless
         placeholder here was the bug behind a pair marked green under a caption saying nothing
         was shared: the placeholder was painted but never listed, so the marks had no name and
         the count said none. Nothing shared now returns nothing. */
      if (found.length < 2) return found;
      // Everything at once, so the reader sees the whole overlap before picking it apart.
      const all = { key: "all", label: t("sim_marks_all"),
        atoms: mols.map((m, i) => [...new Set(found.flatMap(f => f.atoms[i]))]),
        bonds: mols.map((m, i) => [...new Set(found.flatMap(f => f.bonds[i]))]) };
      return [all].concat(found);
    }
    function comparison(rec, qSmiles) {
      const box = el("div", { class: "sim-compare" });
      try {
        const { parts, shared } = drawPair(rec, 200, 150, qSmiles);
        const note = shared ? t("sim_compare_shared") : t("sim_compare_none");
        for (const part of parts) {
          if (!part) continue;
          const cell = el("figure", { class: "sim-figure", role: "button", tabindex: "0",
            title: t("sim_compare_enlarge"),
            onclick: () => openCompare(rec, qSmiles) });
          cell.innerHTML = part.svg;
          cell.appendChild(el("figcaption", { text: part.label }));
          cell.addEventListener("keydown", e => {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openCompare(rec, qSmiles); } });
          box.appendChild(cell);
        }
        box.appendChild(el("p", { class: "sim-compare-note", text: note }));
        // The rail is too narrow to name what the two share; the enlarged pair does, and
        // without this line there is nothing to say so.
        box.appendChild(el("p", { class: "sim-compare-note sim-compare-more",
          text: t("sim_compare_enlarge") }));
      } catch (error) { box.appendChild(el("p", { class: "muted small", text: t("sim_compare_failed") })); }
      return box;
    }

  async function run(prefix) {
    const query = input.value.trim();
    clear(results);
    if (!query) { status.textContent = ""; if (onResults) onResults(null); return; }
    status.textContent = (prefix || "") + t("sim_working");
    try {
      const [loaded, payloadFp] = await Promise.all([
        getRdkit(),
        fingerprints ? Promise.resolve(fingerprints) : L.loadLigandFingerprints()]);
      mod = loaded;
      fingerprints = payloadFp;
      const mol = mod.get_mol(query);
      if (!mol || !mol.is_valid || !mol.is_valid()) {
        if (mol) mol.delete();
        status.textContent = t("sim_invalid"); if (onResults) onResults(null); return;
      }
      const bits = mol.get_morgan_fp_as_uint8array(
        JSON.stringify({ radius: payloadFp.radius, nBits: payloadFp.bits }));
      mol.delete();
      const scored = (payloadFp.records || [])
        .map(r => ({ rec: r, score: tanimoto(bits, unpack(r.fp)) }))
        .filter(r => r.score > 0 && (r.rec.seen_in || []).length)
        .sort((a, b) => b.score - a.score).slice(0, 20);
      status.textContent = (prefix || "") +
        (scored.length ? t("sim_found", { n: scored.length }) : t("sim_none"));
      const handOver = hits => onResults({ query, hits });
      if (onResults) {
        // The caller draws them; the strip inside a query panel is the wrong place to work in.
        handOver(scored.map(hit => ({ ccd: hit.rec.ccd, score: hit.score, rec: hit.rec,
          openCompare: () => openCompare(hit.rec, query) })));
        return;
      }
      for (const hit of scored) {
        const place = hit.rec.seen_in[0];
        /* A hit opens where its structures are, in a new tab, so the list the reader was working
           with is still there when they come back. It lands on a named deposition rather than on
           the filtered list: the row said "1 structures" without ever saying which one, so the
           identifier the reader would have gone looking for was the one thing missing. The
           pipeline puts the sharpest structure of the family first, and that is the one opened. */
        // Straight into the 3D panel, which is what the line under the row promises. Every
        // structure in this release carries a viewer bundle, so the route holds for all of them.
        const href = "#" + buildHash({ family: place.family, view: "3d",
                                       pdb: place.pdb_id, q: hit.rec.ccd }).slice(1);
        // Across every family it appears in, not just the first — the count read as the total.
        const total = (hit.rec.seen_in || []).reduce((n, x) => n + (x.structures || 0), 0);
        const family = familyDisplayName(
          (L.getManifest().families || []).find(f => f.slug === place.family)?.name || place.family);
        results.appendChild(el("a", { class: "sim-hit", href, target: "_blank", rel: "noopener",
          title: t("sim_open_hint", { family }) }, [
          el("span", { class: "sim-score", text: Math.round(hit.score * 100) + "%" }),
          el("span", { class: "sim-ccd", text: hit.rec.ccd }),
          el("span", { class: "sim-name", text: plainName(hit.rec.name || "") }),
          el("span", { class: "sim-where", text: total + " " + t("structures_short") }),
          // The affordance was carried only by the cursor and a tooltip, which is to say by
          // nothing a reader scanning the list would see.
          el("span", { class: "sim-open" }, [
            el("code", { class: "sim-open-pdb", text: place.pdb_id }),
            el("span", { text: t("sim_open_pocket") })])]));
        if (hit.rec.smiles) {
          const details = el("details", { class: "sim-compare-wrap" });
          details.appendChild(el("summary", { text: t("sim_compare_open") }));
          let drawn = false;
          details.addEventListener("toggle", () => {
            if (!details.open || drawn) return;
            drawn = true; details.appendChild(comparison(hit.rec, query));
          });
          results.appendChild(details);
        }
      }
    } catch (error) { status.textContent = t("sim_failed"); if (onResults) onResults(null); }
  }

  // A query typed as SMILES is no longer the one taken from an entry, so the other components
  // of that entry stop being offered.
  const runTyped = () => { clear(alternatives); run(); };
  input.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); runTyped(); } });
  exampleOnTab(input, t("sim_example_smiles"));
  pdbInput.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); fromPdb(); } });
  exampleOnTab(pdbInput, t("sim_pdb_placeholder"));
  body.appendChild(el("label", { class: "sim-label" }, [
    document.createTextNode(t("sim_smiles_label") + " "),
    el("span", { class: "sim-tab-hint", text: t("sim_tab_hint") })]));
  body.appendChild(input);
  body.appendChild(el("button", { class: "btn small sim-run", type: "button",
    text: t("sim_run"), onclick: runTyped }));
  /* A structure someone drew is in a file, and asking them to convert it to SMILES first is
     asking them to do the one step this panel exists to save. Molfiles are read by the same RDKit
     build that does everything else here, so the file is parsed in the browser and never uploaded;
     "upload" is the familiar word for the control, but nothing leaves the machine.

     Mol2 is not offered: this RDKit build exposes get_mol and get_mol_from_uint8array and carries
     no mol2 parser, so a .mol2 would fail with a message about SMILES that explained nothing. It
     is named as unsupported instead. */
  const fileName = el("span", { class: "sim-file-name" });
  const fileInput = el("input", { type: "file", class: "sim-file", id: "sim-file-single",
    accept: ".sdf,.mol,.mdl,.sd,chemical/x-mdl-molfile,chemical/x-mdl-sdfile" });
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files && fileInput.files[0];
    fileName.textContent = file ? file.name : "";
    if (!file) return;
    clear(results); clear(alternatives);
    if (/\.mol2$/i.test(file.name)) { status.textContent = t("sim_file_mol2"); return; }
    status.textContent = t("sim_working");
    try {
      const text = await file.text();
      // An SDF holds a series; the first record is taken as the query and the panel says so.
      const parts = text.split(/^\$\$\$\$/m).filter(x => x.trim());
      const mod = await getRdkit();
      const mol = mod.get_mol(parts[0] || text);
      if (!mol || !mol.is_valid || !mol.is_valid()) {
        if (mol) mol.delete();
        status.textContent = t("sim_file_invalid", { name: file.name }); return;
      }
      const smiles = mol.get_smiles();
      mol.delete();
      input.value = smiles;
      const prefix = t("sim_file_taken", { name: file.name }) +
        (parts.length > 1 ? " " + t("sim_file_more", { n: parts.length - 1 }) : "");
      status.textContent = prefix;
      await run(prefix + " ");
    } catch (error) { status.textContent = t("sim_file_failed", { name: file.name }); }
  });
  body.appendChild(el("label", { class: "sim-label sim-or", text: t("sim_file_label") }));
  body.appendChild(el("div", { class: "sim-file-row" }, [fileInput,
    el("label", { class: "btn small sim-file-button", for: "sim-file-single",
      text: t("sim_file_choose") }), fileName]));
  body.appendChild(el("label", { class: "sim-label sim-or" }, [
    document.createTextNode(t("sim_pdb_label") + " "),
    el("span", { class: "sim-tab-hint", text: t("sim_tab_hint") })]));
  const pdbRow = el("div", { class: "sim-pdb-row" }, [pdbInput,
    el("button", { class: "btn small", type: "button", text: t("sim_pdb_run"), onclick: fromPdb })]);
  body.appendChild(pdbRow);
  body.appendChild(status);
  body.appendChild(alternatives);
  body.appendChild(results);
  /* Several queries at once. Kept behind a disclosure because it answers a different need from
     the one the panel opens with: not "show me what this resembles" but "give me the table for
     these twenty and let me keep it". */
  const batchBox = el("details", { class: "sim-batch", open: true });
  batchBox.appendChild(el("summary", {}, [document.createTextNode(t("sim_batch_title") + " "),
    el("span", { class: "sim-tab-hint", text: t("sim_tab_hint") })]));
  const batchInput = el("textarea", { class: "sim-batch-input", rows: "5",
    placeholder: t("sim_batch_placeholder"), spellcheck: "false" });
  const batchStatus = el("p", { class: "sim-status muted small" });
  const batchActions = el("div", { class: "sim-batch-actions" });
  const runButton = el("button", { class: "btn small btn-primary", type: "button", text: t("sim_batch_run"),
    onclick: async () => {
      batchStatus.textContent = t("sim_batch_working", { done: 0, total: 0 });
      let result;
      try {
        mod = await getRdkit();
        result = await runBatch({ text: batchInput.value, onProgress: (done, total) => {
          batchStatus.textContent = t("sim_batch_working", { done, total }); } });
      } catch (error) { batchStatus.textContent = t("sim_failed"); return; }
      if (!result.queries.length) { batchStatus.textContent = t("sim_batch_empty"); return; }
      batchStatus.textContent = t("sim_batch_done", { queries: result.queries.length,
        rows: result.rows.length })
        + (result.failed.length ? " " + t("sim_batch_failed",
            { n: result.failed.length, list: result.failed.map(f => f.label).join(", ") }) : "");
      /* A batch drives the page exactly as a single query does. Keeping its results in this box
         meant two query mechanisms competing for one listing, with only one of them winning and
         nothing on screen saying which — so the box showed one set of molecules while the banner
         named another. The single-query field is cleared for the same reason. */
      if (onResults) {
        input.value = "";
        onResults({ batch: result, queries: result.queries.length,
          hits: bestPerHit(result).map(h => ({ ...h,
            openCompare: () => openCompare(h.rec, h.querySmiles) })) });
      }
    } });
  batchActions.appendChild(runButton);
  exampleOnTab(batchInput, t("sim_batch_example"));

  /* Two more ways to fill the box, because a set of queries rarely starts life as typed SMILES.
     Both append lines rather than replacing what is there, so a reader can build a list from a
     folder of molfiles, a handful of depositions and their own typing at once. */
  const appendLines = lines => {
    const existing = batchInput.value.replace(/\s+$/, "");
    batchInput.value = (existing ? existing + "\n" : "") + lines.join("\n") + "\n";
    batchInput.scrollTop = batchInput.scrollHeight;
  };
  const batchFileName = el("span", { class: "sim-file-name" });
  const batchFiles = el("input", { type: "file", class: "sim-file", multiple: true,
    accept: ".sdf,.mol,.mdl,.sd,chemical/x-mdl-molfile,chemical/x-mdl-sdfile" });
  batchFiles.id = "sim-file-batch";
  batchFiles.addEventListener("change", async () => {
    const files = [...(batchFiles.files || [])];
    batchFileName.textContent = files.length ? t("sim_file_count", { n: files.length }) : "";
    if (!files.length) return;
    batchStatus.textContent = t("sim_working");
    const added = [], failed = [];
    try {
      mod = await getRdkit();
      for (const file of files) {
        if (/\.mol2$/i.test(file.name)) { failed.push(file.name); continue; }
        const text = await file.text();
        // Every record of an SDF, not just the first: a file of twenty molecules is twenty queries.
        const records = text.split(/^\$\$\$\$/m).map(x => x.trim()).filter(Boolean);
        records.forEach((record, i) => {
          const molecule = mod.get_mol(record);
          if (!molecule || !molecule.is_valid || !molecule.is_valid()) {
            if (molecule) molecule.delete();
            failed.push(file.name + (records.length > 1 ? " #" + (i + 1) : "")); return;
          }
          const named = /^\s*(\S.*)$/.exec(record);
          const label = records.length > 1 && named && !named[1].startsWith("$")
            ? named[1].trim().slice(0, 40) : file.name.replace(/\.[^.]+$/, "");
          added.push(molecule.get_smiles() + "  " + (label || file.name));
          molecule.delete();
        });
      }
    } catch (error) { batchStatus.textContent = t("sim_batch_file_failed"); return; }
    if (added.length) appendLines(added);
    batchStatus.textContent = t("sim_batch_files_added", { n: added.length })
      + (failed.length ? " " + t("sim_batch_files_skipped", { list: failed.join(", ") }) : "");
    batchFiles.value = "";
  });

  const batchPdb = el("input", { type: "text", class: "sim-batch-pdb", spellcheck: "false",
    placeholder: t("sim_batch_pdb_placeholder") });
  const batchPdbButton = el("button", { class: "btn small", type: "button",
    text: t("sim_batch_pdb_run"), onclick: async () => {
      const codes = batchPdb.value.toUpperCase().split(/[^0-9A-Z]+/).filter(x => x.length === 4);
      if (!codes.length) { batchStatus.textContent = t("sim_pdb_invalid"); return; }
      batchStatus.textContent = t("sim_working");
      try {
        const payloadFp = fingerprints || (fingerprints = await L.loadLigandFingerprints());
        const chemistry = await L.loadLigandChemistry();
        const smilesOf = new Map((chemistry.records || []).map(r => [r.ccd, r.raw_smiles]));
        const added = [], missing = [];
        for (const code of codes) {
          // Every component of the entry that the atlas holds a structure for, not just one:
          // naming a deposition is naming its ligands, and which of them is the query is the
          // reader's choice, not a coin toss.
          const components = ((payloadFp.by_structure || {})[code] || []).filter(x => smilesOf.get(x));
          if (!components.length) { missing.push(code); continue; }
          for (const component of components)
            added.push(smilesOf.get(component) + "  " + code + ":" + component);
        }
        if (added.length) appendLines(added);
        batchStatus.textContent = t("sim_batch_pdb_added", { n: added.length, codes: codes.length })
          + (missing.length ? " " + t("sim_batch_pdb_missing", { list: missing.join(", ") }) : "");
        batchPdb.value = "";
      } catch (error) { batchStatus.textContent = t("sim_failed"); }
    } });

  batchBox.appendChild(batchInput);
  batchBox.appendChild(el("div", { class: "sim-batch-feeds" }, [
    el("label", { class: "sim-label", text: t("sim_batch_files_label") }),
    el("div", { class: "sim-file-row" }, [batchFiles,
      el("label", { class: "btn small sim-file-button", for: "sim-file-batch",
        text: t("sim_file_choose_many") }), batchFileName]),
    el("label", { class: "sim-label", text: t("sim_batch_pdb_label") }),
    el("div", { class: "sim-pdb-row" }, [batchPdb, batchPdbButton])]));
  batchBox.appendChild(batchActions);
  batchBox.appendChild(batchStatus);
  batchBox.appendChild(el("p", { class: "sim-note", text: t("sim_batch_note") }));
  body.appendChild(batchBox);
  body.appendChild(el("p", { class: "sim-note", text: t("sim_note") }));
  box.appendChild(body);
  return box;
}
