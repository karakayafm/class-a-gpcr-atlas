/* Superposing a second structure onto the one on screen.
 *
 * The obvious way to do this is NGL's own `superpose(s1, s2, true)`, which runs a Smith-Waterman
 * alignment over the two sequences and fits the matched CA atoms. For two depositions of the same
 * receptor it works. Across receptors it is the wrong instrument: the sequences diverge, the
 * alignment starts making judgement calls in the loops, and the answer depends on where those calls
 * fell rather than on the helices anyone wants compared.
 *
 * The atlas already holds the correspondence that question needs. Structure-based generic numbering
 * says that 6x48 in one receptor is 6x48 in another, and it says so from the structures rather than
 * from the sequence. So the fit here is over the CA atoms of the generic positions the two
 * structures share, paired by position rather than by alignment. Two β2-adrenoceptor depositions
 * and a β2/M2 pair are then the same operation, and the readout can say honestly how many positions
 * carried it.
 *
 * What is deliberately not done: no attempt is made to fit on the pocket alone, or on one helix.
 * A whole-receptor fit is the only one whose RMSD means what a reader will assume it means.
 */
import { t } from "../core/i18n.js";
import { loadBundleMeta, bundleCifUrl, loadReceptorResidues, errorMessage } from "../data/loader.js";
import * as LC from "./lifecycle.js";
import * as V from "./viewer.js";

/* Distinct from each other, from the green the base structure takes while any of these are on
   screen, and from the orange the measurement layer uses. Reused in order; a fifth overlay wraps
   and is told apart by its label. */
const COLOURS = [0x4f9de0, 0xd95f9a, 0xc9a227, 0xa07ad6];
/* The base structure while superposition is on. Every structure in the scene then reads as one
   colour from its cartoon through its side chains to its ligand, which is the only way to see at a
   glance which of three overlapping ligands belongs to which receptor. */
const BASE_COLOUR = "#3fa96a";
const MIN_POSITIONS = 12;

const overlays = [];   // { pdb, comp, colour, rmsd, n, chain, name }

export function overlayList() {
  return overlays.map(o => ({ pdb: o.pdb, colour: o.colour, rmsd: o.rmsd, n: o.n, name: o.name }));
}
export function hasOverlays() { return overlays.length > 0; }
export function isOverlaid(pdb) {
  return overlays.some(o => o.pdb === String(pdb || "").toUpperCase());
}
export function overlayCount() { return overlays.length; }
/* The panel draws the legend, so it has to be told what the base structure was painted. */
export function baseColour() { return BASE_COLOUR; }

/* Labels carry the structure's identity in their *text* colour, on the same black background every
   structure uses.
 *
 * Tinting the background instead was tried and is worse in both directions: dark enough for white
 * text to read against, it is indistinguishable from black, so two labels stacked on the same
 * position — V3x33 from one receptor, I3x33 from the other — say nothing about which is which;
 * light enough to be recognisable, the white text stops being legible. Colouring the glyphs keeps
 * the contrast of black behind them and puts the identity where the eye already is. */
function hex(colour) { return "#" + colour.toString(16).padStart(6, "0"); }
const LABEL_BACKGROUND = "#111111";

/* generic position -> CA coordinate, for one chain of a loaded structure. Built by walking the
   structure once rather than by running a selection per position: a receptor has ~300 numbered
   positions and that would be 300 selection parses. */
function caByPosition(structure, rows, chain) {
  const want = new Map();                       // "chain:resno" -> generic position
  for (const r of rows) {
    if (chain && r.c !== chain) continue;
    want.set(r.c + ":" + r.n, r.p);
  }
  const out = new Map();
  structure.eachAtom(a => {
    if (a.atomname !== "CA") return;
    const p = want.get(a.chainname + ":" + a.resno);
    // A position resolved twice — altloc, or a chain repeated in the asymmetric unit — keeps its
    // first occurrence, so both structures resolve it the same deterministic way.
    if (p && !out.has(p)) out.set(p, [a.x, a.y, a.z]);
  });
  return out;
}

function dominantChain(rows) {
  const count = new Map();
  for (const r of rows) count.set(r.c, (count.get(r.c) || 0) + 1);
  let best = "", n = -1;
  for (const [c, v] of count) if (v > n) { best = c; n = v; }
  return best;
}

function rmsdOf(a, b) {
  let sum = 0;
  for (let i = 0; i < a.length; i += 3)
    sum += (a[i] - b[i]) ** 2 + (a[i+1] - b[i+1]) ** 2 + (a[i+2] - b[i+2]) ** 2;
  return Math.sqrt(sum / (a.length / 3));
}

/* The ligand of the overlaid structure, as an NGL selection. Its own metadata knows which residues
   those are; without this the overlay would show a bare receptor and the comparison a reader most
   often wants — two ligands in one pocket — would be the one thing missing. */
function ligandSelectionOf(meta) {
  const parts = [];
  for (const o of meta.observations || []) {
    const ls = o.ligand_selection;
    if (!ls || !(ls.residues || []).length) continue;
    if (ls.selection_kind === "polymer_segment") continue;   // whole chains would dwarf the scene
    parts.push(ls.residues.map(r => r[1] + ":" + r[0]).join(" or "));
  }
  return parts.length ? "(" + parts.join(" or ") + ") and hetero and not hydrogen" : null;
}

/* The side chains this structure's own ligand contacts. Without them an overlay is a ribbon and a
   ligand floating in it, and the question superposition is usually asked in order to answer — does
   the other receptor put the same residue against the same part of the ligand — has nothing on
   screen to answer it with. Its own contact list is used, not the base structure's: these are that
   receptor's contacts, and borrowing the base structure's residue numbers would draw the wrong ones. */
function contactSelectionOf(meta) {
  const residues = [];
  for (const o of meta.observations || [])
    for (const r of o.contact_receptor_residues || []) residues.push(r);
  if (!residues.length) return null;
  const seen = new Set(), parts = [];
  for (const [chain, seq] of residues) {
    const key = seq + ":" + chain;
    if (seen.has(key)) continue;
    seen.add(key); parts.push(key);
  }
  return "(" + parts.join(" or ") + ") and not hydrogen and sidechainAttached";
}

/* The contacting residues as a plain residue selection — no `sidechainAttached` — which is what the
   interaction representation needs on both sides of the line. */
function contactResiduesOf(meta) {
  const seen = new Set();
  for (const o of meta.observations || [])
    for (const [chain, seq] of o.contact_receptor_residues || []) seen.add(seq + ":" + chain);
  return seen.size ? [...seen].join(" or ") : null;
}

/* Labels for the contacting residues, in the generic numbering this structure was aligned on. The
   base structure builds these from its observation details; here the numbering table already holds
   the one-letter code and the position, so the same label falls out of the rows without needing the
   viewer's own naming path. */
function contactLabelText(entry) {
  const wanted = new Map();
  const contacts = new Set();
  for (const o of entry.meta.observations || [])
    for (const [chain, seq] of o.contact_receptor_residues || []) contacts.add(seq + ":" + chain);
  for (const r of entry.rows) {
    if (!contacts.has(r.n + ":" + r.c)) continue;
    wanted.set(r.c + ":" + r.n, r.a + r.p);
  }
  const text = {}, keys = [];
  if (!wanted.size || !window.NGL) return { text, sele: null };
  try {
    entry.comp.structure.eachAtom(a => {
      const label = wanted.get(a.chainname + ":" + a.resno);
      if (label) { text[a.index] = label; keys.push(a.resno + ":" + a.chainname); }
    }, new window.NGL.Selection(".CA"));
  } catch (e) {}
  return { text, sele: keys.length ? keys.join(" or ") : null };
}

/* Draws one overlay from its layer state. Called on load and again whenever a layer is toggled or
   measurement mode changes the form the atoms are drawn in, so there is one description of what an
   overlay looks like rather than one per entry point. */
function paintOverlay(entry) {
  const { comp, colour } = entry;
  try { comp.removeAllRepresentations(); } catch (e) {}
  /* One colour for the whole structure so it reads as one object against the base structure's green
     and against the other overlays — but on the atomistic layers the colour is carried by carbon
     and the heteroatoms keep theirs, so nitrogen and oxygen stay identifiable in every ligand on
     screen. That is what the comparison is usually about. */
  const flat = { colorScheme: "uniform", colorValue: colour };
  const byElement = { colorScheme: "element", colorValue: colour };
  /* The same reason the base structure switches: licorice draws bonds and no atom centres, so in
     measurement mode there is often nothing to aim at. An overlay left in licorice while the base
     structure gained spheres was the half of the scene that could not be measured. */
  const atomType = V.isMeasuring() ? "ball+stick" : "licorice";
  const atomExtra = V.isMeasuring() ? { aspectRatio: 1.9, scale: 0.30 } : { radiusScale: 0.9 };
  if (entry.layers.cartoon)
    comp.addRepresentation("cartoon", Object.assign({
      sele: entry.chain ? ":" + entry.chain : "polymer", opacity: 0.85, side: "front" }, flat));
  const contacts = contactSelectionOf(entry.meta);
  if (entry.layers.sidechains && contacts)
    comp.addRepresentation(atomType, Object.assign({ sele: contacts, opacity: 0.95 },
      atomExtra, byElement));
  const lig = ligandSelectionOf(entry.meta);
  if (entry.layers.ligand && lig)
    comp.addRepresentation("ball+stick", Object.assign({
      sele: lig, aspectRatio: 1.6, radiusScale: 1.1 }, byElement));
  if (entry.layers.interactions) {
    const cr = contactResiduesOf(entry.meta);
    /* Both sides parenthesised. Unbracketed, `a or b or (c) and hetero and not hydrogen` is at the
       mercy of the selection language's precedence, and the reading that binds `and` across the
       whole disjunction leaves only hetero atoms selected — no receptor side, so no contacts. */
    if (cr && lig) comp.addRepresentation("contact", {
      sele: "(" + cr + ") or (" + lig + ")", maxHbondDist: 3.6, maxHydrophobicDist: 4.2,
      maxPiStackingDist: 5.5, labelVisible: true, labelUnit: "angstrom", labelSize: 0.72,
      labelColor: V.currentBackground() === "white" ? "#111111" : "#ffffff" });
  }
  if (entry.layers.labels) {
    const { text, sele } = contactLabelText(entry);
    /* Restricted to the atoms the text map actually covers, the way the base structure does it.
       Handing NGL every CA in the chain while the map holds twenty-three of them leaves the rest
       with no text, and the buffer it builds from that draws nothing at all. */
    if (sele) comp.addRepresentation("label", {
      sele: "(" + sele + ") and .CA", labelType: "text", labelText: text, color: hex(colour),
      backgroundColor: LABEL_BACKGROUND, backgroundOpacity: 0.8,
      showBackground: true, fixedSize: false, labelSize: 2.2, radius: 0.8, zOffset: 2 });
  }
  /* Residues picked from the whole-receptor list while this structure was the active one. Drawn and
     labelled here rather than on the base component, which is the whole point: a position outside
     the pocket of the *other* receptor is what superposition was opened to look at. */
  if (entry.selected.size) {
    const sele = [...entry.selected].join(" or ");
    comp.addRepresentation("licorice", Object.assign({
      sele: "(" + sele + ") and not hydrogen and sidechainAttached",
      radiusScale: 1.5, opacity: 1 }, byElement));
    comp.addRepresentation("label", {
      sele: "(" + sele + ") and .CA", labelType: "format",
      labelFormat: "%(resname)s%(resno)s", labelGrouping: "residue",
      color: hex(colour), fixedSize: false, labelSize: 2.2, zOffset: 2,
      showBackground: true, backgroundColor: LABEL_BACKGROUND, backgroundOpacity: 0.8 });
  }
}

/* Residue picking on an overlay, keyed the way NGL selections are written so the set can be joined
   into one straight away. */
function residueKey(chain, seq) { return String(seq) + ":" + String(chain); }
export function toggleOverlayResidue(pdb, chain, seq) {
  const o = overlays.find(x => x.pdb === String(pdb || "").toUpperCase());
  if (!o) return false;
  const key = residueKey(chain, seq);
  if (o.selected.has(key)) o.selected.delete(key); else o.selected.add(key);
  paintOverlay(o);
  return o.selected.has(key);
}
export function isOverlayResidueSelected(pdb, chain, seq) {
  const o = overlays.find(x => x.pdb === String(pdb || "").toUpperCase());
  return !!(o && o.selected.has(residueKey(chain, seq)));
}
export function overlaySelectionSize(pdb) {
  const o = overlays.find(x => x.pdb === String(pdb || "").toUpperCase());
  return o ? o.selected.size : 0;
}
export function clearOverlaySelection(pdb) {
  const o = overlays.find(x => x.pdb === String(pdb || "").toUpperCase());
  if (!o || !o.selected.size) return false;
  o.selected.clear(); paintOverlay(o); return true;
}
/* The overlay's whole-receptor list, grouped into helices exactly as the base structure's is. */
export function segmentsOf(pdb) {
  const o = overlays.find(x => x.pdb === String(pdb || "").toUpperCase());
  if (!o) return [];
  const contacts = new Set();
  for (const ob of o.meta.observations || [])
    for (const [c, seq] of ob.contact_receptor_residues || []) contacts.add(String(seq) + ":" + c);
  return V.segmentRows(o.rows, o.chain, contacts);
}

/* Frames the camera on one overlay, which is how the switcher answers "where is this structure". */
export function frameOverlay(pdb) {
  const o = overlays.find(x => x.pdb === String(pdb || "").toUpperCase());
  if (!o) return false;
  try { o.comp.autoView(o.chain ? ":" + o.chain : "polymer", 400); return true; }
  catch (e) { return false; }
}

/* Which layers an overlay is showing, and the switch for one of them. The panel drives these for
   whichever structure is active, so the toggles mean the same thing whatever is selected. */
export function layerState(pdb) {
  const o = overlays.find(x => x.pdb === String(pdb || "").toUpperCase());
  return o ? Object.assign({}, o.layers) : null;
}
export function setLayer(pdb, name, on) {
  const o = overlays.find(x => x.pdb === String(pdb || "").toUpperCase());
  if (!o || !(name in o.layers)) return false;
  o.layers[name] = !!on;
  paintOverlay(o);
  return true;
}
/* Redraws every overlay in the form the current measurement mode calls for. */
export function refreshStyle() { for (const o of overlays) paintOverlay(o); }

/* The numbering table an overlay was aligned on, so the panel can offer its positions the way it
   offers the base structure's. */
export function residueRowsOf(pdb) {
  const o = overlays.find(x => x.pdb === String(pdb || "").toUpperCase());
  return o ? o.rows : null;
}
export function chainOf(pdb) {
  const o = overlays.find(x => x.pdb === String(pdb || "").toUpperCase());
  return o ? o.chain : "";
}

export async function addOverlay(pdb, onStatus) {
  const NGL = window.NGL;
  const stage = LC.getStage();
  const base = V.baseComponent();
  const id = String(pdb || "").toUpperCase();
  const say = onStatus || (() => {});
  if (!NGL || !stage || !base) return { error: t("align_err_no_structure") };
  if (isOverlaid(id)) return { error: t("align_err_already", { pdb: id }) };
  if (id === V.basePdb()) return { error: t("align_err_self") };

  say(t("align_loading", { pdb: id }));
  let baseRows, rows, meta;
  try {
    [baseRows, rows, meta] = await Promise.all([
      V.ensureBaseResidueRows(), loadReceptorResidues(id), loadBundleMeta(id)]);
  } catch (e) { return { error: errorMessage(e) }; }
  const mobileRows = (rows && rows.residues) || [];
  if (!baseRows.length) return { error: t("align_err_no_numbering", { pdb: V.basePdb() }) };
  if (!mobileRows.length) return { error: t("align_err_no_numbering", { pdb: id }) };

  let comp;
  try { comp = await stage.loadFile(bundleCifUrl(id), { ext: "cif" }); }
  catch (e) { return { error: t("err_bundle") }; }

  const baseChain = V.receptorChain();
  const mobileChain = dominantChain(mobileRows);
  const refCA = caByPosition(base.structure, baseRows, baseChain);
  const mobCA = caByPosition(comp.structure, mobileRows, mobileChain);
  /* Sorted so the pairing is reproducible and independent of payload order — the two coordinate
     arrays have to be in corresponding order, and nothing downstream would notice if they were not. */
  const shared = [...refCA.keys()].filter(p => mobCA.has(p)).sort();
  if (shared.length < MIN_POSITIONS) {
    try { stage.removeComponent(comp); } catch (e) {}
    return { error: t("align_err_too_few", { n: shared.length, min: MIN_POSITIONS }) };
  }
  const ref = new Float32Array(shared.length * 3), mob = new Float32Array(shared.length * 3);
  shared.forEach((p, i) => {
    const a = refCA.get(p), b = mobCA.get(p);
    ref[i*3] = a[0]; ref[i*3+1] = a[1]; ref[i*3+2] = a[2];
    mob[i*3] = b[0]; mob[i*3+1] = b[1]; mob[i*3+2] = b[2];
  });
  try {
    new NGL.Superposition(mob, ref).transform(comp.structure);
    comp.structure.refreshPosition();
  } catch (e) {
    try { stage.removeComponent(comp); } catch (e2) {}
    return { error: t("align_err_failed") };
  }
  // Recomputed from the moved coordinates rather than taken from the fit, so the number reported
  // is a property of what is on screen.
  const moved = caByPosition(comp.structure, mobileRows, mobileChain);
  const after = new Float32Array(shared.length * 3);
  shared.forEach((p, i) => {
    const b = moved.get(p);
    after[i*3] = b[0]; after[i*3+1] = b[1]; after[i*3+2] = b[2];
  });
  const rmsd = rmsdOf(after, ref);

  const colour = COLOURS[overlays.length % COLOURS.length];
  try { comp.setName(id); comp.structure.name = id; } catch (e) {}
  comp.setVisibility(true);
  // The base structure goes uniform on the first overlay, not on every one.
  if (!overlays.length) V.setUniformColour(BASE_COLOUR);
  const entry = { pdb: id, comp, colour, rmsd, n: shared.length, chain: mobileChain,
    rows: mobileRows, meta,
    name: (meta.receptor_name || meta.receptor_entry_name || ""),
    // Same three layers the base structure's own toggles control, so the switcher can drive either.
    layers: { cartoon: true, sidechains: true, ligand: true,
              labels: true, interactions: true },
    // Positions the reader has clicked in the whole-receptor list while this structure was active.
    selected: new Set() };
  overlays.push(entry);
  /* Handed to the viewer so an atom picked here is named by its generic position rather than by the
     deposited residue number of a receptor whose numbering means nothing to the rest of the atlas. */
  V.registerStructureTable(id, mobileRows);
  paintOverlay(entry);
  say("");
  return { pdb: id, colour, rmsd, n: shared.length,
           name: (meta.receptor_name || meta.receptor_entry_name || "") };
}

export function removeOverlay(pdb) {
  const id = String(pdb || "").toUpperCase();
  const i = overlays.findIndex(o => o.pdb === id);
  if (i < 0) return false;
  const stage = LC.getStage();
  try { if (stage) stage.removeComponent(overlays[i].comp); } catch (e) {}
  V.registerStructureTable(id, []);
  overlays.splice(i, 1);
  // Nothing left to tell apart, so the scene's ordinary colouring — element colours on the ligand,
  // the contact tint on the side chains — comes back.
  if (!overlays.length) V.setUniformColour(null);
  return true;
}

export function clearOverlays() {
  const stage = LC.getStage();
  for (const o of overlays) { try { if (stage) stage.removeComponent(o.comp); } catch (e) {} }
  overlays.length = 0;
  V.forgetStructureTables();
  V.setUniformColour(null);
}

/* Called when the base structure changes or the modal closes. The components belong to a stage that
   is about to be destroyed, so this only has to forget them. */
export function reset() { overlays.length = 0; }

/* Frame everything on screen rather than the base structure alone, so adding an overlay that
   extends past the receptor does not leave it half out of view. */
export function frameAll() {
  const stage = LC.getStage();
  if (!stage) return false;
  try { stage.autoView(500); return true; } catch (e) { return false; }
}
