// All views. Each returns a DOM node; none recomputes science — every number is read from a
// Phase 4-derived payload field.
import { t, siteClassLabel, siteClassDefinition, stateLabel, warnLabel, transducerLabel,
  ligandClassLabel, biologicalTypeLabel, methodLabel, getLang } from "../core/i18n.js";
import { el, clear, fmt, pct, paginate, debounce } from "../components/dom.js";
import { toCSV, download } from "../components/csv.js";
import { downloadXLSX } from "../components/xlsx.js";
import * as L from "../data/loader.js";
import * as ST from "../core/state.js";
import { buildHash, navigate, parseRoute } from "../core/router.js";
import * as RG from "./reviewgate.js";
import * as SOURCES from "../components/sources.js";

const POLYMER = { extracellular_polymer_interface: 1, tethered_ligand_interface: 1 };

export function plainName(value) {
  const node = document.createElement("span");
  node.innerHTML = String(value || "").replace(/<sub>(.*?)<\/sub>/gi, "$1");
  return (node.textContent || "").replace(/\s+/g, " ").trim();
}
export function familyDisplayName(value) {
  const clean = plainName(value);
  if (getLang() !== "tr") return clean;
  return ({ "Aminergic receptors": "Aminergik reseptörler", "Peptide receptors": "Peptit reseptörleri",
    "Lipid receptors": "Lipit reseptörleri", "Orphan receptors": "Yetim reseptörler",
    "Nucleotide receptors": "Nükleotit reseptörleri", "Protein receptors": "Protein reseptörleri",
    "Sensory receptors": "Duyusal reseptörler", "Melatonin receptors": "Melatonin reseptörleri",
    "Steroid receptors": "Steroit reseptörleri",
    "Alicarboxylic acid receptors": "Alikarboksilik asit reseptörleri",
    "Other": "Diğer" })[clean] || clean;
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

/* ---------------------------------------------------------------- transducer panels */
export async function panels(initialPanel, open3D) {
  const data = await L.loadPanels();
  const wrap = el("section", { class:"view panel-workspace" });
  wrap.appendChild(el("h2", { text:t("panel_heading") }));
  wrap.appendChild(el("p", { class:"muted", text:t("panel_intro") }));
  const strip = el("div", { class:"panel-strip", role:"tablist", "aria-label":t("panel_heading") });
  const detail = el("section", { class:"panel-detail", "aria-live":"polite" });
  let selected = data.panels.find(p => p.id === initialPanel) || data.panels[0];

  const draw = () => {
    for (const button of strip.querySelectorAll("button")) {
      const on = button.dataset.panel === selected.id;
      button.classList.toggle("active", on);
      button.setAttribute("aria-selected", on ? "true" : "false");
      button.tabIndex = on ? 0 : -1;
    }
    clear(detail);
    detail.appendChild(el("h3", { text:selected.id }));
    const facts = el("div", { class:"panel-facts" }, [
      panelFact(selected.n_structures, t("structures")),
      panelFact(selected.n_units, t("panel_total_units")),
      panelFact(selected.n_prevalence_estimable, t("panel_estimable_units")),
      panelFact(selected.n_not_estimable, t("panel_not_estimable_units"))
    ]);
    detail.appendChild(facts);
    detail.appendChild(el("p", { class:"notice denominator-note", text:t("panel_denominator_note", {
      total:selected.n_units, estimable:selected.n_prevalence_estimable,
      canonical:selected.denominators.all
    }) }));
    const table = el("table", { class:"data panel-sites" });
    table.appendChild(el("thead", {}, el("tr", {}, [
      t("site_class"), t("panel_total_units"), t("panel_estimable_units"),
      t("panel_not_estimable_units"), t("denominator")
    ].map(label => el("th", { scope:"col", text:label })))));
    const body = el("tbody");
    for (const site of selected.site_classes) body.appendChild(el("tr", {}, [
      el("th", { scope:"row", text:siteClassLabel(site.binding_site_class) }),
      el("td", { class:"num", text:String(site.n_units) }),
      el("td", { class:"num", text:String(site.n_prevalence_estimable) }),
      el("td", { class:"num", text:String(site.n_not_estimable) }),
      el("td", { class:"num", text:String(site.denominators.all) })
    ]));
    table.appendChild(body); detail.appendChild(table);
    detail.appendChild(el("p", { class:"muted small", text:t("panel_metric_note") }));

    const explorer = el("section", { class:"panel-pocket-explorer" });
    explorer.appendChild(el("h3", { text:t("panel_pocket_heading") }));
    explorer.appendChild(el("p", { class:"muted", text:t("panel_pocket_intro") }));
    const rows = (data.structure_index || []).filter(row => (row.panels || []).includes(selected.id));
    const families = Array.from(new Map(rows.map(row => [row.family_slug, {
      slug:row.family_slug, name:row.family_name
    }])).values()).sort((a,b) => familyDisplayName(a.name).localeCompare(familyDisplayName(b.name), getLang()));
    const controls = el("div", { class:"panel-pocket-controls" });
    const familySelect = el("select", { "aria-label":t("panel_choose_family") }, [
      el("option", { value:"", text:t("panel_choose_family") }),
      ...families.map(f => el("option", { value:f.slug, text:familyDisplayName(f.name) }))
    ]);
    const structureSelect = el("select", { disabled:true, "aria-label":t("panel_choose_structure") }, [
      el("option", { value:"", text:t("panel_choose_structure") })
    ]);
    const pocket = el("div", { class:"panel-pocket-detail", "aria-live":"polite" });
    const resetPocket = () => {
      clear(pocket);
      pocket.appendChild(el("p", { class:"panel-pocket-prompt muted", text:t("panel_pocket_prompt") }));
    };
    familySelect.addEventListener("change", () => {
      clear(structureSelect);
      structureSelect.appendChild(el("option", { value:"", text:t("panel_choose_structure") }));
      const familyRows = rows.filter(row => row.family_slug === familySelect.value)
        .sort((a,b) => a.pdb_id.localeCompare(b.pdb_id));
      for (const row of familyRows) structureSelect.appendChild(el("option", {
        value:row.pdb_id, text:row.pdb_id + " — " + plainName(row.receptor_name)
      }));
      structureSelect.disabled = !familySelect.value;
      resetPocket();
    });
    structureSelect.addEventListener("change", async () => {
      resetPocket();
      if (!structureSelect.value) return;
      clear(pocket); pocket.appendChild(el("p", { class:"muted", text:t("loading") }));
      try {
        const payload = await L.loadPocketDetail(familySelect.value);
        const record = (payload.structures || []).find(s => s.pdb_id === structureSelect.value);
        clear(pocket);
        if (!record) {
          pocket.appendChild(el("p", { class:"notice", text:t("panel_pocket_missing") })); return;
        }
        pocket.appendChild(el("div", { class:"panel-pocket-summary" }, [
          panelFact(record.n_contacts, t("contacts_short")),
          panelFact(record.n_mapped, t("panel_mapped_contacts")),
          panelFact(record.pharmacological_ligand_count, t("panel_ligand_count"))
        ]));
        if (record.empty_reason) {
          pocket.appendChild(el("div", { class:"panel-empty-state " + record.empty_reason }, [
            el("strong", { text:t("panel_empty_" + record.empty_reason + "_title") }),
            el("span", { text:t("panel_empty_" + record.empty_reason + "_body") })
          ]));
          return;
        }
        const core = corePositions(panelPositions(data, selected && selected.id,
          (record.segments || []).flatMap(s => s.residues || [])
            .map(r => r.binding_site_class).find(Boolean)));
        pocket.appendChild(bandLegend(core.size > 0));
        pocket.appendChild(pocketSegments(record, open3D, core));
        const missing = missingCoreRow(record, core);
        if (missing) pocket.appendChild(missing);
      } catch (error) {
        clear(pocket); pocket.appendChild(el("p", { class:"notice", text:t("err_family") }));
      }
    });
    controls.append(familySelect, structureSelect);
    explorer.append(controls, pocket); resetPocket(); detail.appendChild(explorer);
  };
  for (const panel of data.panels) {
    const button = el("button", { class:"panel-tab", role:"tab", "data-panel":panel.id,
      text:transducerLabel(panel.id), onclick:() => { selected=panel; draw(); } });
    strip.appendChild(button);
  }
  wrap.append(strip, detail); draw();
  return wrap;
}

/* Distance bands follow the enrichment pipeline definition: <=3.5, 3.5-4.3, 4.3-5.0 A.
   Derived from the numeric distance, not the display string, so the token stays stable
   across locales and dash characters. */
function bandToken(distance) {
  const d = Number(distance);
  if (!isFinite(d)) return "unknown";
  if (d <= 3.5) return "near";
  if (d <= 4.3) return "mid";
  return "far";
}

/* A position is "core" for a panel when at least this share of the panel's units contact it.
   Kept as one constant so the cards, the missing-contact row and the legend cannot drift apart. */
const CORE_PREVALENCE = 0.75;

/* Positions that most of the panel contacts, keyed by generic number. Purely a comparison aid:
   it marks conserved pocket positions and, conversely, lets the caller list core positions this
   particular structure does not reach. It never hides anything — that is the threshold filter's job. */
/* Every mapped position in the panel with its prevalence, so both the ≥75% markers and the
   contact-frequency slider read from one table instead of two slightly different ones. */
function panelPositions(panelStats, panelId, siteClass) {
  const out = new Map();
  if (!panelStats || !panelId) return out;
  const panels = panelStats.panels || panelStats;
  const list = Array.isArray(panels) ? panels : Object.values(panels);
  const panel = list.find(p => p.id === panelId);
  if (!panel) return out;
  // Exactly one binding-site class, never a merge. Site classes carry very different
  // denominators — a covalent-core panel may hold two units, so a position contacted in both
  // reads 100% and would swamp the canonical pocket if the classes were pooled.
  const wanted = siteClass || "canonical_7tm_pocket";
  const site = (panel.site_classes || []).find(s => s.binding_site_class === wanted);
  if (!site) return out;
  for (const position of site.positions || []) {
    const prevalence = Number(position.prevalence);
    if (!isFinite(prevalence)) continue;
    out.set(position.gn, { prevalence, segment: position.segment, topAa: position.top_aa });
  }
  return out;
}

function corePositions(positions) {
  const out = new Map();
  for (const [gn, info] of positions || [])
    if (info.prevalence >= CORE_PREVALENCE) out.set(gn, info);
  return out;
}

/* Shared by the panels explorer and the family structure detail, so both stay in step. */
function pocketSegments(record, open3D, core, keep) {
  const segments = el("div", { class:"panel-pocket-segments" });
  for (const segment of record.segments || []) {
    const visible = (segment.residues || []).filter(r => !keep || keep(r));
    if (!visible.length) continue;
    const group = el("section", { class:"panel-pocket-segment" });
    group.appendChild(el("h4", { text:segment.segment }));
    const cards = el("div", { class:"panel-residue-cards" });
    for (const residue of visible) {
      const label = (residue.aa || "") + " " + (residue.generic_number || residue.auth_seq_id);
      const hit = core && core.get(residue.generic_number);
      const card = el("button", { class:"panel-residue-card band-" +
        String(residue.distance_band || "").replace(/[^0-9]+/g,"-"),
        "data-band":bandToken(residue.distance_angstrom),
        title:t("panel_open_residue_3d"), onclick:() => open3D(record.pdb_id, null, {
          chain:residue.chain, seq:residue.auth_seq_id
        }) }, [
          el("strong", { text:label }),
          el("span", { class:"residue-sub", text:residue.residue_name + residue.auth_seq_id +
            " · " + fmt(residue.distance_angstrom, 1) + " Å" })
        ]);
      if (hit) {
        card.classList.add("is-core");
        card.appendChild(el("i", { class:"core-dot", "aria-hidden":"true" }));
        card.title = t("core_position_hint", { percent: Math.round(hit.prevalence * 100) });
      }
      cards.appendChild(card);
    }
    group.appendChild(cards); segments.appendChild(group);
  }
  return segments;
}

/* Core positions the panel reaches but this structure does not. "Expected here, absent" is a
   finding in its own right, so it is shown rather than silently left out of the segment list. */
function missingCoreRow(record, core) {
  if (!core || !core.size) return null;
  const contacted = new Set();
  for (const segment of record.segments || [])
    for (const residue of segment.residues || []) contacted.add(residue.generic_number);
  const missing = [...core.entries()].filter(([gn]) => !contacted.has(gn))
    .sort((a, b) => b[1].prevalence - a[1].prevalence);
  if (!missing.length) return null;
  const row = el("section", { class:"panel-pocket-segment missing-core" });
  row.appendChild(el("h4", { text:t("no_contact_here") }));
  const cards = el("div", { class:"panel-residue-cards" });
  for (const [gn, info] of missing) {
    cards.appendChild(el("span", { class:"panel-residue-card is-missing",
      title:t("core_position_hint", { percent: Math.round(info.prevalence * 100) }) }, [
        el("strong", { text:(info.topAa || "") + " " + gn }),
        el("span", { class:"residue-sub", text:(info.segment || "—") + " · " +
          Math.round(info.prevalence * 100) + "%" })
      ]));
  }
  row.appendChild(cards);
  return row;
}

/* Counts sit in their own boxed, right-aligned badge. Run together with the label they read as
   part of the protein name — "G12 / G13 5" looks like a subunit, not a tally of five structures. */
/* Mirrors pipeline/phase5/build_payloads.py:panel_slug so URLs and payload paths agree. */
function panelSlugOf(panel) {
  return String(panel).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

/* Chemistry filtering is three-state, not boolean.
   MATCH            the ligand carries chemistry and satisfies every active chemistry filter
   NO_MATCH         it carries chemistry and fails at least one
   NOT_ASSESSABLE   it carries none, so the filter cannot be applied to it at all

   Roughly a quarter of the pharmacologically relevant ligands in this atlas are peptides or
   polymers with no chemical component, so folding them into NO_MATCH would quietly assert they
   fail a test that was never run on them. They are counted separately instead.

   The biological-type filter is different in kind: it reads a field peptides do have, so a
   peptide can be a genuine MATCH there. */
const CHEM_MATCH = "match", CHEM_NO_MATCH = "no_match", CHEM_UNKNOWN = "unknown";

function chemistryReason(record) {
  if (!record) return "missing_representation";
  if (record.parse_status === "failed") return "parse_failed";
  return "missing_representation";
}

/* Reasons a ligand cannot be assessed, in the order the interface reports them. */
function unassessableReason(observation, record) {
  const form = observation.entity_form || "";
  const type = observation.biological_type || "";
  if (form === "polymer_chain" || type === "peptide" || type === "protein") return "peptide_polymer";
  return chemistryReason(record);
}

function componentOf(observation) {
  const components = observation.ligand_components || [];
  return components.length ? components[0] : null;
}

/* Numeric range filters are stored as [min, max] with null meaning "open". */
function withinRange(value, range) {
  if (!range) return true;
  if (value == null) return false;
  const [low, high] = range;
  return (low == null || value >= low) && (high == null || value <= high);
}

function evaluateChemistry(observation, chemistry, active) {
  if (!active.any) return CHEM_MATCH;
  const code = componentOf(observation);
  const record = code && chemistry ? chemistry.get(code) : null;

  // The biological-type axis is answerable for every ligand, chemistry or not.
  if (active.biologicalType && (observation.biological_type || "") !== active.biologicalType) {
    return CHEM_NO_MATCH;
  }
  if (!active.needsChemistry) return CHEM_MATCH;

  if (!record || record.parse_status === "failed") return CHEM_UNKNOWN;
  for (const group of active.functionalGroups) {
    if (!(record.facets.functional_groups || []).includes(group)) return CHEM_NO_MATCH;
  }
  for (const ring of active.ringSystems) {
    if (!(record.facets.ring_systems || []).includes(ring)) return CHEM_NO_MATCH;
  }
  if (active.ranges.length) {
    // Descriptors are absent for components that only exist bound; that is unassessable,
    // not a failure.
    if (!record.descriptors) return CHEM_UNKNOWN;
    for (const [field, range] of active.ranges) {
      if (!withinRange(record.descriptors[field], range)) return CHEM_NO_MATCH;
    }
  }
  return CHEM_MATCH;
}

/* A structure matches when any one of its ligands does. It is unassessable only when nothing
   matched and something could not be judged; otherwise every ligand was judged and failed. */
function structureChemistryState(structure, chemistry, active) {
  if (!active.any) return { state: CHEM_MATCH, matches: [], unknown: [] };
  const matches = [], unknown = [];
  for (const observation of structure.observations || []) {
    const verdict = evaluateChemistry(observation, chemistry, active);
    if (verdict === CHEM_MATCH) matches.push(observation);
    else if (verdict === CHEM_UNKNOWN) unknown.push(observation);
  }
  if (matches.length) return { state: CHEM_MATCH, matches, unknown };
  if (unknown.length) return { state: CHEM_UNKNOWN, matches, unknown };
  return { state: CHEM_NO_MATCH, matches, unknown };
}

function countBadge(value) {
  return el("span", { class:"tab-count", text:String(value == null ? "" : value),
    "aria-label":t("structure_count") });
}

/* Flat table reading of the same pocket rows: sortable by eye, easier to scan for a single
   distance, and it exposes the panel prevalence that the cards only hint at with a dot. */
function pocketTable(record, open3D, core, positions, keep) {
  const table = el("table", { class:"data compact pocket-table" });
  table.appendChild(el("thead", {}, el("tr", {}, [t("pt_segment"), t("pt_position"),
    t("pt_residue"), t("pt_distance"), t("pt_prevalence")].map(h => el("th", { text:h })))));
  const body = el("tbody");
  for (const segment of record.segments || []) {
    for (const residue of (segment.residues || []).filter(r => !keep || keep(r))) {
      const info = positions && positions.get(residue.generic_number);
      const row = el("tr", { class: core && core.has(residue.generic_number) ? "is-core-row" : "" }, [
        el("td", { text:segment.segment }),
        el("td", {}, el("button", { class:"link-button", title:t("panel_open_residue_3d"),
          // Without a generic number the position is just the residue letter; appending a dash
          // made it read as an empty field rather than a residue with no generic mapping.
          text:[residue.aa, residue.generic_number].filter(Boolean).join(" "),
          onclick:() => open3D(record.pdb_id, null, { chain:residue.chain, seq:residue.auth_seq_id }) })),
        el("td", { text:residue.residue_name + residue.auth_seq_id }),
        el("td", { "data-band":bandToken(residue.distance_angstrom),
          text:fmt(residue.distance_angstrom, 1) + " Å" }),
        el("td", { text:info ? Math.round(info.prevalence * 100) + "%" : "—" })
      ]);
      body.appendChild(row);
    }
  }
  table.appendChild(body);
  return table;
}

function bandLegend(withCore) {
  const box = el("div", { class:"band-legend", "aria-label":t("band_legend") });
  for (const token of ["near", "mid", "far"]) {
    box.appendChild(el("span", { class:"band-key", "data-band":token }, [
      el("i", { class:"band-swatch" }), el("span", { text:t("band_" + token) })
    ]));
  }
  if (withCore) box.appendChild(el("span", { class:"band-key" }, [
    el("i", { class:"core-dot static" }), el("span", { text:t("core_legend") })
  ]));
  return box;
}

function panelFact(value, label) {
  return el("div", { class:"panel-fact" }, [
    el("strong", { text:String(value) }), el("span", { text:label })
  ]);
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
/* One explorer, two sources. With `panelSlug` it lists every structure in a transducer panel
   across all families; otherwise it lists one family. Panel rows carry their own family_slug,
   so anything family-scoped (pocket detail, evidence, sources) is resolved per row. */
export async function structures(root, slug, onOpen3D, initialSite, initialPdb, opts) {
  const { panelSlug = null, ligandSlug = null } = opts || {};
  const panelMode = !!panelSlug, ligandMode = !!ligandSlug;
  // Chemistry filters belong to the ligand view. In the family and transducer explorers the
  // question is which receptors and complexes exist, and a chemistry sidebar there only
  // crowded the receptor-oriented filters it sat among.
  const chemMode = ligandMode;
  const d = ligandMode ? await L.loadLigandStructures(ligandSlug)
          : panelMode ? await L.loadPanelStructures(panelSlug)
          : await L.loadFamilyFile(slug, "structures.json");
  const famOf = row => row.family_slug || slug;
  const wrap = el("section", { class: "view" });
  const family = (L.getManifest().families || []).find(f => f.slug === slug);
  const availableSites = new Set(d.structures.flatMap(x => x.observations.map(o => o.binding_site_class).filter(Boolean)));
  const filters = { family: "", receptor: "", mode: "", state: "", transducer:"", evidenceTier:"",
    representativeOnly: false,
    site: availableSites.has(initialSite) ? initialSite : "", search: "", sort: "resolution",
    contactThreshold: 0,
    biologicalType: "", functionalGroups: [], ringSystems: [], ranges: {} };
  // Chemistry payloads are fetched on first use; until then no chemistry filter can be active.
  let chemistry = null, chemistryCatalog = null;
  function activeChemistry() {
    const ranges = Object.entries(filters.ranges).filter(([, r]) => r && (r[0] != null || r[1] != null));
    const needsChemistry = filters.functionalGroups.length > 0 || filters.ringSystems.length > 0
      || ranges.length > 0;
    return { biologicalType: filters.biologicalType,
             functionalGroups: filters.functionalGroups, ringSystems: filters.ringSystems,
             ranges, needsChemistry,
             any: needsChemistry || !!filters.biologicalType };
  }
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
    el("div", {}, [el("h2", { text: ligandMode ? ligandClassLabel(d.ligand_class)
      : panelMode ? transducerLabel(d.panel)
      : familyDisplayName(family ? family.name : slug) })]),
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
  const quickModes = ["", "Agonist", "Agonist (partial)", "Antagonist", "Inverse agonist",
    "Allosteric agonist", "Allosteric antagonist", "PAM", "NAM"];
  for (const mode of quickModes) if (!mode || modeCounts.has(mode)) {
    const b = el("button", { class: "quick-filter" + modeClass(mode) + (!mode ? " active" : ""), "data-mode": mode,
      onclick: () => {
        filters.mode = mode; if (filterControls.mode) filterControls.mode.value = mode;
        for (const n of quick.querySelectorAll("button")) n.classList.toggle("active", n === b);
        drawList(); drawDetail();
      } }, [
        el("span", { class: "tab-label", text: mode ? ligandClassLabel(mode) : t("all") }),
        countBadge(mode ? modeCounts.get(mode) : d.count)
      ]);
    quick.appendChild(b);
  }
  wrap.appendChild(quick);

  /* Ligand mode gets its own strip along the pharmacology axis, mirroring how the transducer
     strip works: pick a class, browse every structure in it regardless of family. */
  if (ligandMode) {
    const strip=el("div", { class:"family-panel-strip", "aria-label":t("nav_ligands") });
    const classes=(L.getManifest().ligand_files) || {};
    (async () => {
      let index;
      try { index=await L.loadGlobal("ligand_classes.json"); }
      catch (error) { return; }
      for (const entry of index.classes || []) {
        if (!classes[entry.slug]) continue;
        const active=entry.slug===ligandSlug;
        const button=el("button", { class:"panel-tab family-panel-tab"+(active?" active":""),
          "data-panel":entry.slug, "aria-pressed":active?"true":"false",
          onclick:()=>navigate({ view:"ligands", ligand:entry.slug }) }, [
            el("span", { class:"tab-label", text:ligandClassLabel(entry.label) }),
            countBadge(entry.structures)
          ]);
        strip.appendChild(button);
      }
    })();
    wrap.appendChild(strip);
  }

  const ALL_PANELS=["Gs","Gi/o","Gq/11","G12/13","arrestin","transducer_free"];
  // A single-family offline export only carries the panels that family appears in, so the strip
  // must not offer a panel whose payload was never bundled.
  const availablePanels=L.getManifest().panel_files || {};
  const transducerPanels=ligandMode ? []
    : panelMode ? ALL_PANELS.filter(x => availablePanels[panelSlugOf(x)])
    : ALL_PANELS;
  const panelStrip=el("div", { class:"family-panel-strip", "aria-label":t("transducer") });
  for (const panel of transducerPanels) {
    // In panel mode the strip switches between panels instead of filtering within one family,
    // so every panel is offered even though the current payload only holds one of them.
    const count=panelMode ? null
      : d.structures.filter(x=>(x.transducer_panels||[]).includes(panel)).length;
    if (!panelMode && !count) continue;
    const button=el("button", { class:"panel-tab family-panel-tab", "data-panel":panel,
      "aria-pressed":panelMode && panel===d.panel ? "true" : "false",
      onclick:()=>{
        if (panelMode) { navigate({ view:"panels", panel:panelSlugOf(panel) }); return; }
        filters.transducer=filters.transducer===panel?"":panel;
        if (filterControls.transducer) filterControls.transducer.value=filters.transducer;
        for (const node of panelStrip.querySelectorAll("button")) {
          const active=node.dataset.panel===filters.transducer;
          node.classList.toggle("active",active); node.setAttribute("aria-pressed",active?"true":"false");
        }
        drawList(); drawDetail();
      } }, [
        el("span", { class:"tab-label", text:transducerLabel(panel) }),
        count === null ? el("span") : countBadge(count)
      ]);
    if (panelMode && panel===d.panel) button.classList.add("active");
    panelStrip.appendChild(button);
  }
  wrap.appendChild(panelStrip);

  /* In ligand mode the chemistry filters get their own column on the far right, so the left
     rail keeps its role as the result list and the detail panel stays in the middle. */
  const layout = el("div", { class: "explorer-layout" + (chemMode ? " with-chemistry" : "") });
  const rail = el("aside", { class: "explorer-rail" });
  const detail = el("section", { class: "structure-detail", "aria-live": "polite" });
  const chemRail = el("aside", { class: "chemistry-rail" });
  layout.appendChild(rail); layout.appendChild(detail);
  if (chemMode) layout.appendChild(chemRail);
  wrap.appendChild(layout);

  const filterGrid = el("div", { class: "filter-grid" });
  function selectFilter(key, label, values, display) {
    const box = el("label", { class: "filter-field" }, [el("span", { text: label })]);
    const s = el("select", { onchange: e => { filters[key] = e.target.value;
      if (key === "mode") for (const n of quick.querySelectorAll("button"))
        n.classList.toggle("active", n.getAttribute("data-mode") === e.target.value);
      if (key === "transducer") for (const n of panelStrip.querySelectorAll("button")) {
        const active=n.dataset.panel===e.target.value;
        n.classList.toggle("active",active); n.setAttribute("aria-pressed",active?"true":"false");
      }
      drawList(); drawDetail(); } });
    filterControls[key] = s;
    s.appendChild(el("option", { value: "", text: t("all") }));
    for (const value of values) s.appendChild(el("option", { value,
      text: display ? display(value) : plainName(value), selected:filters[key] === value }));
    box.appendChild(s); return box;
  }
  filterGrid.appendChild(selectFilter("family", t("receptor_family"), uniq(x => [x.receptor_family_name])));
  filterGrid.appendChild(selectFilter("receptor", t("receptors"), uniq(x => [x.receptor_name])));
  filterGrid.appendChild(selectFilter("mode", t("ligand_class"),
    uniq(x => x.observations.map(o => o.binding_mode)), value => ligandClassLabel(value)));
  filterGrid.appendChild(selectFilter("site", t("site_class"),
    uniq(x => x.observations.map(o => o.binding_site_class)), siteClassLabel));
  filterGrid.appendChild(selectFilter("state", t("state"), uniq(x => [x.structural_state]),
    value => stateLabel(value)));
  filterGrid.appendChild(selectFilter("transducer", t("transducer"),
    uniq(x => x.transducer_panels || []), value => transducerLabel(value)));
  filterGrid.appendChild(selectFilter("evidenceTier", t("evidence_tier"),
    uniq(x => x.pathway_evidence_tiers || []), value=>t("evidence_tier_"+value)));
  // The controls that narrow the list sit on their own surface, so the panel reads as two
  // parts: what you set at the top, and what comes back below it.
  const filterBlock = el("div", { class: "filter-block" });
  filterBlock.appendChild(filterGrid);
  // Repeat depositions of one receptor-ligand context dominate the larger families, so this
  // reduces each to its sharpest structure. A count is offered next to it because the
  // reduction is large and worth seeing before it is applied.
  const repToggle = el("input", { type:"checkbox",
    onchange: e => { filters.representativeOnly = e.target.checked; drawList(); drawDetail(); } });
  const repCount = el("span", { class:"rep-count" });
  filterBlock.appendChild(el("label", { class:"rep-filter" }, [
    repToggle,
    el("span", { class:"rep-filter-text" }, [
      el("span", { text:t("representative_only") }), repCount ]),
    metricHelp(t("representative_only_help"))
  ]));
  filterBlock.appendChild(el("label", { class: "filter-field search-field" }, [
    el("span", { text: t("search") }), el("input", { type: "search", placeholder: t("search_placeholder"),
      oninput: debounce(e => { filters.search = e.target.value; drawList(); drawDetail(); }, 120) })
  ]));
  rail.appendChild(filterBlock);
  const listHead = el("div", { class: "result-head" });
  const resultList = el("div", { class: "result-list" });
  const unknownBox = el("div", { class: "unassessable" });
  // Chemistry is a filter, so it belongs with the other filters rather than under the
  // result list. The element is created later; insert it here to keep that order.
  const chemSlot = el("div", { class: "chem-slot" });
  if (chemMode) chemRail.appendChild(chemSlot);
  rail.appendChild(listHead); rail.appendChild(resultList); rail.appendChild(unknownBox);

  /* Ligands a chemistry filter could not judge. Collapsed by default so it does not compete
     with the results, but always present when non-empty: a filter that silently drops a
     quarter of the corpus would make the visible subset look like the whole. */
  function drawUnknown(split) {
    if (!split.ligandUnknown.length) return;
    const byReason = new Map();
    for (const item of split.ligandUnknown) {
      byReason.set(item.reason, (byReason.get(item.reason) || 0) + 1);
    }
    const details = el("details", { class: "unassessable-box" });
    details.appendChild(el("summary", { text:
      t("unassessable_summary", { count: split.ligandUnknown.length }) }));
    const list = el("ul", { class: "unassessable-reasons" });
    for (const [reason, count] of [...byReason.entries()].sort((a, b) => b[1] - a[1])) {
      list.appendChild(el("li", {}, [
        el("strong", { text: String(count) }),
        el("span", { text: " " + t("unassessable_reason_" + reason) })
      ]));
    }
    details.appendChild(list);
    const items = el("ul", { class: "unassessable-items" });
    for (const item of split.ligandUnknown.slice(0, 40)) {
      const label = plainName(item.observation.ligand_name || t("apo"));
      const code = componentOf(item.observation);
      const record = code && chemistry ? chemistry.get(code) : null;
      const note = record && record.parse_status === "failed" && record.parse_error
        ? " — " + record.parse_error : "";
      items.appendChild(el("li", {}, [
        el("strong", { text: item.structure.pdb_id }),
        el("span", { text: " " + label + (code ? " (" + code + ")" : "") + note })
      ]));
    }
    details.appendChild(items);
    if (split.ligandUnknown.length > 40) details.appendChild(el("p", { class: "muted small",
      text: t("unassessable_truncated", { shown: 40, total: split.ligandUnknown.length }) }));
    unknownBox.appendChild(details);
  }
  /* One row per dataset, each offering both formats. CSV holds a single table; the XLSX
     variant can carry the related tables as extra sheets, which is why the two are not
     generated from an identical row set. */
  /* The buttons read only "CSV"/"XLSX", so each carries an accessible name describing the
     dataset it downloads — otherwise a screen reader announces six identical controls. */
  const exportName = ligandMode ? "ligand-" + ligandSlug
    : panelMode ? "panel-" + panelSlug : slug;
  function exportRow(labelKey, csvName, xlsxName, onCsv, onXlsx) {
    return el("div", { class: "export-row" }, [
      el("span", { class: "export-label" }, [
        el("span", { text: t(labelKey) }), metricHelp(t(labelKey + "_help")) ]),
      el("span", { class: "export-buttons" }, [
        el("button", { class: "btn small", text: "CSV", "aria-label": csvName, onclick: onCsv }),
        el("button", { class: "btn small", text: "XLSX", "aria-label": xlsxName, onclick: onXlsx })
      ])
    ]);
  }
  /* Exports can span families in panel mode, so gather every family the current filter
     touches. In family mode this resolves to the single family file already cached. */
  async function withPocket(action) {
    try {
      const slugs = Array.from(new Set(filtered().map(famOf)));
      const parts = await Promise.all(slugs.map(s => L.loadPocketDetail(s)));
      action({ structures: parts.flatMap(part => part.structures || []) });
    } catch (error) { window.alert(L.errorMessage(error)); }
  }
  /* Chemistry filters. The payload is fetched the first time this section is opened; before
     that no chemistry filter can be active, so the landing path never pays for it. */
  const chemBox = el("div", { class: "rail-chemistry" });
  const chemDetails = el("details", { class: "chem-details" });
  chemDetails.appendChild(el("summary", { text: t("chem_heading") }));
  const chemBody = el("div", { class: "chem-body" }, [el("p", { class: "muted small", text: t("chem_prompt") })]);
  chemDetails.appendChild(chemBody);
  chemBox.appendChild(chemDetails);
  chemSlot.appendChild(chemBox);

  // The chemistry column exists for these filters, so it opens with the view rather than
  // hiding behind a disclosure the reader has to find first.
  if (chemMode) chemDetails.open = true;
  let chemLoaded = false;
  const loadChemistry = async () => {
    if (!chemDetails.open || chemLoaded) return;
    chemLoaded = true;
    clear(chemBody); chemBody.appendChild(el("p", { class: "muted small", text: t("loading") }));
    try {
      const [payload, catalog] = await Promise.all([L.loadLigandChemistry(), L.loadChemistryCatalog()]);
      chemistry = new Map((payload.records || []).map(r => [r.ccd, r]));
      chemistryCatalog = catalog;
      buildChemistryControls(payload, catalog);
      refreshFacetCounts(partition().match);
    } catch (error) {
      clear(chemBody); chemBody.appendChild(el("p", { class: "notice", text: L.errorMessage(error) }));
    }
  };
  chemDetails.addEventListener("toggle", loadChemistry);
  if (chemMode) loadChemistry();

  const countNodes = new Map();
  let coverageNodes = [];

  /* Recount every facet against the rows currently shown. Patterns that can no longer be
     reached drop to zero and are dimmed rather than removed, so the reader can see that the
     option exists but the current selection excludes it. */
  function refreshFacetCounts(rows) {
    if (!chemistry || !countNodes.size) return;
    const counts = new Map();
    let assessable = 0;
    for (const structure of rows) {
      for (const observation of structure.observations || []) {
        const code = componentOf(observation);
        const record = code ? chemistry.get(code) : null;
        if (!record || record.parse_status === "failed") continue;
        assessable += 1;
        for (const facet of ["functional_groups", "ring_systems"]) {
          for (const name of record.facets[facet] || []) {
            counts.set(name, (counts.get(name) || 0) + 1);
          }
        }
      }
    }
    for (const [name, node] of countNodes) {
      const value = counts.get(name) || 0;
      node.countSpan.textContent = String(value);
      node.row.classList.toggle("is-empty", value === 0 && !node.row.querySelector("input").checked);
    }
    for (const node of coverageNodes) {
      const covered = rows.reduce((n, structure) => n + (structure.observations || [])
        .filter(observation => {
          const code = componentOf(observation);
          const record = code ? chemistry.get(code) : null;
          return record && record.descriptors && record.descriptors[node.field] != null;
        }).length, 0);
      node.el.textContent = t("chem_coverage", { covered, total: assessable });
    }
  }

  const rangeResets = [];

  function buildChemistryControls(payload, catalog) {
    clear(chemBody);
    countNodes.clear(); coverageNodes = []; rangeResets.length = 0;
    chemBody.appendChild(el("p", { class: "muted small", text:
      t("chem_provenance", { rdkit: payload.rdkit_version, catalog: payload.catalog_version }) }));

    // Biological type reads a field every ligand has, so peptides are answerable here.
    const types = Array.from(new Set(d.structures.flatMap(x =>
      (x.observations || []).map(o => o.biological_type).filter(Boolean)))).sort();
    const typeSelect = el("select", { onchange: e => {
      filters.biologicalType = e.target.value; drawList(); drawDetail(); } });
    typeSelect.appendChild(el("option", { value: "", text: t("all") }));
    for (const value of types)
      typeSelect.appendChild(el("option", { value, text: biologicalTypeLabel(value) }));
    chemBody.appendChild(el("label", { class: "filter-field" }, [
      el("span", { text: t("chem_biological_type") }), typeSelect ]));

    /* Counts are recomputed against whatever is currently on screen, not against the whole
       corpus. A static number would claim, say, 549 carbonyl ligands whether the reader had
       narrowed to lipids or not, which tells them nothing about what is still reachable. */
    const present = { functional_groups: new Map(), ring_systems: new Map() };
    for (const record of payload.records || []) {
      if (!record.pharmacological_instances) continue;
      for (const facet of ["functional_groups", "ring_systems"]) {
        for (const name of record.facets[facet] || []) {
          present[facet].set(name, (present[facet].get(name) || 0) + record.pharmacological_instances);
        }
      }
    }
    const facetBox = (facet, key, labelKey) => {
      const entries = [...present[facet].entries()].sort((a, b) => b[1] - a[1]);
      if (!entries.length) return;
      const box = el("details", { class: "chem-facet" });
      box.appendChild(el("summary", {}, [el("span", { text: t(labelKey) }),
        el("span", { class: "chem-facet-count", text: String(entries.length) })]));
      const list = el("div", { class: "chem-checks" });
      for (const [name, count] of entries) {
        const spec = (catalog.patterns || {})[name] || {};
        const input = el("input", { type: "checkbox", value: name, onchange: e => {
          const set = new Set(filters[key]);
          if (e.target.checked) set.add(name); else set.delete(name);
          filters[key] = [...set]; drawList(); drawDetail(); } });
        const countSpan = el("span", { class: "chem-count", text: String(count) });
        const row = el("label", { class: "chem-check", "data-pattern": name }, [ input,
          el("span", { text: spec["label_" + getLang()] || spec.label_en || name }), countSpan ]);
        countNodes.set(name, { countSpan, row });
        list.appendChild(row);
      }
      box.appendChild(list); chemBody.appendChild(box);
    };
    facetBox("functional_groups", "functionalGroups", "chem_functional_groups");
    facetBox("ring_systems", "ringSystems", "chem_ring_systems");

    /* Every descriptor carries its own coverage: how many ligand instances actually have that
       value. Applying one global percentage to all of them would misstate each one. */
    const withDescriptors = (payload.records || []).filter(r => r.descriptors && r.pharmacological_instances);
    const totalInstances = (payload.records || [])
      .reduce((n, r) => n + (r.pharmacological_instances || 0), 0);
    const rangeBox = el("details", { class: "chem-facet" });
    rangeBox.appendChild(el("summary", { text: t("chem_descriptors") }));
    for (const [field, labelKey, step] of [["mw", "chem_mw", 10], ["mollogp", "chem_logp", 0.5],
      ["tpsa", "chem_tpsa", 5], ["hbd", "chem_hbd", 1], ["hba", "chem_hba", 1],
      ["rotatable_bonds", "chem_rotb", 1], ["heavy_atoms", "chem_heavy", 1],
      ["aromatic_rings", "chem_arom", 1], ["fraction_csp3", "chem_fsp3", 0.05]]) {
      const values = withDescriptors.map(r => r.descriptors[field]).filter(v => v != null);
      if (!values.length) continue;
      const covered = withDescriptors
        .filter(r => r.descriptors[field] != null)
        .reduce((n, r) => n + r.pharmacological_instances, 0);
      const lo = Math.min(...values), hi = Math.max(...values);
      /* Two sliders rather than typed numbers: dragging shows the result count moving, which
         is how a reader finds where a property actually separates the set. The pair is kept
         ordered so the low handle can never pass the high one. */
      const low = Math.floor(lo), high = Math.ceil(hi);
      const decimals = step < 1 ? 2 : 0;
      const minInput = el("input", { type: "range", min: String(low), max: String(high),
        step: String(step), value: String(low), "aria-label": t(labelKey) + " min" });
      const maxInput = el("input", { type: "range", min: String(low), max: String(high),
        step: String(step), value: String(high), "aria-label": t(labelKey) + " max" });
      const readout = el("span", { class: "chem-range-value" });
      const apply = () => {
        let a = Number(minInput.value), b = Number(maxInput.value);
        if (a > b) { [a, b] = [b, a]; minInput.value = String(a); maxInput.value = String(b); }
        readout.textContent = a.toFixed(decimals) + " – " + b.toFixed(decimals);
        // A range spanning the whole observed span is not a filter; leaving it null keeps
        // ligands whose descriptor is missing from being judged against it.
        filters.ranges[field] = (a <= low && b >= high) ? null : [a, b];
        drawList(); drawDetail();
      };
      const live = debounce(apply, 90);
      minInput.addEventListener("input", live); maxInput.addEventListener("input", live);
      readout.textContent = low.toFixed(decimals) + " – " + high.toFixed(decimals);
      /* Clearing a range input by setting value to "" lands a slider on its midpoint, which
         collapsed both handles together and read as a filter of one value. Reset puts each
         handle back on its own end instead. */
      rangeResets.push(() => {
        minInput.value = String(low); maxInput.value = String(high);
        readout.textContent = low.toFixed(decimals) + " – " + high.toFixed(decimals);
        filters.ranges[field] = null;
      });
      const coverageNode = el("span", { class: "chem-coverage",
        text: t("chem_coverage", { covered, total: totalInstances }) });
      coverageNodes.push({ field, el: coverageNode });
      rangeBox.appendChild(el("div", { class: "chem-range" }, [
        el("span", { class: "chem-range-label", text: t(labelKey) }), readout,
        el("div", { class: "chem-sliders" }, [minInput, maxInput]),
        coverageNode
      ]));
    }
    chemBody.appendChild(rangeBox);

    const reset = el("button", { class: "btn small", type: "button", text: t("chem_reset"),
      onclick: () => {
        filters.biologicalType = ""; filters.functionalGroups = []; filters.ringSystems = [];
        filters.ranges = {};
        for (const input of chemBody.querySelectorAll("input[type=checkbox]")) input.checked = false;
        for (const reset of rangeResets) reset();
        typeSelect.value = "";
        drawList(); drawDetail();
      } });
    chemBody.appendChild(reset);
  }

  /* Contact-frequency threshold. It hides pocket positions the panel rarely touches, which is a
     different question from the ≥75% markers: the markers annotate, this filters. */
  const thresholdValue = el("span", { class: "threshold-value", text: "0%" });
  const thresholdCaption = el("span", { class: "threshold-caption", text: t("threshold_all") });
  const thresholdInput = el("input", { type: "range", min: "0", max: "100", step: "5", value: "0",
    "aria-label": t("threshold_contacts") });
  thresholdInput.addEventListener("input", debounce(event => {
    const percent = Number(event.target.value);
    filters.contactThreshold = percent / 100;
    thresholdValue.textContent = percent + "%";
    thresholdCaption.textContent = percent
      ? t("threshold_min", { percent }) : t("threshold_all");
    drawDetail();
  }, 120));
  rail.appendChild(el("div", { class: "rail-threshold" }, [
    el("div", { class: "threshold-head" }, [
      el("span", { class: "threshold-label", text: t("threshold_contacts") }),
      metricHelp(t("threshold_help")), thresholdValue
    ]),
    thresholdInput, thresholdCaption
  ]));

  rail.appendChild(el("div", { class: "rail-actions" }, [
    el("h4", { class: "rail-actions-head", text: t("export_heading") }),
    exportRow("export_filtered_set",
      t("export_structures") + " (CSV)",
      t("export_structures") + " / " + t("export_observations") + " (XLSX)",
      () => exportStructures(filtered(), exportName),
      () => exportStructuresXLSX(filtered(), exportName)),
    exportRow("export_contact_list",
      t("export_contacts") + " (CSV)", t("export_contacts") + " (XLSX)",
      () => withPocket(p => exportContactList(filtered(), p, exportName, false)),
      () => withPocket(p => exportContactList(filtered(), p, exportName, true))),
    exportRow("export_matrix",
      t("export_matrix") + " (CSV)", t("export_matrix") + " (XLSX)",
      () => withPocket(p => exportMatrix(filtered(), p, exportName, false)),
      () => withPocket(p => exportMatrix(filtered(), p, exportName, true)))
  ]));

  /* Structures passing every non-chemistry filter. Chemistry is applied afterwards so the
     three-state split can be counted rather than silently folded into the result list. */
  function baseFiltered() {
    const q = filters.search.trim().toLowerCase();
    const rows = d.structures.filter(x =>
      (!filters.family || x.receptor_family_name === filters.family) &&
      (!filters.receptor || x.receptor_name === filters.receptor) &&
      (!filters.mode || x.observations.some(o => o.binding_mode === filters.mode)) &&
      (!filters.site || x.observations.some(o => o.binding_site_class === filters.site)) &&
      (!filters.state || x.structural_state === filters.state) &&
      (!filters.transducer || (x.transducer_panels||[]).includes(filters.transducer)) &&
      (!filters.evidenceTier || (x.pathway_evidence_tiers||[]).includes(filters.evidenceTier)) &&
      (!filters.representativeOnly || x.analysis_unit_representative === true) &&
      (!q || [x.pdb_id, plainName(x.receptor_name), x.receptor_entry_name,
        ...x.observations.map(o => o.ligand_name || "")].join(" ").toLowerCase().includes(q)));
    return rows.sort((a,b) => (a.resolution == null) - (b.resolution == null) ||
      (a.resolution || 99) - (b.resolution || 99) || a.pdb_id.localeCompare(b.pdb_id));
  }

  /* Split the base set three ways. `matches` feeds the result list and the headline count;
     `unknown` is surfaced separately so nothing disappears without being accounted for. */
  function partition() {
    const active = activeChemistry();
    const base = baseFiltered();
    if (!active.any) return { match: base, unknown: [], ligandMatches: 0, ligandUnknown: [] };
    const match = [], unknown = [], ligandUnknown = [];
    let ligandMatches = 0;
    for (const structure of base) {
      const verdict = structureChemistryState(structure, chemistry, active);
      if (verdict.state === CHEM_MATCH) { match.push(structure); ligandMatches += verdict.matches.length; }
      else if (verdict.state === CHEM_UNKNOWN) {
        unknown.push(structure);
        for (const observation of verdict.unknown) {
          const code = componentOf(observation);
          ligandUnknown.push({ structure, observation,
            reason: unassessableReason(observation, code && chemistry ? chemistry.get(code) : null) });
        }
      }
    }
    return { match, unknown, ligandMatches, ligandUnknown };
  }

  function filtered() { return partition().match; }
  function drawList() {
    const split = partition();
    const rows = split.match;
    clear(resultList); clear(listHead); clear(unknownBox);
    if (rows.length && !rows.includes(selected)) selected = rows[0];
    // Structures and ligand instances are different units and are never added together.
    listHead.appendChild(el("strong", { text: rows.length + " " + t("results") }));
    if (split.ligandMatches) listHead.appendChild(el("span", { class: "muted small",
      text: " · " + split.ligandMatches + " " + t("ligand_matches") }));
    listHead.appendChild(el("span", { class: "muted small", text: t("sorted_resolution") }));
    drawUnknown(split);
    // What the toggle would leave, counted against the other filters as they currently stand,
    // so the number answers "how many if I tick this" rather than quoting an atlas-wide total.
    const was = filters.representativeOnly;
    filters.representativeOnly = true;
    const representatives = was ? rows.length : partition().match.length;
    filters.representativeOnly = was;
    repCount.textContent = String(representatives);
    refreshFacetCounts(rows);
    let selectedItem = null;
    for (const x of rows) {
      const o = observationFor(x);
      const shown = observationsFor(x);
      const ligandText = Array.from(new Set(shown.map(v => plainName(v.ligand_name || t("apo"))))).join(" + ");
      const item = el("button", { class: "result-item" + (selected === x ? " selected" : ""),
        "aria-pressed": selected === x ? "true" : "false", onclick: () => {
          selected = x;
          // Record the selection in the address bar. The view is rebuilt from the route on a
          // language change, so a selection that lived only in memory was lost there; it also
          // makes the chosen structure linkable and survivable across back and forward.
          navigate(Object.assign({}, parseRoute(), { pdb: x.pdb_id }), true);
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
          .map(mode => el("span", { class: "mode-pill" + modeClass(mode),
            text: ligandClassLabel(mode) })))
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
    if (x.superseded) detail.appendChild(supersededNotice(x));
    detail.appendChild(el("div", { class: "detail-tags" }, [
      el("span", { class: "chip", text: plainName(x.receptor_family_name || "—") }),
      el("span", { class: "chip", text: stateLabel(x.structural_state || "unknown") }),
      ...modes.map(mode => el("span", { class: "chip mode-pill" + modeClass(mode),
        text: ligandClassLabel(mode) })),
      el("span", { class: "chip", text: siteClassLabel(o.binding_site_class || "unresolved") }),
      ...(x.transducer_class ? [el("span", { class: "chip chip-transducer",
        text: t("transducer") + ": " + transducerLabel(x.transducer_class) })] : []),
      // A structure can sit in more than one panel; show the extra memberships explicitly
      // rather than letting the primary class imply exclusivity.
      ...(x.transducer_panels || []).filter(p => p !== x.transducer_class).map(p =>
        el("span", { class: "chip chip-panel-extra",
          text: t("also_in_panel", { panel: transducerLabel(p) }) }))
    ]));
    // One compact line instead of three large tiles: the shell counts are reference numbers,
    // not the headline of the page, and the tiles pushed the evidence table below the fold.
    // It rides in the fact row rather than below it, where the row already ends in dead space.
    const facts = el("div", { class: "detail-facts" }, [
      fact(t("receptors"), plainName(x.receptor_name || "—")), fact(t("resolution"), fmt(x.resolution,2) + " Å"),
      fact(t("method"), methodLabel(x.experimental_method)), fact(t("species"), x.species || "—"),
      fact(t("ligand_class"), modes.map(ligandClassLabel).join(" + ") || "—"),
      fact(t("transducer"), transducerLabel(x.transducer_class))
    ]);
    facts.appendChild(el("div", { class: "detail-shell" }, [
      el("span", { class: "shell-label", text: t("contact_shell") }),
      el("strong", { text: (o.receptor_residues_5A || 0) + " " + t("residues") }),
      el("span", { class: "shell-extra", title: t("binding_site_explain"),
        text: "≤ 4.5 Å: " + (o.receptor_residues_4_5A || 0) +
          " · ≤ 4.0 Å: " + (o.receptor_residues_4A || 0) })
    ]));
    detail.appendChild(facts);
    const sourcesSection = el("section", { class: "detail-section sources" }, [
      el("h3", { text: t("source_links") }),
      SOURCES.linkRow(famOf(x),x)
    ]);
    // Both sections load asynchronously; the placeholders are appended now so the order on
    // screen is stable no matter which payload resolves first.
    const evidenceSection = el("section", { class: "detail-section evidence-table" });
    const pocketSection = el("section", { class: "detail-section pocket-detail" });
    // Reference layout: the compact facts block ends with its sources, then the evidence table
    // gets a full-width block of its own, then the pocket.
    detail.append(sourcesSection, evidenceSection, pocketSection);
    const seq = ++detailSeq;
    drawEvidence(x, evidenceSection, seq);
    drawPocket(x, o.binding_site_class, pocketSection, seq, sourcesSection);
  }

  async function drawEvidence(x, section, seq) {
    section.appendChild(el("p", { class: "muted", text: t("loading") }));
    let rows;
    try {
      const payload = await L.loadFamilyEvidence(famOf(x));
      rows = (payload.records || []).filter(row => row.pdb_id === x.pdb_id);
    } catch (error) {
      if (seq !== detailSeq) return;
      clear(section); section.appendChild(el("p", { class: "notice", text: t("err_family") })); return;
    }
    if (seq !== detailSeq) return;
    clear(section);
    if (!rows.length) return;
    // Structural evidence first, then functional, so the row order matches how the claim is built.
    rows.sort((a, b) => (a.tier || "").localeCompare(b.tier || ""));
    const table = el("table", { class: "data compact evidence" });
    // The membership column decides whether a row puts this structure in a panel, which is not
    // obvious from a tick mark; the header carries the explanation.
    table.appendChild(el("thead", {}, el("tr", {}, [
      el("th", { text: t("ev_col_pathway") }), el("th", { text: t("ev_col_evidence") }),
      el("th", { text: t("ev_col_assay") }), el("th", { text: t("ev_col_source") }),
      el("th", {}, [el("span", { text: t("ev_col_membership") }), metricHelp(t("ev_membership_help"))])
    ])));
    const body = el("tbody");
    for (const row of rows) {
      const fe = row.functional_evidence || {};
      const source = row.source || {};
      const resultLabel = t("ev_result_" + row.result);
      const rationale = row["rationale_" + getLang()] || row.rationale_en || "";
      // Tier A rationales already open with the result phrase, and tier B rationales repeat the
      // assay name — so pick one source of words per tier instead of concatenating all three.
      const detailText = row.tier === "A"
        ? (rationale.startsWith(resultLabel)
            ? rationale.slice(resultLabel.length).replace(/^\s*[—–-]\s*/, "") : rationale)
        : [fe.assay_or_evidence, fe.curator_note].filter(Boolean).join(" — ");
      const sourceLabel = (source.reference_id || "").replace(/^PMCID:/, "") ||
        (/rcsb\.org/.test(source.url || "") ? "RCSB " + row.pdb_id : t("source_open"));
      body.appendChild(el("tr", {}, [
        el("td", {}, el("strong", { text: transducerLabel(row.panel) })),
        el("td", {}, el("span", { class: "tier-badge tier-" + (row.tier || "").toLowerCase(),
          text: row["tier_label_" + getLang()] || row.tier_label_en || row.tier })),
        el("td", {}, [el("strong", { text: resultLabel }),
          el("span", { text: detailText ? " — " + detailText : "" })]),
        el("td", {}, source.url
          ? el("a", { href: source.url, target: "_blank", rel: "noopener", text: sourceLabel })
          : el("span", { class: "muted", text: "—" })),
        el("td", {}, el("span", { class: row.panel_membership ? "member-yes" : "member-no",
          text: (row.panel_membership ? "✓ " : "✗ ") +
            t(row.panel_membership ? "ev_member_yes" : "ev_member_no") }))
      ]));
    }
    table.appendChild(body);
    section.appendChild(table);
    section.appendChild(el("p", { class: "muted small", text: t("ev_table_note") }));
  }

  // Pocket detail is a per-family file of a few MB, so it is fetched only once a structure is
  // actually selected. `detailSeq` guards against a slow response landing after the user has
  // already clicked a different structure.
  let detailSeq = 0;
  let pocketAsTable = false;
  async function drawPocket(x, siteClass, section, seq, overlapTarget) {
    section.append(el("h3", { text: t("pocket_by_segment") }),
      el("p", { class: "muted", text: t("loading") }));
    let record = null, core = null, positions = null;
    try {
      const payload = await L.loadPocketDetail(famOf(x));
      record = (payload.structures || []).find(s => s.pdb_id === x.pdb_id) || null;
      // Compare against the panel the user is currently filtering by; with no filter, fall back
      // to the panel the structure was actually solved in.
      const panelId = filters.transducer ||
        (x.transducer_panels_structural || x.transducer_panels || [])[0];
      positions = panelPositions(await L.loadPanels(), panelId, siteClass);
      core = corePositions(positions);
    } catch (error) {
      if (seq !== detailSeq) return;
      clear(section); section.appendChild(el("h3", { text: t("pocket_by_segment") }));
      section.appendChild(el("p", { class: "notice", text: t("err_family") }));
      return;
    }
    if (seq !== detailSeq) return;
    clear(section);
    section.appendChild(el("h3", { text: t("pocket_by_segment") }));
    if (!record) {
      section.appendChild(el("p", { class: "notice", text: t("panel_pocket_missing") })); return;
    }
    if (record.empty_reason) {
      section.appendChild(el("div", { class: "panel-empty-state " + record.empty_reason }, [
        el("strong", { text: t("panel_empty_" + record.empty_reason + "_title") }),
        el("span", { text: t("panel_empty_" + record.empty_reason + "_body") })
      ]));
      return;
    }
    section.appendChild(el("p", { class: "muted small", text:
      record.n_contacts + " " + t("contacts_short") + " · " +
      record.n_mapped + " " + t("panel_mapped_contacts") }));
    if (core && core.size) {
      const mapped = (record.segments || []).flatMap(s => s.residues || [])
        .filter(r => r.generic_number);
      const shared = mapped.filter(r => core.has(r.generic_number)).length;
      // Belongs with the sources block in the reference layout, not above the residue cards.
      (overlapTarget || section).appendChild(el("p", { class: "panel-overlap" }, [
        el("span", { class: "panel-overlap-label", text: t("panel_overlap_label") }),
        el("strong", { text: t("panel_overlap_value",
          { shared, total: mapped.length, percent: Math.round(CORE_PREVALENCE * 100) }) })
      ]));
    }
    // The threshold hides positions the panel rarely touches. Residues with no generic mapping
    // have no panel prevalence to judge, so they are never hidden — we cannot claim they are rare.
    const minPrevalence = filters.contactThreshold || 0;
    const keep = residue => {
      if (!minPrevalence) return true;
      const info = positions && positions.get(residue.generic_number);
      return !info || info.prevalence >= minPrevalence;
    };
    const all = (record.segments || []).flatMap(s => s.residues || []);
    const shown = all.filter(keep).length;
    if (minPrevalence && shown < all.length) section.appendChild(el("p", { class: "muted small",
      text: t("threshold_hidden", { hidden: all.length - shown, total: all.length }) }));

    // Cards and table are two readings of the same rows; the toggle only swaps this body,
    // so switching costs no fetch and keeps the surrounding blocks in place.
    const body = el("div", { class: "pocket-body" });
    const toggle = el("button", { class: "btn small", type: "button" });
    const renderBody = () => {
      clear(body);
      toggle.textContent = pocketAsTable ? t("pocket_view_cards") : t("pocket_view_table");
      toggle.setAttribute("aria-pressed", pocketAsTable ? "true" : "false");
      if (pocketAsTable) { body.appendChild(pocketTable(record, onOpen3D, core, positions, keep)); }
      else {
        body.appendChild(bandLegend(core && core.size > 0));
        body.appendChild(pocketSegments(record, onOpen3D, core, keep));
      }
      const missing = missingCoreRow(record, core);
      if (missing) body.appendChild(missing);
    };
    toggle.addEventListener("click", () => { pocketAsTable = !pocketAsTable; renderBody(); });
    section.querySelector("h3").appendChild(toggle);
    section.appendChild(body);
    renderBody();
  }
  drawList(); drawDetail();
  return wrap;
}
function supersededNotice(structure) {
  const info=structure.superseded;
  const replacement=(info.replaced_by||[structure.superseded_by]).filter(Boolean).join(", ");
  const status=info.replacement_in_atlas?t("superseded_replacement_in_atlas"):
    t("superseded_replacement_not_in_atlas");
  return el("aside", { class:"notice superseded-notice", role:"note" }, [
    el("strong", { text:t("superseded_title") }),
    el("p", { text:t("superseded_body", { pdb:structure.pdb_id,replacement,date:info.remove_date||"—" }) }),
    info.details?el("p", { text:info.details }):null,
    el("p", { class:"muted small", text:status }),
    el("a", { href:info.source,target:"_blank",rel:"noopener",text:t("superseded_rcsb_record") })
  ]);
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
const STRUCTURE_COLS = [{ key: "pdb_id" }, { key: "receptor_name" }, { key: "receptor_entry_name" },
  { key: "species" }, { key: "experimental_method" }, { key: "resolution" },
  { key: "release_date" }, { key: "structural_state" }, { key: "transducer_class" },
  { key: "transducer_panels" }, { key: "apo_status" }, { key: "ligand_status" },
  { key: "observation_count" }];
const OBSERVATION_COLS = [{ key: "pdb_id" }, { key: "receptor_name" }, { key: "observation_id" },
  { key: "ligand_name" }, { key: "ligand_components" }, { key: "binding_mode" },
  { key: "binding_site_class" }, { key: "receptor_residues_5A" }, { key: "receptor_residues_4_5A" },
  { key: "receptor_residues_4A" }];

/* The workbook carries structures and their observations as two sheets, which a flat CSV
   cannot express without either duplicating structure rows or losing the observations. */
function exportStructuresXLSX(rows, slug) {
  const flat = [];
  for (const s of rows) for (const o of s.observations)
    flat.push(Object.assign({ pdb_id: s.pdb_id, receptor_name: s.receptor_name }, o));
  downloadXLSX("structures_" + slug + ".xlsx", [
    { name: "Structures", columns: STRUCTURE_COLS, rows },
    { name: "Observations", columns: OBSERVATION_COLS, rows: flat }
  ]);
}

function pocketRows(rows, pocket) {
  const byPdb = new Map((pocket.structures || []).map(r => [r.pdb_id, r]));
  const out = [];
  for (const s of rows) {
    const record = byPdb.get(s.pdb_id);
    if (!record) continue;
    for (const segment of record.segments || [])
      for (const residue of segment.residues || [])
        out.push({ pdb_id: s.pdb_id, receptor_name: s.receptor_name,
          transducer_class: s.transducer_class, segment: segment.segment,
          generic_number: residue.generic_number, residue_name: residue.residue_name,
          aa: residue.aa, auth_seq_id: residue.auth_seq_id, chain: residue.chain,
          distance_angstrom: residue.distance_angstrom, distance_band: residue.distance_band,
          binding_site_class: residue.binding_site_class, ligand_residue_name: residue.ligand_residue_name });
  }
  return out;
}
const CONTACT_COLS = [{ key: "pdb_id" }, { key: "receptor_name" }, { key: "transducer_class" },
  { key: "segment" }, { key: "generic_number" }, { key: "aa" }, { key: "residue_name" },
  { key: "auth_seq_id" }, { key: "chain" }, { key: "distance_angstrom" },
  { key: "distance_band" }, { key: "binding_site_class" }, { key: "ligand_residue_name" }];

function exportContactList(rows, pocket, slug, xlsx) {
  const list = pocketRows(rows, pocket);
  const info = meta(slug, { table: "contact_list", structures: rows.length, rows: list.length });
  if (xlsx) downloadXLSX("contacts_" + slug + ".xlsx",
    [{ name: "Contacts", columns: CONTACT_COLS, rows: list }]);
  else download("contacts_" + slug + ".csv", toCSV(CONTACT_COLS, list, info));
}

/* Generic positions down the rows, structures across the columns, closest heavy-atom distance
   in the cells. Blank means the position was not within the 5 Å shell for that structure —
   distinct from a position that is absent from the numbering, which never gets a row at all. */
function exportMatrix(rows, pocket, slug, xlsx) {
  const list = pocketRows(rows, pocket);
  const pdbs = Array.from(new Set(list.map(r => r.pdb_id))).sort();
  const positions = new Map();
  for (const r of list) {
    if (!r.generic_number) continue;
    if (!positions.has(r.generic_number))
      positions.set(r.generic_number, { generic_number: r.generic_number, segment: r.segment });
    const cell = positions.get(r.generic_number);
    const previous = cell[r.pdb_id];
    if (previous === undefined || r.distance_angstrom < previous) cell[r.pdb_id] = r.distance_angstrom;
  }
  const sortKey = gn => {
    const m = /^(\d+)x(\d+)/.exec(gn || "");
    return m ? Number(m[1]) * 1000 + Number(m[2]) : 1e9;
  };
  const matrix = Array.from(positions.values()).sort((a, b) =>
    sortKey(a.generic_number) - sortKey(b.generic_number));
  const cols = [{ key: "generic_number" }, { key: "segment" },
    ...pdbs.map(pdb => ({ key: pdb, label: pdb }))];
  const info = meta(slug, { table: "comparison_matrix", cell: "closest heavy-atom distance (A)",
    structures: pdbs.length, positions: matrix.length });
  if (xlsx) downloadXLSX("matrix_" + slug + ".xlsx",
    [{ name: "Matrix", columns: cols, rows: matrix }]);
  else download("matrix_" + slug + ".csv", toCSV(cols, matrix, info));
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
        s.appendChild(el("option", { value: f, text: fam ? familyDisplayName(fam.name) : f })); } }
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
  const lang = getLang();
  const roles = d.source_roles || {};
  const roleTable = el("table", { class: "data source-roles" });
  roleTable.appendChild(el("thead", {}, el("tr", {}, [t("sr_source"), t("sr_role"),
    t("sr_fields"), t("sr_licence"), t("sr_transform")].map(h => el("th", { text: h })))));
  const roleBody = el("tbody");
  // Coordinates first, then annotation, pharmacology, chemistry, and the bundled viewer last —
  // the order the data actually flows through the pipeline. Unlisted sources fall in alphabetically.
  const ORDER = ["rcsb", "gpcrdb", "gtopdb", "chembl", "pubchem", "unichem", "uniprot", "ngl"];
  const rank = key => { const i = ORDER.indexOf(key); return i < 0 ? ORDER.length : i; };
  for (const key of Object.keys(roles).sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))) {
    const s = roles[key];
    roleBody.appendChild(el("tr", {}, [
      el("th", { scope: "row" }, [
        el("strong", { text: s["label_" + lang] || s.label_en || key }),
        s.license_page ? el("a", { class: "source-home", href: s.license_page,
          target: "_blank", rel: "noopener", text: s.license_page }) : el("span")
      ]),
      el("td", { class: "small", text: s["role_" + lang] || s.role_en || "—" }),
      el("td", { class: "small" }, el("ul", { class: "field-list" },
        (s.fields_used || []).map(f => el("li", { text: f })))),
      el("td", { class: "small" }, [
        el("span", { text: s.licence || "—" }),
        s.attribution_text ? el("p", { class: "muted", text: s.attribution_text }) : el("span")
      ]),
      el("td", { class: "small", text: s["transform_" + lang] || s.transform_en || "—" })
    ]));
  }
  roleTable.appendChild(roleBody); wrap.appendChild(roleTable);

  // Licence verification is a separate claim from the licence itself: it records whether this
  // project confirmed the terms first-hand or is repeating what the owner supplied.
  wrap.appendChild(el("h3", { text: t("sr_verification") }));
  const verify = el("table", { class: "data" });
  verify.appendChild(el("thead", {}, el("tr", {}, [t("sr_source"), t("sr_licence"),
    t("sr_verification_method")].map(h => el("th", { text: h })))));
  const vb = el("tbody");
  for (const s of d.licences || []) vb.appendChild(el("tr", {}, [
    el("th", { scope: "row", text: s.provider }),
    // Some records carry the owner's structured values rather than a single sentence.
    el("td", {}, typeof s.licence === "string" ? el("span", { text: s.licence })
      : el("ul", { class: "field-list" }, Object.entries(s.licence || {}).map(([k, v]) =>
          el("li", { text: k.replace(/_/g, " ") + ": " + v })))),
    el("td", { class: "small", text: s.verification_method })]));
  verify.appendChild(vb); wrap.appendChild(verify);

  wrap.appendChild(el("h3", { text: t("sr_release_gates") }));
  wrap.appendChild(el("ul", {}, (d.release_gates || []).map(g =>
    el("li", {}, [el("strong", { text: g.gate + " — " + g.status }),
      el("span", { text: ": " + g.note })]))));
  return wrap;
}
export async function references(root, slug) {
  const g = await L.loadGlobal("references.json");
  const wrap = el("section", { class: "view prose" });
  wrap.appendChild(el("h2", { text: t("nav_references") }));
  // The payload carries full bibliographic records (database_citations); the old `databases`
  // array it replaced is gone, which is why this page rendered empty.
  const cites = g.database_citations || {};
  const keys = Object.keys(cites).sort();
  if (keys.length) {
    wrap.appendChild(el("h3", { text: t("ref_databases") }));
    const list = el("ol", { class: "reference-list" });
    for (const key of keys) {
      const c = cites[key];
      const item = el("li", {}, [ el("strong", { class: "ref-db-label", text: databaseLabel(key) + " — " }),
        el("span", { text: plainCitation(c) }) ]);
      if (c.pubmed_url) item.appendChild(el("a", { href: c.pubmed_url, target: "_blank",
        rel: "noopener", text: " PubMed" }));
      list.appendChild(item);
    }
    wrap.appendChild(list);
    wrap.appendChild(el("p", { class: "muted small", text: t("cite_db_note") }));
  }
  if (g.atlas) wrap.appendChild(el("p", { class: "muted small",
    text: g.atlas.title + " " + (g.atlas.version || "") + " — " +
      (g["atlas"]["doi_note_" + getLang()] || g.atlas.doi_note_en || "") }));
  if (!slug) wrap.appendChild(el("p", { class: "muted", text: t("ref_pick_family") }));
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
/* Copyable block: the text people actually paste into a manuscript, with the button beside it
   rather than a bare <pre> they have to select by hand. */
function citationBlock(text, labelKey) {
  const box = el("div", { class: "cite-block" }, [ el("pre", { text }) ]);
  const button = el("button", { class: "btn small", type: "button", text: t(labelKey) });
  button.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(text); button.textContent = t("cite_copied"); }
    catch (error) { button.textContent = t("cite_copy_failed"); }
    setTimeout(() => { button.textContent = t(labelKey); }, 1800);
  });
  box.appendChild(button);
  return box;
}

function bibtex(pdb, citation) {
  const first = (citation.authors || [])[0] || "Unknown";
  const key = String(first).split(",")[0].replace(/[^A-Za-z]/g, "") + (citation.year || "");
  const lines = ["@article{" + (key || pdb) + ","];
  const field = (name, value) => { if (value) lines.push("  " + name + " = {" + value + "},"); };
  field("author", (citation.authors || []).join(" and "));
  field("title", citation.title);
  field("journal", citation.journal);
  field("year", citation.year);
  field("volume", citation.volume);
  field("pages", [citation.pages, citation.page_last].filter(Boolean).join("--"));
  field("doi", citation.doi);
  lines.push("}");
  return lines.join("\n");
}

/* Which resource a citation belongs to. The payload keys are internal, so they are mapped to
   the name a reader would recognise; an unmapped key falls back to the key rather than being
   hidden, so a newly added resource is visible rather than silently unlabelled. */
function databaseLabel(key) {
  const label = t("db_label_" + key);
  return label === "db_label_" + key ? key : label;
}

function plainCitation(citation) {
  const authors = (citation.authors || []).join(", ");
  const where = [citation.journal, citation.year].filter(Boolean).join(" ");
  const detail = [citation.volume, [citation.pages, citation.page_last].filter(Boolean).join("-")]
    .filter(Boolean).join(":");
  return [authors, citation.title, [where, detail].filter(Boolean).join(";"),
    citation.doi ? "doi:" + citation.doi : ""].filter(Boolean).join(". ");
}

export async function cite(root, pdb, slug) {
  const g = await L.loadGlobal("references.json");
  const rm = await L.loadGlobal("release_metadata.json");
  const m = L.getManifest();
  const lang = getLang();
  const wrap = el("section", { class: "view prose" });
  wrap.appendChild(el("h2", { text: t("nav_cite") }));

  const tabs = el("div", { class: "cite-tabs", role: "tablist" });
  const body = el("div", { class: "cite-body" });
  wrap.append(tabs, body);

  const panels = {
    atlas: () => {
      const text = "Class A GPCR Atlas, version " + m.version + " (pre-release). Data freeze " +
        m.data_version + ".";
      body.appendChild(el("p", { class: "muted", text: t("no_doi") }));
      body.appendChild(citationBlock(text, "cite_copy"));
      body.appendChild(el("p", { class: "notice",
        text: rm["code_licence_note_" + lang] || rm.code_licence_note_en }));
    },
    structure: async () => {
      // Without a family there is nothing to list, so send the reader somewhere they can pick one
      // rather than leaving the tab asking for a selection it offers no way to make.
      if (!slug) {
        body.appendChild(el("p", { class: "muted", text: t("cite_pick_family") }));
        body.appendChild(el("a", { class: "btn", href: "#view=landing", text: t("families") }));
        return;
      }
      body.appendChild(el("p", { class: "muted", text: t("loading") }));
      let structures = [], refs = null;
      try {
        const [list, references] = await Promise.all([
          L.loadFamilyFile(slug, "structures.json"), L.loadFamilyReferences(slug)]);
        structures = (list.structures || []).slice().sort((a, b) =>
          a.pdb_id.localeCompare(b.pdb_id));
        refs = references;
      } catch (error) {
        clear(body); body.appendChild(el("p", { class: "notice", text: L.errorMessage(error) })); return;
      }
      clear(body);
      let current = structures.find(s => s.pdb_id === pdb) || structures[0];
      if (!current) { body.appendChild(el("p", { class: "muted", text: t("no_results") })); return; }

      const picker = el("select", { "aria-label": t("cite_choose_structure") });
      for (const s of structures) picker.appendChild(el("option", { value: s.pdb_id,
        text: s.pdb_id + " — " + plainName(s.receptor_name || s.receptor_entry_name || "") }));
      picker.value = current.pdb_id;
      const output = el("div");
      body.append(el("label", { class: "filter-field cite-picker" }, [
        el("span", { text: t("cite_choose_structure") }), picker ]), output);

      const render = () => {
        clear(output);
        const id = current.pdb_id;
        output.appendChild(el("h3", { text: t("cite_deposited") }));
        output.appendChild(citationBlock("Protein Data Bank entry " + id +
          ". https://doi.org/10.2210/pdb" + id + "/pdb", "cite_copy_structure"));
        const reference = (refs.structure_sources || []).find(r => r.pdb_id === id);
        const citation = reference && reference.primary_citation;
        if (!citation) { output.appendChild(el("p", { class: "muted", text: t("cite_no_primary") })); return; }
        output.appendChild(el("h3", { text: t("cite_primary") }));
        output.appendChild(citationBlock(plainCitation(citation), "cite_copy_plain"));
        output.appendChild(el("h3", { text: "BibTeX" }));
        output.appendChild(citationBlock(bibtex(id, citation), "cite_copy_bibtex"));
      };
      picker.addEventListener("change", event => {
        current = structures.find(s => s.pdb_id === event.target.value) || current;
        pdb = current.pdb_id;
        // Keep the address bar in step so the citation for this structure can be linked to.
        navigate(Object.assign({}, parseRoute(), { pdb: current.pdb_id }), true);
        render();
      });
      render();
    },
    databases: () => {
      const cites = g.database_citations || {};
      const keys = Object.keys(cites).sort();
      if (!keys.length) { body.appendChild(el("p", { class: "muted", text: t("source_none") })); return; }
      for (const key of keys) {
        body.appendChild(el("h3", { class: "cite-db-label", text: databaseLabel(key) }));
        body.appendChild(citationBlock(plainCitation(cites[key]), "cite_copy"));
      }
      body.appendChild(el("p", { class: "muted small", text: t("cite_db_note") }));
    }
  };

  let active = "atlas";
  const draw = async () => {
    clear(body);
    for (const node of tabs.querySelectorAll("button"))
      node.setAttribute("aria-selected", node.dataset.tab === active ? "true" : "false");
    await panels[active]();
  };
  for (const [key, labelKey] of [["atlas", "cite_tab_atlas"], ["structure", "cite_tab_structure"],
    ["databases", "cite_tab_databases"]]) {
    const button = el("button", { class: "cite-tab", role: "tab", "data-tab": key,
      "aria-selected": "false", text: t(labelKey) });
    button.addEventListener("click", () => { active = key; draw(); });
    tabs.appendChild(button);
  }
  await draw();
  return wrap;
}
