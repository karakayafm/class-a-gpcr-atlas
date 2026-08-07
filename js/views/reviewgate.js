// Phase 6A.1 — review-gate and validation-scope presentation.
//
// The public presentation uses the review-gated overlay. The original Phase 4 value is still
// available, but only in a labelled panel — never as the default, never in the main ranking,
// never in a comparison.
//
import { t, getLang } from "../core/i18n.js";
import { el } from "../components/dom.js";
import * as L from "../data/loader.js";

const L10N = k => (getLang() === "tr" ? k + "_tr" : k + "_en");

export async function gateFor(slug) { return L.loadOverlay("families/" + slug + "/review_gate.json"); }
export async function globalIndex() { return L.loadOverlay("global/review_gate_index.json"); }

/* ------------------------------------------------------------------ review gate panel */
export function gatePanel(gate, siteClass) {
  if (!gate) return null;
  const sc = (gate.site_classes || {})[siteClass] || {};
  const rows = [
    [t("rg_status"), t("rg_applied")],
    [t("rg_denominator_before"), String(sc.denominator_before_review_gate ?? "—")],
    [t("rg_denominator_after"), String(sc.denominator_after_review_gate ?? "—")],
    [t("rg_excluded_slots"), String(gate.structure_slots_excluded ?? 0)],
    [t("rg_warning_slots"), String(gate.structure_slots_warning_only ?? 0)],
    [t("rg_removed_units"), String(sc.units_removed ?? gate.units_removed ?? 0)],
    [t("rg_modified_units"), String(sc.units_modified ?? gate.units_modified ?? 0)],
    [t("rg_affecting_items"), String((gate.affecting_review_items || []).length)]
  ];
  const tbl = el("table", { class: "data compact" });
  const tb = el("tbody");
  for (const [k, v] of rows) {
    tb.appendChild(el("tr", {}, [el("th", { scope: "row", text: k }), el("td", { class: "num", text: v })]));
  }
  tbl.appendChild(tb);

  const wrap = el("section", { class: "review-gate", "aria-label": t("rg_status") });
  wrap.appendChild(el("h3", { text: t("rg_heading") }));
  wrap.appendChild(el("p", { class: "small", text: gate[L10N("explanation")] }));
  wrap.appendChild(tbl);
  const warn = gate[L10N("coverage_warning")];
  if (warn) wrap.appendChild(el("p", { class: "muted small", text: warn }));
  if (sc.estimable === false) {
    wrap.appendChild(el("p", { class: "notice", text: sc[L10N("not_estimable_note")] || t("not_estimable") }));
  }
  return wrap;
}

/* The original, un-gated Phase 4 value. Explicitly labelled, collapsed, and never the default. */
export function originalPanel(gate, phase4Positions) {
  if (!gate || !phase4Positions) return null;
  return el("details", { class: "original-aggregate" }, [
    el("summary", { text: gate[L10N("original_label")] }),
    el("p", { class: "muted small", text: t("rg_original_note") }),
    el("pre", { class: "small", text: JSON.stringify(phase4Positions.slice(0, 25), null, 1) })
  ]);
}

/* Beta value lookup for the current threshold/weighting. Every combination is precomputed in the
   overlay, so this reads a field — it never recomputes a fraction in the browser. */
const TH_KEY = { "4.0A": "4A", "4.5A": "4_5A", "5.0A": "5A" };
const W_KEY = {
  unit_weighted_continuous: "unit_weighted_continuous",
  unit_weighted_any_contact: "unit_weighted_any_contact",
  structure_weighted_binary: "structure_weighted",
  receptor_weighted: "receptor_weighted",
  ligand_weighted: "ligand_weighted"
};

export function betaValue(pos, weighting, threshold) {
  if (!pos) return null;
  const th = TH_KEY[threshold] || "5A";
  const w = W_KEY[weighting] || "unit_weighted_continuous";
  if (w === "unit_weighted_any_contact") {
    const v = pos.unit_weighted_any_contact_5A;
    return v === undefined ? null : v;
  }
  const v = pos[w + "_" + th];
  return v === undefined ? null : v;
}

export function betaPositions(gate, siteClass) {
  const sc = (gate && gate.site_classes && gate.site_classes[siteClass]) || null;
  return sc ? sc.positions : null;
}
