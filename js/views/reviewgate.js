// Phase 6A.1 — review-gate and validation-scope presentation.
//
// Two commitments made in the release policy live here. Both are about not letting a number look
// more settled than it is:
//
//   1. Pooled public-beta values come from the review-gated overlay. The original Phase 4 value
//      is still available, but only in a labelled panel — never as the default, never in the main
//      ranking, never in a comparison.
//   2. Contact-rule validation scope is shown wherever a contact number is shown. The 5 Å rule
//      was reference-tested on aminergic small-molecule pockets; everything else inherited it,
//      and a reader is entitled to know which they are looking at.
import { t, getLang } from "../core/i18n.js";
import { el } from "../components/dom.js";
import * as L from "../data/loader.js";

const L10N = k => (getLang() === "tr" ? k + "_tr" : k + "_en");

export async function gateFor(slug) { return L.loadOverlay("families/" + slug + "/review_gate.json"); }
export async function validationFor(slug) { return L.loadOverlay("families/" + slug + "/validation.json"); }
export async function globalIndex() { return L.loadOverlay("global/review_gate_index.json"); }

/* ------------------------------------------------------------------ validation badge */
const BADGE_TEXT = {
  reference_tested_within_scope: { en: "Reference-tested within scope", tr: "Kapsam içinde referans testli" },
  transferred_method: { en: "Transferred method", tr: "Aktarılmış yöntem" },
  descriptive_interface_rule: { en: "Descriptive interface rule", tr: "Betimleyici arayüz kuralı" },
  covalent_shell_untested: { en: "Covalent shell untested", tr: "Kovalent kabuk test edilmemiş" },
  mixed_validation_scope: { en: "Mixed validation scope", tr: "Karma doğrulama kapsamı" },
  unresolved: { en: "Validation scope unresolved", tr: "Doğrulama kapsamı belirsiz" },
  not_applicable: { en: "Not applicable", tr: "Kapsam dışı" }
};

export function validationBadge(val, opts) {
  if (!val || !val.badge) return null;
  const b = BADGE_TEXT[val.badge] || BADGE_TEXT.unresolved;
  const txt = b[getLang()] || b.en;
  const node = el("span", {
    class: "badge validation " + val.badge,
    title: (val["global_statement_" + getLang()] || val.global_statement_en || "") +
           " — " + txt,
    text: txt
  });
  if (opts && opts.href) {
    return el("a", { class: "badge-link", href: opts.href, "aria-label": txt }, node);
  }
  return node;
}

/* Per site class, the row that applies to what is currently being shown. */
export function validationRowsFor(val, siteClass) {
  if (!val || !val.rows) return [];
  return val.rows.filter(r => !siteClass || r.site_class === siteClass);
}

export function validationNotice(val, siteClass) {
  const rows = validationRowsFor(val, siteClass);
  if (!rows.length) return null;
  const wrap = el("div", { class: "notice validation-notice" });
  for (const r of rows) {
    wrap.appendChild(el("p", { class: "small",
      text: r["statement_" + getLang()] || r.statement_en }));
  }
  return wrap;
}

/* A polymer interface must never be presented as a validated pocket. This warning is persistent
   rather than dismissable, because the mistake it prevents is a reader treating a descriptive
   shell as a biological threshold. */
export function interfaceShellWarning() {
  return el("p", { class: "notice interface-shell", text: t("descriptive_shell_warning") });
}

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
