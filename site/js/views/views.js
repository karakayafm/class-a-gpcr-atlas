// All views. Each returns a DOM node; none recomputes science — every number is read from a
// Phase 4-derived payload field.
import { t, siteClassLabel, siteClassDefinition, stateLabel, warnLabel, getLang } from "../core/i18n.js";
import { el, clear, fmt, pct, paginate, debounce } from "../components/dom.js";
import { toCSV, download } from "../components/csv.js";
import * as L from "../data/loader.js";
import * as ST from "../core/state.js";
import { buildHash, navigate } from "../core/router.js";
import * as RG from "./reviewgate.js";

const POLYMER = { extracellular_polymer_interface: 1, tethered_ligand_interface: 1 };

export function plainName(value) {
  const node = document.createElement("span");
  node.innerHTML = String(value || "").replace(/<sub>(.*?)<\/sub>/gi, "$1");
  return (node.textContent || "").replace(/\s+/g, " ").trim();
}
function familyDisplayName(value) {
  const clean = plainName(value);
  if (getLang() !== "tr") return clean;
  return ({ "Aminergic receptors": "Aminergik reseptörler", "Peptide receptors": "Peptit reseptörleri",
    "Lipid receptors": "Lipit reseptörleri", "Orphan receptors": "Yetim reseptörler",
    "Nucleotide receptors": "Nükleotit reseptörleri", "Protein receptors": "Protein reseptörleri",
    "Sensory receptors": "Duyusal reseptörler", "Melatonin receptors": "Melatonin reseptörleri",
    "Steroid receptors": "Steroid reseptörleri", "Other": "Diğer" })[clean] || clean;
}
export function modeClass(value) {
  const key = String(value || "").toLowerCase();
  return key.includes("partial agonist") ? " mode-partial" : key.includes("inverse agonist") ? " mode-inverse" :
    (key === "pam" || key === "nam" || key.includes("pam") || key.includes("nam")) ? " mode-modulator" :
    key.includes("antagonist") ? " mode-antagonist" : key.includes("agonist") ? " mode-agonist" : "";
}

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

let pinnedSiteHelp = null;
function openRouteInNewTab(state, event) {
  if (!event || event.button !== 1) return;
  event.preventDefault();
  event.stopPropagation();
  window.open(new URL(buildHash(state), window.location.href).href, "_blank", "noopener");
}
function siteClassChip(id, count, familySlug) {
  const tipId = "site-help-" + id + "-" + Math.random().toString(36).slice(2, 8);
  const tip = el("span", { class:"site-help-popover", id:tipId, role:"tooltip", hidden:true,
    text:siteClassDefinition(id) });
  let pinned = false;
  const button = el("button", { class:"site-help-button", type:"button", text:"?",
    "aria-label":siteClassLabel(id) + " — " + t("site_help_aria"),
    "aria-describedby":tipId, "aria-expanded":"false" });
  const filterLink = el("span", { class:"chip site-filter-link", role:"link", tabindex:"0",
    text:siteClassLabel(id) + " " + count });
  const openFiltered = e => { e.preventDefault(); e.stopPropagation();
    navigate({ family:familySlug, view:"structures", site:id }); };
  filterLink.addEventListener("click", openFiltered);
  filterLink.addEventListener("auxclick", e => openRouteInNewTab(
    { family:familySlug, view:"structures", site:id }, e));
  filterLink.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") openFiltered(e);
  });
  const wrap = el("span", { class:"sitechip-wrap" }, [filterLink, button, tip]);
  const show = () => { tip.hidden=false; button.setAttribute("aria-expanded", "true"); };
  const hide = () => { if (!pinned) { tip.hidden=true; button.setAttribute("aria-expanded", "false"); } };
  wrap.addEventListener("mouseenter", show);
  wrap.addEventListener("mouseleave", hide);
  button.addEventListener("focus", show);
  button.addEventListener("blur", hide);
  button.addEventListener("click", e => {
    e.preventDefault(); e.stopPropagation();
    if (pinnedSiteHelp && pinnedSiteHelp.button !== button) pinnedSiteHelp.close();
    pinned = !pinned;
    if (pinned) { show(); pinnedSiteHelp = { button, close:() => {
      pinned=false; tip.hidden=true; button.setAttribute("aria-expanded", "false");
    } }; }
    else { tip.hidden=true; button.setAttribute("aria-expanded", "false"); pinnedSiteHelp=null; }
  });
  return wrap;
}

function metricHelp(text) {
  const tipId = "metric-help-" + Math.random().toString(36).slice(2, 8);
  const tip = el("span", { class:"site-help-popover", id:tipId, role:"tooltip", hidden:true, text });
  let pinned = false;
  const button = el("button", { class:"site-help-button", type:"button", text:"?",
    "aria-label":text, "aria-describedby":tipId, "aria-expanded":"false" });
  const wrap = el("span", { class:"metric-help-wrap" }, [button, tip]);
  const show = () => { tip.hidden=false; button.setAttribute("aria-expanded", "true"); };
  const hide = () => { if (!pinned) { tip.hidden=true; button.setAttribute("aria-expanded", "false"); } };
  wrap.addEventListener("mouseenter", show); wrap.addEventListener("mouseleave", hide);
  button.addEventListener("focus", show); button.addEventListener("blur", hide);
  button.addEventListener("click", e => {
    e.preventDefault(); e.stopPropagation(); pinned = !pinned;
    if (pinned) show(); else { tip.hidden=true; button.setAttribute("aria-expanded", "false"); }
  });
  return wrap;
}

function reviewItemLink(count, familySlug) {
  if (!(Number(count) > 0)) return [];
  const open = e => { e.preventDefault(); e.stopPropagation();
    navigate({ family:familySlug, view:"evidence", open:"1" }); };
  return [
    el("dt", {}, el("span", { class:"review-item-link", role:"link", tabindex:"0",
      text:t("review_items"), onclick:open,
      onauxclick:e => openRouteInNewTab({ family:familySlug, view:"evidence", open:"1" }, e),
      onkeydown:e => {
        if (e.key === "Enter" || e.key === " ") open(e);
      } })),
    el("dd", {}, el("span", { class:"review-item-link", role:"link", tabindex:"0",
      text:String(count), onclick:open,
      onauxclick:e => openRouteInNewTab({ family:familySlug, view:"evidence", open:"1" }, e),
      onkeydown:e => {
        if (e.key === "Enter" || e.key === " ") open(e);
      } }))
  ];
}

/* ---------------------------------------------------------------- landing */
export async function landing(root) {
  const m = await L.loadManifest();
  const d = await L.loadGlobal("landing.json");
  const wrap = el("section", { class: "view" });
  wrap.appendChild(el("h2", { text: t("families") + " (" + d.family_count + ")" }));
  const grid = el("div", { class: "cards" });
  for (const f of d.families) {
    const reviewRows = reviewItemLink(f.human_review_required, f.family_slug);
    const card = el("a", { class: "card", href: "#family=" + f.family_slug + "&view=structures",
      "aria-label": f.family_name, onauxclick:e => {
        if (e.target.closest(".sitechip-wrap,.review-item-link")) return;
        openRouteInNewTab({ family:f.family_slug, view:"structures" }, e);
      } }, [
      el("h3", { text: familyDisplayName(f.family_name) }),
      el("dl", { class: "kv" }, [
        el("dt", {}, [document.createTextNode(t("structure_count") + " "), metricHelp(t("structure_count_help"))]),
        el("dd", { text: String(f.analysis_unit_count) + " / " + String(f.structure_count) }),
        el("dt", { text: t("receptor_family_count") }), el("dd", { text: String(f.receptor_family_count) }),
        el("dt", { text: t("receptor_count") }), el("dd", { text: String(f.receptor_count) }),
        ...reviewRows
      ]),
      el("div", { class: "sitechips" }, Object.keys(f.site_class_counts || {}).sort().map(k =>
        siteClassChip(k, f.site_class_counts[k], f.family_slug)))
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
    ["annotated_not_observed", s.annotated_not_observed_observations]
  ];
  for (const [k, v] of rows) { kv.appendChild(el("dt", { text: k })); kv.appendChild(el("dd", { text: String(v) })); }
  if (s.human_review_required > 0) {
    const open = () => navigate({ family:slug, view:"evidence", open:"1" });
    kv.appendChild(el("dt", {}, el("button", { class:"review-inline-link", type:"button",
      text:t("review_items"), onclick:open })));
    kv.appendChild(el("dd", {}, el("button", { class:"review-inline-link", type:"button",
      text:String(s.human_review_required), onclick:open })));
  }
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
export async function structures(root, slug, onOpen3D, initialSite, initialPdb) {
  const d = await L.loadFamilyFile(slug, "structures.json");
  const wrap = el("section", { class: "view" });
  const family = (L.getManifest().families || []).find(f => f.slug === slug);
  const availableSites = new Set(d.structures.flatMap(x => x.observations.map(o => o.binding_site_class).filter(Boolean)));
  const filters = { family: "", receptor: "", mode: "", state: "",
    site: availableSites.has(initialSite) ? initialSite : "", search: "", sort: "resolution" };
  let selected = d.structures.find(x => x.pdb_id === String(initialPdb || "").toUpperCase()) ||
    d.structures.find(x => x.pdb_id === "9IJE") || d.structures[0];
  let revealInitialSelection = !!initialPdb;
  const uniq = fn => Array.from(new Set(d.structures.flatMap(fn).filter(Boolean))).sort();
  const observed = d.structures.filter(x => x.observations.some(o => o.coordinate_status === "observed"));
  const ligandNames = new Set(observed.flatMap(x => x.observations.map(o => o.ligand_name).filter(Boolean)));
  const receptorNames = new Set(d.structures.map(x => x.receptor_entry_name).filter(Boolean));
  const contactCounts = observed.flatMap(x => x.observations.map(o => o.receptor_residues_5A || 0));
  const median = contactCounts.slice().sort((a,b) => a-b)[Math.floor(contactCounts.length / 2)] || 0;

  wrap.appendChild(el("section", { class: "atlas-intro" }, [
    el("div", {}, [el("h2", { text: familyDisplayName(family ? family.name : slug) })]),
    el("div", { class: "summary-strip" }, [
      summaryMetric(d.count, t("structures")), summaryMetric(receptorNames.size, t("receptors")),
      summaryMetric(ligandNames.size, t("different_ligands")), summaryMetric(median, t("median_contacts"))
    ])
  ]));

  const quick = el("div", { class: "quick-filters", "aria-label": t("ligand_class") });
  const modeCounts = new Map();
  for (const x of d.structures) for (const mode of new Set(x.observations.map(o => o.binding_mode).filter(Boolean)))
    modeCounts.set(mode, (modeCounts.get(mode) || 0) + 1);
  const filterControls = {};
  const quickModes = ["", "Agonist", "Partial agonist", "Antagonist", "Inverse agonist", "PAM", "NAM"];
  for (const mode of quickModes) if (!mode || modeCounts.has(mode)) {
    const b = el("button", { class: "quick-filter" + modeClass(mode) + (!mode ? " active" : ""), "data-mode": mode,
      text: (mode || t("all")) + "  " + (mode ? modeCounts.get(mode) : d.count), onclick: () => {
        filters.mode = mode; if (filterControls.mode) filterControls.mode.value = mode;
        for (const n of quick.querySelectorAll("button")) n.classList.toggle("active", n === b);
        drawList(); drawDetail();
      } });
    quick.appendChild(b);
  }
  wrap.appendChild(quick);

  const layout = el("div", { class: "explorer-layout" });
  const rail = el("aside", { class: "explorer-rail" });
  const detail = el("section", { class: "structure-detail", "aria-live": "polite" });
  layout.appendChild(rail); layout.appendChild(detail); wrap.appendChild(layout);

  const filterGrid = el("div", { class: "filter-grid" });
  function selectFilter(key, label, values, display) {
    const box = el("label", { class: "filter-field" }, [el("span", { text: label })]);
    const s = el("select", { onchange: e => { filters[key] = e.target.value;
      if (key === "mode") for (const n of quick.querySelectorAll("button"))
        n.classList.toggle("active", n.getAttribute("data-mode") === e.target.value);
      drawList(); drawDetail(); } });
    filterControls[key] = s;
    s.appendChild(el("option", { value: "", text: t("all") }));
    for (const value of values) s.appendChild(el("option", { value,
      text: display ? display(value) : plainName(value), selected:filters[key] === value }));
    box.appendChild(s); return box;
  }
  filterGrid.appendChild(selectFilter("family", t("receptor_family"), uniq(x => [x.receptor_family_name])));
  filterGrid.appendChild(selectFilter("receptor", t("receptors"), uniq(x => [x.receptor_name])));
  filterGrid.appendChild(selectFilter("mode", t("ligand_class"), uniq(x => x.observations.map(o => o.binding_mode))));
  filterGrid.appendChild(selectFilter("site", t("site_class"),
    uniq(x => x.observations.map(o => o.binding_site_class)), siteClassLabel));
  filterGrid.appendChild(selectFilter("state", t("state"), uniq(x => [x.structural_state])));
  rail.appendChild(filterGrid);
  rail.appendChild(el("label", { class: "filter-field search-field" }, [
    el("span", { text: t("search") }), el("input", { type: "search", placeholder: t("search_placeholder"),
      oninput: debounce(e => { filters.search = e.target.value; drawList(); drawDetail(); }, 120) })
  ]));
  const listHead = el("div", { class: "result-head" });
  const resultList = el("div", { class: "result-list" });
  rail.appendChild(listHead); rail.appendChild(resultList);
  rail.appendChild(el("div", { class: "rail-actions" }, [
    el("button", { class: "btn", text: t("export_csv"),
      "aria-label": t("export_structures") + " / " + t("export_observations"),
      onclick: () => exportStructures(filtered(), slug) })
  ]));

  function filtered() {
    const q = filters.search.trim().toLowerCase();
    const rows = d.structures.filter(x => !x.superseded_by &&
      (!filters.family || x.receptor_family_name === filters.family) &&
      (!filters.receptor || x.receptor_name === filters.receptor) &&
      (!filters.mode || x.observations.some(o => o.binding_mode === filters.mode)) &&
      (!filters.site || x.observations.some(o => o.binding_site_class === filters.site)) &&
      (!filters.state || x.structural_state === filters.state) &&
      (!q || [x.pdb_id, plainName(x.receptor_name), x.receptor_entry_name,
        ...x.observations.map(o => o.ligand_name || "")].join(" ").toLowerCase().includes(q)));
    return rows.sort((a,b) => (a.resolution == null) - (b.resolution == null) ||
      (a.resolution || 99) - (b.resolution || 99) || a.pdb_id.localeCompare(b.pdb_id));
  }
  function drawList() {
    const rows = filtered(); clear(resultList); clear(listHead);
    if (rows.length && !rows.includes(selected)) selected = rows[0];
    listHead.appendChild(el("strong", { text: rows.length + " " + t("results") }));
    listHead.appendChild(el("span", { class: "muted small", text: t("sorted_resolution") }));
    let selectedItem = null;
    for (const x of rows) {
      const o = observationFor(x);
      const shown = observationsFor(x);
      const ligandText = Array.from(new Set(shown.map(v => plainName(v.ligand_name || t("apo"))))).join(" + ");
      const item = el("button", { class: "result-item" + (selected === x ? " selected" : ""),
        "aria-pressed": selected === x ? "true" : "false", onclick: () => {
          selected = x;
          for (const n of resultList.querySelectorAll(".result-item")) {
            const active = n === item;
            n.classList.toggle("selected", active);
            n.setAttribute("aria-pressed", active ? "true" : "false");
          }
          drawDetail();
        } }, [
        el("div", { class: "result-line" }, [el("strong", { text: x.pdb_id }),
          el("span", { text: plainName(x.receptor_name || "—") }),
          el("small", { text: fmt(x.resolution, 2) + " Å · " + (o.receptor_residues_5A || 0) + " " + t("contacts_short") })]),
        el("div", { class: "result-ligand", text: ligandText }),
        el("div", { class: "result-modes" }, Array.from(new Set(shown.map(v => v.binding_mode).filter(Boolean)))
          .map(mode => el("span", { class: "mode-pill" + modeClass(mode), text: mode })))
      ]);
      if (selected === x) selectedItem = item;
      resultList.appendChild(item);
    }
    if (revealInitialSelection && selectedItem) {
      requestAnimationFrame(() => { resultList.scrollTop = Math.max(0,
        selectedItem.offsetTop - resultList.clientHeight / 2); });
      revealInitialSelection = false;
    }
    if (!rows.length) resultList.appendChild(el("p", { class: "notice", text: t("no_results") }));
  }
  function observationsFor(x) {
    const matched = x.observations.filter(o => (!filters.site || o.binding_site_class === filters.site) &&
      (!filters.mode || o.binding_mode === filters.mode));
    return matched.length ? matched : x.observations;
  }
  function observationFor(x) {
    return observationsFor(x)[0] || {};
  }
  function drawDetail() {
    clear(detail);
    const rows = filtered();
    if (!rows.length) { detail.appendChild(el("p", { class:"notice", text:t("no_results") })); return; }
    if (!rows.includes(selected)) selected = rows[0];
    const x = selected; const o = observationFor(x); const shown = observationsFor(x);
    const ligandText = Array.from(new Set(shown.map(v => plainName(v.ligand_name || t("apo"))))).join(" + ");
    const modes = Array.from(new Set(shown.map(v => v.binding_mode).filter(Boolean)));
    detail.appendChild(el("header", { class: "detail-head" }, [
      el("div", {}, [el("div", { class: "detail-title" }, [el("strong", { text: x.pdb_id }),
        el("span", { text: ligandText })]),
        el("p", { class: "muted", text: plainName(x.receptor_name || "—") + " · " + x.receptor_entry_name })]),
      el("button", { class: "btn btn-primary", text: t("open_binding_site"),
        onclick: () => onOpen3D(x.pdb_id, o.observation_id) })
    ]));
    detail.appendChild(el("div", { class: "detail-tags" }, [
      el("span", { class: "chip", text: plainName(x.receptor_family_name || "—") }),
      el("span", { class: "chip", text: stateLabel(x.structural_state || "unknown") }),
      ...modes.map(mode => el("span", { class: "chip mode-pill" + modeClass(mode), text: mode })),
      el("span", { class: "chip", text: siteClassLabel(o.binding_site_class || "unresolved") })
    ]));
    detail.appendChild(el("div", { class: "detail-facts" }, [
      fact(t("receptors"), plainName(x.receptor_name || "—")), fact(t("resolution"), fmt(x.resolution,2) + " Å"),
      fact(t("method"), x.experimental_method || "—"), fact(t("species"), x.species || "—"),
      fact(t("ligand_class"), modes.join(" + ") || "—"), fact(t("contact_shell"),
        (o.receptor_residues_5A || 0) + " " + t("residues"))
    ]));
    detail.appendChild(el("section", { class: "detail-section" }, [
      el("h3", { text: t("binding_site_summary") }),
      el("p", { text: t("binding_site_explain") }),
      el("div", { class: "contact-levels" }, [
        contactLevel("≤ 4.0 Å", o.receptor_residues_4A || 0),
        contactLevel("≤ 4.5 Å", o.receptor_residues_4_5A || 0),
        contactLevel("≤ 5.0 Å", o.receptor_residues_5A || 0)
      ])
    ]));
    detail.appendChild(el("section", { class: "detail-section sources" }, [
      el("h3", { text: t("source_links") }),
      el("a", { class: "btn", href: "https://www.rcsb.org/structure/" + x.pdb_id,
        target: "_blank", rel: "noopener", text: "RCSB " + x.pdb_id }),
      el("a", { class: "btn", href: "https://gpcrdb.org/structure/" + x.pdb_id,
        target: "_blank", rel: "noopener", text: "GPCRdb " + x.pdb_id })
    ]));
  }
  drawList(); drawDetail();
  return wrap;
}

function summaryMetric(value, label) { return el("div", { class: "summary-metric" }, [
  el("strong", { text: String(value) }), el("span", { text: label }) ]); }
function fact(label, value) { return el("div", { class: "detail-fact" }, [
  el("span", { text: label }), el("strong", { text: String(value) }) ]); }
function contactLevel(label, value) { return el("div", { class: "contact-level" }, [
  el("span", { text: label }), el("strong", { text: String(value) }), el("small", { text: t("residues") }) ]); }

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
    const slugOf = fid => { const f = (m.families || []).find(x => x.family_id === fid);
      return f ? f.slug : null; };
    const [ga, gb] = await Promise.all([RG.gateFor(slugOf(A)), RG.gateFor(slugOf(B))]);
    const gateDen = (g) => {
      const s = g && g.site_classes ? g.site_classes[c] : null;
      return s ? (s.denominator_after_review_gate + " / " + s.denominator_before_review_gate) : "—";
    };
    const rows = [[t("units"), a.analysis_units, b.analysis_units],
      [t("structures"), a.structures, b.structures],
      [t("receptors"), a.unique_receptors, b.unique_receptors],
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
export async function evidence(root, slug, openOnly) {
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
    const rows = d.items.filter(i => (!openOnly || (i.human_review_requirement === "required" &&
      i.human_review_status !== "completed")) && (!f || i.issue_types.indexOf(f) >= 0));
    const pg = paginate(rows, 0, 60);
    const tbl = el("table", { class: "data" });
    tbl.appendChild(el("thead", {}, el("tr", {}, ["PDB", "issue", t("adjudication"), "confidence",
      t("human_review"), t("rg_effect"), t("rg_scope"), t("source_conflict")]
      .map(h => el("th", { text: h })))));
    const tb = el("tbody");
    for (const i of pg.rows) {
      const e = effect[i.review_item_id];
      tb.appendChild(el("tr", {}, [
        el("td", {}, el("a", { class:"pdb-review-link", text:i.pdb_id,
          href:buildHash({ family:slug, view:"3d", pdb:i.pdb_id }),
          title:i.pdb_id + " — 3B" })),
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
