// All views. Each returns a DOM node; none recomputes science — every number is read from a
// Phase 4-derived payload field.
import { t, siteClassLabel, stateLabel, warnLabel, getLang } from "../core/i18n.js";
import { el, clear, fmt, pct, paginate, debounce } from "../components/dom.js";
import { toCSV, download } from "../components/csv.js";
import * as L from "../data/loader.js";
import * as ST from "../core/state.js";
import { navigate } from "../core/router.js";
import * as RG from "./reviewgate.js";

const POLYMER = { extracellular_polymer_interface: 1, tethered_ligand_interface: 1 };

function warnBadges(ws) {
  if (!ws || !ws.length) return null;
  return el("span", { class: "badges" }, ws.map(w => el("span", {
    class: "badge warn", title: warnLabel(w), text: warnLabel(w) })));
}
function metricHead(payload) {
  return el("div", { class: "metric-head" }, [
    el("h3", { text: payload.metric["label_" + getLang()] || payload.metric.label_en }),
    el("p", { class: "muted", text: payload.metric["definition_" + getLang()] || payload.metric.definition_en }),
    el("p", { class: "muted small", text: t("denominator") + ": " +
      payload.denominator.count + " " + t("denominator_units") })
  ]);
}

/* ---------------------------------------------------------------- landing */
export async function landing(root) {
  const m = await L.loadManifest();
  const d = await L.loadGlobal("landing.json");
  const wrap = el("section", { class: "view" });
  wrap.appendChild(el("h2", { text: t("families") + " (" + d.family_count + ")" }));
  // A global one-liner, so the varying scope is visible before any family is opened.
  wrap.appendChild(el("p", { class: "muted small", text: t("validation_global") }));
  const fvs = await L.loadOverlay("global/family_validation_status.json");
  const badgeOf = fid => (fvs && fvs.per_family_badge ? fvs.per_family_badge[fid] : null);
  const grid = el("div", { class: "cards" });
  for (const f of d.families) {
    const card = el("a", { class: "card", href: "#family=" + f.family_slug + "&view=overview",
      "aria-label": f.family_name }, [
      el("h3", { text: f.family_name }),
      el("div", { class: "muted small", text: f.major_family_id }),
      el("dl", { class: "kv" }, [
        el("dt", { text: t("structures") }), el("dd", { text: String(f.structure_count) }),
        el("dt", { text: t("receptors") }), el("dd", { text: String(f.receptor_count) }),
        el("dt", { text: t("units") }), el("dd", { text: String(f.analysis_unit_count) }),
        el("dt", { text: t("coverage") }), el("dd", { text: pct(f.generic_mapping_coverage) }),
        el("dt", { text: t("review_items") }), el("dd", { text: String(f.human_review_required) })
      ]),
      el("div", { class: "sitechips" }, Object.keys(f.site_class_counts || {}).sort().map(k =>
        el("span", { class: "chip", text: siteClassLabel(k) + " " + f.site_class_counts[k] }))),
      RG.validationBadge(badgeOf(f.major_family_id) ? {
        badge: badgeOf(f.major_family_id).badge,
        global_statement_en: fvs.global_statement_en,
        global_statement_tr: fvs.global_statement_tr } : null),
      warnBadges(f.warnings)
    ]);
    grid.appendChild(card);
  }
  wrap.appendChild(grid);
  return wrap;
}

/* ---------------------------------------------------------------- overview */
export async function overview(root, slug) {
  const s = await L.loadFamilyFile(slug, "summary.json");
  const cov = await L.loadFamilyFile(slug, "coverage.json");
  const wrap = el("section", { class: "view" });
  wrap.appendChild(el("h2", { text: s.family_name }));
  const kv = el("dl", { class: "kv wide" });
  const rows = [
    [t("structures"), s.structure_count], [t("receptors"), s.receptor_count],
    [t("species"), s.species_count], [t("units"), s.analysis_unit_count],
    ["Apo", s.apo_count],
    [t("observations") + " (coordinate-observed)", s.coordinate_observed_ligand_observations],
    ["annotated_not_observed", s.annotated_not_observed_observations],
    [t("review_items"), s.human_review_required]
  ];
  for (const [k, v] of rows) { kv.appendChild(el("dt", { text: k })); kv.appendChild(el("dd", { text: String(v) })); }
  wrap.appendChild(kv);
  if (s.unresolved_site_class_observations)
    wrap.appendChild(el("p", { class: "notice", text: t("unresolved_site") + " — " +
      s.unresolved_site_class_observations }));
  wrap.appendChild(el("h3", { text: t("coverage") }));
  const ct = el("table", { class: "data" }, [el("tbody", {},
    Object.keys(cov.dimensions).map(k => el("tr", {}, [
      el("th", { scope: "row", text: k }), el("td", { text: pct(cov.dimensions[k]) })])))]);
  wrap.appendChild(ct);
  const wb = warnBadges(cov.warnings);
  if (wb) {
    wrap.appendChild(el("p", { class: "notice", text: t("warn_lown", {
      units: s.analysis_unit_count, receptors: s.receptor_count }) }));
    wrap.appendChild(wb);
  }
  // Validation scope, at the granularity it actually varies: site class and ligand form.
  const val = await RG.validationFor(slug);
  if (val && val.rows && val.rows.length) {
    wrap.appendChild(el("h3", { text: t("validation_table") }));
    wrap.appendChild(el("p", { class: "muted small", text: val["global_statement_" + getLang()] ||
      val.global_statement_en }));
    const vt = el("table", { class: "data" });
    vt.appendChild(el("thead", {}, el("tr", {}, [t("v_site_class"), t("v_ligand_form"),
      t("units"), t("v_ref_status"), t("v_ref_count"), t("v_human"), t("v_limitation")]
      .map(h => el("th", { text: h })))));
    const vtb = el("tbody");
    for (const r of val.rows) {
      vtb.appendChild(el("tr", {}, [
        el("th", { scope: "row", text: r.site_class ? siteClassLabel(r.site_class) : "—" }),
        el("td", { text: r.ligand_entity_form || "—" }),
        el("td", { class: "num", text: String(r.aggregation_units) }),
        el("td", { text: r.reference_test_status }),
        el("td", { class: "num", text: String(r.reference_structure_count) }),
        el("td", { text: r.independent_human_validation_status }),
        el("td", { class: "small", text: r.limitations })
      ]));
      vtb.appendChild(el("tr", { class: "statement" }, [
        el("td", { colspan: "7", class: "small muted",
          text: r["statement_" + getLang()] || r.statement_en })]));
    }
    vt.appendChild(vtb);
    wrap.appendChild(el("div", { class: "tablewrap" }, vt));
  }
  // Review gate for this family, at family level.
  const gate = await RG.gateFor(slug);
  if (gate) {
    const g = el("section", { class: "review-gate" });
    g.appendChild(el("h3", { text: t("rg_heading") }));
    g.appendChild(el("p", { class: "small", text: gate["explanation_" + getLang()] ||
      gate.explanation_en }));
    g.appendChild(el("p", { class: "muted small", text: gate["coverage_warning_" + getLang()] ||
      gate.coverage_warning_en }));
    wrap.appendChild(g);
  }
  return wrap;
}

/* ---------------------------------------------------------------- structures */
export async function structures(root, slug, onOpen3D) {
  const d = await L.loadFamilyFile(slug, "structures.json");
  const st = ST.get();
  const wrap = el("section", { class: "view" });
  wrap.appendChild(el("h2", { text: t("nav_structures") + " (" + d.count + ")" }));
  const controls = el("div", { class: "controls" });
  const mk = (key, label, values) => {
    const s = el("select", { "aria-label": label, onchange: e => { ST.set({ [key]: e.target.value, page: 0 }); render(); } });
    s.appendChild(el("option", { value: "", text: label + " —" }));
    for (const v of values) s.appendChild(el("option", { value: v, text: v, selected: ST.get()[key] === v }));
    return s;
  };
  const uniq = f => Array.from(new Set(d.structures.map(f).filter(Boolean))).sort();
  const search = el("input", { type: "search", placeholder: "PDB / " + t("receptors") + " / " + t("ligand"),
    "aria-label": "search", value: st.search,
    oninput: debounce(e => { ST.set({ search: e.target.value, page: 0 }); render(); }, 200) });
  controls.appendChild(search);
  controls.appendChild(mk("receptorFilter", t("receptors"), uniq(x => x.receptor_name)));
  controls.appendChild(mk("speciesFilter", t("species"), uniq(x => x.species)));
  controls.appendChild(mk("methodFilter", t("method"), uniq(x => x.experimental_method)));
  controls.appendChild(mk("stateFilter", t("state"), uniq(x => x.structural_state)));
  wrap.appendChild(controls);
  const body = el("div");
  wrap.appendChild(body);

  function filtered() {
    const s = ST.get(); const q = (s.search || "").toLowerCase();
    return d.structures.filter(x =>
      (!s.receptorFilter || x.receptor_name === s.receptorFilter) &&
      (!s.speciesFilter || x.species === s.speciesFilter) &&
      (!s.methodFilter || x.experimental_method === s.methodFilter) &&
      (!s.stateFilter || x.structural_state === s.stateFilter) &&
      (!q || x.pdb_id.toLowerCase().includes(q) ||
        (x.receptor_name || "").toLowerCase().includes(q) ||
        x.observations.some(o => (o.ligand_name || "").toLowerCase().includes(q))));
  }
  function render() {
    clear(body);
    const rows = filtered();
    const pg = paginate(rows, ST.get().page, ST.get().pageSize);
    body.appendChild(el("p", { class: "muted small",
      text: rows.length + " " + t("structures") + " · " + (pg.page + 1) + "/" + pg.pages }));
    const tbl = el("table", { class: "data" });
    tbl.appendChild(el("thead", {}, el("tr", {}, ["PDB", t("receptors"), t("species"), t("method"),
      t("resolution"), t("state"), "Apo", t("observations"), t("nav_evidence"), ""].map(h => el("th", { text: h })))));
    const tb = el("tbody");
    for (const x of pg.rows) {
      const obsCell = el("ul", { class: "obs" }, x.observations.map(o => el("li", {}, [
        el("span", { class: "chip", text: o.ligand_name || (o.ligand_components || []).join("+") || "—" }),
        el("span", { class: "muted small", text: " " + o.ligand_role + " · " + o.entity_form + " · " +
          siteClassLabel(o.binding_site_class) + " · " + o.coordinate_status }),
        o.binding_site_class === "unresolved" ? el("span", { class: "badge warn", text: t("unresolved_site") }) : null,
        o.coordinate_status === "annotated_not_observed" ? el("span", { class: "badge warn", text: t("ano_msg") }) : null
      ])));
      tb.appendChild(el("tr", {}, [
        el("td", {}, el("a", { href: "https://www.rcsb.org/structure/" + x.pdb_id,
          target: "_blank", rel: "noopener", text: x.pdb_id })),
        el("td", { text: x.receptor_name || "—" }), el("td", { text: x.species }),
        el("td", { text: x.experimental_method || "—" }), el("td", { text: fmt(x.resolution, 2) }),
        el("td", { text: stateLabel(x.structural_state || "unknown") }),
        el("td", { text: x.apo_status }),
        el("td", {}, obsCell),
        el("td", { text: String(x.human_review_required) }),
        el("td", {}, el("button", { class: "btn", text: t("viewer"),
          onclick: () => onOpen3D(x.pdb_id, (x.observations[0] || {}).observation_id) }))
      ]));
    }
    tbl.appendChild(tb);
    body.appendChild(tbl);
    const nav = el("div", { class: "pager" }, [
      el("button", { class: "btn", text: "‹", disabled: pg.page === 0,
        onclick: () => { ST.set({ page: pg.page - 1 }); render(); } }),
      el("button", { class: "btn", text: "›", disabled: pg.page >= pg.pages - 1,
        onclick: () => { ST.set({ page: pg.page + 1 }); render(); } }),
      el("button", { class: "btn", text: t("export_csv") + " — " + t("export_structures"),
        onclick: () => exportStructures(rows, slug) }),
      el("button", { class: "btn", text: t("export_csv") + " — " + t("export_observations"),
        onclick: () => exportObservations(rows, slug) })
    ]);
    body.appendChild(nav);
  }
  render();
  return wrap;
}

function meta(slug, extra) {
  const m = L.getManifest();
  return Object.assign({ atlas_version: m.version, data_version: m.data_version,
    family: slug, export_date: new Date().toISOString(),
    source_data_hash: m.phase4_manifest_hash }, extra || {});
}
function exportStructures(rows, slug) {
  const cols = [{ key: "pdb_id" }, { key: "receptor_name" }, { key: "receptor_entry_name" },
    { key: "species" }, { key: "experimental_method" }, { key: "resolution" },
    { key: "release_date" }, { key: "structural_state" }, { key: "apo_status" },
    { key: "ligand_status" }, { key: "construct_engineering_status" },
    { key: "metadata_completeness" }, { key: "generic_mapping_status" },
    { key: "assembly_review_status" }, { key: "observation_count" },
    { key: "human_review_required" }];
  download("structures_" + slug + ".csv", toCSV(cols, rows, meta(slug, { table: "structures", rows: rows.length })));
}
function exportObservations(rows, slug) {
  const flat = [];
  for (const s of rows) for (const o of s.observations)
    flat.push(Object.assign({ pdb_id: s.pdb_id, receptor_name: s.receptor_name,
      species: s.species, structural_state: s.structural_state }, o));
  const cols = [{ key: "pdb_id" }, { key: "receptor_name" }, { key: "species" },
    { key: "structural_state" }, { key: "observation_id" }, { key: "ligand_name" },
    { key: "ligand_components" }, { key: "ligand_role" }, { key: "entity_form" },
    { key: "biological_type" }, { key: "binding_mode" }, { key: "binding_site_class" },
    { key: "coordinate_status" }, { key: "production_status" },
    { key: "generic_contact_eligibility" }, { key: "receptor_residues_5A" },
    { key: "receptor_residues_4_5A" }, { key: "receptor_residues_4A" },
    { key: "ligand_residue_contacts" }, { key: "manual_review_status" }];
  download("observations_" + slug + ".csv", toCSV(cols, flat, meta(slug, { table: "observations", rows: flat.length })));
}

/* ---------------------------------------------------------------- contacts / interfaces */
export async function contacts(root, slug, siteClass, polymer) {
  const fm = await L.loadFamilyManifest(slug);
  const dir = polymer ? "interfaces/" : "contacts/";
  const avail = fm.files.filter(f => f.name.startsWith(dir) && !f.name.includes(".by_receptor"))
    .map(f => f.name.slice(dir.length, -5));
  const wrap = el("section", { class: "view" });
  wrap.appendChild(el("h2", { text: polymer ? t("nav_interfaces") : t("nav_contacts") }));
  if (!avail.length) { wrap.appendChild(el("p", { class: "notice", text: t("no_data") })); return wrap; }
  const site = avail.indexOf(siteClass) >= 0 ? siteClass :
    (avail.indexOf("canonical_7tm_pocket") >= 0 ? "canonical_7tm_pocket" : avail[0]);
  const bar = el("div", { class: "controls" });
  const ssel = el("select", { "aria-label": t("site_class"),
    onchange: e => navigate(Object.assign(currentRoute(), { site: e.target.value })) });
  for (const a of avail) ssel.appendChild(el("option", { value: a, text: siteClassLabel(a), selected: a === site }));
  bar.appendChild(el("label", { text: t("site_class") }));
  bar.appendChild(ssel);
  const d = await L.loadFamilyFile(slug, dir + site + ".json");
  // Public-beta default: the review-gated overlay. The original Phase 4 values stay reachable
  // through a labelled panel below, never as the default and never in the ranking.
  const gate = await RG.gateFor(slug);
  const val = await RG.validationFor(slug);
  const betaPos = RG.betaPositions(gate, site);
  const betaBy = {};
  if (betaPos) for (const p of betaPos) betaBy[p.generic_position] = p;
  const thsel = el("select", { "aria-label": t("threshold"), onchange: e => { ST.set({ threshold: e.target.value }); draw(); } });
  for (const th of ["4.0A", "4.5A", "5.0A"]) thsel.appendChild(el("option", { value: th, text: th, selected: ST.get().threshold === th }));
  bar.appendChild(el("label", { text: t("threshold") })); bar.appendChild(thsel);
  const wsel = el("select", { "aria-label": t("weighting"), onchange: e => { ST.set({ weighting: e.target.value }); draw(); } });
  for (const w of ["unit_weighted_continuous", "unit_weighted_any_contact", "structure_weighted_binary",
                   "receptor_weighted", "ligand_weighted"])
    wsel.appendChild(el("option", { value: w, text: w, selected: ST.get().weighting === w }));
  bar.appendChild(el("label", { text: t("weighting") })); bar.appendChild(wsel);
  wrap.appendChild(bar);
  wrap.appendChild(metricHead(d));
  if (betaPos) wrap.appendChild(el("p", { class: "muted small", text: t("rg_default_note") }));
  const vb = RG.validationBadge(val, { href: "#family=" + slug + "&view=overview" });
  if (vb) wrap.appendChild(el("p", { class: "small" }, [
    el("span", { class: "muted", text: t("validation_scope") + ": " }), vb]));
  const vn = RG.validationNotice(val, site);
  if (vn) wrap.appendChild(vn);
  if (polymer) wrap.appendChild(RG.interfaceShellWarning());
  const gp = RG.gatePanel(gate, site);
  if (gp) wrap.appendChild(gp);
  if (polymer) wrap.appendChild(el("p", { class: "muted small", text: t("interface_terms") + " — " +
    t("receptor_interface_residue") + " / " + t("ligand_polymer_residue") + " / " + t("residue_pair") }));
  const wb = warnBadges(d.warnings); if (wb) wrap.appendChild(wb);
  const body = el("div"); wrap.appendChild(body);

  function valueFor(p) {
    const w = ST.get().weighting, th = ST.get().threshold;
    // The beta overlay precomputes every threshold x weighting combination, including the
    // receptor- and ligand-weighted schemes the Phase 4 payload could not express.
    const b = betaBy[p.generic_position];
    if (b) {
      if (b.status !== "estimable") return null;
      return RG.betaValue(b, w, th);
    }
    if (betaPos) return null;   // gated away: NA, never 0
    if (w === "unit_weighted_continuous")
      return th === "4.0A" ? p.unit_weighted_contact_fraction_4A :
             th === "4.5A" ? p.unit_weighted_contact_fraction_4_5A : p.unit_weighted_contact_fraction_5A;
    if (w === "unit_weighted_any_contact") return p.unit_weighted_any_contact;
    if (w === "structure_weighted_binary") return p.structure_weighted_binary;
    return p.unit_weighted_contact_fraction_5A;   // receptor/ligand weighted: see sensitivity table
  }
  function draw() {
    clear(body);
    if (!d.estimable || d.denominator.count === 0) {
      body.appendChild(el("p", { class: "notice", text: t("not_estimable") })); return; }
    const rows = d.positions.slice().sort((a, b) => (valueFor(b) || 0) - (valueFor(a) || 0));
    const pg = paginate(rows, ST.get().page, 40);
    const tbl = el("table", { class: "data" });
    tbl.appendChild(el("thead", {}, el("tr", {}, [t("generic_position"), t("metric_label"),
      "4.0 Å", "4.5 Å", "5.0 Å", t("units"), "any", "median d (Å)"].map(h => el("th", { text: h })))));
    const tb = el("tbody");
    for (const p of pg.rows) {
      const v = valueFor(p);
      tb.appendChild(el("tr", {}, [
        el("th", { scope: "row", text: p.generic_position }),
        el("td", { class: "num", text: v === null || v === undefined ? t("not_estimable") : fmt(v) }),
        el("td", { class: "num", text: fmt(p.unit_weighted_contact_fraction_4A) }),
        el("td", { class: "num", text: fmt(p.unit_weighted_contact_fraction_4_5A) }),
        el("td", { class: "num", text: fmt(p.unit_weighted_contact_fraction_5A) }),
        el("td", { class: "num", text: String(p.units) }),
        el("td", { class: "num", text: String(p.units_with_any_contact) }),
        el("td", { class: "num", text: fmt(p.median_min_distance, 2) })
      ]));
    }
    tbl.appendChild(tb); body.appendChild(tbl);
    body.appendChild(el("div", { class: "pager" }, [
      el("button", { class: "btn", text: "‹", disabled: pg.page === 0,
        onclick: () => { ST.set({ page: pg.page - 1 }); draw(); } }),
      el("button", { class: "btn", text: "›", disabled: pg.page >= pg.pages - 1,
        onclick: () => { ST.set({ page: pg.page + 1 }); draw(); } }),
      el("button", { class: "btn", text: t("export_csv") + " — " + t("export_contacts"),
        onclick: () => {
          const cols = [{ key: "generic_position" }, { key: "units" }, { key: "units_with_any_contact" },
            { key: "unit_weighted_contact_fraction_4A" }, { key: "unit_weighted_contact_fraction_4_5A" },
            { key: "unit_weighted_contact_fraction_5A" }, { key: "unit_weighted_any_contact" },
            { key: "structure_weighted_binary" }, { key: "median_min_distance" }];
          download((polymer ? "interface_" : "contacts_") + slug + "_" + site + ".csv",
            toCSV(cols, rows, meta(slug, { table: polymer ? "polymer_interface" : "pocket_contacts",
              binding_site_class: site, threshold: ST.get().threshold,
              weighting: ST.get().weighting, denominator_type: d.denominator.type,
              denominator_count: d.denominator.count, rows: rows.length })));
        } })
    ]));
    const op = RG.originalPanel(gate, d.positions);
    if (op) body.appendChild(op);
    body.appendChild(el("details", {}, [el("summary", { text: t("weighting") + " / " + t("threshold") }),
      el("pre", { class: "small", text: JSON.stringify({ weighting: d.weighting_sensitivity,
        threshold: d.threshold_sensitivity }, null, 1) })]));
  }
  draw();
  return wrap;
}
function currentRoute() {
  const h = (location.hash || "").replace(/^#/, ""); const o = {};
  for (const p of h.split("&")) { if (!p) continue; const i = p.indexOf("=");
    o[decodeURIComponent(p.slice(0, i))] = decodeURIComponent(p.slice(i + 1)); }
  return o;
}

/* ---------------------------------------------------------------- motifs */
export async function motifs(root, slug) {
  const d = await L.loadFamilyFile(slug, "motifs.json");
  const wrap = el("section", { class: "view" });
  wrap.appendChild(el("h2", { text: t("nav_motifs") }));
  wrap.appendChild(el("p", { class: "notice", text: t("motif_no_state") }));
  const tbl = el("table", { class: "data" });
  tbl.appendChild(el("thead", {}, el("tr", {}, [t("motif"), t("motif_positions"), t("structures"),
    t("canonical"), t("noncanonical"), "unresolved", "median (Å)", t("coverage")].map(h => el("th", { text: h })))));
  const tb = el("tbody");
  for (const m of d.motifs) tb.appendChild(el("tr", {}, [
    el("th", { scope: "row", text: m.motif_id }),
    el("td", { text: m.generic_positions.join(", ") }),
    el("td", { class: "num", text: String(m.structures) }),
    el("td", { class: "num", text: String(m.canonical_identity) }),
    el("td", { class: "num", text: String(m.noncanonical_identity) }),
    el("td", { class: "num", text: String(m.generic_mapping_unresolved + m.expected_but_unresolved) }),
    el("td", { class: "num", text: fmt(m.median_angstrom, 2) }),
    el("td", { class: "num", text: pct(m.coverage) })
  ]));
  tbl.appendChild(tb); wrap.appendChild(tbl);
  wrap.appendChild(el("p", { class: "muted small", text: t("motif_assoc") }));
  wrap.appendChild(el("h3", { text: t("motif_positions") }));
  const pt = el("table", { class: "data" });
  pt.appendChild(el("thead", {}, el("tr", {}, [t("generic_position"), t("motif"), t("canonical"),
    t("noncanonical"), "Na⁺"].map(h => el("th", { text: h })))));
  const pb = el("tbody");
  for (const p of d.positions) pb.appendChild(el("tr", {}, [
    el("th", { scope: "row", text: p.generic_position }),
    el("td", { text: p.motif_memberships.join(", ") }),
    el("td", { class: "num", text: String(p.canonical) }),
    el("td", { class: "num", text: String(p.noncanonical) }),
    el("td", { class: "small", text: Object.keys(p.sodium_environment).map(k => k + ":" + p.sodium_environment[k]).join(" ") })
  ]));
  pt.appendChild(pb); wrap.appendChild(pt);
  wrap.appendChild(el("button", { class: "btn", text: t("export_csv") + " — " + t("export_motifs"),
    onclick: () => download("motifs_" + slug + ".csv", toCSV(
      [{ key: "motif_id" }, { key: "generic_positions" }, { key: "structures" },
       { key: "canonical_identity" }, { key: "noncanonical_identity" },
       { key: "generic_mapping_unresolved" }, { key: "median_angstrom" }, { key: "coverage" }],
      d.motifs, meta(slug, { table: "core_motifs", rows: d.motifs.length }))) }));
  return wrap;
}

/* ---------------------------------------------------------------- compare */
export async function compare(root) {
  const m = await L.loadManifest();
  const cf = await L.loadGlobal("cross_family_summary.json");
  const wrap = el("section", { class: "view" });
  wrap.appendChild(el("h2", { text: t("nav_compare") }));
  wrap.appendChild(el("p", { class: "muted", text: cf["comparison_rule_" + getLang()] || cf.comparison_rule_en }));
  wrap.appendChild(el("p", { class: "muted small", text: t("validation_global") }));
  const bar = el("div", { class: "controls" });
  const classes = Object.keys(cf.site_class_families).sort();
  const csel = el("select", { "aria-label": t("site_class") });
  for (const c of classes) csel.appendChild(el("option", { value: c, text: siteClassLabel(c) }));
  const fa = el("select", { "aria-label": "A" }), fb = el("select", { "aria-label": "B" });
  bar.appendChild(el("label", { text: t("site_class") })); bar.appendChild(csel);
  bar.appendChild(el("label", { text: "A" })); bar.appendChild(fa);
  bar.appendChild(el("label", { text: "B" })); bar.appendChild(fb);
  wrap.appendChild(bar);
  const out = el("div"); wrap.appendChild(out);
  function fams() {
    const c = csel.value; const list = cf.site_class_families[c] || [];
    for (const s of [fa, fb]) { clear(s);
      for (const f of list) { const fam = (m.families || []).find(x => x.family_id === f);
        s.appendChild(el("option", { value: f, text: fam ? fam.name : f })); } }
  }
  async function draw() {
    clear(out);
    const c = csel.value, A = fa.value, B = fb.value;
    if (!A || !B) { out.appendChild(el("p", { class: "notice", text: t("no_data") })); return; }
    const pos = await L.loadGlobal(cf.by_site_class_url);
    const pick = fid => (pos.by_major_family || []).find(x => x.group_key[0] === fid && x.group_key[1] === c);
    const a = pick(A), b = pick(B);
    if (!a || !b) { out.appendChild(el("p", { class: "notice", text: t("incompatible") })); return; }
    const tbl = el("table", { class: "data" });
    tbl.appendChild(el("thead", {}, el("tr", {}, ["", "A", "B"].map(h => el("th", { text: h })))));
    const tb = el("tbody");
    // A coloured comparison without validation scope invites the reader to treat two families
    // as equally evidenced when one inherited its contact rule untested. The scope travels with
    // the denominator.
    const slugOf = fid => { const f = (m.families || []).find(x => x.family_id === fid);
      return f ? f.slug : null; };
    const [va, vb] = await Promise.all([RG.validationFor(slugOf(A)), RG.validationFor(slugOf(B))]);
    const [ga, gb] = await Promise.all([RG.gateFor(slugOf(A)), RG.gateFor(slugOf(B))]);
    const scopeText = (v, sc) => {
      const r = RG.validationRowsFor(v, sc)[0];
      return r ? (r.transfer_status || "—") : "—";
    };
    const gateDen = (g) => {
      const s = g && g.site_classes ? g.site_classes[c] : null;
      return s ? (s.denominator_after_review_gate + " / " + s.denominator_before_review_gate) : "—";
    };
    const rows = [[t("units"), a.analysis_units, b.analysis_units],
      [t("structures"), a.structures, b.structures],
      [t("receptors"), a.unique_receptors, b.unique_receptors],
      [t("validation_scope"), scopeText(va, c), scopeText(vb, c)],
      [t("rg_denominator_after") + " / " + t("rg_denominator_before"), gateDen(ga), gateDen(gb)],
      [t("denominator"), a.denominator_count + " " + t("denominator_units"),
        b.denominator_count + " " + t("denominator_units")],
      [t("warnings"), (a.warnings || []).map(warnLabel).join(", ") || "—",
        (b.warnings || []).map(warnLabel).join(", ") || "—"]];
    for (const r of rows) tb.appendChild(el("tr", {}, r.map((x, i) =>
      i === 0 ? el("th", { scope: "row", text: String(x) }) : el("td", { text: String(x) }))));
    tbl.appendChild(tb); out.appendChild(tbl);
    const keys = {}; for (const p of a.positions) keys[p.generic_position] = [p, null];
    for (const p of b.positions) (keys[p.generic_position] = keys[p.generic_position] || [null, null])[1] = p;
    const pt = el("table", { class: "data" });
    pt.appendChild(el("thead", {}, el("tr", {}, [t("generic_position"), "A", "B", "Δ"].map(h => el("th", { text: h })))));
    const pb = el("tbody");
    for (const k of Object.keys(keys).sort()) {
      const [x, y] = keys[k];
      const xv = x && x.unit_weighted_contact_fraction_5A, yv = y && y.unit_weighted_contact_fraction_5A;
      pb.appendChild(el("tr", {}, [el("th", { scope: "row", text: k }),
        el("td", { class: "num", text: fmt(xv) }), el("td", { class: "num", text: fmt(yv) }),
        el("td", { class: "num", text: (xv != null && yv != null) ? fmt(xv - yv) : "—" })]));
    }
    pt.appendChild(pb); out.appendChild(pt);
  }
  csel.addEventListener("change", () => { fams(); draw(); });
  fa.addEventListener("change", draw); fb.addEventListener("change", draw);
  fams(); await draw();
  return wrap;
}

/* ---------------------------------------------------------------- evidence */
export async function evidence(root, slug) {
  const d = await L.loadFamilyFile(slug, "reviews.json");
  // Every review item is shown with what it actually does to a pooled metric. Without this the
  // reader cannot tell an item that removed data from one that changed nothing.
  const idx = await RG.globalIndex();
  const effect = {};
  if (idx && idx.items) for (const it of idx.items) effect[it.review_item_id] = it;
  const wrap = el("section", { class: "view" });
  wrap.appendChild(el("h2", { text: d["label_" + getLang()] || d.label_en }));
  wrap.appendChild(el("p", { class: "muted", text: t("adjud_note") }));
  wrap.appendChild(el("p", { class: "muted small",
    text: d.human_review_required + " / " + d.count + " — " + d.unit_of_count }));
  const bar = el("div", { class: "controls" });
  const isel = el("select", { "aria-label": "issue" });
  const issues = Array.from(new Set(d.items.flatMap(i => i.issue_types))).sort();
  isel.appendChild(el("option", { value: "", text: "—" }));
  for (const i of issues) isel.appendChild(el("option", { value: i, text: i }));
  bar.appendChild(isel); wrap.appendChild(bar);
  const body = el("div"); wrap.appendChild(body);
  function draw() {
    clear(body);
    const f = isel.value;
    const rows = d.items.filter(i => !f || i.issue_types.indexOf(f) >= 0);
    const pg = paginate(rows, 0, 60);
    const tbl = el("table", { class: "data" });
    tbl.appendChild(el("thead", {}, el("tr", {}, ["PDB", "issue", t("adjudication"), "confidence",
      t("human_review"), t("rg_effect"), t("rg_scope"), t("source_conflict")]
      .map(h => el("th", { text: h })))));
    const tb = el("tbody");
    for (const i of pg.rows) {
      const e = effect[i.review_item_id];
      tb.appendChild(el("tr", {}, [
        el("td", { text: i.pdb_id }), el("td", { class: "small", text: i.issue_types.join(", ") }),
        el("td", { class: "small", text: i.evidence_adjudication || "—" }),
        el("td", { text: i.adjudication_confidence || "—" }),
        el("td", { text: t("human_not_started") }),
        el("td", { class: "small " + (e ? "eff-" + e.aggregation_effect : ""),
          text: e ? e.aggregation_effect : "no_effect" }),
        el("td", { class: "small", title: e ? e.effect_reason : "",
          text: e ? e.affected_scope : "no_current_aggregate_effect" }),
        el("td", { text: i.source_conflict ? "✔" : "" })
      ]));
      if (e && e.aggregation_effect === "exclude_from_public_beta_pooled_analysis") {
        tb.appendChild(el("tr", { class: "statement" }, [
          el("td", { colspan: "8", class: "small muted",
            text: t("rg_reason") + ": " + e.effect_reason })]));
      }
    }
    tbl.appendChild(tb); body.appendChild(tbl);
    body.appendChild(el("p", { class: "muted small", text: rows.length + " / " + d.count }));
    body.appendChild(el("button", { class: "btn", text: t("export_csv") + " — " + t("export_reviews"),
      onclick: () => download("reviews_" + slug + ".csv", toCSV(
        [{ key: "review_item_id" }, { key: "pdb_id" }, { key: "issue_types" },
         { key: "automated_proposal" }, { key: "evidence_adjudication" },
         { key: "adjudication_basis" }, { key: "adjudication_confidence" },
         { key: "human_curator_decision" }, { key: "human_review_status" },
         { key: "human_review_requirement" }, { key: "source_conflict" }],
        rows, meta(slug, { table: "review_items", rows: rows.length }))) }));
  }
  isel.addEventListener("change", draw); draw();
  return wrap;
}

/* ---------------------------------------------------------------- static pages */
export async function methods() {
  const wrap = el("section", { class: "view prose" });
  wrap.appendChild(el("h2", { text: t("nav_methods") }));
  const items = [
    ["Class A universe", "1,358 deposited structures across 11 GPCRdb major families, taken from the frozen Phase 1 universe. No filter on species, method or resolution."],
    ["Taxonomy", "Read at build time from the GPCRdb Class A tree; the family list is never hard-coded."],
    ["Structure and entity normalization", "Structure-anchored records with a complete entity inventory; water is summarised, never inventoried per molecule."],
    ["Ligand entity model", "A ligand may be a non-polymer component, a whole polymer chain, a polymer segment, a receptor segment or a covalent adduct. A ligand is pharmacological only when a per-structure source annotation says so."],
    ["Apo assignment", "Apo is never inferred from the absence of non-polymer components; it requires positive source evidence."],
    ["Receptor and generic mapping", "auth_seq_id → label_seq_id → UniProt position → GPCRdb generic number, with three candidate routes scored against observed residue identity and an 0.80 agreement floor."],
    ["Contact definition", "Exact minimum heavy-atom distance between receptor and ligand, hydrogens excluded, deterministic altloc policy."],
    ["Thresholds", "4.0, 4.5 and 5.0 Å are derived from the exact distance; nothing is rounded at generation time."],
    ["Site-class separation", "Small-molecule pockets and polymer interfaces are different analysis objects and never share a denominator."],
    ["Polymer interface model", "Residue-pair contacts with ligand residue identity preserved; the ligand is never reduced to a bag of atoms."],
    ["Motif extraction", "Eight core motifs defined by 21 generic positions; residue identity is measured, not assumed."],
    ["Structural-state normalization", "State comes from the source annotation only; it is never derived from motif geometry."],
    ["Aggregation unit", "receptor accession × species × normalized ligand identity × ligand form × binding-site class × structural state."],
    ["Weighting", "Unit-weighted continuous contact fraction is the default; four alternatives are tabulated."],
    ["Denominators", "Every record declares its denominator; a zero denominator yields NA, never 0%."],
    ["Mutation sensitivity", "Cohorts are provided; a structure carrying mutations is never excluded wholesale."],
    ["Coverage warnings", "Seven coverage dimensions and ten machine-readable warning types from the Phase 4 freeze."],
    ["Evidence adjudication versus human curation", "Adjudication was performed from sources by the pipeline. It is not human curation, and no accuracy figure is reported."],
    ["Public-beta review gate", "Pooled public-beta summaries are review-gated: an observation or structure slot is excluded where an unresolved review item can change receptor identity, ligand identity, site classification, coordinate context or aggregation eligibility. Metadata-only items stay visible and remove nothing. Most open items change no pooled metric, and the gate is applied per item rather than per structure."],
    ["Contact-rule validation scope", "Validation of the 5 Å rule varies by family and site class, and the per-family matrix is shown in each family overview. The rule was reference-tested on aminergic small-molecule pockets; other families inherited it without a family-specific reference test; polymer interfaces use it as a descriptive interface shell rather than a validated biological threshold; and for covalent sites the bond is evidenced by deposited connectivity while the surrounding shell is not reference-tested."],
    ["Limitations", "189 evidence items still require human review; 103 binding-site classes and 26 receptor-instance mappings remain unresolved and are excluded from pooled aggregation. No accuracy figure exists for the automated adjudication, and none can be computed until human decisions exist."]
  ];
  for (const [h, b] of items) { wrap.appendChild(el("h3", { text: h })); wrap.appendChild(el("p", { text: b })); }
  const idx = await RG.globalIndex();
  if (idx) {
    wrap.appendChild(el("h3", { text: t("rg_heading") }));
    wrap.appendChild(el("p", { text: idx["explanation_" + getLang()] || idx.explanation_en }));
    wrap.appendChild(el("p", { class: "muted small",
      text: idx["policy_wording_" + getLang()] || idx.policy_wording_en }));
    const c = idx.counts || {}, e = idx.effect_counts_open_items || {};
    const tbl = el("table", { class: "data" });
    const tb = el("tbody");
    for (const [k, v] of [
      [t("review_items"), c.human_review_required_items],
      ["exclude_from_public_beta_pooled_analysis", e.exclude_from_public_beta_pooled_analysis || 0],
      ["already_excluded", e.already_excluded || 0],
      ["warning_only", e.warning_only || 0],
      ["no_effect", e.no_effect || 0],
      [t("rg_removed_units"), c.units_removed],
      [t("rg_modified_units"), c.units_modified]])
      tb.appendChild(el("tr", {}, [el("th", { scope: "row", text: String(k) }),
        el("td", { class: "num", text: String(v) })]));
    tbl.appendChild(tb); wrap.appendChild(tbl);
  }
  const fvs = await L.loadOverlay("global/family_validation_status.json");
  if (fvs) {
    wrap.appendChild(el("h3", { text: t("validation_table") }));
    wrap.appendChild(el("p", { text: fvs["global_statement_" + getLang()] || fvs.global_statement_en }));
    const ae = fvs.aminergic_reference_evidence || {};
    wrap.appendChild(el("p", { class: "muted small", text:
      "Aminergic reference evidence: " + ae.independent_reference_structures +
      " independent reference structures; crosswalk over " + ae.crosswalk_observations +
      " observations with " + ae.crosswalk_discrepancies + " discrepancies. " + (ae.note || "") }));
    const vt = el("table", { class: "data" });
    vt.appendChild(el("thead", {}, el("tr", {}, [t("families"), t("v_site_class"),
      t("v_ligand_form"), t("v_rule")].map(h => el("th", { text: h })))));
    const vb = el("tbody");
    for (const r of fvs.rows) vb.appendChild(el("tr", {}, [
      el("th", { scope: "row", text: r.family_name }),
      el("td", { text: r.site_class ? siteClassLabel(r.site_class) : "—" }),
      el("td", { text: r.ligand_entity_form || "—" }),
      el("td", { class: "small", text: r.transfer_status })]));
    vt.appendChild(vb);
    wrap.appendChild(el("div", { class: "tablewrap" }, vt));
  }
  return wrap;
}
export async function sources() {
  const d = await L.loadGlobal("sources.json");
  const wrap = el("section", { class: "view prose" });
  wrap.appendChild(el("h2", { text: t("nav_sources") }));
  const tbl = el("table", { class: "data" });
  tbl.appendChild(el("thead", {}, el("tr", {}, ["Source", "Licence", "Verification"].map(h => el("th", { text: h })))));
  const tb = el("tbody");
  for (const s of d.licences || []) tb.appendChild(el("tr", {}, [
    el("th", { scope: "row", text: s.provider }),
    el("td", { text: typeof s.licence === "string" ? s.licence : JSON.stringify(s.licence) }),
    el("td", { class: "small", text: s.verification_method })]));
  tbl.appendChild(tb); wrap.appendChild(tbl);
  wrap.appendChild(el("h3", { text: "Release gates" }));
  wrap.appendChild(el("ul", {}, (d.release_gates || []).map(g =>
    el("li", { text: g.gate + " — " + g.status + ": " + g.note }))));
  return wrap;
}
export async function references(root, slug) {
  const g = await L.loadGlobal("references.json");
  const wrap = el("section", { class: "view prose" });
  wrap.appendChild(el("h2", { text: t("nav_references") }));
  wrap.appendChild(el("ul", {}, (g.databases || []).map(db => el("li", {}, [
    el("a", { href: db.url, target: "_blank", rel: "noopener", text: db.name }),
    el("span", { class: "muted small", text: " — " + db.licence })]))));
  if (slug) {
    const r = await L.loadFamilyFile(slug, "references.json");
    wrap.appendChild(el("h3", { text: "PDB" }));
    const ul = el("ul", { class: "cols" });
    for (const s of (r.structure_sources || []).slice(0, 400)) ul.appendChild(el("li", {}, [
      el("a", { href: s.rcsb_entry, target: "_blank", rel: "noopener", text: s.pdb_id }),
      el("span", { class: "muted small", text: " · " }),
      el("a", { href: s.pdb_doi, target: "_blank", rel: "noopener", text: "DOI" }),
      el("span", { class: "muted small", text: " · " }),
      el("a", { href: s.gpcrdb_structure, target: "_blank", rel: "noopener", text: "GPCRdb" })]));
    wrap.appendChild(ul);
  }
  return wrap;
}
export async function cite(root, pdb) {
  const g = await L.loadGlobal("references.json");
  const rm = await L.loadGlobal("release_metadata.json");
  const m = L.getManifest();
  const wrap = el("section", { class: "view prose" });
  wrap.appendChild(el("h2", { text: t("nav_cite") }));
  wrap.appendChild(el("h3", { text: t("cite_atlas") }));
  wrap.appendChild(el("pre", { text: "Class A GPCR Atlas, version " + m.version +
    " (pre-release). Data freeze " + m.data_version + ". " + t("no_doi") }));
  wrap.appendChild(el("p", { class: "notice", text: rm["code_licence_note_" + getLang()] || rm.code_licence_note_en }));
  wrap.appendChild(el("h3", { text: t("cite_structure") }));
  wrap.appendChild(el("pre", { text: pdb ? ("PDB " + pdb + " — https://doi.org/10.2210/pdb" + pdb + "/pdb")
    : g.pdb_doi_pattern }));
  wrap.appendChild(el("h3", { text: t("cite_db") }));
  wrap.appendChild(el("ul", {}, (g.databases || []).map(db =>
    el("li", { text: db.name + " — " + db.licence }))));
  return wrap;
}
