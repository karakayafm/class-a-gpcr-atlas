// Site-aware 3D viewer. Small-molecule pockets and polymer interfaces use different
// terminology, different default representations and different camera framing.
import { t, siteClassLabel } from "../core/i18n.js";
import { el, clear } from "../components/dom.js";
import { loadBundleMeta, bundleCifUrl, errorMessage } from "../data/loader.js";
import * as LC from "./lifecycle.js";

let comp = null, meta = null, current = null, reps = {};
const POLYMER = { extracellular_polymer_interface: 1, tethered_ligand_interface: 1 };

function sel(residues) {
  if (!residues || !residues.length) return "none";
  return residues.map(r => r[1] + ":" + r[0]).join(" or ");
}

export async function open(host, pdb, observationId, onStatus) {
  const NGL = window.NGL;
  if (!NGL) { onStatus(t("err_webgl")); return null; }
  onStatus(t("loading_structure"));
  try { meta = await loadBundleMeta(pdb); }
  catch (e) { onStatus(errorMessage(e)); return null; }
  let stage;
  try { stage = LC.createStage(NGL, host, { backgroundColor: "white", quality: "medium" }); }
  catch (e) { onStatus(t("err_webgl")); return null; }
  // the host is visible by the time we get here; resize after creation and after load
  LC.resizeStageIfVisible();
  try {
    comp = await stage.loadFile(bundleCifUrl(pdb), { ext: "cif" });
  } catch (e) { onStatus(t("err_bundle")); LC.destroyStage(); return null; }
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

export function close() { LC.destroyStage(); comp = null; meta = null; current = null; reps = {}; }
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
  const rc = (meta.receptor_chains || []).map(c => ":" + c).join(" or ") || "polymer";
  addRep("cartoon", "cartoon", { sele: rc, color: "residueindex", opacity: 0.9 });
  const o = obs();
  if (o && o.ligand_selection) {
    const lsel = sel(o.ligand_selection.residues);
    if (POLYMER[o.binding_site_class]) {
      addRep("ligand", "cartoon", { sele: lsel, color: "orange" });
      addRep("ligand_stick", "licorice", { sele: lsel, color: "orange", opacity: 0.85 });
      addRep("iface", "licorice", { sele: sel(o.contact_receptor_residues), color: "steelblue" });
    } else {
      addRep("ligand", "ball+stick", { sele: lsel, color: "orange" });
      addRep("contacts", "licorice", { sele: sel(o.contact_receptor_residues), color: "steelblue" });
    }
    frame(lsel);
  } else {
    comp.autoView(400);
  }
}

export function frame(selection) {
  if (!comp) return;
  try { comp.autoView(selection, 400); } catch (e) { comp.autoView(400); }
}

export const toggles = {
  cartoon(on) { const rc = (meta.receptor_chains || []).map(c => ":" + c).join(" or ") || "polymer";
    on ? addRep("cartoon", "cartoon", { sele: rc, color: "residueindex", opacity: 0.9 }) : dropRep("cartoon"); },
  allLigands(on) {
    if (!on) { dropRep("all_lig"); return; }
    const all = (meta.observations || []).filter(o => o.ligand_selection)
      .map(o => sel(o.ligand_selection.residues)).filter(s => s !== "none");
    if (all.length) addRep("all_lig", "ball+stick", { sele: all.join(" or "), color: "element" });
  },
  contacts(on) { const o = obs(); if (!on || !o) { dropRep("contacts"); dropRep("iface"); return; }
    const key = POLYMER[o.binding_site_class] ? "iface" : "contacts";
    addRep(key, "licorice", { sele: sel(o.contact_receptor_residues), color: "steelblue" }); },
  lines(on) { const o = obs(); if (!on || !o || !o.ligand_selection) { dropRep("lines"); return; }
    addRep("lines", "contact", { sele: sel(o.contact_receptor_residues) + " or " +
      sel(o.ligand_selection.residues), maxDistance: 5.0 }); },
  surface(on) { const o = obs(); if (!on || !o) { dropRep("surface"); return; }
    addRep("surface", "surface", { sele: sel(o.contact_receptor_residues),
      opacity: 0.28, colorValue: "lightgrey" }); },
  motifs(on) { if (!on) { dropRep("motifs"); return; }
    const m = (meta.motif_residues || []).map(r => r.auth_seq_id + ":" + r.auth_asym_id);
    if (m.length) addRep("motifs", "licorice", { sele: m.join(" or "), color: "green" }); },
  motifLabels(on) { if (!on) { dropRep("motif_labels"); return; }
    const m = (meta.motif_residues || []).map(r => r.auth_seq_id + ":" + r.auth_asym_id);
    if (m.length) addRep("motif_labels", "label", { sele: m.join(" or ") + " and .CA",
      labelType: "text", labelText: (meta.motif_residues || []).map(r => r.generic_position),
      color: "black", zOffset: 2 }); },
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
  const un = (meta.receptor_instances || []).some(r => r.generic_mapping === "unresolved");
  if (un) return t("generic_unresolved");
  return "";
}
export { LC as lifecycle };
