/* Ligand explorer.
 *
 * The other views answer questions about depositions, so their result is a PDB entry. This one
 * answers questions about compounds, and a compound is not a deposition: adrenaline is one
 * molecule whether it was crystallised four times or forty. Listing PDB entries here made the
 * page a second copy of the structure list with a chemistry filter applied, and made the reader
 * count the same molecule once per deposition.
 *
 * So the unit here is the ligand entity, and depositions appear beneath one as its evidence.
 *
 * Two things the payload forces, both of which a purely component-keyed list would get wrong:
 *
 *   A quarter of the pharmacological observations carry no chemical component at all — 303 of
 *   them are polymer chains, peptides and proteins. They are ligands and they are the point of
 *   several families. They are keyed by name, listed beside the small molecules, and marked as
 *   what they are rather than dropped for being undrawable.
 *
 *   A ligand's pharmacological role is a property of the observation, not of the molecule.
 *   Retinal is an agonist at four receptors and an inverse agonist at three others; twenty-two
 *   components in this release carry more than one role. A card claiming a single role would be
 *   wrong for them, so roles are given per receptor context and the role filter selects
 *   observations rather than compounds.
 *
 * The class payloads overlap — forty-five depositions and ninety-five observations appear in more
 * than one file, because a structure is listed under every class its ligands belong to. Everything
 * here is deduplicated by observation id before it is counted.
 */
import { t, getLang, biologicalTypeLabel, siteClassLabel, stateLabel,
  transducerLabel, methodLabel } from "../core/i18n.js";
import { el, clear, debounce } from "../components/dom.js";
import { toCSV, download } from "../components/csv.js";
import * as L from "../data/loader.js";
import { navigate, buildHash } from "../core/router.js";
import { plainName, familyDisplayName } from "./names.js";
import { metricHelp } from "./views.js";
import { createSimilarityPanel, getRdkit } from "./chemsearch.js";

const CARD_PAGE = 60;

/* Why a ligand has no 2D depiction. The card used to guess from the biological type and call
   everything that was not a protein a peptide, which labelled an unresolved small molecule a
   peptide ligand. The reason is in the record: a polymer has no component code because it is a
   chain, and an unresolved ligand has none because it was annotated but never modelled. */
function noDepictionKey(entry) {
  const types = entry.biologicalTypes;
  if (types.has("protein")) return "lx_no_depiction_protein";
  if (types.has("peptide")) return "lx_no_depiction_peptide";
  if (entry.forms && entry.forms.has("unresolved")) return "lx_no_depiction_unresolved";
  return "lx_no_depiction_other";
}

/* Affinities run from picomolar to millimolar. Fixed decimals would print 0.00 at one end and
   eleven digits at the other, so the precision follows the magnitude. */
/* The strongest median a compound has, and the receptor it was measured at. "Strongest" is the
   lowest concentration, and binding constants are preferred over functional ones because Ki and
   Kd measure the same thing whereas an IC50 depends on the assay it came from. */
function strongestOf(rows) {
  if (!rows || !rows.length) return null;
  const rank = { Ki: 0, Kd: 0, IC50: 1, EC50: 1 };
  const best = rows.slice().sort((a, b) =>
    (rank[a.type] ?? 2) - (rank[b.type] ?? 2) || a.median_nm - b.median_nm)[0];
  return { ...best, receptors: new Set(rows.map(r => r.receptor)).size };
}

function fmtNm(value) {
  if (value == null) return "—";
  if (value < 1) return value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  if (value < 100) return value.toFixed(1).replace(/\.0$/, "");
  return Math.round(value).toLocaleString();
}

/* One entry per ligand entity. `key` distinguishes the two kinds so a peptide named after a
   component code could never collide with the component itself. */
function entityKey(observation) {
  const components = observation.ligand_components || [];
  if (components.length === 1) return "ccd:" + components[0];
  if (components.length > 1) return "ccd:" + components.slice().sort().join("+");
  return "name:" + plainName(observation.ligand_name || "").toLowerCase();
}

function buildIndex(payloads) {
  const structures = new Map();
  const observations = new Map();
  for (const payload of payloads) {
    for (const structure of payload.structures || []) {
      if (!structures.has(structure.pdb_id)) structures.set(structure.pdb_id, structure);
      for (const observation of structure.observations || [])
        if (!observations.has(observation.observation_id))
          observations.set(observation.observation_id, { structure, observation });
    }
  }
  /* An observation whose ligand was annotated but never resolved in the coordinates carries no
     chemical component, so keying on the component alone split such a compound in two: carazolol
     appeared once as CAU with twelve structures and again, undrawable, with three. They are one
     molecule. Where a componentless observation's name matches exactly one component-keyed
     compound, it joins that compound. Where the name would match two different components it is
     left alone rather than guessed at; in this release no name does. */
  const nameToKeys = new Map();
  for (const { observation } of observations.values()) {
    const components = observation.ligand_components || [];
    if (!components.length) continue;
    const name = plainName(observation.ligand_name || "").toLowerCase();
    if (!name) continue;
    if (!nameToKeys.has(name)) nameToKeys.set(name, new Set());
    nameToKeys.get(name).add(entityKey(observation));
  }
  const mergeInto = name => {
    const keys = nameToKeys.get(name);
    return keys && keys.size === 1 ? [...keys][0] : null;
  };

  const ligands = new Map();
  for (const { structure, observation } of observations.values()) {
    const components = observation.ligand_components || [];
    const key = components.length ? entityKey(observation)
      : (mergeInto(plainName(observation.ligand_name || "").toLowerCase()) || entityKey(observation));
    let entry = ligands.get(key);
    if (!entry) {
      const components = observation.ligand_components || [];
      entry = { key, components,
        name: plainName(observation.ligand_name || ""),
        forms: new Set(),
        roles: new Map(), receptors: new Set(), families: new Map(), structures: new Set(),
        siteClasses: new Set(), biologicalTypes: new Set(), species: new Set(),
        states: new Set(), transducers: new Set(), methods: new Set(),
        observations: [] };
      ligands.set(key, entry);
    }
    const receptor = structure.receptor_entry_name || structure.receptor_name || structure.pdb_id;
    const role = observation.binding_mode || t("unknown_role");
    if (!entry.roles.has(role)) entry.roles.set(role, new Set());
    entry.roles.get(role).add(receptor);
    entry.receptors.add(receptor);
    entry.families.set(structure.family_slug, structure.family_name);
    entry.structures.add(structure.pdb_id);
    if (observation.binding_site_class) entry.siteClasses.add(observation.binding_site_class);
    if (observation.biological_type) entry.biologicalTypes.add(observation.biological_type);
    if (observation.entity_form) entry.forms.add(observation.entity_form);
    if (structure.species) entry.species.add(structure.species);
    if (structure.structural_state) entry.states.add(structure.structural_state);
    if (structure.experimental_method) entry.methods.add(structure.experimental_method);
    for (const panel of structure.transducer_panels || []) entry.transducers.add(panel);
    entry.observations.push({ structure, observation, receptor, role });
  }
  return { ligands, structures, observations };
}

export async function ligandExplorer(root, initialLigand) {
  clear(root);
  const wrap = el("section", { class: "view ligand-explorer" });
  root.appendChild(wrap);
  wrap.appendChild(el("h2", {}, [document.createTextNode(t("lx_title") + " "),
    metricHelp(t("lx_help"))]));
  const status = el("p", { class: "muted", text: t("loading") });
  wrap.appendChild(status);

  let index, chemistry, catalog;
  const xrefs = new Map();
  let affinity = null;
  try {
    const classes = Object.keys(L.getManifest().ligand_files || {});
    const families = (L.getManifest().families || []).map(f => f.slug);
    const [payloads, chem, cat, xrefFiles] = await Promise.all([
      Promise.all(classes.map(slug => L.loadLigandStructures(slug))),
      L.loadLigandChemistry(),
      L.loadChemistryCatalog().catch(() => ({ patterns: {} })),
      /* Cross-references are per family; a compound seen in two of them has the same identifiers
         in both, so the first one wins and a missing file costs only its own links. */
      Promise.all(families.map(slug => L.loadLigandXrefs(slug).catch(() => null)))]);
    // Optional: a release built without the enrichment step simply shows no affinity section.
    affinity = await L.loadBindingAffinity().catch(() => null);
    index = buildIndex(payloads);
    chemistry = new Map((chem.records || []).map(r => [r.ccd, r]));
    catalog = cat;
    for (const file of xrefFiles) {
      for (const record of (file && file.records) || [])
        if (!xrefs.has(record.ccd)) xrefs.set(record.ccd, record);
    }
  } catch (error) {
    clear(status); status.className = "notice"; status.textContent = L.errorMessage(error); return wrap;
  }
  status.remove();
  wrap.appendChild(el("p", { class: "lx-lead", text: t("lx_lead") }));

  const all = [...index.ligands.values()];
  const hitOf = entry => simResult && entry.components.length === 1
    ? simResult.byCcd.get(entry.components[0]) : null;
  const scoreOf = entry => { const h = hitOf(entry); return h ? h.score : 0; };
  const strongest = entry => entry.components.length === 1 && affinity
    ? strongestOf((affinity.records || {})[entry.components[0]]) : null;
  const chemOf = entry => entry.components.length === 1 ? chemistry.get(entry.components[0]) : null;
  for (const entry of all) entry.chem = chemOf(entry);

  const filters = { roles: new Set(), biologicalTypes: new Set(), siteClasses: new Set(),
    functionalGroups: new Set(), ringSystems: new Set(), scaffolds: new Set(),
    families: new Set(), species: new Set(), states: new Set(), transducers: new Set(),
    methods: new Set(), affinity: new Set(), ranges: {}, query: "" };

  /* ------------------------------------------------------------------ header numbers */
  const statRow = el("div", { class: "summary-strip lx-stats" });
  wrap.appendChild(statRow);
  const statNodes = [];
  for (const [key, labelKey] of [["ligands", "lx_stat_ligands"], ["receptors", "lx_stat_receptors"],
    ["structures", "lx_stat_structures"], ["scaffolds", "lx_stat_scaffolds"]]) {
    const value = el("strong", { text: "—" });
    statRow.appendChild(el("div", { class: "summary-metric" }, [value, el("span", { text: t(labelKey) })]));
    statNodes.push({ key, value });
  }

  /* The query a reader arrives with a molecule for. It opens the page rather than sitting in a
     side rail, because on a page about compounds it is the first question, not an aside. */
  const querySlot = el("div", { class: "lx-query" });
  wrap.appendChild(querySlot);
  /* A query supersedes the default listing rather than answering into a strip beside it. The
     stat tiles, the role tabs, every facet count and the CSV all read the same filtered rows, so
     once the hits are the rows the whole page follows the query without any of it being special-
     cased. A reader who came to search should not be looking at 671 unrelated compounds. */
  let simResult = null;
  querySlot.appendChild(createSimilarityPanel({ onResults: payload => {
    simResult = payload && payload.hits && payload.hits.length
      ? { query: payload.query, byCcd: new Map(payload.hits.map(h => [h.ccd, h])) } : null;
    shown = CARD_PAGE; selected = null;
    draw();
    if (simResult) resultHead.scrollIntoView({ block: "start", behavior: "smooth" });
  } }));

  const layout = el("div", { class: "lx-layout" });
  const rail = el("aside", { class: "lx-rail" });
  const main = el("div", { class: "lx-main" });
  layout.appendChild(rail); layout.appendChild(main);
  wrap.appendChild(layout);

  /* ------------------------------------------------------------------ filters */
  const chipRow = el("div", { class: "lx-roles" });
  wrap.insertBefore(chipRow, layout);

  const searchInput = el("input", { type: "search", class: "lx-search",
    placeholder: t("lx_search_placeholder") });
  searchInput.addEventListener("input", debounce(() => {
    filters.query = searchInput.value.trim().toLowerCase(); draw(); }, 180));
  rail.appendChild(el("label", { class: "filter-field" }, [
    el("span", { text: t("lx_search") }), searchInput]));

  const countsOver = (rows, pick) => {
    const out = new Map();
    for (const entry of rows) for (const value of pick(entry)) {
      if (!out.has(value)) out.set(value, { ligands: 0, structures: new Set() });
      const bucket = out.get(value);
      bucket.ligands += 1;
      for (const pdb of entry.structures) bucket.structures.add(pdb);
    }
    return out;
  };

  /* A checkbox group over one field. Every count says how many ligands and how many depositions,
     because the two are different numbers and the page is about the first. */
  const groups = [];
  function checkGroup(labelKey, set, pick, labelOf, open) {
    const box = el("details", { class: "chem-facet lx-facet" });
    if (open) box.open = true;
    const count = el("span", { class: "chem-facet-count", text: "0" });
    box.appendChild(el("summary", {}, [el("span", { text: t(labelKey) }), count]));
    const list = el("div", { class: "chem-checks" });
    box.appendChild(list);
    rail.appendChild(box);
    const group = { set, pick, list, count, labelOf, rows: new Map() };
    groups.push(group);
    return group;
  }
  function paintGroup(group, rows) {
    const counts = countsOver(rows, group.pick);
    const universe = countsOver(all, group.pick);
    const entries = [...universe.keys()].sort((a, b) =>
      (counts.get(b)?.ligands || 0) - (counts.get(a)?.ligands || 0) || String(a).localeCompare(String(b)));
    if (!group.rows.size) {
      for (const value of entries) {
        const input = el("input", { type: "checkbox", value: String(value), onchange: e => {
          if (e.target.checked) group.set.add(value); else group.set.delete(value); draw(); } });
        const tally = el("span", { class: "chem-count" });
        // A scaffold's label is its SMILES and can be long; the row clips it and carries the
        // whole string on hover rather than widening the rail.
        const label = group.labelOf(value);
        const row = el("label", { class: "chem-check", title: label }, [input,
          el("span", { class: "lx-check-label", text: label }), tally]);
        group.list.appendChild(row);
        group.rows.set(value, { row, tally, input });
      }
    }
    let live = 0;
    for (const [value, node] of group.rows) {
      const bucket = counts.get(value);
      const n = bucket ? bucket.ligands : 0;
      node.tally.textContent = String(n);
      node.tally.title = t("lx_count_detail", { ligands: n, structures: bucket ? bucket.structures.size : 0 });
      node.row.classList.toggle("is-empty", n === 0 && !node.input.checked);
      if (n > 0) live += 1;
    }
    group.count.textContent = String(live);
  }

  const roleLabel = value => value;
  const facetOf = (entry, facet) => (entry.chem && entry.chem.facets && entry.chem.facets[facet]) || [];
  const patternLabel = name => {
    const spec = (catalog.patterns || {})[name] || {};
    return spec["label_" + getLang()] || spec.label_en || name;
  };

  /* Which compounds have a measured constant at all, and of what kind. It leads the rail because
     "only the ones somebody has measured" is a question asked before any question about chemistry,
     and because the answer is a small share of the list. */
  const affinityTypes = entry => {
    const rows = entry.components.length === 1 && affinity
      ? (affinity.records || {})[entry.components[0]] : null;
    if (!rows || !rows.length) return [];
    return ["any", ...new Set(rows.map(r => r.type))];
  };
  if (affinity) checkGroup("lx_affinity_filter", filters.affinity, affinityTypes,
    v => v === "any" ? t("lx_affinity_any") : v, true);
  checkGroup("lx_biological_type", filters.biologicalTypes, e => e.biologicalTypes,
    biologicalTypeLabel, true);
  checkGroup("lx_site_class", filters.siteClasses, e => e.siteClasses, siteClassLabel);
  checkGroup("chem_functional_groups", filters.functionalGroups,
    e => facetOf(e, "functional_groups"), patternLabel);
  checkGroup("chem_ring_systems", filters.ringSystems, e => facetOf(e, "ring_systems"), patternLabel);
  /* Scaffolds group compounds; a scaffold only one compound carries groups nothing, so as in the
     chemistry rail this lists only the ones two or more share. The label is the scaffold SMILES
     because the release does not name them — it computes them, and a name would claim a chemotype
     class that was never asserted. */
  const sharedScaffolds = new Map();
  for (const entry of all) {
    const scaffold = entry.chem && entry.chem.scaffold;
    if (scaffold) sharedScaffolds.set(scaffold, (sharedScaffolds.get(scaffold) || 0) + 1);
  }
  const scaffoldOf = entry => {
    const scaffold = entry.chem && entry.chem.scaffold;
    return scaffold && sharedScaffolds.get(scaffold) > 1 ? [scaffold] : [];
  };
  checkGroup("chem_scaffolds", filters.scaffolds, scaffoldOf, v => v);

  /* Descriptor ranges. Only components carry them: a peptide chain has no molecular weight in
     this release, and a range filter therefore excludes every peptide rather than judging it
     against a value it does not have. The note under the box says so. */
  const rangeResets = [];
  const rangeBox = el("details", { class: "chem-facet lx-facet" });
  rangeBox.appendChild(el("summary", {}, [el("span", { text: t("chem_descriptors") })]));
  const withDescriptors = all.filter(e => e.chem && e.chem.descriptors);
  for (const [field, labelKey, step] of [["mw", "chem_mw", 10], ["mollogp", "chem_logp", 0.5],
    ["tpsa", "chem_tpsa", 5], ["hbd", "chem_hbd", 1], ["hba", "chem_hba", 1],
    ["rotatable_bonds", "chem_rotb", 1], ["aromatic_rings", "chem_arom", 1]]) {
    const values = withDescriptors.map(e => e.chem.descriptors[field]).filter(v => v != null);
    if (!values.length) continue;
    const low = Math.floor(Math.min(...values)), high = Math.ceil(Math.max(...values));
    const decimals = step < 1 ? 2 : 0;
    const minInput = el("input", { type: "range", min: String(low), max: String(high),
      step: String(step), value: String(low), "aria-label": t(labelKey) + " min" });
    const maxInput = el("input", { type: "range", min: String(low), max: String(high),
      step: String(step), value: String(high), "aria-label": t(labelKey) + " max" });
    const readout = el("span", { class: "chem-range-value",
      text: low.toFixed(decimals) + " – " + high.toFixed(decimals) });
    const apply = () => {
      let a = Number(minInput.value), b = Number(maxInput.value);
      if (a > b) { [a, b] = [b, a]; minInput.value = String(a); maxInput.value = String(b); }
      readout.textContent = a.toFixed(decimals) + " – " + b.toFixed(decimals);
      filters.ranges[field] = (a <= low && b >= high) ? null : [a, b];
      draw();
    };
    const live = debounce(apply, 90);
    minInput.addEventListener("input", live); maxInput.addEventListener("input", live);
    rangeResets.push(() => {
      minInput.value = String(low); maxInput.value = String(high);
      readout.textContent = low.toFixed(decimals) + " – " + high.toFixed(decimals);
      filters.ranges[field] = null;
    });
    rangeBox.appendChild(el("div", { class: "chem-range" }, [
      el("span", { class: "chem-range-label", text: t(labelKey) }), readout,
      el("div", { class: "chem-sliders" }, [minInput, maxInput])]));
  }
  rangeBox.appendChild(el("p", { class: "chem-facet-note", text: t("lx_descriptor_note") }));
  rail.appendChild(rangeBox);

  /* Where the compound was seen, rather than what it is. Secondary and folded away: these are
     the structure view's questions, and a reader who came here for chemistry should not have to
     walk past them. */
  const evidenceBox = el("details", { class: "lx-evidence" });
  evidenceBox.appendChild(el("summary", { text: t("lx_evidence_filters") }));
  rail.appendChild(evidenceBox);
  const evidenceRail = el("div");
  evidenceBox.appendChild(evidenceRail);
  const railTarget = rail;
  for (const [labelKey, set, pick, labelOf] of [
    ["lx_family", filters.families, e => e.families.keys(), slug =>
      familyDisplayName(all.find(x => x.families.has(slug))?.families.get(slug) || slug)],
    ["lx_receptor_species", filters.species, e => e.species, v => v],
    ["state", filters.states, e => e.states, stateLabel],
    ["lx_transducer", filters.transducers, e => e.transducers, transducerLabel],
    ["lx_method", filters.methods, e => e.methods, methodLabel]]) {
    const group = checkGroup(labelKey, set, pick, labelOf);
    evidenceRail.appendChild(group.list.parentNode);
  }

  const resetButton = el("button", { class: "btn small lx-reset", type: "button",
    text: t("lx_reset"), onclick: () => {
      for (const group of groups) {
        group.set.clear();
        for (const node of group.rows.values()) node.input.checked = false;
      }
      for (const reset of rangeResets) reset();
      filters.ranges = {}; filters.query = ""; searchInput.value = "";
      draw();
    } });
  rail.insertBefore(el("div", { class: "chem-reset-row" }, [resetButton]), rail.firstChild.nextSibling);

  /* ------------------------------------------------------------------ selection */
  function passes(entry) {
    if (simResult && !(entry.components.length === 1 && simResult.byCcd.has(entry.components[0])))
      return false;
    if (filters.query) {
      const hay = (entry.name + " " + entry.components.join(" ") + " " +
        [...entry.receptors].join(" ")).toLowerCase();
      if (!hay.includes(filters.query)) return false;
    }
    if (filters.roles.size && ![...entry.roles.keys()].some(r => filters.roles.has(r))) return false;
    if (filters.affinity.size && !affinityTypes(entry).some(v => filters.affinity.has(v))) return false;
    for (const [set, pick] of [[filters.biologicalTypes, e => e.biologicalTypes],
      [filters.siteClasses, e => e.siteClasses], [filters.species, e => e.species],
      [filters.states, e => e.states], [filters.transducers, e => e.transducers],
      [filters.methods, e => e.methods]]) {
      if (set.size && ![...pick(entry)].some(v => set.has(v))) return false;
    }
    if (filters.families.size && ![...entry.families.keys()].some(v => filters.families.has(v))) return false;
    for (const [set, facet] of [[filters.functionalGroups, "functional_groups"],
      [filters.ringSystems, "ring_systems"]]) {
      if (set.size) {
        const have = facetOf(entry, facet);
        for (const want of set) if (!have.includes(want)) return false;
      }
    }
    if (filters.scaffolds.size && !scaffoldOf(entry).some(v => filters.scaffolds.has(v))) return false;
    for (const [field, span] of Object.entries(filters.ranges)) {
      if (!span) continue;
      const value = entry.chem && entry.chem.descriptors ? entry.chem.descriptors[field] : null;
      if (value == null || value < span[0] || value > span[1]) return false;
    }
    return true;
  }

  /* ------------------------------------------------------------------ results */
  const queryBanner = el("div", { class: "lx-banner" });
  const resultHead = el("div", { class: "result-head lx-head" });
  const grid = el("div", { class: "lx-grid" });
  const more = el("div", { class: "lx-more" });
  const detail = el("div", { class: "lx-detail" });
  main.appendChild(queryBanner); main.appendChild(resultHead); main.appendChild(grid); main.appendChild(more); main.appendChild(detail);

  let shown = CARD_PAGE;
  let selected = null;

  /* Depictions are drawn as they come into view. Five hundred molecules is more than a page needs
     at once, and RDKit is loaded on demand rather than on arrival. */
  const drawQueue = new Map();
  const observer = ("IntersectionObserver" in window) ? new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const job = drawQueue.get(entry.target);
      observer.unobserve(entry.target);
      drawQueue.delete(entry.target);
      if (job) job();
    }
  }, { rootMargin: "200px" }) : null;

  async function depict(node, smiles, width, height) {
    try {
      const mod = await getRdkit();
      const mol = mod.get_mol(smiles);
      if (!mol || !mol.is_valid || !mol.is_valid()) { if (mol) mol.delete(); return; }
      node.innerHTML = mol.get_svg(width, height);
      mol.delete();
    } catch (error) { /* a molecule that will not draw simply keeps its placeholder */ }
  }
  function schedule(node, smiles, width, height) {
    const job = () => depict(node, smiles, width, height);
    if (!observer) { job(); return; }
    drawQueue.set(node, job);
    observer.observe(node);
  }

  function roleSummary(entry) {
    return [...entry.roles.entries()]
      .sort((a, b) => b[1].size - a[1].size)
      .map(([role, receptors]) => ({ role, contexts: receptors.size }));
  }

  function card(entry) {
    const node = el("button", { class: "lx-card" + (entry === selected ? " active" : ""),
      type: "button", onclick: () => { selected = entry; draw(); detail.scrollIntoView({ block: "nearest" }); } });
    const art = el("div", { class: "lx-art" });
    if (entry.chem && entry.chem.raw_smiles) schedule(art, entry.chem.raw_smiles, 190, 140);
    else art.appendChild(el("span", { class: "lx-art-none", text: t(noDepictionKey(entry)) }));
    node.appendChild(art);
    const hit = hitOf(entry);
    if (hit) {
      const badge = el("div", { class: "lx-card-hit" }, [
        el("strong", { class: "lx-card-score", text: Math.round(hit.score * 100) + "%" }),
        el("button", { class: "lx-card-compare", type: "button", text: t("sim_compare_open"),
          title: t("sim_compare_enlarge"),
          onclick: e => { e.stopPropagation(); hit.openCompare(); } })]);
      node.appendChild(badge);
    }
    node.appendChild(el("div", { class: "lx-card-name", title: entry.name, text: entry.name || "—" }));
    node.appendChild(el("div", { class: "lx-card-id" },
      entry.components.length ? [el("code", { text: entry.components.join(" + ") })]
        : [el("span", { class: "lx-tag", text: biologicalTypeLabel([...entry.biologicalTypes][0] || "") })]));
    const roles = el("div", { class: "lx-card-roles" });
    for (const { role, contexts } of roleSummary(entry))
      roles.appendChild(el("span", { class: "lx-role",
        title: t("lx_role_contexts", { role, n: contexts }),
        text: role + " · " + contexts }));
    node.appendChild(roles);
    /* Weight and lipophilicity, then the strongest reported affinity where there is one. TPSA
       fills that third slot only when there is not: a measured constant is what a reader came for,
       and a polar surface area is what can be said when nobody has published one. The chip names
       the receptor it belongs to, because an affinity with no target attached is not a fact about
       anything — the full table is in the detail. */
    const d = (entry.chem && entry.chem.descriptors) || null;
    const best = strongest(entry);
    if (d || best) {
      const parts = [];
      if (d) parts.push("MW " + Math.round(d.mw));
      if (d && d.mollogp != null) parts.push("logP " + d.mollogp.toFixed(1));
      if (!best && d && d.tpsa != null) parts.push("TPSA " + Math.round(d.tpsa));
      const line = el("div", { class: "lx-card-props", title: t("lx_props_hint"),
        text: parts.join(" · ") });
      if (best) {
        line.appendChild(el("span", { class: "lx-card-aff",
          title: t("lx_card_aff_hint", { receptor: best.receptor, n: best.n, receptors: best.receptors }),
          text: " · " + best.type + " " + fmtNm(best.median_nm) + " nM" }));
      }
      node.appendChild(line);
    }
    node.appendChild(el("div", { class: "lx-card-counts", text:
      t("lx_card_counts", { receptors: entry.receptors.size, families: entry.families.size,
                            structures: entry.structures.size }) }));
    /* Under a query the card is the hit, so it carries what the hit row carried: the deposition
       the pipeline ranks sharpest for this compound, opening its pocket in 3D. Without it the
       reader would have to select the card and cross the detail table to reach the same place. */
    const place = hit && hit.rec && (hit.rec.seen_in || [])[0];
    if (place) {
      const pocket = el("a", { class: "lx-card-pocket", target: "_blank", rel: "noopener",
        href: "#" + buildHash({ family: place.family, view: "3d", pdb: place.pdb_id }).slice(1),
        title: t("lx_open_structure", { pdb: place.pdb_id }),
        onclick: e => e.stopPropagation() }, [
        el("code", { text: place.pdb_id }),
        el("span", { text: t("sim_open_pocket") })]);
      node.appendChild(pocket);
    }
    return node;
  }

  function drawDetail() {
    clear(detail);
    if (!selected) return;
    const entry = selected;
    const head = el("div", { class: "lx-detail-head" });
    head.appendChild(el("h3", { text: entry.name || entry.components.join(" + ") }));
    if (entry.components.length)
      head.appendChild(el("code", { class: "lx-detail-ccd", text: entry.components.join(" + ") }));
    head.appendChild(el("button", { class: "btn small", type: "button", text: t("lx_close_detail"),
      onclick: () => { selected = null; draw(); } }));
    detail.appendChild(head);

    const body = el("div", { class: "lx-detail-body" });
    const art = el("figure", { class: "lx-detail-art" });
    if (entry.chem && entry.chem.raw_smiles) schedule(art, entry.chem.raw_smiles, 320, 260);
    else art.appendChild(el("span", { class: "lx-art-none", text: t(noDepictionKey(entry)) }));
    body.appendChild(art);

    const facts = el("dl", { class: "lx-facts" });
    const fact = (label, value) => {
      if (value == null || value === "") return;
      facts.appendChild(el("dt", { text: label })); facts.appendChild(el("dd", { text: String(value) }));
    };
    const d = (entry.chem && entry.chem.descriptors) || {};
    fact(t("lx_formula"), entry.chem && entry.chem.formula);
    fact(t("chem_mw"), d.mw != null ? d.mw.toFixed(1) : null);
    fact(t("chem_logp"), d.mollogp != null ? d.mollogp.toFixed(2) : null);
    fact(t("chem_tpsa"), d.tpsa != null ? d.tpsa.toFixed(1) : null);
    fact(t("chem_hbd") + " / " + t("chem_hba"),
      d.hbd != null && d.hba != null ? d.hbd + " / " + d.hba : null);
    fact(t("lx_inchikey"), entry.chem && entry.chem.inchikey);
    fact(t("lx_biological_type"),
      [...entry.biologicalTypes].map(biologicalTypeLabel).join(", "));
    fact(t("lx_site_class"), [...entry.siteClasses].map(siteClassLabel).join(", "));
    body.appendChild(facts);
    detail.appendChild(body);

    const groupsFound = [...(entry.chem?.facets?.functional_groups || []),
                         ...(entry.chem?.facets?.ring_systems || [])];
    if (groupsFound.length) {
      const chips = el("div", { class: "lx-chips" });
      chips.appendChild(el("span", { class: "muted small", text: t("lx_chemistry_facets") }));
      for (const name of groupsFound) chips.appendChild(el("span", { class: "lx-tag", text: patternLabel(name) }));
      detail.appendChild(chips);
    }

    /* Where the pharmacology is. This release carries no affinity or potency value: what ChEMBL
       and GtoPdb publish is content under CC BY-SA, and the release's position that their
       share-alike terms are not engaged rests on carrying none of it. So the reader is sent to
       the entry rather than shown a number that would change the licence of everything here.
       See SOURCE_DATA_LICENSES.md. */
    const xref = entry.components.length === 1 ? xrefs.get(entry.components[0]) : null;
    if (xref) {
      const links = el("div", { class: "lx-chips lx-xrefs" });
      links.appendChild(el("span", { class: "muted small", text: t("lx_pharmacology_at") }));
      for (const [source, label] of [["gtopdb", "db_label_gtopdb"], ["chembl", "db_label_chembl"],
        ["pubchem", "db_label_pubchem"]]) {
        const ref = xref[source];
        if (!ref || !ref.url) continue;
        links.appendChild(el("a", { class: "lx-xref", href: ref.url, target: "_blank",
          rel: "noopener", title: t("lx_xref_hint", { basis: ref.basis || "", date: ref.retrieved || "" }),
          text: t(label) + " " + ref.id + (ref.approximate ? " ≈" : "") }));
      }
      if (links.childNodes.length > 1) detail.appendChild(links);
    }

    /* Reported affinity, where BindingDB's staff-curated subset has any. It is deliberately not
       folded into the context table above: that table is what this atlas observed in a structure,
       and this is what someone else measured in an assay, usually on a different construct and
       sometimes a different species. Keeping them apart is the point. Values are given as a
       median over the measurements with their range and the papers they came from, because a
       single number would hide that assays disagree. */
    const measured = affinity && entry.components.length === 1
      ? (affinity.records || {})[entry.components[0]] : null;
    if (measured && measured.length) {
      detail.appendChild(el("h4", { text: t("lx_affinity_heading") }));
      const table = el("table", { class: "data compact lx-affinity" });
      table.appendChild(el("thead", {}, el("tr", {}, [t("lx_receptor"), t("lx_affinity_type"),
        t("lx_affinity_value"), t("lx_affinity_n"), t("lx_affinity_papers")]
        .map(x => el("th", {}, x)))));
      const body = el("tbody");
      for (const row of measured) {
        const spread = row.n > 1 && row.min_nm !== row.max_nm
          ? fmtNm(row.min_nm) + " – " + fmtNm(row.max_nm) : "";
        const papers = el("td", { class: "lx-pmids" });
        for (const pmid of row.pmids)
          papers.appendChild(el("a", { class: "lx-pmid", target: "_blank", rel: "noopener",
            href: "https://pubmed.ncbi.nlm.nih.gov/" + pmid + "/", text: pmid }));
        body.appendChild(el("tr", {}, [
          el("td", {}, [el("strong", { text: row.receptor })]),
          el("td", { text: row.type }),
          el("td", {}, [el("strong", { text: fmtNm(row.median_nm) + " nM" }),
            spread ? el("span", { class: "muted small", text: " (" + spread + ")" })
                   : document.createTextNode("")]),
          el("td", { text: String(row.n) }),
          papers]));
      }
      table.appendChild(body);
      detail.appendChild(table);
      detail.appendChild(el("p", { class: "muted small lx-affinity-note",
        text: t("lx_affinity_measured_note") }));
    } else if (entry.components.length === 1 && affinity) {
      detail.appendChild(el("p", { class: "muted small lx-affinity-note", text:
        t("lx_affinity_none", { with: affinity.coverage.components_with_values,
                                total: affinity.coverage.components_total }) }));
    }

    /* Roles, spelled out per receptor. This is the table that a single role label on the card
       would have flattened, and for twenty-two components in this release it differs by row. */
    detail.appendChild(el("h4", { text: t("lx_where_seen") }));
    const table = el("table", { class: "data compact lx-contexts" });
    table.appendChild(el("thead", {}, el("tr", {}, [t("lx_receptor"), t("lx_family"),
      t("lx_role"), t("lx_site_class"), t("lx_structures_col")].map(x => el("th", {}, x)))));
    const tbody = el("tbody");
    const byContext = new Map();
    for (const row of entry.observations) {
      const key = row.receptor + "|" + row.role;
      if (!byContext.has(key)) byContext.set(key, { receptor: row.receptor, role: row.role,
        family: row.structure.family_name, slug: row.structure.family_slug,
        sites: new Set(), pdbs: new Set() });
      const bucket = byContext.get(key);
      if (row.observation.binding_site_class) bucket.sites.add(row.observation.binding_site_class);
      bucket.pdbs.add(row.structure.pdb_id);
    }
    for (const bucket of [...byContext.values()].sort((a, b) => b.pdbs.size - a.pdbs.size)) {
      /* Links rather than buttons, opening the 3D panel in a new tab: a reader working through a
         ligand's contexts is comparing them, and replacing the page they are comparing from is
         the wrong move. Every structure in this release carries a viewer bundle, so the 3D route
         is safe for all of them. */
      const pdbCell = el("td", { class: "lx-pdbs" });
      for (const pdb of [...bucket.pdbs].sort())
        pdbCell.appendChild(el("a", { class: "lx-pdb", text: pdb, target: "_blank", rel: "noopener",
          title: t("lx_open_structure", { pdb }),
          href: "#" + buildHash({ family: bucket.slug, view: "3d", pdb }).slice(1) }));
      tbody.appendChild(el("tr", {}, [
        el("td", {}, [el("strong", { text: bucket.receptor })]),
        el("td", { text: familyDisplayName(bucket.family || bucket.slug) }),
        el("td", {}, [el("span", { class: "lx-role", text: bucket.role })]),
        el("td", { text: [...bucket.sites].map(siteClassLabel).join(", ") }),
        pdbCell]));
    }
    table.appendChild(tbody);
    detail.appendChild(table);
    detail.appendChild(el("p", { class: "muted small", text: t("lx_evidence_note") }));
  }

  function draw() {
    const rows = all.filter(passes);
    // Under a query the ranking is the answer, so it wins over the default order.
    if (simResult) rows.sort((a, b) => scoreOf(b) - scoreOf(a));
    else rows.sort((a, b) => b.structures.size - a.structures.size ||
      (a.name || "").localeCompare(b.name || ""));
    for (const group of groups) paintGroup(group, rows);
    paintRoles(rows);

    const receptors = new Set(), structures = new Set(), scaffolds = new Set();
    for (const entry of rows) {
      for (const r of entry.receptors) receptors.add(r);
      for (const p of entry.structures) structures.add(p);
      if (entry.chem && entry.chem.scaffold) scaffolds.add(entry.chem.scaffold);
    }
    const values = { ligands: rows.length, receptors: receptors.size,
                     structures: structures.size, scaffolds: scaffolds.size };
    for (const node of statNodes) node.value.textContent = String(values[node.key]);

    clear(resultHead); clear(grid); clear(more); clear(queryBanner);
    if (simResult) {
      queryBanner.appendChild(el("span", { class: "lx-banner-mark", text: t("lx_query_active") }));
      queryBanner.appendChild(el("code", { class: "lx-banner-query", text: simResult.query }));
      queryBanner.appendChild(el("span", { class: "muted small", text: t("lx_query_ranked") }));
      queryBanner.appendChild(el("button", { class: "btn small", type: "button",
        text: t("lx_query_clear"), onclick: () => {
          simResult = null; shown = CARD_PAGE; selected = null;
          const input = wrap.querySelector(".sim-input");
          if (input) input.value = "";
          const status = wrap.querySelector(".sim-status");
          if (status) status.textContent = "";
          const alt = wrap.querySelector(".sim-alt");
          if (alt) clear(alt);
          draw();
        } }));
    }
    resultHead.appendChild(el("strong", { text: t("lx_results", { n: rows.length }) }));
    resultHead.appendChild(el("span", { class: "muted small",
      text: t("lx_results_evidence", { structures: structures.size, receptors: receptors.size }) }));
    resultHead.appendChild(el("button", { class: "btn small", type: "button", text: t("export_csv"),
      onclick: () => exportRows(rows) }));

    if (!rows.length) grid.appendChild(el("p", { class: "muted", text: t("no_results") }));
    for (const entry of rows.slice(0, shown)) grid.appendChild(card(entry));
    if (rows.length > shown)
      more.appendChild(el("button", { class: "btn", type: "button",
        text: t("lx_show_more", { n: Math.min(CARD_PAGE, rows.length - shown), total: rows.length }),
        onclick: () => { shown += CARD_PAGE; draw(); } }));
    drawDetail();
  }

  function paintRoles(rows) {
    const counts = new Map();
    for (const entry of all) {
      for (const role of entry.roles.keys()) {
        if (!counts.has(role)) counts.set(role, { ligands: 0, structures: new Set() });
      }
    }
    for (const entry of rows) {
      for (const [role, receptors] of entry.roles) {
        const bucket = counts.get(role);
        bucket.ligands += 1;
        for (const row of entry.observations) if (row.role === role) bucket.structures.add(row.structure.pdb_id);
      }
    }
    clear(chipRow);
    chipRow.appendChild(el("span", { class: "muted small", text: t("lx_role_filter") }));
    for (const [role, bucket] of [...counts.entries()].sort((a, b) => b[1].ligands - a[1].ligands)) {
      const on = filters.roles.has(role);
      // Dimmed rather than dropped, as the facet rows are: the option still exists, it is the
      // current selection that puts it out of reach.
      chipRow.appendChild(el("button", { class: "lx-role-tab" + (on ? " active" : "")
        + (bucket.ligands === 0 && !on ? " is-empty" : ""), type: "button",
        "aria-pressed": on ? "true" : "false",
        onclick: () => { if (on) filters.roles.delete(role); else filters.roles.add(role);
                         shown = CARD_PAGE; draw(); } }, [
        el("span", { text: role }),
        // Both numbers, because "Agonist 917" was read as 917 agonists.
        el("span", { class: "tab-count", text: t("lx_tab_counts",
          { ligands: bucket.ligands, structures: bucket.structures.size }) })]));
    }
  }

  function exportRows(rows) {
    // Whatever the page is showing, including the query's ranking when there is one.
    const cols = [
      ...(simResult ? [{ key: "similarity", label: "tanimoto_similarity",
        get: r => scoreOf(r).toFixed(4) }] : []),
      { key: "name", label: "ligand_name" },
      { key: "components", label: "chemical_components", get: r => r.components.join("+") },
      { key: "roles", label: "roles_by_receptor_context",
        get: r => roleSummary(r).map(x => x.role + ":" + x.contexts).join("; ") },
      { key: "receptors", label: "receptors", get: r => r.receptors.size },
      { key: "families", label: "families", get: r => r.families.size },
      { key: "structures", label: "structures", get: r => r.structures.size },
      { key: "pdb_ids", label: "pdb_ids", get: r => [...r.structures].sort().join(" ") },
      { key: "mw", label: "mw", get: r => r.chem?.descriptors?.mw ?? "" },
      { key: "mollogp", label: "mollogp", get: r => r.chem?.descriptors?.mollogp ?? "" },
      { key: "inchikey", label: "inchikey", get: r => r.chem?.inchikey ?? "" }];
    download(simResult ? "ligands_similar.csv" : "ligands.csv", toCSV(cols, rows, {
      release: L.getManifest().data_version || "", rows: rows.length,
      unit: "one row per ligand entity; role counts are distinct receptors",
      ...(simResult ? { query: simResult.query,
        ranking: "Tanimoto over Morgan fingerprints, radius 2, 2048 bits" } : {}) }));
  }

  if (initialLigand) {
    selected = all.find(e => e.components.includes(initialLigand)) ||
               all.find(e => e.key === initialLigand) || null;
  }
  draw();
  return wrap;
}
