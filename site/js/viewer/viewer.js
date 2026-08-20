// Site-aware 3D viewer. Small-molecule pockets and polymer interfaces use different
// terminology, different default representations and different camera framing.
import { t, siteClassLabel } from "../core/i18n.js";
import { el, clear } from "../components/dom.js";
import { loadBundleMeta, bundleCifUrl, errorMessage } from "../data/loader.js";
import * as LC from "./lifecycle.js";

let comp = null, meta = null, current = null, reps = {};
let ligandMode = "cartoon";
let viewerBackground = "black";
/* Every generic-numbered residue of the receptor chain, not only the ligand's contact shell.
   The coordinates always held the whole chain; what was missing was the table saying which
   residue carries which generic number, so a position outside the pocket could be named in the
   motif panel and then not clicked on here. Loaded on demand — a reader who stays in the pocket
   never fetches it — so an empty table means "not asked for yet" or "not available for this
   structure", and the panel says which. */
let residueTable = [];
/* The positions a reader arrived with, carried over from the motif panel's query. Held apart from
   the manual selection on purpose: they are not something clicked here and must survive the two
   residue lists, so switching between the pocket and the whole receptor does not lose the reason
   the reader opened the structure. */
const queryResidues = new Set();
let queryPositions = [];
const selectedResidues = new Set();
const selectedMotifs = new Set();
const HELICES = ["TM1", "TM2", "TM3", "TM4", "TM5", "TM6", "TM7"];
const POLYMER = { extracellular_polymer_interface: 1, tethered_ligand_interface: 1 };
const MOTIF_SPECS = {
  PIF_connector: { positions:["3x40","5x50","6x44"], expected:{
    "3x40":["I"], "5x50":["P"], "6x44":["F"] } },
  DRY_region: { positions:["3x49","3x50","3x51"], expected:{
    "3x49":["D","E"], "3x50":["R"], "3x51":["Y"] } },
  ionic_lock_pair: { positions:["3x50","6x30"], expected:{
    "3x50":["R"], "6x30":["D","E"] } },
  CWxP_W6x48_switch: { positions:["6x47","6x48","6x50"], expected:{
    "6x47":["C"], "6x48":["W"], "6x50":["P"] } },
  NPxxY_region: { positions:["7x49","7x50","7x51","7x52","7x53"], expected:{
    "7x49":["N"], "7x50":["P"], "7x53":["Y"] } },
  TM5_TM7_tyrosine_network: { positions:["5x58","7x53"], expected:{
    "5x58":["Y"], "7x53":["Y"] } }
};
const MOTIF_POSITIONS = {
  tm5_polar:["5x42","5x43","5x46","5x461"],
  aromatic_pocket:["6x48","6x51","6x52","7x42"],
  sodium_pocket_network:["2x50","3x39","7x45","7x46","7x49"]
};
function backgroundColor() { return viewerBackground === "white" ? "#ffffff" : "#0b0d10"; }
export function currentBackground() { return viewerBackground; }
export function setBackground(mode) {
  viewerBackground = mode === "white" ? "white" : "black";
  const stage = LC.getStage();
  if (stage) stage.setParameters({ backgroundColor:backgroundColor() });
  /* The distance labels are legible against one background and not the other, so they follow the
     switch rather than waiting for the next redraw. Rebuilt rather than repainted: going back to
     white has to restore NGL's own per-interaction label colouring, and rebuilding restores it by
     construction instead of by naming a value we would be guessing at. Only rebuilt if the lines
     are on screen — if the reader turned them off, they stay off. */
  if (reps.lines) addDisplayedInteractions();
  // The carbon overlay is background-dependent for the same reason and is rebuilt with it.
  if (reps.ligand) addDisplayedLigands();
}

function sel(residues) {
  if (!residues || !residues.length) return "none";
  return residues.map(r => r[1] + ":" + r[0]).join(" or ");
}

function activeReceptorChain() {
  const o = obs();
  const chain = o && (o.contact_receptor_details || [])[0] && o.contact_receptor_details[0].auth_asym_id;
  return chain || (meta && meta.receptor_chains && meta.receptor_chains[0]) || "";
}

function receptorSelection() {
  const chain = activeReceptorChain();
  return chain ? ":" + chain : "polymer";
}

function withoutHydrogen(selection) { return "(" + selection + ") and not hydrogen"; }

function ligandSelection(o) {
  if (!o || !o.ligand_selection) return "none";
  if (o.ligand_selection.selection_kind === "polymer_segment")
    return sel(o.ligand_selection.residues || []);
  // Contact residues are intentionally sparse.  Using them as the displayed
  // selection fragments peptide/protein ligands and makes their backbone look
  // missing.  The bundle already records the ligand chain paired with this
  // receptor instance, so polymer interfaces must display that complete chain.
  if (POLYMER[o.binding_site_class] && (o.ligand_selection.chains || []).length)
    return o.ligand_selection.chains.map(chain => ":" + chain).join(" or ");
  // Ligand selections may contain symmetry-related copies from every protomer.
  // The contact list identifies the copy paired with the active receptor chain, so it is
  // preferred — but only where it agrees with the residues this observation declares. A
  // structure can hold two copies of one component in different sites (7CFN: INT-777 at R:403
  // orthosteric and R:401 lipid-facing), and there the contact list names both copies. Taking
  // it whole made the two observations resolve to the same atoms, so switching between them
  // changed nothing on screen.
  const declared = o.ligand_selection.residues || [];
  const contacts = o.contact_ligand_residues || [];
  const residueKey = r => r[0] + ":" + r[1];
  const declaredKeys = new Set(declared.map(residueKey));
  const narrowed = contacts.filter(r => declaredKeys.has(residueKey(r)));
  const residueSele = sel(narrowed.length ? narrowed : (declared.length ? declared : contacts));
  // Author residue numbers are not globally unique across ATOM and HETATM records.  Without
  // this guard, a ligand such as A:301 also selects receptor residue A:301 and creates a false
  // second ligand/contact focus. Polymer ligands take the complete-chain branch above.
  return residueSele === "none" ? residueSele : "(" + residueSele + ") and hetero";
}

function heavyAtomsWithContactHydrogens(residueSelection, ligandSele, cutoff=2.7) {
  if (!comp || !window.NGL) return withoutHydrogen(residueSelection);
  const ligandHeavy = [], chosen = [];
  try {
    comp.structure.eachAtom(a => {
      if (a.number === 7 || a.number === 8 || a.number === 16)
        ligandHeavy.push([a.x, a.y, a.z]);
    }, new window.NGL.Selection(withoutHydrogen(ligandSele)));
    const cutoff2 = cutoff * cutoff;
    comp.structure.eachAtom(a => {
      if (a.number !== 1) { chosen.push(a.index); return; }
      let donorHydrogen = false;
      try { a.eachBondedAtom(b => { if (b.number === 7 || b.number === 8 || b.number === 16) donorHydrogen = true; }); }
      catch (e) {}
      if (!donorHydrogen) return;
      for (const p of ligandHeavy) {
        const dx=a.x-p[0], dy=a.y-p[1], dz=a.z-p[2];
        if (dx*dx + dy*dy + dz*dz <= cutoff2) { chosen.push(a.index); break; }
      }
    }, new window.NGL.Selection(residueSelection));
  } catch (e) { return withoutHydrogen(residueSelection); }
  return chosen.length ? "@" + chosen.join(",") : withoutHydrogen(residueSelection);
}

function addCovalentHighlight(o) {
  if (!comp || !o || o.binding_site_class !== "covalent_core_site") return;
  const ligandAtoms = [], receptorAtoms = [];
  try {
    comp.structure.eachAtom(a => { if (a.number !== 1) ligandAtoms.push({ i:a.index, x:a.x, y:a.y, z:a.z }); },
      new window.NGL.Selection(withoutHydrogen(ligandSelection(o))));
    comp.structure.eachAtom(a => { if (a.number !== 1) receptorAtoms.push({ i:a.index, x:a.x, y:a.y, z:a.z }); },
      new window.NGL.Selection(withoutHydrogen(sel(o.contact_receptor_residues))));
  } catch (e) { return; }
  let best = null, best2 = Infinity;
  for (const a of ligandAtoms) for (const b of receptorAtoms) {
    const dx=a.x-b.x, dy=a.y-b.y, dz=a.z-b.z, d2=dx*dx+dy*dy+dz*dz;
    if (d2 < best2) { best2=d2; best=[a.i,b.i]; }
  }
  // A generous upper bound covers deposited covalent bonds while excluding ordinary contacts.
  if (!best || best2 > 2.2*2.2) return;
  addRep("covalent_atoms", "ball+stick", { sele:"@" + best.join(","),
    colorScheme:"element", scale:1.18, aspectRatio:2.2 });
  addRep("covalent_bond", "distance", { atomPair:[best], colorValue:0xf28c00,
    labelColor:0xffb14a, labelUnit:"angstrom", labelSize:0.9, labelFixedSize:true,
    useCylinder:false, linewidth:5 });
}

/* The ligand under discussion is the subject of the picture, so its carbon skeleton is the
   brightest thing in it — white against the dark receptor rather than NGL's default grey, which
   sits at about the same value as the cartoon behind it. Which colour that is has to follow the
   background: white carbons on the white background would be an invisible ligand. */
function ligandCarbonColour() { return viewerBackground === "black" ? "#ffffff" : "#2b2f36"; }

/* An overlay on the carbons only, not a recolour of the ligand: N, O, S and the halogens keep
   their element colours, which is most of what makes a ligand readable as a chemical structure. */
function addSelectedCarbonHighlight(key, type, selection, params={}) {
  addRep(key + "_selected_carbon", type, Object.assign({
    sele:"(" + withoutHydrogen(selection) + ") and _C", color:ligandCarbonColour(), opacity:1
  }, params));
}

function addLigandRepresentation(o, key="ligand", selected=false) {
  if (!o || !o.ligand_selection) return;
  const lsel = ligandSelection(o);
  if (POLYMER[o.binding_site_class]) {
    if (ligandMode === "licorice") {
      addRep(key, "licorice", { sele:withoutHydrogen(lsel),
        colorScheme:"element", opacity:0.96, radiusScale:1.08 });
      if (selected) addSelectedCarbonHighlight(key, "licorice", lsel, { radiusScale:1.1 });
    } else {
      addRep(key, "cartoon", { sele:lsel, color:"#eadb72", opacity:0.96 });
      // Keep the old hybrid view: the whole peptide is a cartoon, while only
      // ligand residues that contact the receptor remain atomically readable.
      const contacting = sel(o.contact_ligand_residues || []);
      if (contacting !== "none")
        addRep(key + "_stick", "licorice", { sele:withoutHydrogen(contacting),
          colorScheme:"element", opacity:0.96, radiusScale:1.08 });
      if (selected && contacting !== "none")
        addSelectedCarbonHighlight(key + "_stick", "licorice", contacting, { radiusScale:1.1 });
    }
  } else {
    addRep(key, "ball+stick", { sele:withoutHydrogen(lsel), colorScheme:"element" });
    if (selected) addSelectedCarbonHighlight(key, "ball+stick", lsel);
  }
}

function ligandObservations() {
  return (meta && meta.observations || []).filter(o => o.ligand_selection);
}

function dropByPrefix(prefix) {
  for (const key of Object.keys(reps)) if (key === prefix || key.startsWith(prefix + "_")) dropRep(key);
}

function addDisplayedLigands() {
  const active = obs();
  const ligands = ligandObservations();
  const ordered = ligands.slice().sort((a, b) =>
    (a === active ? -1 : 0) - (b === active ? -1 : 0));
  /* Applied to the active ligand however many there are. It used to be conditional on there being
     more than one, so the ordinary case — one ligand — was the one that never got it, and the
     carbons stayed grey exactly where nothing else was competing for attention. Where a structure
     does hold several, the others keep the default grey and the distinction the condition was
     there to make still holds. */
  ordered.forEach((o, i) => addLigandRepresentation(o,
    i ? "ligand_extra_" + i : "ligand", o === active));
}

export function hasCovalentBond() {
  const o = obs();
  return !!(o && o.binding_site_class === "covalent_core_site");
}

export function isPolymerLigand() {
  const o = obs();
  return !!(o && POLYMER[o.binding_site_class]);
}

export async function open(host, pdb, observationId, onStatus) {
  const NGL = window.NGL;
  if (!NGL) { onStatus(t("err_webgl")); return null; }
  onStatus(t("loading_structure"));
  /* Cleared before the new structure loads, not only in close(). Opening a second structure while
     the modal stays open — which changing the address does — left the previous structure's residue
     table in place, and every position in it keyed by an auth_seq_id that means something else
     here. It survived only because the chain letters usually differ and the chain filter emptied
     the list; where two structures share a chain letter it would have drawn one receptor's
     positions on another's coordinates. */
  residueTable = []; queryResidues.clear(); queryPositions = [];
  try { meta = await loadBundleMeta(pdb); }
  catch (e) { onStatus(errorMessage(e)); return null; }
  let stage;
  try { stage = LC.createStage(NGL, host, { backgroundColor: backgroundColor(), quality: "high" }); }
  catch (e) { onStatus(t("err_webgl")); return null; }
  // the host is visible by the time we get here; resize after creation and after load
  LC.resizeStageIfVisible();
  try {
    comp = await stage.loadFile(bundleCifUrl(pdb), { ext: "cif" });
  } catch (e) { onStatus(t("err_bundle")); LC.destroyStage(); return null; }
  // NGL appends the component name to its atom hover tooltip.  The transport
  // filename "viewer.cif" is an implementation detail; use the meaningful PDB id.
  try { comp.setName(meta.pdb_id); comp.structure.name = meta.pdb_id; } catch (e) {}
  // A WebGL canvas is opaque to assistive technology: without a name it is announced as nothing
  // at all. Name it after the structure it is showing, and re-name it whenever that changes.
  labelCanvas(host, pdb);
  LC.resizeStageIfVisible();
  current = observationId ||
    (meta.observations.find(o => o.ligand_selection) || meta.observations[0] || {}).observation_id;
  applyDefaults();
  onStatus("");
  return meta;
}

function labelCanvas(host, pdb) {
  const cv = host && host.querySelector("canvas");
  if (!cv) return;
  cv.setAttribute("role", "img");
  cv.setAttribute("aria-label", t("viewer_canvas_label").replace("{pdb}", pdb || ""));
}

export function close() { LC.destroyStage(); comp = null; meta = null; current = null; reps = {};
  residueTable = []; queryResidues.clear(); queryPositions = [];
  selectedResidues.clear(); selectedMotifs.clear(); }

/* Resolved through the residue table, so a position the structure does not resolve simply does not
   appear rather than being drawn at the wrong atom. Returns how many of the asked-for positions
   this structure actually has, which is what the panel reports. */
export function setQueryPositions(positions) {
  queryPositions = Array.isArray(positions) ? positions.filter(Boolean) : [];
  queryResidues.clear();
  const chain = activeReceptorChain();
  const want = new Set(queryPositions);
  for (const r of residueTable) {
    if (chain && r.c !== chain) continue;
    if (want.has(r.p)) queryResidues.add(residueKey(r.c, r.n));
  }
  redrawSelections();
  return queryResidues.size;
}
export function queryPositionList() { return queryPositions.slice(); }
export function hasQueryMarks() { return queryResidues.size > 0; }
export function isQueryPosition(position) { return queryPositions.indexOf(position) >= 0; }
/* The marks alone, so a reader who came with a query lands looking at it rather than at whatever
   the default framing chose. Falls back to the receptor when nothing resolved. */
export function frameQuery() {
  if (!comp) return false;
  if (!queryResidues.size) return false;
  frame(Array.from(queryResidues).join(" or "));
  return true;
}

/* ------------------------------------------------- the receptor beyond the pocket */
export function setResidueTable(rows) { residueTable = Array.isArray(rows) ? rows : []; }
export function hasResidueTable() { return residueTable.length > 0; }

/* Grouped for the panel: one list per helix, in position order, for the chain on screen. H8 and
   the resolved loop residues are kept in a group of their own rather than dropped — they are as
   real as the helical ones, they just are not one of the seven columns the panel draws. */
/* The seven the panel draws, so a caller can tell which of them a structure has nothing for. */
export function helixOrder() { return HELICES.slice(); }

export function receptorSegments() {
  const chain = activeReceptorChain();
  const rows = residueTable.filter(r => !chain || r.c === chain);
  /* Which of these the ligand is already in contact with. Marked rather than listed separately:
     the pocket list and this one then describe the same residues the same way, and a reader can
     see at a glance which of the positions they are browsing the pocket panel would have shown. */
  const contacts = new Set();
  const o = obs();
  for (const r of (o && o.contact_receptor_details) || [])
    contacts.add(residueKey(r.auth_asym_id, r.auth_seq_id));
  for (const [c, seq] of (o && o.contact_receptor_residues) || [])
    contacts.add(residueKey(c, seq));
  const groups = new Map();
  for (const r of rows) {
    const key = HELICES.indexOf(r.s) >= 0 ? r.s : "other";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(Object.assign({ contact:contacts.has(residueKey(r.c, r.n)),
      query:queryResidues.has(residueKey(r.c, r.n)) }, r));
  }
  const out = HELICES.filter(h => groups.has(h)).map(h => ({ segment:h, helix:true,
    residues:groups.get(h) }));
  if (groups.has("other")) out.push({ segment:"other", helix:false, residues:groups.get("other") });
  return out;
}

/* The whole bundle rather than the pocket. Used when a reader opens a structure to look at a
   position the ligand never touches: framing the pocket would put it off screen.

   Framed on the receptor's own residues, not on its chain. A crystallisation construct puts the
   fusion partner on the same auth chain — 6E59 carries the receptor at 28-320 and a BRIL domain
   at 1001-1196 — so framing the chain fits a bounding sphere around both, leaves the receptor at
   a third of the viewport and shrinks the residue labels to a few pixels. The generic-numbered
   residues are exactly the receptor, which is what the reader asked to see. */
export function frameReceptor() {
  if (!comp) return;
  frame(receptorFrameSelection());
}

function receptorFrameSelection() {
  const chain = activeReceptorChain();
  const numbers = residueTable.filter(r => !chain || r.c === chain)
    .map(r => parseInt(r.n, 10)).filter(n => Number.isFinite(n)).sort((a, b) => a - b);
  if (!numbers.length) return receptorSelection();
  // Collapsed into runs so the selection stays short. A structure resolved in many fragments
  // falls back to its span rather than emitting a selection string of unbounded length.
  const runs = [];
  for (const n of numbers) {
    const last = runs[runs.length - 1];
    if (last && n <= last[1] + 1) last[1] = Math.max(last[1], n);
    else runs.push([n, n]);
  }
  const suffix = chain ? ":" + chain : "";
  if (runs.length > 24) return numbers[0] + "-" + numbers[numbers.length - 1] + suffix;
  return runs.map(([a, b]) => (a === b ? a : a + "-" + b) + suffix).join(" or ");
}
export function meta_() { return meta; }
export function currentObservation() { return current; }
export function setObservation(id) { if (!comp) { current = id; return; } current = id; applyDefaults(); }

function obs() { return (meta && meta.observations || []).find(o => o.observation_id === current) || null; }

// A late event — a toggle fired while the modal is closing, or a stray change handler — must
// not throw against a torn-down component. Every representation helper is a no-op once the
// stage is gone.
function addRep(key, type, params) {
  if (!comp) return null;
  if (reps[key]) { try { comp.removeRepresentation(reps[key]); } catch (e) {} }
  try { reps[key] = comp.addRepresentation(type, params); } catch (e) { return null; }
  return reps[key];
}
function dropRep(key) {
  if (reps[key] && comp) { try { comp.removeRepresentation(reps[key]); } catch (e) {} }
  delete reps[key];
}

export function applyDefaults() {
  if (!comp || !meta) return;
  for (const k of Object.keys(reps)) dropRep(k);
  const rc = receptorSelection();
  ligandMode = "cartoon";
  selectedResidues.clear(); selectedMotifs.clear();
  addRep("cartoon", "cartoon", { sele: rc, color: "#646a73", opacity: 0.68 });
  const o = obs();
  if (o && o.ligand_selection) {
    const all = ligandObservations();
    addDisplayedLigands();
    all.forEach((lig, i) => addRep((POLYMER[lig.binding_site_class] ? "iface_" : "contacts_") + i,
      "licorice", { sele:withoutHydrogen(sel(lig.contact_receptor_residues)),
        colorScheme:"element", colorValue:0x8ab8e8 }));
    addDisplayedInteractions();
    addCovalentHighlight(o);
    addContactLabels();
    frame(all.map(lig => "(" + ligandSelection(lig) + ") or (" +
      sel(lig.contact_receptor_residues) + ")").join(" or "));
  } else {
    comp.autoView(400);
  }
}

export function frame(selection) {
  if (!comp) return;
  try { comp.autoView(selection, 400); } catch (e) { comp.autoView(400); }
}

function residueKey(chain, seq) { return String(seq) + ":" + String(chain); }
function motifLabel(id) {
  const key = ({ tm5_polar:"v_motif_tm5_polar", aromatic_pocket:"v_motif_aromatic",
    PIF_connector:"v_motif_pif", CWxP_W6x48_switch:"v_motif_cwxp",
    DRY_region:"v_motif_dry", ionic_lock_pair:"v_motif_ionic_lock",
    sodium_pocket_network:"v_motif_sodium", NPxxY_region:"v_motif_npxxy",
    TM5_TM7_tyrosine_network:"v_motif_tyrosine_network" })[id];
  return key ? t(key) : id.replaceAll("_", " ");
}
function genericShort(value) {
  const s = String(value || "");
  const m = s.match(/^(\d+)(?:\.\d+)?x(\d+)$/);
  return m ? m[1] + "x" + m[2] : s;
}
function oneLetter(name) { return ({ ALA:"A",ARG:"R",ASN:"N",ASP:"D",CYS:"C",GLN:"Q",GLU:"E",
  GLY:"G",HIS:"H",ILE:"I",LEU:"L",LYS:"K",MET:"M",PHE:"F",PRO:"P",SER:"S",THR:"T",
  TRP:"W",TYR:"Y",VAL:"V" })[String(name || "").toUpperCase()] || "?"; }

/* A selected residue outside the ligand's contact shell has no entry in the observation, so the
   label map had nothing to say about it and it was drawn as an unnamed stick. The whole-receptor
   table covers exactly those, and the observation still wins where both describe a residue —
   it carries the distance and the contact type, which the table does not. */
function selectedDetails() {
  const o = obs();
  const out = [], seen = new Set();
  for (const r of (o && o.contact_receptor_details) || []) {
    const key = residueKey(r.auth_asym_id, r.auth_seq_id);
    if (selectedResidues.has(key)) { out.push(r); seen.add(key); }
  }
  for (const r of residueTable) {
    const key = residueKey(r.c, r.n);
    if (!selectedResidues.has(key) || seen.has(key)) continue;
    seen.add(key);
    out.push({ auth_asym_id:r.c, auth_seq_id:r.n, generic_position:r.p, one_letter:r.a });
  }
  return out;
}

function labelTextFor(details) {
  const wanted = new Map((details || []).filter(r => r.generic_position).map(r =>
    [residueKey(r.auth_asym_id, r.auth_seq_id),
     (r.one_letter || oneLetter(r.residue_name || r.residue_identity)) + genericShort(r.generic_position)]));
  const text = {};
  if (!comp || !wanted.size) return text;
  try {
    comp.structure.eachAtom(a => {
      const label = wanted.get(residueKey(a.chainname, a.resno));
      if (label) text[a.index] = label;
    }, new window.NGL.Selection(".CA"));
  } catch (e) {}
  return text;
}

function addContactLabels() {
  const o = obs(), details = o && o.contact_receptor_details || [];
  if (!details.length) return;
  const s = details.map(r => residueKey(r.auth_asym_id, r.auth_seq_id)).join(" or ");
  addRep("motif_labels", "label", { sele:"(" + s + ") and .CA", labelType:"text",
    labelText:labelTextFor(details), color:"white", backgroundColor:"#111111",
    backgroundOpacity:0.68, showBackground:true, fixedSize:false, labelSize:2.2, radius:0.8, zOffset:2 });
}

/* NGL colours a contact's distance label to match the interaction it belongs to, which is right
   on the white background — a navy figure beside a navy hydrogen bond, an amber one beside an
   amber stacking contact. On the black background the navy is all but invisible, so there the
   labels are forced white and the lines keep carrying the interaction type. */
function contactLabelColour() { return viewerBackground === "black" ? "white" : undefined; }
function addInteractionLines(o=obs(), key="lines") {
  if (!o || !o.ligand_selection) return;
  const params = { sele:sel(o.contact_receptor_residues) + " or " +
    ligandSelection(o), maxHbondDist:3.6, maxHydrophobicDist:4.2,
    maxPiStackingDist:5.5, labelVisible:true, labelUnit:"angstrom", labelSize:0.72 };
  const colour = contactLabelColour();
  if (colour) params.labelColor = colour;
  addRep(key, "contact", params);
}

function addDisplayedInteractions() {
  ligandObservations().forEach((o, i) => addInteractionLines(o, i ? "lines_extra_" + i : "lines"));
}

export function contactResidues() {
  const o = obs();
  if (!o) return [];
  if ((o.contact_receptor_details || []).length) return o.contact_receptor_details.map(r => ({
    chain: r.auth_asym_id, seq: String(r.auth_seq_id),
    motif: r.generic_position ? oneLetter(r.residue_name) + genericShort(r.generic_position) : r.residue_name + r.auth_seq_id,
    residue: r.residue_name + r.auth_seq_id,
    distance: Number(r.min_distance_angstrom).toFixed(1) + " Å"
  }));
  const motifByResidue = new Map((meta.motif_residues || []).map(r =>
    [residueKey(r.auth_asym_id, r.auth_seq_id), r]));
  return (o.contact_receptor_residues || []).map(([chain, seq]) => {
    const m = motifByResidue.get(residueKey(chain, seq));
    return { chain, seq: String(seq), label: m
      ? m.residue_identity + seq + " · " + m.generic_position
      : chain + ":" + seq };
  });
}

export function motifGroups() {
  const groups = new Map();
  const activeChain = activeReceptorChain();
  for (const r of (meta && meta.motif_residues || []).filter(r => !activeChain || r.auth_asym_id === activeChain))
    for (const id of (r.motif_memberships || [])) {
    if (id === "ligand_transmission_connector") continue;
    if (!groups.has(id)) groups.set(id, []);
    groups.get(id).push(r);
  }
  const details = (obs() && obs().contact_receptor_details) || [];
  const pseudo = { tm5_polar: new Set(["5x42","5x43","5x46","5x461"]),
    aromatic_pocket: new Set(["6x48","6x51","6x52","7x42"]) };
  for (const [id, positions] of Object.entries(pseudo)) {
    const residues = (meta.shortcut_residues || details)
      .filter(r => positions.has(r.generic_short || genericShort(r.generic_position)));
    if (residues.length) groups.set(id, residues);
  }
  const ligand = new Set(["tm5_polar","aromatic_pocket"]);
  const structural = new Set([]);
  return Array.from(groups, ([id, residues]) => {
    const spec = MOTIF_SPECS[id];
    const byPosition = new Map(residues.map(r =>
      [r.generic_short || genericShort(r.generic_position), oneLetter(r.residue_identity || r.residue_name)]));
    let differences = 0;
    if (spec) for (const position of spec.positions) {
      const actual = byPosition.get(position), expected = spec.expected[position];
      if (expected && (!actual || !expected.includes(actual))) differences++;
    }
    const motifPositions = spec ? spec.positions : MOTIF_POSITIONS[id] || Array.from(byPosition.keys());
    const positions = motifPositions.join(", ");
    const pattern = id === "NPxxY_region"
      ? [{ aa:byPosition.get("7x49") || "?", position:"7x49" },
         { aa:byPosition.get("7x50") || "?", position:"7x50" }, { wildcard:"xx" },
         { aa:byPosition.get("7x53") || "?", position:"7x53" }]
      : motifPositions.map(position => ({ aa:byPosition.get(position) || "?", position }));
    const differenceText = differences ? t(differences === 1
      ? "v_motif_difference_one" : "v_motif_difference_many", { count:differences }) : "";
    return { id, label:motifLabel(id) + (differences ? " *" : ""), differences,
      pattern, differenceText,
      tooltip:t("v_motif_positions", { positions }) + (differenceText ? " — " + differenceText : ""),
      group:structural.has(id) ? "structural" : ligand.has(id) ? "ligand" : "activation" };
  });
}

function residuesForMotif(id) {
  if (id === "tm5_polar" || id === "aromatic_pocket") {
    const positions = id === "tm5_polar" ? new Set(["5x42","5x43","5x46","5x461"])
      : new Set(["6x48","6x51","6x52","7x42"]);
    const source = (meta && meta.shortcut_residues && meta.shortcut_residues.length)
      ? meta.shortcut_residues : ((obs() && obs().contact_receptor_details) || []);
    return source.filter(r => positions.has(r.generic_short || genericShort(r.generic_position)))
      .map(r => ({ auth_asym_id:r.auth_asym_id, auth_seq_id:r.auth_seq_id }));
  }
  const activeChain = activeReceptorChain();
  const positions = MOTIF_SPECS[id] && new Set(MOTIF_SPECS[id].positions);
  return (meta.motif_residues || []).filter(r => (!activeChain || r.auth_asym_id === activeChain) &&
    (r.motif_memberships || []).includes(id) &&
    (!positions || positions.has(r.generic_short || genericShort(r.generic_position))));
}

function selectionInView(selection, margin) {
  const stage = LC.getStage();
  if (!comp || !stage || !selection) return true;
  const viewer = stage.viewer, trans = viewer.translationGroup.position,
    rot = viewer.rotationGroup.matrix, cam = viewer.camera;
  let seen = 0, inside = true;
  try {
    comp.structure.eachAtom(a => {
      seen++;
      if (!inside) return;
      const p = new window.NGL.Vector3(a.x, a.y, a.z).add(trans).applyMatrix4(rot).project(cam);
      if (Math.abs(p.x) > margin || Math.abs(p.y) > margin || p.z < -1 || p.z > 1) inside = false;
    }, new window.NGL.Selection(selection));
  } catch (e) { return true; }
  return seen > 0 && inside;
}

/* Every label in the scene is sized in Angstroms and grows as the reader zooms in, the picked ones
   included. A fixed pixel size was tried for them, to keep a pick named at the whole-receptor
   framing where an Angstrom-sized label is a few pixels tall. It bought that at the cost of the
   case readers actually use: zooming onto a residue then left its name at the same few pixels
   while everything around it grew. The framing was the real fault there and is fixed at its own
   source — the fusion partner no longer drags the camera back — so these behave exactly like the
   contact labels beside them, which is also the behaviour a reader has already learned. */
function redrawSelections() {
  dropRep("picked_residues"); dropRep("picked_labels"); dropRep("picked_motifs"); dropRep("picked_motif_labels");
  dropRep("query_residues"); dropRep("query_labels");
  /* A residue can be reached three ways — clicked in a list, carried in from a query, or part of a
     named motif — and the same residue is often reached twice: pick 7x50 in the whole-receptor
     columns and NPxxY among the motifs, and it is in both. Each source used to draw its own stick
     and its own label at the same alpha carbon, and because the two labels ask for slightly
     different offsets they landed a few pixels apart, so the name read as two overlapping copies of
     itself. Each residue is therefore claimed once, in order of how specific the act was: a residue
     clicked on its own, then a motif chosen by name, then whatever the query brought in. */
  const claimed = new Set();
  const take = keys => { const out = keys.filter(k => !claimed.has(k)); for (const k of out) claimed.add(k); return out; };

  const picked = take(Array.from(selectedResidues));
  if (picked.length) {
    const s = picked.join(" or ");
    const o = obs(), details = selectedDetails();
    const pickedSele = heavyAtomsWithContactHydrogens(s, ligandSelection(o));
    addRep("picked_residues", "ball+stick", { sele:pickedSele, colorScheme:"element",
      colorValue:0xef72aa, scale:1.15 });
    addRep("picked_labels", "label", { sele: "(" + s + ") and .CA", labelType: "text",
      labelText:labelTextFor(details), color: "white", backgroundColor: "#12151a",
      backgroundOpacity:0.75, showBackground:true, fixedSize:false, labelSize:2.2, radius:0.85, zOffset:2 });
  }

  if (selectedMotifs.size) {
    const residues = Array.from(selectedMotifs).flatMap(residuesForMotif);
    const byKey = new Map(residues.map(r => [residueKey(r.auth_asym_id, r.auth_seq_id), r]));
    const keys = take(Array.from(byKey.keys()));
    if (keys.length) {
      const s = keys.join(" or ");
      addRep("picked_motifs", "ball+stick", { sele:withoutHydrogen(s), colorScheme:"uniform",
        colorValue:0x32b56b, scale:1.18, aspectRatio:2.1 });
      addRep("picked_motif_labels", "label", { sele: "(" + s + ") and .CA", labelType: "text",
        labelText:labelTextFor(keys.map(k => byKey.get(k))), color:"white", backgroundColor:"#17683b",
        backgroundOpacity:0.78, showBackground:true, fixedSize:false, labelSize:2.2, radius:0.8, zOffset:2 });
    }
  }

  const query = take(Array.from(queryResidues));
  if (query.length) {
    const sq = query.join(" or ");
    const rows = residueTable.filter(r => query.indexOf(residueKey(r.c, r.n)) >= 0)
      .map(r => ({ auth_asym_id:r.c, auth_seq_id:r.n, generic_position:r.p, one_letter:r.a }));
    addRep("query_residues", "ball+stick", { sele:withoutHydrogen(sq), colorScheme:"uniform",
      colorValue:0x32b56b, scale:1.18, aspectRatio:2.1 });
    addRep("query_labels", "label", { sele:"(" + sq + ") and .CA", labelType:"text",
      labelText:labelTextFor(rows), color:"white", backgroundColor:"#17683b",
      backgroundOpacity:0.78, showBackground:true, fixedSize:false, labelSize:2.2,
      radius:0.8, zOffset:2 });
  }
}

export function toggleResidue(chain, seq) {
  const key = residueKey(chain, seq);
  const removing = selectedResidues.has(key);
  removing ? selectedResidues.delete(key) : selectedResidues.add(key);
  redrawSelections();
  if (!removing) {
    const o = obs(), ligand = ligandSelection(o);
    const both = "(" + Array.from(selectedResidues).join(" or ") + ") or (" + ligand + ")";
    if (!selectionInView(both, 0.92)) frame(both);
  }
  return selectedResidues.has(key);
}

export function isResidueSelected(chain, seq) {
  return selectedResidues.has(residueKey(chain, seq));
}

export function toggleMotif(id) {
  selectedMotifs.has(id) ? selectedMotifs.delete(id) : selectedMotifs.add(id);
  redrawSelections();
  const residues = residuesForMotif(id);
  if (selectedMotifs.has(id) && residues.length) {
    const o = obs(), motif = residues.map(r => residueKey(r.auth_asym_id, r.auth_seq_id)).join(" or ");
    const ligand = ligandSelection(o);
    const both = "(" + motif + ") or (" + ligand + ")";
    if (!selectionInView(both, 0.92)) frame(both);
  }
  return selectedMotifs.has(id);
}

export function clearSelections() {
  selectedResidues.clear(); selectedMotifs.clear(); redrawSelections();
}

export async function snapshot() {
  const stage = LC.getStage();
  if (!stage || !meta) return;
  const blob = await stage.makeImage({ factor:3, antialias:true, trim:false, transparent:true });
  const url = URL.createObjectURL(blob), a = document.createElement("a");
  a.href = url; a.download = meta.pdb_id + "_binding_site.png"; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function focusPocket() {
  const o = obs();
  if (o && o.ligand_selection) frame(ligandSelection(o) + " or " + sel(o.contact_receptor_residues));
  else if (comp) comp.autoView(400);
}

export const toggles = {
  cartoon(on) { const rc = receptorSelection();
    on ? addRep("cartoon", "cartoon", { sele:rc, color:"#646a73", opacity:0.68 }) : dropRep("cartoon"); },
  allLigands(on) {
    if (!on) { dropRep("all_lig"); return; }
    const all = (meta.observations || []).filter(o => o.ligand_selection)
      .map(o => sel(o.ligand_selection.residues)).filter(s => s !== "none");
    if (all.length) addRep("all_lig", "ball+stick", { sele: all.join(" or "), color: "element" });
  },
  contacts(on) {
    dropByPrefix("contacts"); dropByPrefix("iface");
    if (!on) return;
    ligandObservations().forEach((o, i) => addRep((POLYMER[o.binding_site_class] ? "iface_" : "contacts_") + i,
      "licorice", { sele:withoutHydrogen(sel(o.contact_receptor_residues)),
        colorScheme:"element", colorValue:0x8ab8e8 }));
  },
  lines(on) { if (!on) { dropByPrefix("lines"); return; } addDisplayedInteractions(); },
  ligand(on) {
    if (!on) { dropByPrefix("ligand"); dropByPrefix("lines");
      dropRep("covalent_atoms"); dropRep("covalent_bond"); return; }
    addDisplayedLigands(); addDisplayedInteractions(); addCovalentHighlight(obs()); },
  ligandMode(mode) {
    ligandMode = mode === "licorice" ? "licorice" : "cartoon";
    dropByPrefix("ligand");
    addDisplayedLigands();
  },
  surface(on) { this.surfaceReceptor(on); this.surfaceLigand(on); },
  surfaceReceptor(on) { const o = obs(); if (!on || !o) { dropRep("surface_receptor"); return; }
    addRep("surface_receptor", "surface", { sele: "(" + sel(o.contact_receptor_residues) + ") and protein",
      opacity: 0.28, colorValue: "lightgrey" }); },
  surfaceLigand(on) { const o = obs(); if (!on || !o || !o.ligand_selection) { dropRep("surface_ligand"); return; }
    // The observation selector defines the active ligand.  Showing every ligand surface in a
    // multi-ligand structure obscures which orthosteric/allosteric partner is being inspected.
    addRep("surface_ligand", "surface", { sele:withoutHydrogen(ligandSelection(o)),
      opacity:0.34, colorValue:"#f3df78" }); },
  motifs(on) { if (!on) { dropRep("motifs"); return; }
    const activeChain = activeReceptorChain();
    const m = (meta.motif_residues || []).filter(r => !activeChain || r.auth_asym_id === activeChain)
      .map(r => r.auth_seq_id + ":" + r.auth_asym_id);
    if (m.length) addRep("motifs", "licorice", { sele: m.join(" or "), color: "green" }); },
  motifLabels(on) { if (!on) { dropRep("motif_labels"); return; } addContactLabels(); },
  covalent(on) {
    if (!on) { dropRep("covalent_atoms"); dropRep("covalent_bond"); return; }
    addCovalentHighlight(obs());
  },
  ions(on) { if (!on) { dropRep("ions"); return; }
    const na = (meta.observed_sodium || []).map(r => r.auth_seq_id + ":" + r.auth_asym_id);
    if (na.length) addRep("ions", "spacefill", { sele: na.join(" or "), color: "purple", scale: 0.4 }); },
  aux(on) { if (!on || !meta.auxiliary_chains_included) { dropRep("aux"); return; }
    const a = (meta.auxiliary_chains || []).map(c => ":" + c).join(" or ");
    if (a) addRep("aux", "cartoon", { sele: a, color: "lightgrey", opacity: 0.5 }); },
  spin(on) { const s = LC.getStage(); if (s) { try { s.setSpin(!!on); } catch (e) {} } }
};

export function resetView() { if (comp) applyDefaults(); }
export function statusMessage() {
  if (!meta) return "";
  const o = obs();
  if (meta.apo_status === "confirmed_apo") return t("apo_confirmed");
  if (o && o.coordinate_status === "annotated_not_observed") return t("ano_msg");
  if (o && o.binding_site_class === "unresolved") return t("unresolved_site");
  // Some observations are recorded from the annotation but carry no atom selection, so nothing
  // can be drawn or highlighted for them. Silence there reads as a broken viewer.
  if (o && ligandSelection(o) === "none") return t("no_ligand_selection");
  const un = (meta.receptor_instances || []).some(r => r.generic_mapping === "unresolved");
  if (un) return t("generic_unresolved");
  return "";
}
export { LC as lifecycle };
