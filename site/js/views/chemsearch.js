// Chemistry search: the structural-similarity query and the pair comparison it opens.
//
// This was written inside the structures view, where it was the chemistry rail's entry point.
// The ligand explorer asks the same question as its opening move, and a second copy of a
// fingerprint search is not something to keep in step by hand, so it lives here and both views
// call it. Nothing in it is specific to either: it loads its own payloads, draws with the
// vendored RDKit build, and returns a node.
import { t, getLang } from "../core/i18n.js";
import { el, clear, debounce } from "../components/dom.js";
import { downloadBlob } from "../components/csv.js";
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
export function createSimilarityPanel() {
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

  async function run(prefix) {
    const query = input.value.trim();
    clear(results);
    if (!query) { status.textContent = ""; return; }
    status.textContent = (prefix || "") + t("sim_working");
    try {
      const [mod, payloadFp] = await Promise.all([
        getRdkit(),
        fingerprints ? Promise.resolve(fingerprints) : L.loadLigandFingerprints()]);
      fingerprints = payloadFp;
      const mol = mod.get_mol(query);
      if (!mol || !mol.is_valid || !mol.is_valid()) {
        if (mol) mol.delete();
        status.textContent = t("sim_invalid"); return;
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
      /* What the two molecules have in common, drawn rather than asserted. The hit's
         Bemis-Murcko scaffold is matched into both structures and those atoms are highlighted:
         it is the shared ring system, not a maximum common substructure, and the caption says
         so. Where the scaffold does not match the query the pair is still drawn, unmarked. */
      function drawPair(rec, width, height) {
        const pattern = rec.scaffold ? mod.get_qmol(rec.scaffold) : null;
        const prepared = [[query, t("sim_compare_query")], [rec.smiles, rec.ccd]]
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
      async function openCompare(rec) {
        const width = 430, height = 350;
        const catalog = await L.loadChemistryCatalog().catch(() => null);
        const mols = [[query, t("sim_compare_query")], [rec.smiles, rec.ccd]].map(([smiles, label]) => {
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
        if (marks.length > 1) {
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
          const qmol = mod.get_qmol(rec.scaffold);
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
        if (found.length < 2) return found.length ? found : [{ key: "none", label: "",
          atoms: [[], []], bonds: [[], []] }];
        // Everything at once, so the reader sees the whole overlap before picking it apart.
        const all = { key: "all", label: t("sim_marks_all"),
          atoms: mols.map((m, i) => [...new Set(found.flatMap(f => f.atoms[i]))]),
          bonds: mols.map((m, i) => [...new Set(found.flatMap(f => f.bonds[i]))]) };
        return [all].concat(found);
      }
      function comparison(rec) {
        const box = el("div", { class: "sim-compare" });
        try {
          const { parts, shared } = drawPair(rec, 200, 150);
          const note = shared ? t("sim_compare_shared") : t("sim_compare_none");
          for (const part of parts) {
            if (!part) continue;
            const cell = el("figure", { class: "sim-figure", role: "button", tabindex: "0",
              title: t("sim_compare_enlarge"),
              onclick: () => openCompare(rec) });
            cell.innerHTML = part.svg;
            cell.appendChild(el("figcaption", { text: part.label }));
            cell.addEventListener("keydown", e => {
              if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openCompare(rec); } });
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
      for (const hit of scored) {
        const place = hit.rec.seen_in[0];
        // A hit opens where its structures are, in a new tab, so the list the reader was
        // working with is still there when they come back.
        const href = "#" + buildHash({ family: place.family, view: "structures",
                                       q: hit.rec.ccd }).slice(1);
        results.appendChild(el("a", { class: "sim-hit", href, target: "_blank", rel: "noopener",
          title: t("sim_open_hint", { family: familyDisplayName(
            (L.getManifest().families || []).find(f => f.slug === place.family)?.name || place.family) }) }, [
          el("span", { class: "sim-score", text: Math.round(hit.score * 100) + "%" }),
          el("span", { class: "sim-ccd", text: hit.rec.ccd }),
          el("span", { class: "sim-name", text: plainName(hit.rec.name || "") }),
          el("span", { class: "sim-where", text: place.structures + " " + t("structures_short") })]));
        if (hit.rec.smiles) {
          const details = el("details", { class: "sim-compare-wrap" });
          details.appendChild(el("summary", { text: t("sim_compare_open") }));
          let drawn = false;
          details.addEventListener("toggle", () => {
            if (!details.open || drawn) return;
            drawn = true; details.appendChild(comparison(hit.rec));
          });
          results.appendChild(details);
        }
      }
    } catch (error) { status.textContent = t("sim_failed"); }
  }

  // A query typed as SMILES is no longer the one taken from an entry, so the other components
  // of that entry stop being offered.
  const runTyped = () => { clear(alternatives); run(); };
  input.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); runTyped(); } });
  pdbInput.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); fromPdb(); } });
  body.appendChild(el("label", { class: "sim-label", text: t("sim_smiles_label") }));
  body.appendChild(input);
  body.appendChild(el("button", { class: "btn small sim-run", type: "button",
    text: t("sim_run"), onclick: runTyped }));
  body.appendChild(el("label", { class: "sim-label sim-or", text: t("sim_pdb_label") }));
  const pdbRow = el("div", { class: "sim-pdb-row" }, [pdbInput,
    el("button", { class: "btn small", type: "button", text: t("sim_pdb_run"), onclick: fromPdb })]);
  body.appendChild(pdbRow);
  body.appendChild(status);
  body.appendChild(alternatives);
  body.appendChild(results);
  body.appendChild(el("p", { class: "sim-note", text: t("sim_note") }));
  box.appendChild(body);
  return box;
}
