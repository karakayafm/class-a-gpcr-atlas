// Site-aware 3D viewer. Small-molecule pockets and polymer interfaces use different
// terminology, different default representations and different camera framing.
import { t, siteClassLabel } from "../core/i18n.js";
import { el, clear } from "../components/dom.js";
import { loadBundleMeta, bundleCifUrl, loadReceptorResidues, errorMessage } from "../data/loader.js";
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
/* Whether the contact-label layer is on. Tracked rather than inferred from the representation,
   because a selection can legitimately empty that layer — every contact residue picked — and an
   absent representation would then be read as "the reader turned them off". */
let contactLabelsOn = true;
/* Set while a second structure is superposed on this one, and null otherwise. The ordinary scene
   spends colour on meaning — element colours on the ligand, a tint on the contacting side chains,
   another on the motifs — and all of that is worth more than telling two structures apart, right up
   until there are two structures. Then it is worth less than that, and this takes over. */
let uniformColour = null;
/* Measurement. The reader picks atoms in the scene and the viewer reports what can be computed
   from however many they have picked: two give a distance, three an angle at the middle one, four
   a dihedral. Held here rather than in the panel because the picking happens in the scene and the
   atom indices only mean anything against the loaded structure. */
let measureMode = false;
/* Whether the contacting side chains are on screen, so switching measurement mode can redraw them
   in the other form without turning on a layer the reader had switched off. */
let contactsOn = true;
/* Show only what the reader picked. The pocket layer is a good default and a poor place to work:
   twenty side chains, their labels and the interaction lines between them are most of what is on
   screen, and a reader who has chosen three residues is looking past all of it. */
let focusSelection = false;
let measureChanged = null;
const measureAtoms = [];
/* Measurements the reader has kept. The picking set above is the one being built; once it says
   something worth keeping it moves here and the picking starts again empty, so a second question
   — the distance across the pocket, say, beside the one just measured at the ligand — does not
   have to inherit the atoms of the first. */
const measureKept = [];
const MEASURE_MAX = 4;
const MEASURE_COLOUR = 0xff8a3d;
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
  measureAtoms.length = 0; measureKept.length = 0; measureMode = false;
  focusSelection = false; uniformColour = null; foreignTables.clear();
  interactionLayers.ligand = true; interactionLayers.inter = false;
  interactionLayers.intra = false; ligandShown = true;
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
  try { stage.signals.clicked.add(onScenePick); } catch (e) {}
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
  residueTable = []; queryResidues.clear(); queryPositions = []; uniformColour = null;
  foreignTables.clear(); measureShapeComp = null;
  measureAtoms.length = 0; measureKept.length = 0; measureMode = false; measureChanged = null;
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

/* --------------------------------------------------------------- measurement */
/* Plain geometry on the coordinates as deposited, in the units the field reads them in: angstroms
   for a distance, degrees for an angle and for a torsion. Nothing here is rounded before display. */
function measureDistance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
}
function subtract(a, b) { return { x:a.x - b.x, y:a.y - b.y, z:a.z - b.z }; }
function dot(a, b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
function cross(a, b) {
  return { x:a.y * b.z - a.z * b.y, y:a.z * b.x - a.x * b.z, z:a.x * b.y - a.y * b.x };
}
function norm(a) { return Math.hypot(a.x, a.y, a.z); }
function measureAngle(a, b, c) {
  const u = subtract(a, b), v = subtract(c, b);
  const denom = norm(u) * norm(v);
  if (!denom) return null;
  return Math.acos(Math.min(1, Math.max(-1, dot(u, v) / denom))) * 180 / Math.PI;
}
/* Signed, by the IUPAC convention: the angle between the plane through the first three atoms and
   the plane through the last three, positive clockwise looking along b to c. */
function measureDihedral(a, b, c, d) {
  const b1 = subtract(b, a), b2 = subtract(c, b), b3 = subtract(d, c);
  const n1 = cross(b1, b2), n2 = cross(b2, b3), m = cross(n1, b2);
  const l = norm(b2);
  if (!l || !norm(n1) || !norm(n2)) return null;
  return Math.atan2(dot(m, n2) / l, dot(n1, n2)) * 180 / Math.PI;
}

/* Numbering tables for the superposed structures, keyed by the name their NGL structure carries.
   Registered by the align module rather than imported from it, because this module knows nothing
   about superposition and importing it back would close a cycle. Without these, an atom picked in
   an overlay was named from the base structure's table — which is a different receptor with
   different residue numbers — so it fell through to the deposited name and the readout said
   PHE275 where every other part of the atlas says 6x52. */
const foreignTables = new Map();
export function registerStructureTable(name, rows) {
  foreignTables.set(String(name || "").toUpperCase(), Array.isArray(rows) ? rows : []);
}
export function forgetStructureTables() { foreignTables.clear(); }

function structureNameOf(atom) {
  return String((atom && atom.structure && atom.structure.name) || (meta && meta.pdb_id) || "")
    .toUpperCase();
}
/* The base structure's own table is the lazy one loaded for the whole-receptor list; a foreign
   structure falls back to nothing rather than to the base table, because naming an overlay's
   residue from the base receptor's numbering is worse than not naming it. */
function tableFor(name) {
  if (meta && name === String(meta.pdb_id).toUpperCase()) return residueTable;
  return foreignTables.get(name) || [];
}

/* What to call the atom in the readout: the generic position where the structure has one, because
   that is the name the rest of the atlas uses, and the deposited residue otherwise. */
function measureAtomLabel(atom) {
  const struct = structureNameOf(atom);
  const chain = atom.chainname, seq = String(atom.resno);
  const row = tableFor(struct).find(r => r.c === chain && r.n === seq);
  const residue = row ? row.a + row.p : (atom.resname || "") + seq;
  return { residue, atomName: atom.atomname || "", chain, seq, struct };
}

/* Licorice draws bonds and no atom centres, so in measurement mode there is often nothing to aim
   at: at some angles an atom is simply not clickable and the reader has to rotate until it is.
   Ball-and-stick puts a sphere on every atom. Modest spheres — a target to hit, not a change of
   representation the reader has to look past. */
function contactRepType() { return measureMode ? "ball+stick" : "licorice"; }
function contactRepParams(residues) {
  const base = { sele:withoutHydrogen(sel(residues)), colorScheme:"element", colorValue:0x8ab8e8 };
  return measureMode ? Object.assign({ aspectRatio:1.9, scale:0.30 }, base) : base;
}
/* Every contacting side chain the current observations name, in whichever form the mode calls for.
   One place, so the two ways it used to be drawn cannot drift apart. */
function addContactSideChains() {
  dropByPrefix("contacts"); dropByPrefix("iface");
  if (focusSelection) return;
  ligandObservations().forEach((o, i) =>
    addRep((POLYMER[o.binding_site_class] ? "iface_" : "contacts_") + i,
      contactRepType(), contactRepParams(o.contact_receptor_residues)));
}

/* Measurement geometry is drawn in world coordinates on a shape of its own, not as representations
   of the structure the atoms came from.
 *
 * NGL's distance, angle and dihedral representations take atom *indices*, and an index only means
 * anything against one structure. That was fine while there was one structure. With a second
 * superposed on it, a measurement that spans the two has no single structure to be a representation
 * of, and asking the base component to draw an overlay's index silently drew a different atom —
 * the number in the panel was right and the marker on screen was somewhere else.
 *
 * A shape takes positions, and the overlay's coordinates have already been moved into this frame by
 * the superposition, so both cases are the same operation. What is given up is NGL's dashed arc on
 * angles; what is bought is that the picture agrees with the number. */
const MEASURE_RGB = [1, 0.541, 0.239];   // MEASURE_COLOUR as a shape colour
let measureShapeComp = null;

function measureDrop() {
  dropByPrefix("measure");
  const stage = LC.getStage();
  if (measureShapeComp && stage) { try { stage.removeComponent(measureShapeComp); } catch (e) {} }
  measureShapeComp = null;
}

function measureValueText(atoms) {
  const r = resultFor(atoms);
  if (!r || r.value == null || !isFinite(r.value)) return null;
  return r.unit === "angstrom" ? r.value.toFixed(2) + " Å" : r.value.toFixed(1) + "°";
}

function measureDraw() {
  measureDrop();
  const NGL = window.NGL, stage = LC.getStage();
  if (!NGL || !stage) return;
  const sets = measureKept.map(atoms => ({ atoms, marked:false }));
  if (measureAtoms.length) sets.push({ atoms:measureAtoms, marked:true });
  if (!sets.length) return;
  const shape = new NGL.Shape("measurement");
  let drew = false;
  for (const { atoms, marked } of sets) {
    const p = atoms.map(a => [a.x, a.y, a.z]);
    /* Only the set being built gets spheres: those are the atoms a click will take back, and a kept
       set is a result rather than a selection. */
    if (marked) for (const q of p) { shape.addSphere(q, MEASURE_RGB, 0.34); drew = true; }
    for (let i = 0; i + 1 < p.length; i++) {
      shape.addCylinder(p[i], p[i+1], MEASURE_RGB, 0.09);
      drew = true;
    }
    const text = measureValueText(atoms);
    if (text) {
      // At the vertex for an angle, at the midpoint for a distance: in both cases the point the
      // reader is looking at while they read the number.
      const at = p.length === 2
        ? [(p[0][0]+p[1][0])/2, (p[0][1]+p[1][1])/2, (p[0][2]+p[1][2])/2]
        : p[1];
      shape.addText(at, [1, 1, 1], 2.2, text);
      drew = true;
    }
  }
  if (!drew) return;
  try {
    measureShapeComp = stage.addComponentFromObject(shape);
    measureShapeComp.addRepresentation("buffer");
  } catch (e) { measureShapeComp = null; }
}

/* The one answer the current picks support. Reported as a kind and a number so the panel decides
   how to word it and nothing here has to know the interface language. */
function resultFor(p) {
  if (p.length === 2) return { kind:"distance", value:measureDistance(p[0], p[1]), unit:"angstrom" };
  if (p.length === 3) return { kind:"angle", value:measureAngle(p[0], p[1], p[2]), unit:"degree" };
  if (p.length === 4)
    return { kind:"dihedral", value:measureDihedral(p[0], p[1], p[2], p[3]), unit:"degree" };
  return null;
}
export function measureResult() { return resultFor(measureAtoms); }
export function measureKeptList() {
  return measureKept.map((set, i) => Object.assign({ id:i, atoms:set.map(a => Object.assign({}, a)) },
    resultFor(set)));
}
/* Banks the set being built, if it says anything, and starts an empty one. */
export function measureKeep() {
  if (!resultFor(measureAtoms)) return false;
  measureKept.push(measureAtoms.slice());
  measureAtoms.length = 0;
  measureDraw();
  if (measureChanged) measureChanged();
  return true;
}
export function measureRemoveKept(i) {
  if (i < 0 || i >= measureKept.length) return;
  measureKept.splice(i, 1);
  measureDraw();
  if (measureChanged) measureChanged();
}
export function measureList() { return measureAtoms.map(a => Object.assign({}, a)); }
export function isMeasuring() { return measureMode; }
export function measureFull() { return measureAtoms.length >= MEASURE_MAX; }

export function measureClear() {
  measureAtoms.length = 0;
  measureKept.length = 0;
  measureDraw();
  if (measureChanged) measureChanged();
}
export function measureUndo() {
  measureAtoms.pop();
  measureDraw();
  if (measureChanged) measureChanged();
}
export function isFocusSelection() { return focusSelection; }
export function hasSelection() {
  return selectedResidues.size > 0 || selectedMotifs.size > 0 || queryResidues.size > 0;
}
export function setFocusSelection(on) {
  focusSelection = !!on && hasSelection();
  if (contactsOn) addContactSideChains();
  addContactLabels(claimedResidues());
  addDisplayedInteractions();
  if (focusSelection) frameSelection();
  return focusSelection;
}
/* The camera follows, because "only the selection" and "still framed on the pocket you just
   emptied" is not what the words promise. */
function frameSelection() {
  const keys = Array.from(claimedResidues());
  if (keys.length) frame(keys.join(" or "));
}
/* A focus with nothing to focus on is a blank pocket and a reader wondering what broke, so
   emptying the selection releases it. */
function releaseFocusIfEmpty() {
  if (focusSelection && !hasSelection()) setFocusSelection(false);
}

export function setMeasureMode(on, onChange) {
  const was = measureMode;
  measureMode = !!on;
  measureChanged = onChange || measureChanged;
  if (was !== measureMode && contactsOn) addContactSideChains();
  if (!measureMode) { measureAtoms.length = 0; measureKept.length = 0; measureDraw(); }
  if (measureChanged) measureChanged();
  return measureMode;
}

/* Attached once per stage. The guard is here rather than on the binding so that turning the mode
   off and on again does not accumulate handlers on a stage that outlives both. */
function onScenePick(pick) {
  if (!measureMode || !pick || !pick.atom) return;
  const atom = pick.atom;
  /* Clicking a picked atom takes it back, the way clicking a selected residue does in the lists.
     Without this a second click on the same atom added a duplicate, and a duplicate can never
     produce an answer — two coincident points have no angle — so the reader was left with a
     measurement that silently could not resolve. */
  /* Keyed by structure as well as index: an index is only unique within one structure, so with an
     overlay on screen clicking an atom in one could take back an atom in the other. */
  const struct = structureNameOf(atom);
  const already = measureAtoms.findIndex(a => a.index === atom.index && a.struct === struct);
  if (already >= 0) {
    measureAtoms.splice(already, 1);
    measureDraw();
    if (measureChanged) measureChanged();
    return;
  }
  if (measureAtoms.length >= MEASURE_MAX) return;
  const info = measureAtomLabel(atom);
  measureAtoms.push({ index:atom.index, struct, x:atom.x, y:atom.y, z:atom.z,
    residue:info.residue, atomName:info.atomName, chain:info.chain, seq:info.seq });
  measureDraw();
  if (measureChanged) measureChanged();
}

/* ------------------------------------------------- the receptor beyond the pocket */
export function setResidueTable(rows) { residueTable = Array.isArray(rows) ? rows : []; }
export function hasResidueTable() { return residueTable.length > 0; }

/* ------------------------------------------------- what superposition needs from here
   The align module fits a second structure onto this one over the generic positions they share, so
   it needs the loaded component, which chain of it is the receptor, and the numbering table. The
   table is lazy — a reader who never leaves the pocket never fetches it — so this loads it on
   demand rather than reporting an empty receptor for a structure that has one. */
export function baseComponent() { return comp; }
/* Which surfaces the base structure is actually showing. The panel used to keep this in a local
   that was rebuilt — and reset to false — every time the reader switched structures, so a surface
   left on came back with its button reading off. Reading it from the representations that exist
   means the button cannot disagree with the scene. */
export function surfaceState() {
  return { surfaceReceptor: !!reps.surface_receptor, surfaceLigand: !!reps.surface_ligand };
}
/* What the diagram module needs from the structure this module loaded: the component to read
   coordinates from, its metadata, and which observation is on screen — a structure with two ligands
   should diagram the one the reader is looking at, not the first one in the file. */
export function diagramSpec() {
  return comp && meta ? { comp, meta, observation: current,
                          name: meta.receptor_name || meta.receptor_entry_name || "" } : null;
}
/* Deliberately not applyDefaults: that clears the selection, resets the ligand display and reframes
   the camera, and none of those should happen because a second structure arrived. This rebuilds the
   structural layers only — addRep replaces by key — and leaves everything the reader had set. */
export function setUniformColour(hex) {
  const next = hex || null;
  if (next === uniformColour) return;
  uniformColour = next;
  if (!comp || !meta) return;
  addRep("cartoon", "cartoon", { sele: receptorSelection(), color: "#646a73", opacity: CARTOON_OPACITY });
  const o = obs();
  if (o && o.ligand_selection) {
    addDisplayedLigands();
    if (contactsOn) addContactSideChains();
    addDisplayedInteractions();
    addCovalentHighlight(o);
  }
  redrawSelections();
}
export function uniformColourValue() { return uniformColour; }
export function basePdb() { return meta ? meta.pdb_id : ""; }
export function receptorChain() { return activeReceptorChain(); }
export async function ensureBaseResidueRows() {
  if (residueTable.length || !meta) return residueTable.slice();
  try {
    const payload = await loadReceptorResidues(meta.pdb_id);
    setResidueTable((payload && payload.residues) || []);
  } catch (e) { /* a structure without a numbering table simply cannot be aligned on */ }
  return residueTable.slice();
}

/* Grouped for the panel: one list per helix, in position order, for the chain on screen. H8 and
   the resolved loop residues are kept in a group of their own rather than dropped — they are as
   real as the helical ones, they just are not one of the seven columns the panel draws. */
/* The seven the panel draws, so a caller can tell which of them a structure has nothing for. */
export function helixOrder() { return HELICES.slice(); }

/* The same grouping for a structure that is not the one this module loaded — a superposed overlay.
   Kept here rather than duplicated in the align module so the two lists are built by one piece of
   code and cannot drift; what differs between them is only which rows and which contacts go in. */
export function segmentRows(rows, chain, contactKeys) {
  const contacts = contactKeys instanceof Set ? contactKeys : new Set(contactKeys || []);
  const groups = new Map();
  for (const r of (rows || [])) {
    if (chain && r.c !== chain) continue;
    const key = HELICES.indexOf(r.s) >= 0 ? r.s : "other";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(Object.assign({ contact:contacts.has(residueKey(r.c, r.n)), query:false }, r));
  }
  const out = HELICES.filter(h => groups.has(h)).map(h => ({ segment:h, helix:true,
    residues:groups.get(h) }));
  if (groups.has("other")) out.push({ segment:"other", helix:false, residues:groups.get("other") });
  return out;
}

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
/* Layers that keep their own colour while the structure is painted uniform. Two kinds: the ones
   that answer a different question from "which structure is this" — what the reader picked, what
   they measured, what they arrived asking about — and the text, which has to stay legible against
   whatever colour the structure took. Losing those to the uniform coat would make superposition a
   mode in which selection stops giving feedback. */
function keepsOwnColour(key, type) {
  return type === "label" || key.startsWith("measure") ||
    key.startsWith("picked_") || key.startsWith("query_") || key.endsWith("_labels");
}

/* The contact labels are the exception to the exception. They are excluded from the uniform coat
   above because a label painted the structure's colour on a dark background is a label, whereas a
   label whose *background* is painted that colour stops being readable. But leaving them white made
   the identity vanish exactly where it matters most: with a second structure superposed, two labels
   land on the same position — V3x33 from one receptor and I3x33 from the other — and two white tags
   do not say which is which. So the glyphs take the colour and the background stays black. */
function labelColour(fallback) { return uniformColour || fallback; }

/* Representations that draw atoms, where "uniform" is applied as element colouring with the
   structure's colour standing in for carbon. A cartoon has no atoms to distinguish and takes the
   colour flat. */
const ATOMISTIC = { licorice:1, "ball+stick":1, spacefill:1, hyperball:1, line:1, point:1 };

/* The uniform coat, as representation parameters. Carbon carries the structure's identity and the
   heteroatoms keep theirs: nitrogen blue, oxygen red, sulfur yellow. Which is the compromise the
   scene actually needs — the colour still says which structure a ligand belongs to, because carbon
   is most of every ligand, while the atoms that decide what a contact *is* stay readable. */
function uniformParams(type) {
  return ATOMISTIC[type]
    ? { colorScheme: "element", colorValue: uniformColour }
    : { color: uniformColour, colorScheme: undefined };
}

function addRep(key, type, params) {
  if (!comp) return null;
  if (reps[key]) { try { comp.removeRepresentation(reps[key]); } catch (e) {} }
  let p = params;
  /* While something is superposed on this structure, every structural layer of it is one colour,
     so the eye separates the two structures before it reads anything else. `color` overrides
     whatever the layer would have chosen — element colouring on the ligand, the contact tint on the
     side chains — so both are removed rather than left to fight it. */
  if (uniformColour && !keepsOwnColour(key, type)) {
    p = Object.assign({}, params);
    /* Both are dropped before the coat goes on. `color` is what the layer chose for itself — the
       white carbon overlay on the active ligand, the grey cartoon — and NGL lets it override
       colorScheme, so leaving it in place kept that ligand white on a structure painted green. */
    delete p.color; delete p.colorScheme; delete p.colorValue;
    Object.assign(p, uniformParams(type));
    if (p.colorScheme === undefined) delete p.colorScheme;
  }
  try { reps[key] = comp.addRepresentation(type, p); } catch (e) { return null; }
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
  addRep("cartoon", "cartoon", { sele: rc, color: "#646a73", opacity: CARTOON_OPACITY });
  const o = obs();
  if (o && o.ligand_selection) {
    const all = ligandObservations();
    addDisplayedLigands();
    addContactSideChains();
    addDisplayedInteractions();
    addCovalentHighlight(o);
    contactsOn = true;
    contactLabelsOn = true;
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
export function genericShort(value) {
  const s = String(value || "");
  const m = s.match(/^(\d+)(?:\.\d+)?x(\d+)$/);
  return m ? m[1] + "x" + m[2] : s;
}
export function oneLetter(name) { return ({ ALA:"A",ARG:"R",ASN:"N",ASP:"D",CYS:"C",GLN:"Q",GLU:"E",
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

/* The contact labels are the one layer that is on without anyone asking for it, so it is the one
   that has to give way. A residue that is both a ligand contact and a current selection was labelled
   twice — once here and once by the selection — and since the two ask for slightly different label
   offsets the name landed a few pixels from itself and read as a smeared double. Same text either
   way, so dropping this one where a selection already names the residue loses nothing. */
function addContactLabels(exclude) {
  dropRep("motif_labels");
  if (focusSelection) return;
  const o = obs();
  const details = (o && o.contact_receptor_details || []).filter(r =>
    !exclude || !exclude.has(residueKey(r.auth_asym_id, r.auth_seq_id)));
  if (!details.length) return;
  const s = details.map(r => residueKey(r.auth_asym_id, r.auth_seq_id)).join(" or ");
  addRep("motif_labels", "label", { sele:"(" + s + ") and .CA", labelType:"text",
    labelText:labelTextFor(details), color:labelColour("white"), backgroundColor:"#111111",
    backgroundOpacity:0.68, showBackground:true, fixedSize:false, labelSize:2.2, radius:0.8, zOffset:2 });
}

/* NGL colours a contact's distance label to match the interaction it belongs to, which is right
   on the white background — a navy figure beside a navy hydrogen bond, an amber one beside an
   amber stacking contact. On the black background the navy is all but invisible, so there the
   labels are forced white and the lines keep carrying the interaction type. */
function contactLabelColour() { return viewerBackground === "black" ? "white" : undefined; }
/* Hydrogen bonds are drawn light green rather than NGL's blue.
 *
 * The colour cannot be asked for: NGL's contact representation has no colour parameter and assigns
 * one per interaction type from a hardcoded table. The vendored copy of the library could be
 * patched — the constant appears exactly once — but THIRD_PARTY_NOTICES.md states that file is
 * byte-identical to the published distribution and carries its SHA-256, and a colour is not worth
 * making that untrue.
 *
 * So the hydrogen bonds are drawn as a representation of their own, with every other interaction
 * type switched off, and its buffers are repainted after it is built. Everything else keeps NGL's
 * own colouring in a second representation. */
/* Interaction types the atlas recolours, and the rest.
 *
 * NGL assigns a colour per interaction type from a table compiled into the library — there is no
 * parameter for it, and the vendored copy is declared byte-identical to the published distribution
 * with its SHA-256, which a colour is not worth making untrue. So each recoloured type is drawn as
 * a representation of its own with every other type switched off, and its buffers are repainted
 * once built. Everything left over goes in a final representation keeping NGL's own colours. */
const ALL_CONTACT_TYPES = ["hydrogenBond", "waterHydrogenBond", "backboneHydrogenBond",
  "weakHydrogenBond", "hydrophobic", "halogenBond", "ionicInteraction", "metalCoordination",
  "cationPi", "piStacking"];
const RECOLOURED_CONTACTS = [
  { key:"hbond", types:["hydrogenBond", "waterHydrogenBond", "backboneHydrogenBond"],
    rgb:[0x7f / 255, 0xe0 / 255, 0xa0 / 255], label:"#7fe0a0" },
  { key:"phobic", types:["hydrophobic"],
    rgb:[0xd8 / 255, 0xa5 / 255, 0x31 / 255], label:"#d8a531" }
];
/* Which types NGL computes unless told otherwise. Backbone and weak hydrogen bonds and water-
   mediated ones are off in NGL and stay off here except where a caller asks — the helical layers
   do, because backbone hydrogen bonds are most of what holds a helix together. */
const DEFAULT_CONTACT_TYPES = { hydrogenBond:true, waterHydrogenBond:false,
  backboneHydrogenBond:false, weakHydrogenBond:false, hydrophobic:true, halogenBond:true,
  ionicInteraction:true, metalCoordination:true, cationPi:true, piStacking:true };

/* One contact layer, split into one representation per recoloured type plus one for the rest.
   `wanted` says which types this layer asks for at all; a type switched off there is off in every
   representation, so a caller cannot enable something through the back door of a colour group. */
function buildSplitContacts(add, params, wanted) {
  const enabled = Object.assign({}, DEFAULT_CONTACT_TYPES, wanted || {});
  const off = {};
  for (const t of ALL_CONTACT_TYPES) off[t] = false;
  const claimed = new Set();
  for (const group of RECOLOURED_CONTACTS) {
    const mine = group.types.filter(t => enabled[t]);
    for (const t of group.types) claimed.add(t);
    if (!mine.length) continue;
    const types = Object.assign({}, off);
    for (const t of mine) types[t] = true;
    repaintBuffers(add("_" + group.key,
      Object.assign({}, params, types, { labelColor:group.label })), group.rgb);
  }
  const rest = Object.assign({}, off);
  let any = false;
  for (const t of ALL_CONTACT_TYPES)
    if (enabled[t] && !claimed.has(t)) { rest[t] = true; any = true; }
  if (any) add("", Object.assign({}, params, rest));
}

function addSplitContacts(key, params, wanted) {
  buildSplitContacts((suffix, p) => addRep(key + suffix, "contact", p), params, wanted);
}

/* Same split on a component this module did not load — a superposed structure. Exported rather than
   duplicated in the align module so one description of "what colour is an interaction" serves every
   structure in the scene. */
export function addSplitContactsTo(component, params, wanted) {
  if (!component) return;
  buildSplitContacts((suffix, p) => {
    try { return component.addRepresentation("contact", p); } catch (e) { return null; }
  }, params, wanted);
}

function repaintBuffers(element, rgb) {
  const buffers = element && element.repr && element.repr.bufferList;
  if (!buffers || !buffers.length) return false;
  let painted = false;
  for (const buffer of buffers) {
    const attributes = buffer && buffer.geometry && buffer.geometry.attributes;
    if (!attributes) continue;
    for (const name of ["color", "color2"]) {
      const attribute = attributes[name];
      if (!attribute || !attribute.array) continue;
      for (let i = 0; i + 2 < attribute.array.length; i += 3) {
        attribute.array[i] = rgb[0];
        attribute.array[i + 1] = rgb[1];
        attribute.array[i + 2] = rgb[2];
      }
      attribute.needsUpdate = true;
      painted = true;
    }
  }
  return painted;
}

/* Which interaction layers are on. The viewer drew one kind — ligand to receptor — and called it
   "interactions", which is the only kind a binding-site view needs and not the only kind there is.
   The helical ones answer a different question: what holds the bundle together, and which helices
   touch each other. They are off by default because a receptor's intra-helical hydrogen bonds are
   every backbone i,i+4 pair in every helix, which is the shape of an alpha helix and about two
   hundred and fifty lines. */
const interactionLayers = { ligand:true, inter:false, intra:false };
/* Whether the ligand itself is on screen. The protein-ligand lines run to it, so they go when it
   goes — but the helical layers describe the receptor and have no reason to. Tracked rather than
   folded into the layer flag, so re-showing the ligand brings its lines back without the reader
   having to switch them on again. */
let ligandShown = true;
export function interactionLayerState() { return Object.assign({}, interactionLayers); }
export function setInteractionLayer(name, on) {
  if (!(name in interactionLayers)) return false;
  interactionLayers[name] = !!on;
  redrawInteractions();
  return true;
}
export function anyInteractionLayer() {
  return Object.values(interactionLayers).some(Boolean);
}
/* The helical layers are the only part of the viewer that needs to know which helix a residue is
   in, so they are the only part that needs the numbering table. Reported so the panel can load it
   before switching one on rather than drawing nothing and saying nothing. */
export function helicalLayersNeedTable() {
  return (interactionLayers.inter || interactionLayers.intra) && !residueTable.length;
}

function helixGroups() {
  const chain = activeReceptorChain();
  const out = new Map();
  for (const r of residueTable) {
    if (chain && r.c !== chain) continue;
    if (HELICES.indexOf(r.s) < 0) continue;
    if (!out.has(r.s)) out.set(r.s, []);
    out.get(r.s).push(r.n + ":" + r.c);
  }
  return out;
}

/* One group of contacts, drawn as the same two representations everything else uses: the hydrogen
   bonds on their own so they can be repainted green, and every other type in NGL's own colours.
   `filterSele` as a pair of selections is what makes inter-helical expressible — NGL keeps only
   contacts with one atom in the first selection and the other in the second. */
function addContactGroup(key, sele, filterPair, extra) {
  const base = Object.assign({ sele, maxHbondDist:3.6, maxHydrophobicDist:4.2,
    maxPiStackingDist:5.5, labelVisible:false }, extra || {});
  if (filterPair) base.filterSele = filterPair;
  addSplitContacts(key, base,
    { weakHydrogenBond:true, backboneHydrogenBond:!!(extra || {}).backboneHydrogenBond });
  /* Inter-helical contacts run through the interior of the bundle, which is where the cartoon
     ribbon is, and NGL's semi-transparent cartoon writes depth — it does not blend with what is
     behind it, it removes it. Measured on one selected residue: with the ribbon on the layer put
     nothing on screen at all, with it off, 444 pixels. Four ways of drawing through it were tried
     and every one is worse than the problem: a thicker line does not reach past the ribbon,
     thinning the ribbon to 0.22 leaves the receptor invisible and the lines still lost, taking the
     lines out of the depth test changes nothing, and stopping the ribbon writing depth breaks the
     ribbon into fragments. So the ribbon wins, and a reader who wants these contacts turns it
     off — one click, and they show cleanly. */
}

/* The residues actually on screen as atoms: the ligand's contact shell while that layer is on, plus
   anything the reader picked or arrived marking. Used to scope the intra-helical layer, which over
   whole helices is every backbone i,i+4 pair of all seven — several hundred lines that light the
   entire bundle and bury whatever the reader was looking at. */
function displayedResidueKeys() {
  const out = new Set(claimedResidues());
  if (contactsOn && !focusSelection) {
    const o = obs();
    for (const r of (o && o.contact_receptor_details) || [])
      out.add(residueKey(r.auth_asym_id, r.auth_seq_id));
    for (const [c, seq] of (o && o.contact_receptor_residues) || []) out.add(residueKey(c, seq));
  }
  return out;
}

function addHelicalInteractions() {
  if (!interactionLayers.inter && !interactionLayers.intra) return;
  const groups = helixGroups();
  const names = HELICES.filter(h => (groups.get(h) || []).length > 1);
  const seleOf = h => groups.get(h).join(" or ");
  /* Both helical layers are scoped to what is on screen, but they need different scopes.
     Intra-helical: an alpha helix hydrogen-bonds i to i+4, and the residues a pocket puts on one
     helix are scattered along it — taken as the displayed residues alone the layer drew nothing at
     all. So the scope is each displayed residue plus four either side: exactly the span that can
     bond to it, the helix's own number rather than one chosen to make the picture look right.
     Inter-helical: no span, because a side chain reaches across to another helix directly. The
     scope is the displayed residues themselves, and every contact they make with any other helix.
     Left unscoped this poured the whole bundle onto the screen while the reader was looking at one
     residue — the layer answered "which helices touch each other" when they had asked "what does
     this one touch". */
  const shown = displayedResidueKeys();
  const HELIX_BOND_SPAN = 4;
  const intraOf = h => {
    // Ordered along the chain so "four either side" means four turns of sequence, not of payload.
    const ordered = groups.get(h).slice().sort((a, b) => parseInt(a, 10) - parseInt(b, 10));
    const keep = new Set();
    ordered.forEach((key, i) => {
      if (!shown.has(key)) return;
      for (let j = Math.max(0, i - HELIX_BOND_SPAN);
           j <= Math.min(ordered.length - 1, i + HELIX_BOND_SPAN); j++) keep.add(ordered[j]);
    });
    return ordered.filter(k => keep.has(k));
  };
  // Backbone hydrogen bonds are off by default in NGL and are most of what holds a helix together,
  // so the helical layers ask for them explicitly.
  const extra = { backboneHydrogenBond:true };
  if (interactionLayers.intra)
    for (const h of names) {
      const here = intraOf(h);
      if (here.length > 1) addContactGroup("lines_intra_" + h, here.join(" or "), null, extra);
    }
  if (interactionLayers.inter)
    names.forEach(h => {
      /* One side of the pair is the displayed residues of this helix, the other is every other
         helix — so what is drawn is what those residues reach across to, whichever helix answers.
         A contact displayed at both ends is drawn twice over the same line, which costs nothing. */
      const mine = groups.get(h).filter(k => shown.has(k));
      if (!mine.length) return;
      const others = names.filter(x => x !== h).map(seleOf).join(" or ");
      if (!others) return;
      const here = mine.join(" or ");
      addContactGroup("lines_inter_" + h, "(" + seleOf(h) + ") or (" + others + ")",
        [here, others], extra);
    });
}

const CARTOON_OPACITY = 0.68;

function redrawInteractions() {
  dropByPrefix("lines");
  /* Only the ligand's lines go when the reader asks to see the selection alone: they run to the
     contacting side chains, and with those hidden they would end in mid-air. The helical layers are
     drawn over the selection itself, so showing the selection alone is the state they are most
     wanted in — dropping them there left the reader looking at exactly the residues they had picked
     and told that nothing connects them. */
  if (interactionLayers.ligand && ligandShown && !focusSelection)
    ligandObservations().forEach((o, i) => addInteractionLines(o, i ? "lines_extra_" + i : "lines"));
  addHelicalInteractions();
}

function addInteractionLines(o=obs(), key="lines") {
  if (!o || !o.ligand_selection) return;
  const params = { sele:sel(o.contact_receptor_residues) + " or " +
    ligandSelection(o), maxHbondDist:3.6, maxHydrophobicDist:4.2,
    maxPiStackingDist:5.5, labelVisible:true, labelUnit:"angstrom", labelSize:0.72 };
  const colour = contactLabelColour();
  if (colour) params.labelColor = colour;
  addSplitContacts(key, params, { weakHydrogenBond:true });
}

/* Kept as the name the rest of the module calls, but it no longer decides anything: the one place
   that knows which layers survive which state is redrawInteractions. It used to drop every line in
   focus mode and return, which is why moving that rule into redrawInteractions did nothing — this
   is the function focus mode actually calls, and it never got there. */
function addDisplayedInteractions() { redrawInteractions(); }

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
/* Every residue any layer is going to name, whatever the reason. redrawSelections builds the same
   set as it goes, because it also needs the order; this is for callers that only need the answer. */
function claimedResidues() {
  const out = new Set(selectedResidues);
  for (const r of Array.from(selectedMotifs).flatMap(residuesForMotif))
    out.add(residueKey(r.auth_asym_id, r.auth_seq_id));
  for (const key of queryResidues) out.add(key);
  return out;
}

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

  // Rebuilt last, without whatever the layers above have just named.
  if (contactLabelsOn) addContactLabels(claimed);
  /* The intra-helical layer is drawn over the residues on screen, and this is what changes which
     those are. Redrawn only when that layer is on, so an ordinary click pays nothing for it. */
  if (interactionLayers.intra) redrawInteractions();
}

export function toggleResidue(chain, seq) {
  const key = residueKey(chain, seq);
  const removing = selectedResidues.has(key);
  removing ? selectedResidues.delete(key) : selectedResidues.add(key);
  redrawSelections();
  releaseFocusIfEmpty();
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
  releaseFocusIfEmpty();
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
  releaseFocusIfEmpty();
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
    if (!on) { dropRep("cartoon"); return; }
    addRep("cartoon", "cartoon", { sele:rc, color:"#646a73", opacity:CARTOON_OPACITY }); },
  allLigands(on) {
    if (!on) { dropRep("all_lig"); return; }
    const all = (meta.observations || []).filter(o => o.ligand_selection)
      .map(o => sel(o.ligand_selection.residues)).filter(s => s !== "none");
    if (all.length) addRep("all_lig", "ball+stick", { sele: all.join(" or "), color: "element" });
  },
  contacts(on) {
    dropByPrefix("contacts"); dropByPrefix("iface");
    contactsOn = on;
    if (on) addContactSideChains();
    // The contact shell is part of what the intra-helical layer is scoped to.
    if (interactionLayers.intra) redrawInteractions();
  },
  lines(on) {
    // The master switch drives every layer at once; the panel's three controls drive them singly.
    interactionLayers.ligand = on;
    if (!on) { interactionLayers.inter = false; interactionLayers.intra = false; }
    redrawInteractions();
  },
  ligand(on) {
    ligandShown = on;
    if (!on) {
      dropByPrefix("ligand"); dropRep("covalent_atoms"); dropRep("covalent_bond");
      // Only the ligand's own lines go; anything helical stays, because it was never about
      // the ligand.
      redrawInteractions();
      return;
    }
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
  motifLabels(on) { contactLabelsOn = on;
    if (!on) { dropRep("motif_labels"); return; } addContactLabels(claimedResidues()); },
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
