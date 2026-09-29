/* Family contact map, split by ligand class and distance threshold.
 *
 * The structure list can already be filtered to one ligand class and its contacts exported, and
 * a reader who counted those exports by hand got this map. That was the only way to get it, which
 * is reason enough for it to be a view. It reads nothing the exports do not carry: the family's
 * pocket detail (every receptor residue within 5 Å of a ligand, with its closest heavy-atom
 * distance) and its structure list (which ligand is which class).
 *
 * Four decisions, each of which changes the picture if made the other way:
 *
 *   A contact belongs to the ligand that made it, not to the structure. A ternary complex holds an
 *   agonist and a modulator; counting the modulator's contacts as agonist contacts because the
 *   structure is "agonist-bound" puts the allosteric site into the orthosteric map. Contacts are
 *   matched to the observation whose chemical component made them. A polymer ligand has no
 *   component code, so its contacts go to the structure's polymer observation; anything that
 *   still cannot be placed is counted and reported, never guessed.
 *
 *   The receptor is the unit. By default a position's value is the mean over receptors of the
 *   share of that receptor's structures contacting it, so a receptor solved eighty times speaks
 *   once. Structure weighting is offered beside it, because the difference between the two is
 *   itself informative.
 *
 *   One binding-site class at a time. A peptide on the extracellular surface and a small molecule
 *   in the bundle are different objects and never share a denominator.
 *
 *   Every threshold is shown, not one. A contact map drawn at one cut-off is a statement about that
 *   cut-off; the three rows per class show how much of the picture is the threshold.
 *
 * The whole state lives in the URL, like the motif panel's.
 */
import { t, siteClassLabel, ligandClassLabel, getLang } from "../core/i18n.js";
import { el, clear } from "../components/dom.js";
import { toCSV, download } from "../components/csv.js";
import { downloadXLSX } from "../components/xlsx.js";
import * as L from "../data/loader.js";
import { navigate, buildHash } from "../core/router.js";
import { familyDisplayName, plainName, metricHelp } from "./views.js";

const THRESHOLDS = [4.0, 4.5, 5.0];
const DEFAULT_FAMILY = "ca-001-001";
const DEFAULT_SITE = "canonical_7tm_pocket";
const DEFAULT_MIN = 40;
const SMALL_N = 5;

/* Ligand groups a reader can put on either side. The two defaults are the comparison people ask
   for; the singles are there so that a pooled group can be taken apart. */
const GROUPS = {
  ag:      ["Agonist", "Agonist (partial)"],
  full:    ["Agonist"],
  partial: ["Agonist (partial)"],
  ant:     ["Antagonist", "Inverse agonist"],
  antonly: ["Antagonist"],
  inv:     ["Inverse agonist"],
  pam:     ["PAM", "Ago-PAM"],
  nam:     ["NAM"],
  all:     null
};
const GROUP_ORDER = ["ag", "full", "partial", "ant", "antonly", "inv", "pam", "nam", "all"];
const METHODS = { xray: "X-RAY DIFFRACTION", em: "ELECTRON MICROSCOPY" };

function groupLabel(id) {
  if (id === "ag") return t("cm_group_ag");
  if (id === "ant") return t("cm_group_ant");
  if (id === "all") return t("cm_group_all");
  return GROUPS[id].map(ligandClassLabel).join(" + ");
}

function stateFromRoute(r) {
  const num = (v, lo, hi, d) => Number.isFinite(Number(v)) && v !== undefined && v !== ""
    ? Math.max(lo, Math.min(hi, Number(v))) : d;
  return {
    fam: String(r.fam || r.family || DEFAULT_FAMILY),
    site: String(r.site || DEFAULT_SITE),
    a: GROUPS[r.a] !== undefined ? r.a : "ag",
    b: GROUPS[r.b] !== undefined ? r.b : "ant",
    weight: r.w === "structure" ? "structure" : "receptor",
    rep: r.rep !== "0",
    method: METHODS[r.meth] ? r.meth : "",
    min: num(r.min, 0, 100, DEFAULT_MIN),
    delta: THRESHOLDS.includes(Number(r.d)) ? Number(r.d) : THRESHOLDS[0],
    sort: r.sort === "delta" ? "delta" : "position",
    pos: String(r.pos || "")
  };
}
function routeFromState(s, route) {
  const r = { view: "contactmap" };
  if (route && route.family) r.family = route.family;
  if (!route || s.fam !== route.family) r.fam = s.fam;
  if (s.site !== DEFAULT_SITE) r.site = s.site;
  if (s.a !== "ag") r.a = s.a;
  if (s.b !== "ant") r.b = s.b;
  if (s.weight !== "receptor") r.w = s.weight;
  if (!s.rep) r.rep = "0";
  if (s.method) r.meth = s.method;
  if (s.min !== DEFAULT_MIN) r.min = String(s.min);
  if (s.delta !== THRESHOLDS[0]) r.d = String(s.delta);
  if (s.sort !== "position") r.sort = s.sort;
  if (s.pos) r.pos = s.pos;
  return r;
}

/* Generic positions in helix order, loops between the helices they join: 45x52 sorts after TM4
   and before TM5, not after TM7. */
function positionKey(gn) {
  const m = /^(\d+)x(\d+)$/.exec(gn || "");
  if (!m) return 1e9;
  const seg = m[1].length === 2 ? Number(m[1][0]) + 0.5 : Number(m[1]);
  const idx = m[2].length === 3 ? Number(m[2].slice(0, 2)) + Number(m[2][2]) / 10 : Number(m[2]);
  return seg * 1000 + idx;
}

/* Contacts of one family, each assigned to the binding mode of the ligand that made it.
   Returns per structure: { receptor, modes: Map(mode -> Map(position -> distance)) }. */
function assign(structures, pocket, site) {
  const byPdb = new Map(structures.map(s => [s.pdb_id, s]));
  const out = new Map();
  let unassigned = 0;
  const segmentOf = new Map();
  for (const record of pocket.structures || []) {
    const s = byPdb.get(record.pdb_id);
    if (!s) continue;
    const byComponent = new Map(), polymerModes = new Set(), allModes = new Set();
    for (const o of s.observations || []) {
      if (!o.binding_mode) continue;
      allModes.add(o.binding_mode);
      const comps = o.ligand_components || [];
      for (const c of comps) {
        if (!byComponent.has(c)) byComponent.set(c, new Set());
        byComponent.get(c).add(o.binding_mode);
      }
      if (!comps.length || o.is_polymer_interface) polymerModes.add(o.binding_mode);
    }
    for (const segment of record.segments || []) for (const r of segment.residues || []) {
      if (r.binding_site_class !== site || !r.generic_number) continue;
      let modes = byComponent.get(r.ligand_residue_name);
      if (!modes || modes.size !== 1) modes = polymerModes.size === 1 ? polymerModes : null;
      if (!modes && allModes.size === 1) modes = allModes;
      if (!modes || modes.size !== 1) { unassigned++; continue; }
      const mode = [...modes][0];
      if (!segmentOf.has(r.generic_number)) segmentOf.set(r.generic_number, segment.segment);
      if (!out.has(s.pdb_id)) out.set(s.pdb_id, { structure: s, modes: new Map() });
      const entry = out.get(s.pdb_id);
      if (!entry.modes.has(mode)) entry.modes.set(mode, new Map());
      const cell = entry.modes.get(mode);
      const d = Number(r.distance_angstrom);
      if (!cell.has(r.generic_number) || d < cell.get(r.generic_number)) cell.set(r.generic_number, d);
    }
  }
  return { perStructure: out, unassigned, segmentOf };
}

/* One side of the comparison: which structures it holds, grouped by receptor, and the contact
   frequency of every position at every threshold. */
function side(assigned, groupId, s) {
  const modes = GROUPS[groupId];
  const byReceptor = new Map();
  let contacts = 0;
  for (const { structure, modes: m } of assigned.perStructure.values()) {
    if (s.rep && structure.analysis_unit_representative !== true) continue;
    if (s.method && structure.experimental_method !== METHODS[s.method]) continue;
    const merged = new Map(), seen = [];
    for (const [mode, cell] of m) {
      if (modes && !modes.includes(mode)) continue;
      seen.push(mode);
      for (const [p, d] of cell) if (!merged.has(p) || d < merged.get(p)) merged.set(p, d);
    }
    if (!merged.size) continue;
    contacts += merged.size;
    const key = structure.receptor_entry_name || structure.receptor_name;
    if (!byReceptor.has(key)) byReceptor.set(key, { name: structure.receptor_name, structures: [],
      modes: new Map() });
    const rec = byReceptor.get(key);
    rec.structures.push({ pdb: structure.pdb_id, contacts: merged });
    for (const mode of seen) rec.modes.set(mode, (rec.modes.get(mode) || 0) + 1);
  }
  const nStructures = [...byReceptor.values()].reduce((n, r) => n + r.structures.length, 0);
  const freq = new Map();       // position -> [value at each threshold]
  const perReceptor = new Map(); // position -> [{receptor, share at each threshold}]
  const positions = new Set();
  for (const r of byReceptor.values()) for (const x of r.structures) for (const p of x.contacts.keys())
    positions.add(p);
  for (const p of positions) {
    const values = THRESHOLDS.map(th => {
      if (s.weight === "structure") {
        let hit = 0;
        for (const r of byReceptor.values()) for (const x of r.structures)
          if (x.contacts.has(p) && x.contacts.get(p) <= th) hit++;
        return nStructures ? hit / nStructures : null;
      }
      let sum = 0;
      for (const r of byReceptor.values()) {
        const hit = r.structures.filter(x => x.contacts.has(p) && x.contacts.get(p) <= th).length;
        sum += hit / r.structures.length;
      }
      return byReceptor.size ? sum / byReceptor.size : null;
    });
    freq.set(p, values);
    perReceptor.set(p, [...byReceptor.values()].map(r => ({
      name: r.name, n: r.structures.length,
      // The structure list filters on one class at a time, so a link opens the class this
      // receptor's structures in the group mostly carry.
      mode: [...r.modes.entries()].sort((x, y) => y[1] - x[1])[0][0],
      modeCount: [...r.modes.entries()].sort((x, y) => y[1] - x[1])[0][1],
      shares: THRESHOLDS.map(th => r.structures.filter(x => x.contacts.has(p) &&
        x.contacts.get(p) <= th).length / r.structures.length) })));
  }
  return { receptors: byReceptor.size, structures: nStructures, contacts, freq, perReceptor };
}

/* Colours are read from the theme, so the map follows light and dark without a second palette in
   code. Sequential: one hue, surface to dark. Diverging: two hues through a neutral grey. */
function palette() {
  const cs = getComputedStyle(document.documentElement);
  const v = (name, d) => (cs.getPropertyValue(name) || d).trim() || d;
  return { lo: v("--cm-lo", "#f4f8fd"), hi: v("--cm-hi", "#0d366b"),
           neg: v("--cm-neg", "#c43c3b"), mid: v("--cm-mid", "#f0efec"), pos: v("--cm-pos", "#1c5cab") };
}
function hex(c) {
  const m = /^#?([0-9a-f]{6})$/i.exec(c);
  if (!m) return [128, 128, 128];
  const n = parseInt(m[1], 16);
  return [n >> 16, (n >> 8) & 255, n & 255];
}
function mix(a, b, f) {
  const x = hex(a), y = hex(b);
  return "rgb(" + x.map((v, i) => Math.round(v + (y[i] - v) * f)).join(",") + ")";
}
function luminance(rgb) {
  const [r, g, b] = rgb.match(/\d+/g).map(Number);
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}
const pctText = v => v === null || v === undefined ? "—" : Math.round(v * 100) + "%";
const signed = v => (v > 0 ? "+" : v < 0 ? "−" : "±") + Math.abs(Math.round(v * 100)) + "%";

export async function contactMap(root, route) {
  clear(root);
  const wrap = el("section", { class: "view cm" });
  root.appendChild(wrap);
  let currentRoute = route;
  let state = stateFromRoute(route);
  let data = null, token = 0;

  const manifest = L.getManifest();
  const families = (manifest.families || []).slice();
  if (!families.some(f => f.slug === state.fam)) state.fam = DEFAULT_FAMILY;

  wrap.appendChild(el("h2", { text: t("cm_title") }));
  wrap.appendChild(el("p", { class: "muted cm-intro", text: t("cm_intro") }));
  const controls = el("div", { class: "cm-controls filter-block" });
  const summary = el("div", { class: "cm-summary", "aria-live": "polite" });
  const body = el("div", { class: "cm-body" });
  const detail = el("aside", { class: "cm-detail", "aria-live": "polite" });
  wrap.append(controls, summary, body, detail,
    el("p", { class: "muted small cm-limit", text: t("cm_limit") }));

  function update(patch) {
    const reload = patch.fam !== undefined && patch.fam !== state.fam ||
                   patch.site !== undefined && patch.site !== state.site;
    state = Object.assign({}, state, patch);
    const next = routeFromState(state, currentRoute);
    currentRoute = Object.assign({}, next);
    navigate(next, true);
    if (reload) load(); else { drawControls(); draw(); }
  }

  function select(label, help, value, options, onchange) {
    const s = el("select", { "aria-label": label, onchange: e => onchange(e.target.value) });
    for (const [v, text] of options) s.appendChild(el("option", { value: v, text, selected: v === value }));
    return el("label", { class: "filter-field" }, [
      el("span", {}, [label + (help ? " " : ""), help ? metricHelp(help) : null]), s]);
  }

  function drawControls() {
    clear(controls);
    const sites = data ? data.sites : [[state.site, siteClassLabel(state.site)]];
    const groups = GROUP_ORDER.map(id => [id, groupLabel(id)]);
    const grid = el("div", { class: "filter-grid cm-grid" }, [
      select(t("receptor_family"), null, state.fam,
        families.map(f => [f.slug, familyDisplayName(f.name)]), v => update({ fam: v, pos: "" })),
      select(t("site_class"), t("cm_site_help"), state.site, sites, v => update({ site: v, pos: "" })),
      select(t("cm_side_a"), null, state.a, groups, v => update({ a: v })),
      select(t("cm_side_b"), null, state.b, groups, v => update({ b: v })),
      select(t("weighting"), t("cm_weight_help"), state.weight,
        [["receptor", t("cm_weight_receptor")], ["structure", t("cm_weight_structure")]],
        v => update({ weight: v })),
      select(t("method"), t("cm_method_help"), state.method,
        [["", t("all")], ["xray", t("em_x_ray_diffraction")], ["em", t("em_electron_microscopy")]],
        v => update({ method: v })),
      select(t("cm_delta"), null, String(state.delta),
        THRESHOLDS.map(th => [String(th), "≤ " + th.toFixed(1) + " Å"]), v => update({ delta: Number(v) })),
      select(t("cm_sort"), null, state.sort,
        [["position", t("cm_sort_position")], ["delta", t("cm_sort_delta")]], v => update({ sort: v }))
    ]);
    const rep = el("input", { type: "checkbox", checked: state.rep,
      onchange: e => update({ rep: e.target.checked }) });
    const minValue = el("span", { class: "threshold-value", text: state.min + "%" });
    const min = el("input", { type: "range", min: "0", max: "100", step: "5", value: String(state.min),
      "aria-label": t("cm_min"),
      oninput: e => { minValue.textContent = e.target.value + "%"; },
      onchange: e => update({ min: Number(e.target.value) }) });
    controls.append(grid,
      el("div", { class: "cm-row" }, [
        el("label", { class: "rep-toggle" }, [rep, el("span", { text: t("representative_only") }),
          metricHelp(t("representative_only_help"))]),
        el("div", { class: "cm-min" }, [
          el("span", { class: "threshold-label" }, [t("cm_min") + " ", metricHelp(t("cm_min_help"))]),
          min, minValue])
      ]));
  }

  async function load() {
    const my = ++token;
    clear(body); clear(summary); clear(detail);
    body.appendChild(el("p", { class: "muted", text: t("loading_family") }));
    try {
      const [st, pocket] = await Promise.all([
        L.loadFamilyFile(state.fam, "structures.json"), L.loadPocketDetail(state.fam)]);
      if (my !== token) return;
      const siteCounts = new Map();
      for (const rec of pocket.structures || []) for (const seg of rec.segments || [])
        for (const r of seg.residues || [])
          // Unresolved is not a site: the atlas keeps it out of every pooled summary, and so does this.
          if (r.binding_site_class && r.binding_site_class !== "unresolved")
          siteCounts.set(r.binding_site_class, (siteCounts.get(r.binding_site_class) || 0) + 1);
      const sites = [...siteCounts.entries()].sort((a, b) => b[1] - a[1])
        .map(([id]) => [id, siteClassLabel(id)]);
      if (!siteCounts.has(state.site) && sites.length) state.site = siteCounts.has(DEFAULT_SITE)
        ? DEFAULT_SITE : sites[0][0];
      data = { structures: st.structures, pocket, sites,
               assigned: assign(st.structures, pocket, state.site) };
      drawControls(); draw();
    } catch (error) {
      if (my !== token) return;
      clear(body); body.appendChild(el("p", { class: "notice", text: L.errorMessage(error) }));
    }
  }

  function compute() {
    const A = side(data.assigned, state.a, state), B = side(data.assigned, state.b, state);
    const di = THRESHOLDS.indexOf(state.delta);
    const all = new Set([...A.freq.keys(), ...B.freq.keys()]);
    let shown = [...all].filter(p => Math.max((A.freq.get(p) || [0, 0, 0])[2] || 0,
      (B.freq.get(p) || [0, 0, 0])[2] || 0) * 100 >= state.min);
    const deltaOf = p => ((A.freq.get(p) || [0, 0, 0])[di] || 0) - ((B.freq.get(p) || [0, 0, 0])[di] || 0);
    shown.sort(state.sort === "delta"
      ? (x, y) => Math.abs(deltaOf(y)) - Math.abs(deltaOf(x)) || positionKey(x) - positionKey(y)
      : (x, y) => positionKey(x) - positionKey(y));
    return { A, B, shown, deltaOf, di, total: all.size };
  }

  function draw() {
    clear(body); clear(summary);
    if (!data) return;
    const { A, B, shown, deltaOf, di, total } = compute();
    const P = palette();
    const lineFor = (id, X) => el("span", { class: "cm-side" }, [
      el("strong", { text: groupLabel(id) }), " · ",
      t("cm_counts", { receptors: X.receptors, structures: X.structures, contacts: X.contacts })]);
    summary.append(lineFor(state.a, A), lineFor(state.b, B));
    if (data.assigned.unassigned)
      summary.appendChild(el("span", { class: "muted small", text:
        t("cm_unassigned", { n: data.assigned.unassigned }) }));
    for (const [id, X] of [[state.a, A], [state.b, B]])
      if (X.receptors > 0 && X.receptors < SMALL_N)
        summary.appendChild(el("span", { class: "notice small", text:
          t("cm_small_n", { group: groupLabel(id), n: X.receptors,
            share: (getLang() === "tr" ? "%" : "") + Math.round(100 / X.receptors) + (getLang() === "tr" ? "" : "%") }) }));
    if (state.a === state.b)
      summary.appendChild(el("span", { class: "notice small", text: t("cm_same_side") }));
    if (!A.receptors || !B.receptors || !shown.length) {
      body.appendChild(el("p", { class: "notice", text: !shown.length && A.receptors && B.receptors
        ? t("cm_none_above", { min: state.min }) : t("cm_empty") }));
      return;
    }
    body.appendChild(el("p", { class: "muted small", text:
      t("cm_shown", { shown: shown.length, total, min: state.min }) }));

    const table = el("table", { class: "cm-table" });
    const head = el("tr", {}, [el("th", { class: "cm-rowhead", scope: "col", text: "" })]);
    for (const p of shown) {
      const seg = data.assigned.segmentOf.get(p) || "";
      head.appendChild(el("th", { scope: "col", class: "cm-colhead" + (p === state.pos ? " selected" : "") },
        el("button", { type: "button", class: "cm-pos", title: seg + " · " + p,
          "aria-pressed": p === state.pos ? "true" : "false",
          onclick: () => update({ pos: state.pos === p ? "" : p }), text: p })));
    }
    const thead = el("thead", {}, head);
    const tbody = el("tbody");
    const addRows = (id, X) => THRESHOLDS.forEach((th, k) => {
      const tr = el("tr", { class: k === 0 ? "cm-first" : "" }, [
        el("th", { scope: "row", class: "cm-rowhead" }, [
          k === 0 ? el("strong", { text: groupLabel(id) }) : null,
          el("span", { text: " ≤ " + th.toFixed(1) + " Å" })])]);
      for (const p of shown) {
        const v = (X.freq.get(p) || [0, 0, 0])[k] || 0;
        const bg = mix(P.lo, P.hi, v);
        const text = groupLabel(id) + " · " + p + " · ≤ " + th.toFixed(1) + " Å: " + pctText(v);
        tr.appendChild(el("td", { class: "cm-cell" + (p === state.pos ? " selected" : ""),
          style: "background:" + bg + ";color:" + (luminance(bg) < 0.5 ? "#fff" : "#1e2124"),
          title: text, "aria-label": text, text: Math.round(v * 100) }));
      }
      tbody.appendChild(tr);
    });
    addRows(state.a, A);
    addRows(state.b, B);
    const dr = el("tr", { class: "cm-delta" }, [el("th", { scope: "row", class: "cm-rowhead" }, [
      el("strong", { text: t("cm_delta_row") }), el("span", { text: " ≤ " + state.delta.toFixed(1) + " Å" })])]);
    for (const p of shown) {
      const d = deltaOf(p);
      const f = Math.min(1, Math.abs(d) / 0.6);
      const bg = d >= 0 ? mix(P.mid, P.pos, f) : mix(P.mid, P.neg, f);
      const text = p + " · " + groupLabel(state.a) + " − " + groupLabel(state.b) + ": " + signed(d);
      dr.appendChild(el("td", { class: "cm-cell" + (p === state.pos ? " selected" : ""),
        style: "background:" + bg + ";color:" + (luminance(bg) < 0.5 ? "#fff" : "#1e2124"),
        title: text, "aria-label": text, text: Math.abs(d) >= 0.005 ? signed(d) : "0" }));
    }
    tbody.appendChild(dr);
    table.append(thead, tbody);
    body.appendChild(el("div", { class: "cm-scroll" }, table));
    body.appendChild(legend(P));
    body.appendChild(el("div", { class: "lx-exports cm-exports" }, [
      el("button", { class: "btn small", type: "button", text: t("export_csv"),
        onclick: () => exportMap(false, A, B, shown, deltaOf) }),
      el("button", { class: "btn small", type: "button", text: t("export_xlsx"),
        onclick: () => exportMap(true, A, B, shown, deltaOf) })]));
    drawDetail(A, B, di);
  }

  function legend(P) {
    const ramp = (a, b, c) => "linear-gradient(90deg," + [a, b, c].filter(Boolean).join(",") + ")";
    return el("div", { class: "cm-legend" }, [
      el("span", { class: "cm-legend-item" }, [el("span", { text: "0%" }),
        el("i", { class: "cm-ramp", style: "background:" + ramp(P.lo, P.hi) }),
        el("span", { text: "100% · " + t("cm_legend_freq") })]),
      el("span", { class: "cm-legend-item" }, [el("span", { text: "−60%" }),
        el("i", { class: "cm-ramp", style: "background:" + ramp(P.neg, P.mid, P.pos) }),
        el("span", { text: "+60% · " + t("cm_legend_delta", { a: groupLabel(state.a), b: groupLabel(state.b) }) })])
    ]);
  }

  function drawDetail(A, B, di) {
    clear(detail);
    const p = state.pos;
    if (!p) { detail.appendChild(el("p", { class: "muted small", text: t("cm_detail_hint") })); return; }
    detail.appendChild(el("h3", { text: t("cm_detail_title", { position: p,
      threshold: state.delta.toFixed(1) }) }));
    detail.appendChild(el("p", { class: "muted small", text: t("cm_detail_help") }));
    for (const [id, X] of [[state.a, A], [state.b, B]]) {
      const rows = (X.perReceptor.get(p) || []).slice()
        .sort((x, y) => y.shares[di] - x.shares[di] || plainName(x.name).localeCompare(plainName(y.name)));
      const missing = X.receptors - rows.length;
      const tbl = el("table", { class: "data cm-detail-table" }, [
        el("thead", {}, el("tr", {}, [t("receptors"), t("structures"), "≤ " + state.delta.toFixed(1) + " Å"]
          .map(h => el("th", { text: h })))),
        el("tbody", {}, rows.map(r => el("tr", {}, [
          el("td", {}, el("a", { href: buildHash({ family: state.fam, view: "structures",
              rcpt: r.name, mode: r.mode, rep: state.rep ? null : "0" }),
            title: t("cm_open_receptor", { mode: ligandClassLabel(r.mode), k: r.modeCount, n: r.n }),
            html: r.name })),
          el("td", { class: "num", text: String(r.n) }),
          el("td", { class: "num", text: pctText(r.shares[di]) })])))]);
      detail.append(el("h4", { text: groupLabel(id) }), tbl);
      if (missing > 0) detail.appendChild(el("p", { class: "muted small",
        text: t("cm_detail_missing", { n: missing }) }));
    }
  }

  function exportMap(xlsx, A, B, shown, deltaOf) {
    const la = groupLabel(state.a), lb = groupLabel(state.b);
    const cols = [{ key: "generic_position" }, { key: "segment" }];
    for (const [tag, label] of [["a", la], ["b", lb]])
      THRESHOLDS.forEach((th, k) => cols.push({ key: tag + k, label: label + " <=" + th.toFixed(1) + "A" }));
    cols.push({ key: "delta", label: "delta <=" + state.delta.toFixed(1) + "A (" + la + " - " + lb + ")" });
    const round = v => v === null || v === undefined ? "" : Number(v.toFixed(4));
    const rows = shown.map(p => {
      const r = { generic_position: p, segment: data.assigned.segmentOf.get(p) || "" };
      THRESHOLDS.forEach((_, k) => {
        r["a" + k] = round((A.freq.get(p) || [0, 0, 0])[k] || 0);
        r["b" + k] = round((B.freq.get(p) || [0, 0, 0])[k] || 0);
      });
      r.delta = round(deltaOf(p));
      return r;
    });
    const m = L.getManifest();
    const info = { atlas_version: m.version, data_version: m.data_version, family: state.fam,
      export_date: new Date().toISOString(), source_data_hash: m.phase4_manifest_hash,
      table: "contact_map", binding_site_class: state.site,
      side_a: la + " (" + A.receptors + " receptors, " + A.structures + " structures)",
      side_b: lb + " (" + B.receptors + " receptors, " + B.structures + " structures)",
      weighting: state.weight, representative_only: state.rep ? "yes" : "no",
      method: state.method ? METHODS[state.method] : "all",
      positions: "reaching " + state.min + "% in either group at 5.0 A",
      cell: "share of structures with the position within the threshold of the ligand; " +
        (state.weight === "receptor" ? "mean over receptors of each receptor's share" : "over structures"),
      unassigned_contacts: data.assigned.unassigned };
    const name = "contact_map_" + state.fam + "_" + state.a + "_vs_" + state.b;
    if (xlsx) downloadXLSX(name + ".xlsx", [{ name: "Contact map", columns: cols, rows },
      { name: "Settings", columns: [{ key: "k", label: "setting" }, { key: "v", label: "value" }],
        rows: Object.entries(info).map(([k, v]) => ({ k, v: String(v) })) }]);
    else download(name + ".csv", toCSV(cols, rows, info));
  }

  drawControls();
  await load();
  return wrap;
}
