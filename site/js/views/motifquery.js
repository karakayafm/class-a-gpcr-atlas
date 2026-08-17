/* Motif query panel.
 *
 * The family views answer "what is in this structure". This answers the reverse, and it answers
 * it about receptors rather than depositions: given a motif specification, which receptors carry
 * it, which carry something chemically close, and which positions in the query were worth asking
 * about in the first place.
 *
 * Four things this panel keeps apart, because merging any pair of them reports an artefact of the
 * deposition record as biology:
 *
 *   Wild type against construct. The payload's letter is always the receptor's own residue; a
 *   lowercase letter means the deposited construct was engineered there, and `m` carries what the
 *   construct holds instead. Scoring reads the wild type, so a thermostabilising mutation never
 *   moves a score; it is flagged on the cell instead.
 *
 *   Absence of a residue against absence of evidence. A position that is unresolved in the
 *   coordinates, or whose generic numbering could not be assigned, is *uncovered*. It is never
 *   counted as a mismatch, and every score states the coverage it was computed over.
 *
 *   Identity against similarity. An exact match and a chemically conservative substitution are
 *   different answers, so they are reported as two percentages, never blended into one.
 *
 *   Structures against receptors. A receptor solved eighty times is one receptor. Ranking runs
 *   structure -> receptor -> family, families are ranked on the *median* of their receptors, and
 *   the deposition list is demoted into the detail aside where it cannot dominate the reading.
 *
 * The whole panel state lives in the URL, so a query survives reload, language change and
 * back-navigation. See stateFromRoute/routeFromState.
 */
import { t, siteClassLabel } from "../core/i18n.js";
import { el, clear, pct, debounce } from "../components/dom.js";
import { plainName, familyDisplayName, metricHelp } from "./views.js";
import { toCSV, download } from "../components/csv.js";
import { downloadXLSX } from "../components/xlsx.js";
import * as L from "../data/loader.js";
import { buildHash, navigate } from "../core/router.js";

/* ------------------------------------------------------------------ chemistry */

/* Grantham's composition, polarity and volume, as published (Grantham R, Science 1974,
   185:862-864, table 1). Hardcoded rather than fetched: twenty triples are not a dependency. */
const GRANTHAM = {
  S: [1.42, 9.2, 32],   R: [0.65, 10.5, 124], L: [0.00, 4.9, 111],  P: [0.39, 8.0, 32.5],
  T: [0.71, 8.6, 61],   A: [0.00, 8.1, 31],   V: [0.00, 5.9, 84],   G: [0.74, 9.0, 3],
  I: [0.00, 5.2, 111],  F: [0.00, 5.2, 132],  Y: [0.20, 6.2, 136],  C: [2.75, 5.5, 55],
  H: [0.58, 10.4, 96],  Q: [0.89, 10.5, 85],  N: [1.33, 11.6, 56],  K: [0.33, 11.3, 119],
  D: [1.38, 13.0, 54],  E: [0.92, 12.3, 83],  M: [0.00, 5.7, 105],  W: [0.13, 5.4, 170]
};
// The published weights, and the scaling constant that puts the mean of the matrix at 100.
const G_ALPHA = 1.833, G_BETA = 0.1018, G_GAMMA = 0.000399, G_RHO = 50.723;
export const CONSERVATIVE_MAX = 50;

export function granthamDistance(a, b) {
  const x = GRANTHAM[a], y = GRANTHAM[b];
  if (!x || !y) return null;
  if (a === b) return 0;
  const d = G_ALPHA * (x[0] - y[0]) ** 2 + G_BETA * (x[1] - y[1]) ** 2 + G_GAMMA * (x[2] - y[2]) ** 2;
  return G_RHO * Math.sqrt(d);
}

/* ------------------------------------------------------------------ route state */

const UNCOVERED = { " ": "not_applicable", "-": "unresolved", "?": "unmapped" };
const SORTS = ["receptor", "family", "coverage", "exact", "phys", "weighted"];
/* Exact, not physchem. A short query saturates the physicochemical score — three conservative
   substitutions and three identities both read 100% — so ranking on it puts a receptor that
   matches nothing exactly level with one that matches everything. Identity is the sharper
   question, and physchem stays beside it as its own column. */
const DEFAULT_SORT = "-exact", DEFAULT_TOP = 25;
/* Two position sets, one panel. The microswitch payload is the positions that move on
   activation; the pocket payload is the positions a ligand touches. Same schema, so everything
   below — scoring, entropy, aggregation, the heatmap — is unchanged by the choice. */
const POOLS = { motif: L.loadMotifSearch, pocket: L.loadPocketSearch };
const DEFAULT_POOL = "motif", DEFAULT_CLASS = "canonical_7tm_pocket", DEFAULT_MIN_FREQ = 0.10;

function stateFromRoute(route) {
  const raw = String(route.sort || DEFAULT_SORT);
  const key = raw.replace(/^-/, "");
  return {
    query: String(route.motif || ""),
    scope: String(route.scope || "class_a"),
    hit: String(route.hit || ""),
    sort: SORTS.includes(key) ? raw : DEFAULT_SORT,
    top: Math.max(5, Math.min(200, Number(route.top) || DEFAULT_TOP)),
    pool: POOLS[route.pool] ? route.pool : DEFAULT_POOL,
    siteClass: String(route.class || DEFAULT_CLASS),
    minFreq: Number.isFinite(Number(route.minfreq)) && route.minfreq !== undefined
      ? Math.max(0, Math.min(1, Number(route.minfreq))) : DEFAULT_MIN_FREQ,
    // Collapsing redundant depositions is the honest default: the deposition record is the thing
    // being counted, and it counts the same construct dozens of times.
    uniq: String(route.uniq || "1") !== "0"
  };
}
/* The inverse. Defaults are omitted so an untouched panel keeps a short, readable address, and
   `family` is carried through because the chrome's breadcrumb reads it. */
function routeFromState(s, route) {
  const r = { view: "motifsearch" };
  if (route && route.family) r.family = route.family;
  if (s.query) r.motif = s.query;
  if (s.scope && s.scope !== "class_a") r.scope = s.scope;
  if (s.hit) r.hit = s.hit;
  if (s.sort && s.sort !== DEFAULT_SORT) r.sort = s.sort;
  if (s.top !== DEFAULT_TOP) r.top = String(s.top);
  if (!s.uniq) r.uniq = "0";
  if (s.pool !== DEFAULT_POOL) r.pool = s.pool;
  // The pocket filter only means anything for the pocket pool, so it is only written for it.
  if (s.pool === "pocket") {
    if (s.siteClass !== DEFAULT_CLASS) r.class = s.siteClass;
    if (s.minFreq !== DEFAULT_MIN_FREQ) r.minfreq = String(s.minFreq);
  }
  return r;
}

/* Which positions the reference table and the motif cards offer. The microswitch pool offers all
   of them; the pocket pool offers those contacting a ligand often enough in the chosen binding
   site class. Only what is *offered* is filtered — a position named in the query is still scored,
   because a filter is a way of reading the payload, not a restriction on what may be asked. */
function activePositions(payload, state) {
  if (state.pool !== "pocket" || !payload.position_meta) return payload.positions.slice();
  return payload.positions.filter(p => {
    const meta = payload.position_meta[p];
    const freq = meta && meta.frequency ? meta.frequency[state.siteClass] : undefined;
    return freq !== undefined && freq >= state.minFreq;
  });
}
/* What a position is called, in both schemes. The pocket payload carries this inside
   position_meta; the microswitch payload predates it and is read from the side file. */
function labelOf(position, payload, numbering) {
  const meta = payload.position_meta && payload.position_meta[position];
  const info = (meta && meta.bw) || (numbering && numbering.positions
    && numbering.positions[position]) || null;
  if (!info) return { position, display: position, bw: null, diverges: false, variable: false };
  const minority = typeof info.minority === "number" ? info.minority
    : (info.total ? (info.total - (info.receptors || 0)) / info.total : 0);
  return { position, display: info.display || position, bw: info.bw,
           diverges: !!info.diverges, variable: !!info.variable, minority,
           // Marked when the schemes disagree outright, and also when they agree only for a
           // majority: 4x63 is 4.63 in 96 receptors and 4.62 in 94, and a reader shown neither
           // fact would take the modal number for the whole story.
           flagged: !!info.diverges || minority > 0.05,
           receptors: info.receptors, total: info.total, variants: info.variants || [] };
}
/* The marker shown wherever a position is named.
   
   The visible label is the structure-based number on its own — `3x32` — because that is what the
   binding pocket detail and the 3D viewer show, and a panel that spelled the same position
   differently from the rest of the atlas would be its own kind of trap. The Ballesteros-Weinstein
   number is always one hover away, and where the two schemes disagree the position is marked so
   nobody has to hover to find out that they do. */
function positionLabel(position, payload, numbering, opts) {
  const info = labelOf(position, payload, numbering);
  const node = el("span", { class: "mq-pos" + (info.flagged ? " diverges" : ""),
    "data-position": position }, [el("strong", { text: position })]);
  const variants = (info.variants || []).map(v => v[0] + " (" + v[1] + ")").join(", ");
  /* No glyph. Fifty-one of the seventy-eight flagged positions are visible under the default
     filter, and a warning triangle on two rows in three stops reading as a warning and starts
     reading as wallpaper. The dashed underline carries it instead, and the explanation is on the
     hover where it can be read in full. */
  // Three different things to say, and they are not the same warning: the schemes disagree; they
  // disagree and not uniformly; or they agree for most receptors but not for a large minority.
  if (info.diverges)
    node.title = t(info.variable ? "mq_bw_diverges_variable" : "mq_bw_diverges",
      { bw: info.bw, structure: position, n: info.receptors, total: info.total, variants });
  else if (info.flagged)
    node.title = t("mq_bw_minority", { bw: info.bw, n: info.receptors, total: info.total,
      share: Math.round(info.minority * 100), variants });
  else if (info.variable)
    node.title = t("mq_bw_variable", { bw: info.bw, n: info.receptors, total: info.total });
  // Nothing wrong with this position, but the label no longer carries the BW number, so the
  // hover has to.
  else if (info.bw) node.title = t("mq_bw_plain", { bw: info.bw, structure: position });
  if (opts && opts.segment) node.appendChild(el("span", { class: "muted small",
    text: " " + opts.segment }));
  return node;
}
function siteClassesOf(payload) {
  const classes = (payload.pool && payload.pool.site_classes) || {};
  return Object.keys(classes).sort((a, b) => classes[b].receptors - classes[a].receptors);
}

/* ------------------------------------------------------------------ query grammar */

/* `3x50R, 6x30E` asks for arginine at 3x50 and glutamate at 6x30. Several residues at one
   position are a union: `6x30DE` and `6x30D 6x30E` both ask for either. Tokens may be separated
   by spaces, commas, semicolons or `+`, so a query pasted out of the address bar parses back.
   Anything unrecognised is reported rather than dropped, so a typo cannot quietly widen a
   result. */
/* Both numbering schemes are accepted, and the separator says which one is meant: `5x43D` is the
   structure-based label the payload uses, `5.42D` is Ballesteros-Weinstein. A BW token is
   translated through the numbering side file and the translation is reported back, because the
   two disagree at forty-one positions and a reader who typed 5.42 needs to see that the panel
   read it as 5x43 rather than discover it from a puzzling result. */
export function parseQuery(text, known, numbering) {
  const byPosition = new Map(), bad = [], retired = [], translated = [];
  const bwIndex = (numbering && numbering.bw_index) || {};
  const bwAlternatives = (numbering && numbering.bw_alternatives) || {};
  for (const token of String(text || "").split(/[\s,;+]+/).filter(Boolean)) {
    const mutation = /^(\d+[x.]\d+)\s*!$/.exec(token);
    const residue = /^(\d+[x.]\d+)\s*([A-Za-z]+)$/.exec(token);
    if (mutation) { retired.push(token); continue; }
    if (!residue) { bad.push(token); continue; }
    let position = residue[1];
    if (position.includes(".")) {
      const resolved = bwIndex[position];
      if (!resolved) { bad.push(token); continue; }
      /* A BW number can name more than one structure-based position — 4.58 is 4x58 in 106
         receptors and 4x59 in 94 — so resolving it to the most common one and saying nothing
         would be a coin flip presented as an answer. The alternatives travel with the
         translation and the panel offers them. */
      const alternatives = bwAlternatives[position] || null;
      /* Most of the bundle agrees between the two schemes, and there `3.32` resolves to `3x32`:
         the same residue, the same number, nothing translated. Announcing that is noise, and it
         was the loudest thing on the page for a query that had nothing to report. Only a
         translation that moves the position — or a BW number that names more than one — is worth
         a line. */
      if (position.replace(".", "x") !== resolved || alternatives)
        translated.push({ from: position, to: resolved, residues: residue[2].toUpperCase(),
          alternatives });
      position = resolved;
    }
    if (!known.has(position)) { bad.push(token); continue; }
    const letters = residue[2].toUpperCase().split("");
    if (letters.some(c => !GRANTHAM[c])) { bad.push(token); continue; }
    if (!byPosition.has(position))
      byPosition.set(position, { position, residues: new Set() });
    for (const c of letters) byPosition.get(position).residues.add(c);
  }
  const order = p => { const m = /^(\d+)x(\d+)$/.exec(p);
    return m ? Number(m[1]) * 1000 + Number(m[2]) : Number.MAX_SAFE_INTEGER; };
  const groups = [...byPosition.values()].sort((a, b) => order(a.position) - order(b.position));
  return { groups, bad, retired, translated };
}
function queryText(groups) {
  return groups.map(g => g.position + [...g.residues].sort().join("")).join(" ");
}

/* ------------------------------------------------------------------ specificity */

/* Shannon entropy over the receptor-level residue distribution at each position, and a weight
   derived from it. A position where every Class A receptor carries the same residue answers no
   question — every receptor matches it — so asking for the consensus there tells a reader
   nothing, and the weighted score discounts it towards zero. */
function specificity(payload, scope, groups, allow) {
  const dist = (payload.variation || {})[scope] || {};
  const stats = new Map();
  for (const p of payload.positions) {
    const rec = dist[p];
    const pairs = (rec && rec.by_receptor) || [];
    const total = pairs.reduce((a, kv) => a + kv[1], 0);
    let H = 0;
    for (const [, n] of pairs) { const q = total ? n / total : 0; if (q > 0) H -= q * Math.log2(q); }
    stats.set(p, { H, total, pairs, consensus: rec ? rec.consensus : null });
  }
  const Hs = payload.positions.map(p => stats.get(p).H);
  const Hmin = Math.min(...Hs), Hmax = Math.max(...Hs), span = Hmax - Hmin;
  // With no spread there is nothing to weight by; every position then counts the same and the
  // weighted score is reported as equal to the unweighted one rather than as a division by zero.
  const weightOf = p => span > 0 ? (stats.get(p).H - Hmin) / span : 1;
  const asked = groups.map(g => {
    const s = stats.get(g.position) || { pairs: [], total: 0, H: 0 };
    const carried = s.pairs.filter(kv => g.residues.has(kv[0])).reduce((a, kv) => a + kv[1], 0);
    const freq = s.total ? carried / s.total : null;
    return { position: g.position, residues: g.residues, entropy: s.H, weight: weightOf(g.position),
      receptors: s.total, frequency: freq, consensus: s.consensus,
      lowSpecificity: freq !== null && freq > 0.90 };
  });
  const suggestions = payload.positions
    .filter(p => (!allow || allow.has(p)) && !groups.some(g => g.position === p))
    .sort((a, b) => stats.get(b).H - stats.get(a).H)
    .slice(0, 3)
    .map(p => ({ position: p, entropy: stats.get(p).H, consensus: stats.get(p).consensus }));
  return { stats, asked, suggestions, weightOf,
    allLowSpecificity: asked.length > 0 && asked.every(a => a.lowSpecificity) };
}

/* ------------------------------------------------------------------ scoring */

/* One structure against the query. Every position returns a cell, and a cell always says which
   of the four states it is in and — where it is not exact — how far away it is, so the call is
   auditable rather than a colour a reader has to trust. */
export function scoreStructure(record, groups, posIndex, spec) {
  const cells = groups.map(group => {
    const c = record.s[posIndex.get(group.position)];
    const wanted = [...group.residues].sort();
    if (c === undefined || UNCOVERED[c])
      return { position: group.position, wanted, status: "uncovered",
        reason: UNCOVERED[c] || "unresolved", engineered: false, distance: null };
    const engineered = c >= "a" && c <= "z";
    const wild = c.toUpperCase();
    const construct = engineered ? ((record.m || {})[group.position] || "") : "";
    if (group.residues.has(wild))
      return { position: group.position, wanted, status: "exact", wild, construct, engineered,
        distance: 0 };
    const distances = wanted.map(r => granthamDistance(wild, r)).filter(d => d !== null);
    const distance = distances.length ? Math.min(...distances) : null;
    const status = distance !== null && distance <= CONSERVATIVE_MAX ? "conservative" : "mismatch";
    return { position: group.position, wanted, status, wild, construct, engineered, distance };
  });
  const covered = cells.filter(c => c.status !== "uncovered");
  const exact = covered.filter(c => c.status === "exact").length;
  const conservative = covered.filter(c => c.status === "conservative").length;
  let wSum = 0, wHit = 0;
  for (const cell of cells) {
    if (cell.status === "uncovered") continue;
    const w = spec ? spec.weightOf(cell.position) : 1;
    wSum += w;
    if (cell.status === "exact") wHit += w;
  }
  return { cells, covered: covered.length, exact, conservative, engineered:
      cells.filter(c => c.engineered).length,
    // Reported separately, never blended: the denominators differ and so do the questions.
    exactPct: covered.length ? exact / covered.length : null,
    physPct: covered.length ? (exact + conservative) / covered.length : null,
    coverage: groups.length ? covered.length / groups.length : null,
    weightedPct: wSum > 0 ? wHit / wSum : null };
}

/* Distinct depositions, by what they actually carry rather than by how many times they were
   deposited. Two structures of the same construct with the same residues at every position and
   the same engineering are one profile; the atlas holds eighty β2AR entries that differ in
   ligand, resolution and method but say exactly the same thing about the sequence.

   The key is the payload's own `s` string plus the `m` map, so it is a property of the structure
   and not of the query: switching the query never regroups anything. Within a group every member
   has the same `s`, so their coverage is identical for any query and the representative is
   decided by the tie-break alone — the lowest PDB id. The coverage comparison is written out
   anyway, because it is the rule, and a later change to the key must not silently lose it. */
function profileKey(record) {
  const m = record.m || {};
  return record.s + "|" + Object.keys(m).sort().map(p => p + ":" + m[p]).join(",");
}
function uniqueProfiles(structures) {
  const groups = new Map();
  for (const s of structures) {
    const key = profileKey(s.record);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(s);
  }
  return [...groups.values()].map(list => {
    const rep = list.slice().sort((a, b) =>
      b.score.covered - a.score.covered || a.pdb.localeCompare(b.pdb))[0];
    return Object.assign({}, rep, { duplicates: list.length,
      alsoIn: list.filter(x => x !== rep).map(x => x.pdb) });
  }).sort((a, b) => a.pdb.localeCompare(b.pdb));
}

/* Which families carry a given residue at a given position, and how much that concentrates them.
   Counted once per receptor — a receptor with eighty depositions is one receptor — and reported
   against the whole scope as a background, so "62% of peptide receptors, 3.4x the Class A rate"
   can be read off directly. Enrichment is the family's share divided by the scope's share. */
function familyDistribution(payload, scope, position, residues, posIndex) {
  const index = posIndex.get(position);
  if (index === undefined) return null;
  const seen = new Map();                       // receptor -> { family, carries }
  for (const record of Object.values(payload.structures)) {
    if (scope !== "class_a" && record.f !== scope) continue;
    const c = record.s[index];
    if (c === undefined || UNCOVERED[c]) continue;   // no evidence is not evidence of absence
    const key = record.r || "";
    if (!seen.has(key)) seen.set(key, { family: record.f, carries: residues.has(c.toUpperCase()) });
  }
  const families = new Map();
  let total = 0, carrying = 0;
  for (const entry of seen.values()) {
    total++; if (entry.carries) carrying++;
    if (!families.has(entry.family)) families.set(entry.family, { covered: 0, carries: 0 });
    const f = families.get(entry.family);
    f.covered++; if (entry.carries) f.carries++;
  }
  const background = total ? carrying / total : 0;
  const rows = [...families.entries()].map(([slug, f]) => ({
    slug, receptors: f.carries, covered: f.covered,
    share: f.covered ? f.carries / f.covered : 0,
    enrichment: background > 0 && f.covered ? (f.carries / f.covered) / background : null
  })).filter(r => r.receptors > 0)
    .sort((a, b) => (b.enrichment || 0) - (a.enrichment || 0) || b.receptors - a.receptors);
  return { rows, background, total, carrying };
}

function median(values) {
  if (!values.length) return null;
  const v = values.slice().sort((a, b) => a - b), i = Math.floor(v.length / 2);
  return v.length % 2 ? v[i] : (v[i - 1] + v[i]) / 2;
}

/* Structure -> receptor -> family. The receptor's representative is the structure that saw the
   most of the query; where two saw the same, the one that matched more of it. Ranking a receptor
   on its best-covered structure keeps a partially disordered deposition from speaking for a
   receptor that also has a complete one. */
function aggregate(payload, groups, posIndex, spec, scope) {
  const byReceptor = new Map();
  for (const [pdb, record] of Object.entries(payload.structures)) {
    if (scope !== "class_a" && record.f !== scope) continue;
    const score = scoreStructure(record, groups, posIndex, spec);
    const key = record.r || pdb;
    if (!byReceptor.has(key))
      byReceptor.set(key, { receptor: key, name: record.n, family: record.f, structures: [] });
    byReceptor.get(key).structures.push({ pdb, record, score });
  }
  const receptors = [];
  for (const entry of byReceptor.values()) {
    entry.structures.sort((a, b) => a.pdb.localeCompare(b.pdb));
    const best = entry.structures.slice().sort((a, b) =>
      b.score.covered - a.score.covered || b.score.exact - a.score.exact ||
      a.pdb.localeCompare(b.pdb))[0];
    receptors.push(Object.assign({}, entry, { representative: best, score: best.score,
      structureCount: entry.structures.length,
      unique: uniqueProfiles(entry.structures) }));
  }
  const scored = receptors.filter(r => r.score.covered > 0);
  const unscored = receptors.filter(r => r.score.covered === 0);
  const families = new Map();
  for (const r of scored) {
    if (!families.has(r.family)) families.set(r.family, []);
    families.get(r.family).push(r);
  }
  const familyRows = [...families.entries()].map(([slug, rs]) => ({
    slug, receptors: rs.length,
    medianPhys: median(rs.map(r => r.score.physPct)),
    maxPhys: Math.max(...rs.map(r => r.score.physPct)),
    medianExact: median(rs.map(r => r.score.exactPct)),
    maxExact: Math.max(...rs.map(r => r.score.exactPct)),
    medianCoverage: median(rs.map(r => r.score.coverage))
  })).sort((a, b) => b.medianPhys - a.medianPhys || b.receptors - a.receptors);
  return { receptors: scored, unscored, families: familyRows };
}

/* The chosen column first, then a fixed chain: exact, physchem, coverage, receptor name. Ties on
   one score are broken by the next rather than by whatever order the payload happened to be in,
   so the same query always produces the same table. */
const SORT_VALUE = {
  receptor: r => r.receptor,
  family: (r, nameOf) => nameOf.get(r.family) || r.family,
  // Sorted on the number actually displayed, so the column and its order agree.
  structures: (r, nameOf, uniq) => uniq ? r.unique.length : r.structureCount,
  coverage: r => r.score.coverage,
  exact: r => r.score.exactPct,
  phys: r => r.score.physPct,
  weighted: r => (r.score.weightedPct === null ? -1 : r.score.weightedPct)
};
const TIE_CHAIN = ["exact", "phys", "coverage"];

function compareOn(key, a, b, nameOf, uniq) {
  const get = SORT_VALUE[key] || SORT_VALUE.phys;
  const x = get(a, nameOf, uniq), y = get(b, nameOf, uniq);
  if (typeof x === "string") return x.localeCompare(y);
  return x === y ? 0 : x < y ? -1 : 1;
}
function sortReceptors(rows, sort, nameOf, uniq) {
  const desc = sort.startsWith("-"), key = sort.replace(/^-/, "");
  return rows.slice().sort((a, b) => {
    const primary = compareOn(key, a, b, nameOf, uniq);
    if (primary) return desc ? -primary : primary;
    for (const next of TIE_CHAIN) {
      if (next === key) continue;
      const c = compareOn(next, a, b, nameOf, uniq);
      if (c) return -c;                       // every score in the chain reads best-first
    }
    return a.receptor.localeCompare(b.receptor);
  });
}
/* How many receptors share the top row's value in the column being sorted on. A query that leaves
   forty receptors tied at the top has not ranked them, and saying so is more honest than letting
   the alphabetical tie-break look like a result. */
function topTieCount(rows, sort, nameOf, uniq) {
  if (!rows.length) return 0;
  const key = sort.replace(/^-/, "");
  let n = 1;
  while (n < rows.length && compareOn(key, rows[0], rows[n], nameOf, uniq) === 0) n++;
  return n;
}

/* ------------------------------------------------------------------ panel */

let mounted = null;

/* A route change confined to this panel's own keys is applied in place. Rebuilding the view
   would take the query input out of the document and with it the caret, which is the whole
   reason the old panel could not keep its state in the address. */
export function canUpdateInPlace(route) {
  return !!(mounted && mounted.node.isConnected && route.view === "motifsearch");
}
export function applyRoute(route) {
  if (!mounted) return;
  mounted.setRoute(route);
}

export async function motifQuery(root, route) {
  clear(root);
  const wrap = el("section", { class: "view mq" });
  root.appendChild(wrap);

  let currentRoute = route;
  let state = stateFromRoute(route);
  let payload = null, posIndex = new Map(), known = new Set(), loadToken = 0;

  /* The two payloads are fetched on demand and cached by the loader exactly as before. Switching
     scope is therefore a fetch on the first switch and free afterwards. */
  async function loadPool(name) {
    const token = ++loadToken;
    const data = await (POOLS[name] || POOLS[DEFAULT_POOL])();
    if (token !== loadToken) return false;
    payload = data;
    posIndex = new Map(payload.positions.map((p, i) => [p, i]));
    known = new Set(payload.positions);
    return true;
  }
  let numbering = null;
  // A small side file, fetched once and shared by both pools.
  try { numbering = await L.loadGenericNumbering(); } catch (error) { numbering = null; }
  try { await loadPool(state.pool); }
  catch (error) {
    wrap.appendChild(el("p", { class: "notice", text: L.errorMessage(error) }));
    return wrap;
  }
  const families = L.getManifest().families || [];
  const nameOf = new Map(families.map(f => [f.slug, familyDisplayName(f.name)]));

  wrap.appendChild(el("div", {}, [
    el("h2", { text: t("nav_motifs") }),
    el("p", { class: "muted", text: t("mq_intro") })]));

  /* --------------------------------------------------------- 1. query strip */
  const strip = el("div", { class: "mq-strip" });
  const queryInput = el("input", { type: "text", class: "motif-query", spellcheck: "false",
    value: state.query, placeholder: t("mq_query_placeholder"), "aria-label": t("motif_query") });
  const scopeSelect = el("select", { "aria-label": t("motif_scope") });
  scopeSelect.appendChild(el("option", { value: "class_a", text: t("motif_scope_class_a") }));
  for (const f of families)
    scopeSelect.appendChild(el("option", { value: f.slug, text: familyDisplayName(f.name) }));
  const motifTabs = el("div", { class: "motif-strip" });
  const specBox = el("div", { class: "mq-spec" });
  // Open by default: the distributions in it are how a query gets built and how a position's
  // variation is read, which is not something to go looking for behind a disclosure. Whether it
  // is open is deliberately not in the route — it is a reading preference, not a query.
  const positionBox = el("details", { class: "mq-positions", open: true });
  const familyBox = el("div", { class: "mq-block" });
  const receptorBox = el("div", { class: "mq-block" });
  const heatBox = el("div", { class: "mq-block" });
  const aside = el("aside", { class: "mq-detail", hidden: true, "aria-live": "polite" });
  const layout = el("div", { class: "mq-layout" });

  /* The field runs the query as it is typed, so the button is not what makes it work — it is
     there because a search field without one reads as though nothing has happened yet. It sits
     inside the field's box rather than beside it, so it costs the input no width. */
  const searchButton = el("button", { class: "mq-search", type: "button",
    "aria-label": t("mq_search"), title: t("mq_search") }, [
    el("span", { class: "mq-search-glyph", "aria-hidden": "true" }, [
      el("span", { class: "mq-search-ring" }), el("span", { class: "mq-search-stem" })])]);
  searchButton.addEventListener("click", () => update({ query: queryInput.value }));
  const queryField = el("label", { class: "filter-field mq-query-field" }, [
    el("span", { text: t("motif_query") }),
    el("span", { class: "mq-query-box" }, [queryInput, searchButton]),
    el("small", { class: "muted" }, [
      el("span", { text: t("mq_query_hint") }),
      el("span", { class: "mq-tab-hint", text: " " + t("mq_tab_hint") })])]);
  strip.appendChild(queryField);
  strip.appendChild(el("label", { class: "filter-field" }, [
    el("span", { text: t("motif_scope") }), scopeSelect]));

  /* Which position set the panel is reading. Everything downstream is indifferent to the answer:
     the two payloads share a schema, so only the positions change. */
  const poolSelect = el("select", { "aria-label": t("mq_pool") });
  poolSelect.appendChild(el("option", { value: "motif", text: t("mq_pool_motif") }));
  poolSelect.appendChild(el("option", { value: "pocket", text: t("mq_pool_pocket") }));
  poolSelect.addEventListener("change", () => update({ pool: poolSelect.value, hit: "" }));
  strip.appendChild(el("label", { class: "filter-field" }, [
    el("span", { text: t("mq_pool") }), poolSelect]));

  // Pocket-only: which binding site class the frequency is read in, and how often is often
  // enough. Both are read-time choices, which is why they are controls and not pipeline
  // constants baked into the payload.
  const classSelect = el("select", { "aria-label": t("mq_site_class") });
  classSelect.addEventListener("change", () => update({ siteClass: classSelect.value }));
  const freqSelect = el("select", { "aria-label": t("mq_min_freq") });
  for (const value of [0, 0.01, 0.05, 0.10, 0.25, 0.50])
    freqSelect.appendChild(el("option", { value: String(value),
      text: value === 0 ? t("mq_min_freq_any") : Math.round(value * 100) + "%" }));
  freqSelect.addEventListener("change", () => update({ minFreq: Number(freqSelect.value) }));
  const classField = el("label", { class: "filter-field mq-pocket-only" }, [
    el("span", {}, [document.createTextNode(t("mq_site_class") + " "),
      metricHelp(t("mq_site_class_help"))]), classSelect]);
  const freqNote = el("span", { class: "mq-freq-note" });
  const freqField = el("label", { class: "filter-field mq-pocket-only mq-freq-field" }, [
    el("span", {}, [document.createTextNode(t("mq_min_freq") + " "),
      metricHelp(t("mq_min_freq_help"))]), freqSelect, freqNote]);
  strip.appendChild(classField); strip.appendChild(freqField);
  wrap.appendChild(strip);
  /* The cards get their own band with a caption. Sitting flush under the controls they read as a
     second row of controls, which is not what they are: the controls above say what is being
     searched, these are starting points for the search.
     
     Open by default, and foldable for a reader who wants them out of the way. Closing them by
     default was tried and reversed: they are the panel's answer to "what can I even ask here",
     and a reader who has not yet formed a question does not know to go looking behind a
     disclosure for the thing that would give them one. Whether it is open is a reading
     preference and stays out of the route, as with the position reference below. */
  const motifBand = el("details", { class: "mq-band", open: true }, [
    el("summary", { class: "mq-band-label" }), motifTabs]);
  /* The query summary sits above the starting points, not below them. It is what the panel is
     currently being asked, and the cards under it are a way to change that — the answer belongs
     next to the controls that produced it, and the offers belong under the answer. */
  wrap.appendChild(specBox);
  wrap.appendChild(motifBand);
  wrap.appendChild(positionBox);
  layout.appendChild(el("div", { class: "mq-results" }, [familyBox, receptorBox, heatBox]));
  layout.appendChild(aside);
  wrap.appendChild(layout);

  /* State changes never touch the DOM directly: they write the address and redraw from it, so
     what the reader sees and what the address says cannot drift apart. `replace` for the
     continuous controls (typing, sorting, row count) and a real history entry for selecting a
     receptor, so Back closes the detail rather than leaving the panel. */
  function update(patch, push) {
    const previousPool = state.pool;
    state = Object.assign({}, state, patch);
    const next = routeFromState(state, currentRoute);
    currentRoute = Object.assign({}, currentRoute, next);
    navigate(next, !push);
    // Changing the position set means a different payload. `navigate` with replace does not fire
    // a hashchange, so this path has to do the fetch itself rather than wait to be told.
    if (state.pool !== previousPool) { reloadThenDraw(); return; }
    draw();
  }
  function reloadThenDraw() {
    loadPool(state.pool).then(applied => { if (applied) draw(); })
      .catch(error => { clear(specBox);
        specBox.appendChild(el("p", { class: "notice", text: L.errorMessage(error) })); });
  }
  function setRoute(r) {
    currentRoute = r;
    const next = stateFromRoute(r);
    const queryChanged = next.query !== state.query;
    const poolChanged = next.pool !== state.pool;
    state = next;
    if (queryChanged && document.activeElement !== queryInput) queryInput.value = state.query;
    // A different position set: fetch it, then redraw. The panel keeps showing the previous
    // answer until the new one is ready rather than blanking.
    if (poolChanged) reloadThenDraw(); else draw();
  }

  queryInput.addEventListener("input", debounce(() => update({ query: queryInput.value }), 220));
  /* Tab fills the example when the field is empty, as the similarity search does. The example is
     the placeholder, so what is offered and what is typed are the same string. */
  queryInput.addEventListener("keydown", e => {
    if (e.key !== "Tab" || e.shiftKey || queryInput.value.trim()) return;
    e.preventDefault();
    queryInput.value = t("mq_query_placeholder");
    update({ query: queryInput.value });
  });
  scopeSelect.addEventListener("change", () => update({ scope: scopeSelect.value }));

  /* Each motif offers two different actions, so it is two sibling buttons in one wrapper rather
     than a button inside a button: the body replaces the query with this motif, the `+` adds it
     to whatever is already there. Reading one motif and building a query across several are both
     ordinary things to want, and a single target could only serve one of them. */
  function motifTokens(m) {
    const dist = (payload.variation || {})[state.scope] || {};
    return m.positions
      .filter(p => dist[p] && dist[p].consensus)
      .map(p => ({ position: p, token: p + dist[p].consensus }));
  }
  function setQuery(text) { queryInput.value = text; update({ query: text }); }
  // The label of a group the payload derived rather than named: the microswitch payload carries
  // motif ids the dictionary knows, the pocket payload carries segment and consensus groups whose
  // name is built from the segment or the binding site class they came from.
  function motifLabel(m) {
    const key = "motif_" + m.motif_id;
    const known = t(key);
    if (known !== key) return known;
    if (m.motif_id.startsWith("segment_")) return m.motif_id.slice(8);
    // No "Consensus:" prefix. Every card in that row is a consensus set, so the word was on all
    // of them and distinguished none of them.
    if (m.motif_id.startsWith("consensus_")) return siteClassLabel(m.motif_id.slice(10));
    return m.motif_id;
  }
  /* Rebuilt on every draw, because which cards are worth offering follows the active filter:
     a group all of whose positions were filtered out is not a starting point for anything. */
  function drawMotifCards(activeSet) {
    clear(motifTabs);
    let offered = 0;
    for (const m of payload.motifs) {
      const usable = m.positions.filter(p => activeSet.has(p));
      if (!usable.length) continue;
      const label = motifLabel(m);
      const tokensOf = () => motifTokens(m).filter(x => activeSet.has(x.position));
      /* The badge counts positions. It used to repeat the label — "TM1  TM1", "Canonical 7TM
         pocket  Canonical 7TM pocket" — which said the same thing twice and left the one number
         a reader actually wants off the card. */
      const tokens = tokensOf().map(x => x.token);
      const seeded = tokens.join(" ");
      const isCurrent = seeded && state.query.trim() === seeded;
      const body = el("button", { class: "motif-tab-body" + (isCurrent ? " active" : ""),
        type: "button", "aria-pressed": isCurrent ? "true" : "false",
        "aria-label": t(isCurrent ? "mq_motif_clear" : "mq_motif_replace", { motif: label }),
        title: t(isCurrent ? "mq_motif_clear" : "mq_motif_replace", { motif: label }) }, [
        el("span", { text: label }),
        el("span", { class: "tab-count", text: String(usable.length) })]);
      // A second click on the card that is already the whole query clears it, so the same target
      // both sets and unsets rather than only ever setting.
      body.addEventListener("click", () => setQuery(isCurrent ? "" : seeded));
      /* Two stacked actions rather than one. Adding a motif to a query had a target; taking it
         out again meant editing the text by hand, which is the sort of asymmetry that makes a
         reader stop exploring. Each is disabled when it would do nothing, so the pair also says
         whether this motif is currently in the query. */
      const held = parseQuery(state.query, known, numbering).groups;
      const heldSet = new Set(held.map(g => g.position));
      const missing = tokensOf().filter(x => !heldSet.has(x.position));
      const present = m.positions.filter(x => heldSet.has(x));
      const plus = el("button", { class: "motif-tab-add", type: "button", disabled: !missing.length,
        "aria-label": t("mq_motif_add", { motif: label }),
        title: t("mq_motif_add", { motif: label }), text: "+" });
      plus.addEventListener("click", () => {
        // Positions already asked for are left exactly as they are: adding a motif must not
        // quietly rewrite a residue the reader chose by hand.
        if (!missing.length) return;
        setQuery((state.query.trim() + " " + missing.map(x => x.token).join(" ")).trim());
      });
      const minus = el("button", { class: "motif-tab-remove", type: "button",
        disabled: !present.length,
        "aria-label": t("mq_motif_remove", { motif: label }),
        title: t("mq_motif_remove", { motif: label }), text: "\u2212" });
      minus.addEventListener("click", () => {
        if (!present.length) return;
        const drop = new Set(m.positions);
        setQuery(queryText(held.filter(g => !drop.has(g.position))));
      });
      motifTabs.appendChild(el("span", { class: "motif-tab", "data-motif": m.motif_id },
        [body, el("span", { class: "motif-tab-actions" }, [plus, minus])]));
      offered++;
    }
    const summary = motifBand.querySelector("summary");
    if (summary) summary.textContent = t("mq_motif_cards_n", { n: offered });
    motifBand.hidden = !offered;
  }

  /* --------------------------------------------------------- drawing */
  /* A filled arrow in a chip, not a chevron glyph. `\u203a` at text weight disappeared into the
     row: it was the one mark telling a reader the row does something, and it read as punctuation.
     Drawn rather than typed so its weight does not depend on the reader's font. */
  /* A plain white block arrow on a green field — the old Internet Explorer "Go" button, with the
     colour in the field rather than in the glyph. Flat: a gloss and a bevel on a 26px mark read
     as noise at this size, and white on green is the pair that carries at a glance. */
  function goArrowIE() {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 32 12");
    svg.setAttribute("aria-hidden", "true");
    const body = document.createElementNS(NS, "path");
    body.setAttribute("d", "M2 4h16V0.6l11.6 5.4L18 11.4V8H2z");
    body.setAttribute("fill", "#ffffff");
    svg.appendChild(body);
    return svg;
  }
  function goArrow() {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 16 16");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(NS, "path");
    path.setAttribute("d", "M2 6.15h6.1V2.8L14.2 8l-6.1 5.2V9.85H2z");
    svg.appendChild(path);
    return el("span", { class: "mq-go" }, [svg]);
  }
  function scoreCell(value, help) {
    return el("td", { class: "mq-num" }, [
      el("span", { text: value === null || value === undefined ? "—" : pct(value) })]
      .concat(help ? [help] : []));
  }

  function drawSpecificity(spec, parsed) {
    clear(specBox);
    const head = el("div", { class: "mq-spec-head" });
    head.appendChild(el("strong", { text: t("mq_query_label") }));
    head.appendChild(el("code", { class: "mq-query-echo",
      text: parsed.groups.length ? queryText(parsed.groups) : t("mq_query_empty") }));
    if (parsed.groups.length)
      head.appendChild(el("button", { class: "btn small", type: "button", text: t("mq_clear"),
        onclick: () => { queryInput.value = ""; update({ query: "", hit: "" }); } }));
    specBox.appendChild(head);
    for (const item of (parsed.translated || [])) {
      const line = el("p", { class: "mq-translated" });
      if (!item.alternatives) {
        line.appendChild(el("span", { text: t("mq_bw_translated",
          { pairs: item.from + " \u2192 " + item.to }) }));
      } else {
        const [chosen, ...others] = item.alternatives;
        line.appendChild(el("span", { text: t("mq_bw_ambiguous", {
          bw: item.from,
          options: item.alternatives.map(a => t("mq_bw_option", { position: a[0], n: a[1] }))
            .join(t("mq_bw_or")),
          used: item.to }) + " " }));
        // Switching is one click and rewrites the token explicitly, so the query stops being
        // ambiguous rather than staying ambiguous with a different default.
        for (const [alt] of others) {
          if (alt === item.to) continue;
          line.appendChild(el("button", { class: "btn small", type: "button",
            text: t("mq_bw_use_instead", { position: alt }),
            onclick: () => {
              const next = state.query.replace(new RegExp("(^|[\\s,;+])" +
                item.from.replace(".", "\\.") + "(?=[A-Za-z])", "g"), "$1" + alt);
              queryInput.value = next; update({ query: next });
            } }));
        }
      }
      specBox.appendChild(line);
    }
    if (parsed.bad.length) specBox.appendChild(el("p", { class: "motif-bad",
      text: t("motif_query_bad", { tokens: parsed.bad.join(", ") }) }));
    if (parsed.retired.length) specBox.appendChild(el("p", { class: "motif-bad",
      text: t("mq_query_retired", { tokens: parsed.retired.join(", ") }) }));
    if (!parsed.groups.length) {
      specBox.appendChild(el("p", { class: "muted", text: t("mq_empty_prompt") }));
      return;
    }
    const table = el("table", { class: "data compact mq-spec-table" });
    table.appendChild(el("thead", {}, el("tr", {}, [
      el("th", { text: t("motif_position") }),
      el("th", { text: t("motif_segment") }),
      el("th", { text: t("mq_asked_for") }),
      el("th", {}, [document.createTextNode(t("mq_receptor_frequency") + " "),
        metricHelp(t("mq_frequency_help"))]),
      el("th", {}, [document.createTextNode(t("mq_entropy") + " "),
        metricHelp(t("mq_entropy_help"))]),
      el("th", {}, [document.createTextNode(t("mq_weight") + " "),
        metricHelp(t("mq_weight_help"))]),
      el("th", {}, [document.createTextNode(t("mq_top_families") + " "),
        metricHelp(t("mq_top_families_help"))])])));
    const body = el("tbody");
    for (const a of spec.asked) {
      // Which families this particular request points at. A position can be highly variable and
      // still be uninformative if the residue asked for is spread evenly; naming the families it
      // concentrates in is what turns the entropy figure into an answer.
      const top = topFamilies(a);
      body.appendChild(el("tr", { class: a.lowSpecificity ? "mq-low" : null }, [
        el("td", {}, [positionLabel(a.position, payload, numbering)]),
        el("td", { text: payload.segments[a.position] || "" }),
        el("td", {}, [el("strong", { text: [...a.residues].sort().join(" / ") }),
          a.lowSpecificity ? el("span", { class: "mq-flag", text: t("mq_low_specificity") }) : null]),
        el("td", { class: "mq-num", text: a.frequency === null ? "—" : pct(a.frequency) }),
        el("td", { class: "mq-num", text: a.entropy.toFixed(2) + " " + t("mq_bits") }),
        el("td", { class: "mq-num", text: a.weight.toFixed(2) }),
        /* One row per family: the tag on the left, and the way to the receptor table pinned to
           the right edge of the column rather than trailing the enrichment figure, where it read
           as part of the number. */
        el("td", {}, top.length ? top.map(r => {
          const family = nameOf.get(r.slug) || r.slug;
          return el("div", { class: "mq-famtag-row" }, [
            el("span", { class: "mq-famtag",
              title: t("mq_famtag_hint", { family, share: pct(r.share),
                n: r.enrichment.toFixed(1) }) }, [
              el("span", { text: family }),
              el("span", { class: "tab-count", text: t("mq_enrichment_x",
                { n: r.enrichment.toFixed(1) }) })]),
            el("button", { class: "mq-famtag-go", type: "button",
              "aria-label": t("mq_go_to_receptors", { family }),
              title: t("mq_go_to_receptors", { family }),
              onclick: () => receptorBox.scrollIntoView({ behavior: "smooth", block: "start" }) },
              [goArrowIE()])]);
        }) : [el("span", { class: "muted small", text: t("mq_famtag_none") })])]));
    }
    table.appendChild(body);
    specBox.appendChild(table);
    if (spec.allLowSpecificity)
      specBox.appendChild(el("p", { class: "notice mq-warn", text: t("mq_all_low_specificity") }));
    /* A position can be asked for and scored while not being offered in the reference below it,
       because the frequency filter governs what is listed, not what may be asked. Without saying
       so, a reader who typed 3x39 and then went looking for it in the table concludes it is not
       in the payload at all. */
    const offered = new Set(active);
    const hiddenAsked = parsed.groups.map(g => g.position).filter(x => !offered.has(x));
    if (hiddenAsked.length) {
      const line = el("p", { class: "muted small mq-hidden-asked" }, [
        el("span", { text: t("mq_asked_but_hidden", { positions: hiddenAsked.join(", ") }) + " " })]);
      line.appendChild(el("button", { class: "btn small", type: "button",
        text: t("mq_show_all_positions"), onclick: () => update({ minFreq: 0 }) }));
      specBox.appendChild(line);
    }
    if (spec.suggestions.length) {
      const line = el("p", { class: "muted small mq-suggest" }, [
        el("span", { text: t("mq_suggest") + " " })]);
      spec.suggestions.forEach((s, i) => {
        if (i) line.appendChild(document.createTextNode(" · "));
        const token = s.position + (s.consensus || "");
        line.appendChild(el("button", { class: "motif-chip", type: "button",
          title: t("mq_suggest_hint", { position: s.position, bits: s.entropy.toFixed(2) }),
          onclick: () => {
            const next = (state.query ? state.query.trim() + " " : "") + token;
            queryInput.value = next; update({ query: next });
          } }, [el("strong", { text: s.position }),
          el("span", { class: "tab-count", text: s.entropy.toFixed(2) })]));
      });
      specBox.appendChild(line);
    }
  }

  /* Entropy says a position varies. It does not say *who* varies, which is the question a reader
     actually arrives with: 6x30 carrying E in a third of receptors is only interesting once you
     can see which third. This is that breakdown — receptors per family, the share of that family
     carrying the residue, and how far above or below the Class A background it sits. */
  function familyDistributionBlock(position, residues) {
    const wrap = el("div", { class: "mq-famdist" });
    const dist = familyDistribution(payload, state.scope, position, residues, posIndex);
    const asked = [...residues].sort().join(" / ");
    if (!dist || !dist.rows.length) {
      wrap.appendChild(el("p", { class: "muted small", text: t("mq_famdist_none",
        { residue: asked, position }) }));
      return wrap;
    }
    wrap.appendChild(el("p", { class: "mq-famdist-head" }, [
      el("strong", { text: t("mq_famdist_title", { residue: asked, position }) }),
      el("span", { class: "muted small", text: t("mq_famdist_background",
        { carrying: dist.carrying, total: dist.total, share: pct(dist.background) }) }),
      metricHelp(t("mq_famdist_help"))]));
    const table = el("table", { class: "data compact mq-famdist-table" });
    table.appendChild(el("thead", {}, el("tr", {}, [
      el("th", { text: t("col_family") }),
      el("th", { class: "mq-num", text: t("mq_famdist_receptors") }),
      el("th", { class: "mq-num", text: t("mq_famdist_share") }),
      el("th", { class: "mq-num", text: t("mq_famdist_enrichment") })])));
    const tbody = el("tbody");
    for (const row of dist.rows) {
      const enriched = row.enrichment !== null && row.enrichment >= 1.5;
      tbody.appendChild(el("tr", { class: enriched ? "mq-enriched" : null }, [
        el("td", { text: nameOf.get(row.slug) || row.slug }),
        el("td", { class: "mq-num", text: row.receptors + " / " + row.covered }),
        el("td", { class: "mq-num", text: pct(row.share) }),
        el("td", { class: "mq-num", text: row.enrichment === null ? "—"
          : t("mq_enrichment_x", { n: row.enrichment.toFixed(1) }) })]));
    }
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }
  // The two families a requested residue concentrates in most, for the query summary.
  function topFamilies(group) {
    const dist = familyDistribution(payload, state.scope, group.position, group.residues, posIndex);
    if (!dist) return [];
    return dist.rows.filter(r => r.enrichment !== null && r.enrichment > 1).slice(0, 2);
  }

  /* The position reference. It is how a query gets built by clicking rather than typing, and now
     also how the family breakdown above is reached, so it stays on the page — but it is not an
     answer and does not sit above one. */
  function drawPositions(spec, parsed, active, hidden) {
    clear(positionBox);
    positionBox.appendChild(el("summary", {}, [
      el("span", { text: t("mq_positions_open_n", { n: active.length }) }),
      hidden ? el("span", { class: "muted small",
        text: " · " + t("mq_positions_hidden", { n: hidden }) }) : null].filter(Boolean)));
    const table = el("table", { class: "data compact" });
    table.appendChild(el("thead", {}, el("tr", {}, [
      el("th", { text: t("motif_position") }), el("th", { text: t("motif_segment") }),
      el("th", { text: t("motif_consensus") }),
      el("th", {}, [document.createTextNode(t("mq_entropy") + " "),
        metricHelp(t("mq_entropy_help"))]),
      el("th", {}, [document.createTextNode(t("motif_variation") + " "),
        metricHelp(t("motif_variation_help"))]),
      el("th", {}, [document.createTextNode(t("motif_mutation") + " "),
        metricHelp(t("motif_mutation_help"))])])));
    const body = el("tbody");
    const mutations = (payload.mutations || {})[state.scope] || {};
    const toggleResidue = (position, residue, on) => {
      const groups = parsed.groups.map(g => ({ position: g.position, residues: new Set(g.residues) }));
      let group = groups.find(g => g.position === position);
      if (!group) { group = { position, residues: new Set() }; groups.push(group); }
      if (on) group.residues.delete(residue); else group.residues.add(residue);
      const kept = groups.filter(g => g.residues.size)
        .sort((a, b) => payload.positions.indexOf(a.position) - payload.positions.indexOf(b.position));
      const next = queryText(kept);
      queryInput.value = next; update({ query: next });
    };
    for (const position of active) {
      const s = spec.stats.get(position);
      const asked = parsed.groups.find(g => g.position === position);
      const chips = el("span", { class: "motif-dist" });
      for (const [residue, n] of s.pairs) {
        const on = !!(asked && asked.residues.has(residue));
        const key = position + "|" + residue;
        const shown = openDist === key;
        /* Two targets again, for the same reason as the motif cards: reading which families
           carry this residue and asking for it are different intentions. The body opens the
           family breakdown, the `+` puts it in the query. */
        const chipBody = el("button", { class: "motif-chip-body", type: "button",
          "aria-expanded": shown ? "true" : "false",
          "aria-label": t(shown ? "mq_famdist_close" : "mq_famdist_open",
            { residue, position, n }),
          title: t("mq_famdist_open", { residue, position, n }) },
          [el("strong", { text: residue }), el("span", { class: "tab-count", text: String(n) })]);
        chipBody.addEventListener("click", () => { openDist = shown ? null : key; draw(); });
        const chipAdd = el("button", { class: "motif-chip-add", type: "button",
          "aria-pressed": on ? "true" : "false",
          "aria-label": t(on ? "mq_remove_residue" : "mq_add_residue", { residue, position }),
          title: t(on ? "mq_remove_residue" : "mq_add_residue", { residue, position }),
          text: on ? "−" : "+" });
        chipAdd.addEventListener("click", () => toggleResidue(position, residue, on));
        chips.appendChild(el("span", { class: "motif-chip split" + (on ? " active" : "") +
          (shown ? " open" : "") }, [chipBody, chipAdd]));
      }
      const m = mutations[position];
      body.appendChild(el("tr", { class: asked ? "mq-asked" : null }, [
        el("td", {}, [positionLabel(position, payload, numbering)]),
        el("td", { text: payload.segments[position] || "" }),
        el("td", { text: s.consensus || "—" }),
        el("td", { class: "mq-num", text: s.H.toFixed(2) }),
        el("td", {}, [chips]),
        el("td", { class: "mq-num",
          text: m ? m.structures + " " + t("structures_short") : "—" })]));
      if (openDist && openDist.startsWith(position + "|")) {
        const residue = openDist.slice(position.length + 1);
        body.appendChild(el("tr", { class: "mq-famdist-row" }, [
          el("td", { colspan: "6" }, [familyDistributionBlock(position, new Set([residue]))])]));
      }
    }
    table.appendChild(body);
    positionBox.appendChild(table);
  }

  function drawFamilies(agg) {
    clear(familyBox);
    if (!agg.families.length) return;
    familyBox.appendChild(el("h3", {}, [
      document.createTextNode(t("mq_family_ranking") + " "),
      metricHelp(t("mq_family_help"))]));
    const chart = el("div", { class: "mq-bars" });
    for (const f of agg.families) {
      const median = f.medianPhys || 0, max = f.maxPhys || 0;
      chart.appendChild(el("div", { class: "mq-bar-row" }, [
        el("span", { class: "mq-bar-label", text: nameOf.get(f.slug) || f.slug }),
        el("span", { class: "mq-bar-track",
          title: t("mq_bar_title", { median: pct(median), max: pct(max), n: f.receptors }) }, [
          el("span", { class: "mq-bar-fill", style: "width:" + (median * 100).toFixed(1) + "%" }),
          el("span", { class: "mq-bar-max", style: "left:calc(" + (max * 100).toFixed(1) + "% - 1px)" })]),
        el("span", { class: "mq-bar-value", text: pct(median) }),
        el("span", { class: "mq-bar-count", text: t("mq_n_receptors", { n: f.receptors }) })]));
    }
    familyBox.appendChild(chart);
    familyBox.appendChild(el("p", { class: "muted small", text: t("mq_family_note") }));
  }

  function drawReceptors(agg, rows) {
    clear(receptorBox);
    const head = el("div", { class: "result-head" });
    head.appendChild(el("strong", { text: t("mq_n_receptors_scored", { n: agg.receptors.length }) }));
    if (agg.unscored.length) head.appendChild(el("span", { class: "muted small",
      text: t("mq_n_uncovered_receptors", { n: agg.unscored.length }) }));
    const tied = topTieCount(rows, state.sort, nameOf, state.uniq);
    if (tied > 1) head.appendChild(el("span", { class: "mq-tie" }, [
      document.createTextNode(t("mq_tied_at_top", { n: tied,
        column: t("mq_col_" + (state.sort.replace(/^-/, "") === "phys" ? "phys"
          : state.sort.replace(/^-/, ""))) }) + " "),
      metricHelp(t("mq_tied_help"))]));
    /* Presentation only. Scoring already runs on one representative structure per receptor, so
       collapsing duplicate profiles changes no score anywhere — it changes what the structure
       column counts and which depositions the detail lists. */
    const uniqBox = el("input", { type: "checkbox", id: "mq-uniq", checked: state.uniq });
    uniqBox.addEventListener("change", () => update({ uniq: uniqBox.checked }));
    head.appendChild(el("label", { class: "mq-uniq-toggle", for: "mq-uniq" }, [
      uniqBox, el("span", { text: t("mq_uniq_toggle") }), metricHelp(t("mq_uniq_help"))]));
    const columns = [
      { key: "receptor", label: t("col_receptor"), get: r => r.receptor },
      { key: "receptor_name", label: t("col_receptor_name"), get: r => plainName(r.name) },
      { key: "family", label: t("col_family"), get: r => nameOf.get(r.family) || r.family },
      { key: "structures", label: t("mq_col_structures"), get: r => r.structureCount },
      { key: "structures_unique", label: t("mq_col_structures_unique"), get: r => r.unique.length },
      { key: "representative", label: t("mq_col_representative"), get: r => r.representative.pdb },
      { key: "positions_asked", label: t("col_positions_asked"), get: r => r.score.cells.length },
      { key: "positions_covered", label: t("mq_col_covered"), get: r => r.score.covered },
      { key: "exact", label: t("mq_col_exact_n"), get: r => r.score.exact },
      { key: "conservative", label: t("mq_col_conservative_n"), get: r => r.score.conservative },
      { key: "exact_pct", label: t("mq_col_exact"), get: r => r.score.exactPct === null ? "" :
          (r.score.exactPct * 100).toFixed(1) },
      { key: "physchem_pct", label: t("mq_col_phys"), get: r => r.score.physPct === null ? "" :
          (r.score.physPct * 100).toFixed(1) },
      { key: "weighted_pct", label: t("mq_col_weighted"), get: r => r.score.weightedPct === null ? "" :
          (r.score.weightedPct * 100).toFixed(1) },
      { key: "coverage_pct", label: t("mq_col_coverage"), get: r => r.score.coverage === null ? "" :
          (r.score.coverage * 100).toFixed(1) },
      { key: "engineered", label: t("mq_col_engineered"), get: r => r.score.engineered }];
    if (rows.length) {
      const meta = () => ({ release: L.getManifest().data_version || "", scope: state.scope,
        query: queryText(parseQuery(state.query, known, numbering).groups), rows: rows.length,
        unit: "one row per receptor; scores are computed on that receptor's representative "
            + "structure, over the positions the query covers in it" });
      head.appendChild(el("div", { class: "lx-exports" }, [
        el("button", { class: "btn small", type: "button", text: t("export_csv"),
          onclick: () => download("motif_receptors.csv", toCSV(columns, rows, meta())) }),
        el("button", { class: "btn small", type: "button", text: t("export_xlsx"),
          onclick: () => downloadXLSX("motif_receptors.xlsx", [
            { name: "Receptors", columns, rows },
            { name: "Query", columns: [
              { key: "position", label: t("col_position"), get: a => a.position },
              { key: "asked", label: t("mq_asked_for"), get: a => [...a.residues].sort().join(" / ") },
              { key: "consensus", label: t("motif_consensus"), get: a => a.consensus || "" },
              { key: "frequency", label: t("mq_receptor_frequency"),
                get: a => a.frequency === null ? "" : (a.frequency * 100).toFixed(1) },
              { key: "entropy", label: t("mq_entropy"), get: a => a.entropy.toFixed(3) },
              { key: "weight", label: t("mq_weight"), get: a => a.weight.toFixed(3) }],
              rows: lastSpec ? lastSpec.asked : [] }]) })]));
    }
    receptorBox.appendChild(head);
    if (!rows.length) {
      receptorBox.appendChild(el("p", { class: "muted", text: t("mq_no_rows") }));
      return;
    }
    const table = el("table", { class: "data compact mq-table" });
    const sortHead = (key, label, help) => {
      const active = state.sort.replace(/^-/, "") === key;
      const desc = state.sort.startsWith("-");
      const next = active && desc ? key : "-" + key;
      return el("th", { class: active ? "mq-sorted" : null,
        title: active ? t("mq_sorted_by", { column: label }) : null,
        "aria-sort": active ? (desc ? "descending" : "ascending") : "none" }, [
        el("button", { class: "mq-sort", type: "button", onclick: () => update({ sort: next }) }, [
          el("span", { text: label }),
          el("span", { class: "mq-sort-arrow", text: active ? (desc ? "▾" : "▴") : "" })]),
        help ? document.createTextNode(" ") : null, help || null]);
    };
    table.appendChild(el("thead", {}, el("tr", {}, [
      sortHead("receptor", t("col_receptor")),
      sortHead("family", t("col_family")),
      /* No structure count. It answered a question nobody was asking here — the depositions are
         listed by name in the detail beside the table, which is where a reader goes when they
         want them — and a column reading "2 / 4" next to four percentages invited the reading
         that it was a fifth score. */
      sortHead("coverage", t("mq_col_coverage"), metricHelp(t("mq_coverage_help"))),
      sortHead("exact", t("mq_col_exact"), metricHelp(t("mq_exact_help"))),
      sortHead("phys", t("mq_col_phys"), metricHelp(t("mq_phys_help"))),
      sortHead("weighted", t("mq_col_weighted"), metricHelp(t("mq_weighted_help")))])));
    const body = el("tbody");
    const shownReceptor = detailReceptor(agg, rows);
    for (const r of rows) {
      const selected = shownReceptor && r.receptor === shownReceptor.receptor;
      /* The whole row is the target, not just the name. The name still carries the button, so it
         is reachable by keyboard and announced as a control, but a reader who has just read
         across four numbers should not have to travel back to the first column to act on them. */
      const open = () => update({ hit: r.receptor }, true);
      const row = el("tr", { class: "mq-row" + (selected ? " selected" : ""),
        onclick: e => { if (!e.target.closest("button, a")) open(); } }, [
        el("th", { scope: "row" }, [
          el("button", { class: "mq-pick", type: "button",
            "aria-pressed": selected ? "true" : "false",
            title: t("mq_open_detail", { receptor: r.receptor }), onclick: open }, [
            el("strong", { text: plainName(r.name) || r.receptor }),
            el("small", { text: r.receptor })])]),
        el("td", { text: nameOf.get(r.family) || r.family }),
        scoreCell(r.score.coverage), scoreCell(r.score.exactPct),
        scoreCell(r.score.physPct), scoreCell(r.score.weightedPct),
        // The affordance, at the end of the row where the eye finishes.
        el("td", { class: "mq-row-go" }, [goArrow()])]);
      body.appendChild(row);
    }
    table.appendChild(body);
    receptorBox.appendChild(el("div", { class: "mq-table-scroll" }, table));
  }

  function drawHeatmap(rows, parsed) {
    clear(heatBox);
    if (!rows.length || !parsed.groups.length) return;
    const shown = rows.slice(0, state.top);
    heatBox.appendChild(el("h3", {}, [
      document.createTextNode(t("mq_heatmap") + " "), metricHelp(t("mq_heatmap_help"))]));
    const controls = el("div", { class: "mq-heat-controls" });
    controls.appendChild(el("label", { class: "filter-field" }, [
      el("span", { text: t("mq_top_n") }),
      el("input", { type: "number", min: "5", max: "200", step: "5", value: String(state.top),
        class: "mq-top-input", "aria-label": t("mq_top_n"),
        onchange: e => update({ top: Math.max(5, Math.min(200, Number(e.target.value) || 25)) }) })]));
    const legend = el("div", { class: "mq-legend" });
    for (const s of ["exact", "conservative", "mismatch", "uncovered"])
      legend.appendChild(el("span", { class: "mq-legend-item" }, [
        el("i", { class: "mq-swatch mq-" + s }), el("span", { text: t("mq_state_" + s) })]));
    legend.appendChild(el("span", { class: "mq-legend-item" }, [
      el("i", { class: "mq-swatch mq-exact mq-engineered" }),
      el("span", { text: t("mq_state_engineered") })]));
    controls.appendChild(legend);
    heatBox.appendChild(controls);
    const grid = el("div", { class: "mq-heat",
      style: "grid-template-columns:minmax(150px,1.6fr) repeat(" + parsed.groups.length +
             ",minmax(46px,1fr))" });
    grid.appendChild(el("span", { class: "mq-heat-corner", text: t("col_receptor") }));
    for (const g of parsed.groups)
      grid.appendChild(el("span", { class: "mq-heat-head" }, [
        positionLabel(g.position, payload, numbering),
        el("small", { text: [...g.residues].sort().join("/") })]));
    for (const r of shown) {
      grid.appendChild(el("button", { class: "mq-heat-name" +
        (r.receptor === state.hit ? " selected" : ""), type: "button",
        title: t("mq_open_detail", { receptor: r.receptor }),
        onclick: () => update({ hit: r.receptor }, true) }, [
        el("span", { text: plainName(r.name) || r.receptor })]));
      for (const cell of r.score.cells)
        grid.appendChild(el("span", { class: "mq-cell mq-" + cell.status +
            (cell.engineered ? " mq-engineered" : ""),
          title: cellTitle(cell, r),
          text: cell.status === "uncovered" ? "·" : cell.wild }));
    }
    heatBox.appendChild(grid);
    if (rows.length > shown.length) heatBox.appendChild(el("p", { class: "muted small",
      text: t("mq_heat_truncated", { shown: shown.length, total: rows.length }) }));
  }

  function cellTitle(cell, r) {
    const wanted = cell.wanted.join(" / ");
    if (cell.status === "uncovered")
      return r.receptor + " " + cell.position + " — " + t("mq_uncovered_" + cell.reason);
    const base = r.receptor + " " + cell.position + " — " + t("mq_cell_" + cell.status,
      { wanted, carried: cell.wild,
        distance: cell.distance === null ? "—" : cell.distance.toFixed(0) });
    return cell.engineered
      ? base + " · " + t("mq_cell_engineered", { construct: cell.construct || "?" })
      : base;
  }

  /* --------------------------------------------------------- 7. detail aside */
  /* Which receptor the detail shows. With nothing chosen it is the first row: the panel has just
     ranked two hundred receptors and leaving the answer to that ranking closed, behind a click
     whose target was not obvious, wasted the ranking. "none" is an explicit dismissal and is the
     only state written to the address, because it is the only one a reader chose. */
  function detailReceptor(agg, rows) {
    if (state.hit === "none") return null;
    if (state.hit) return agg.receptors.find(r => r.receptor === state.hit) || rows[0] || null;
    return rows[0] || null;
  }
  function drawDetail(agg, parsed, rows) {
    clear(aside);
    const receptor = detailReceptor(agg, rows);
    aside.hidden = !receptor;
    if (!receptor) return;
    const head = el("div", { class: "mq-detail-head" });
    head.appendChild(el("h3", { text: plainName(receptor.name) || receptor.receptor }));
    head.appendChild(el("button", { class: "btn small", type: "button", text: t("lx_close_detail"),
      onclick: () => update({ hit: "none" }, true) }));
    aside.appendChild(head);
    aside.appendChild(el("p", { class: "muted small", text: receptor.receptor + " · " +
      (nameOf.get(receptor.family) || receptor.family) + " · " +
      t("mq_representative_is", { pdb: receptor.representative.pdb }) }));

    const scores = el("dl", { class: "mq-scores" });
    const scoreRow = (label, value, help) => {
      scores.appendChild(el("dt", {}, [document.createTextNode(label + " "), metricHelp(help)]));
      scores.appendChild(el("dd", { text: value === null ? "—" : pct(value) }));
    };
    scoreRow(t("mq_col_exact"), receptor.score.exactPct, t("mq_exact_help"));
    scoreRow(t("mq_col_phys"), receptor.score.physPct, t("mq_phys_help"));
    scoreRow(t("mq_col_weighted"), receptor.score.weightedPct, t("mq_weighted_help"));
    scoreRow(t("mq_col_coverage"), receptor.score.coverage, t("mq_coverage_help"));
    aside.appendChild(scores);

    // Position by position: what was asked, what this receptor carries, and how far apart they
    // are on Grantham's scale, so a "conservative" call can be checked rather than believed.
    const table = el("table", { class: "data compact mq-detail-table" });
    table.appendChild(el("thead", {}, el("tr", {}, [
      el("th", { text: t("motif_position") }), el("th", { text: t("mq_asked_for") }),
      el("th", { text: t("mq_carried") }),
      el("th", {}, [document.createTextNode(t("mq_distance") + " "),
        metricHelp(t("mq_distance_help"))])])));
    const body = el("tbody");
    for (const cell of receptor.score.cells) {
      body.appendChild(el("tr", { class: "mq-" + cell.status }, [
        el("td", {}, [positionLabel(cell.position, payload, numbering,
          { segment: payload.segments[cell.position] || "" })]),
        el("td", { text: cell.wanted.join(" / ") }),
        el("td", {}, cell.status === "uncovered"
          ? [el("span", { class: "muted", text: t("mq_uncovered_" + cell.reason) })]
          : [el("strong", { text: cell.wild }),
             cell.engineered ? el("span", { class: "mq-flag",
               text: t("mq_engineered_to", { construct: cell.construct || "?" }) }) : null]),
        el("td", { class: "mq-num",
          text: cell.distance === null ? "—" : cell.distance.toFixed(0) })]));
    }
    table.appendChild(body);
    aside.appendChild(table);

    const raised = receptor.score.cells.filter(c => c.status === "exact").map(c => c.position);
    const lowered = receptor.score.cells.filter(c => c.status === "mismatch").map(c => c.position);
    const near = receptor.score.cells.filter(c => c.status === "conservative").map(c => c.position);
    const uncovered = receptor.score.cells.filter(c => c.status === "uncovered").map(c => c.position);
    const summary = el("ul", { class: "mq-why" });
    if (raised.length) summary.appendChild(el("li", { class: "mq-exact",
      text: t("mq_why_raised", { positions: raised.join(", ") }) }));
    if (near.length) summary.appendChild(el("li", { class: "mq-conservative",
      text: t("mq_why_near", { positions: near.join(", ") }) }));
    if (lowered.length) summary.appendChild(el("li", { class: "mq-mismatch",
      text: t("mq_why_lowered", { positions: lowered.join(", ") }) }));
    if (uncovered.length) summary.appendChild(el("li", { class: "mq-uncovered",
      text: t("mq_why_uncovered", { positions: uncovered.join(", ") }) }));
    aside.appendChild(summary);

    // The deposition list, which is where it belongs: evidence under a receptor, not the unit
    // the panel ranks.
    const listed = state.uniq ? receptor.unique : receptor.structures;
    aside.appendChild(el("h4", { text: state.uniq
      ? t("mq_structures_unique_of", { n: listed.length, total: receptor.structureCount })
      : t("mq_structures_of", { n: receptor.structureCount }) }));
    const list = el("div", { class: "mq-pdb-list" });
    for (const s of listed) {
      const engineered = Object.keys(s.record.m || {});
      const uncoveredHere = s.score.cells.filter(c => c.status === "uncovered").map(c => c.position);
      list.appendChild(el("div", { class: "mq-pdb" + (s === receptor.representative ? " rep" : "") }, [
        el("code", { text: s.pdb }),
        el("span", { class: "muted small", text:
          t("mq_pdb_line", { covered: s.score.covered, total: s.score.cells.length,
            exact: s.score.exact }) }),
        engineered.length ? el("span", { class: "mq-flag", text: t("mq_pdb_engineered", {
          list: engineered.map(p => p + "→" + s.record.m[p]).join(", ") }) }) : null,
        uncoveredHere.length ? el("span", { class: "muted small",
          text: t("mq_pdb_uncovered", { list: uncoveredHere.join(", ") }) }) : null,
        // What this one entry stands in for, named rather than merely counted away.
        (s.alsoIn && s.alsoIn.length) ? el("span", { class: "muted small mq-pdb-same",
          title: s.alsoIn.join(", "),
          text: t("mq_pdb_same_profile", { n: s.alsoIn.length,
            list: s.alsoIn.slice(0, 6).join(", ") + (s.alsoIn.length > 6 ? " …" : "") }) }) : null,
        // Secondary, and labelled as what it is. The panel never opens the viewer by itself.
        el("a", { class: "mq-3d-link",
          href: "#" + buildHash({ family: s.record.f, view: "3d", pdb: s.pdb }).slice(1),
          title: t("mq_open_3d_hint", { pdb: s.pdb }), text: t("mq_open_3d") })]));
    }
    aside.appendChild(list);
  }

  let lastSpec = null;
  /* What the receptor list is a list *of*. Redrawing rebuilds the scroll box, which resets it to
     the top; that is right when the query changed and wrong when the reader merely picked a row
     forty rows down and watched the table jump away from them. Everything except the selection
     goes into this signature, and the scroll position is carried over when it has not moved. */
  const listSignature = st => [st.pool, st.scope, st.query, st.sort, st.uniq,
                               st.siteClass, st.minFreq].join("\u0000");
  // The position subset currently on offer, recomputed by draw() before anything reads it.
  let active = [];
  let drawnSignature = null;
  /* Which residue chip has its family breakdown open, as "position|residue". Kept out of the
     route deliberately: it is a glance at a distribution, not a query worth sharing. */
  let openDist = null;
  function draw() {
    scopeSelect.value = state.scope;
    poolSelect.value = state.pool;
    const pocket = state.pool === "pocket";
    classField.hidden = !pocket; freqField.hidden = !pocket;
    if (pocket) {
      const classes = siteClassesOf(payload);
      const chosen = classes.includes(state.siteClass) ? state.siteClass : classes[0];
      clear(classSelect);
      for (const name of classes) {
        const info = payload.pool.site_classes[name];
        classSelect.appendChild(el("option", { value: name, selected: name === chosen,
          text: siteClassLabel(name) + " (" + info.receptors + ")" }));
      }
      classSelect.value = chosen;
      freqSelect.value = String(state.minFreq);
      /* With a small denominator the threshold stops discriminating: in a class of eight
         receptors a single one already counts for 12.5%, so every slider position below that is
         the same filter wearing different numbers. Said plainly rather than left for the reader
         to work out from a dropdown they were not looking at. */
      const denominator = (payload.pool.site_classes[chosen] || {}).receptors || 0;
      clear(freqNote);
      if (denominator && denominator < 20) {
        const one = 1 / denominator;
        freqNote.appendChild(el("span", { class: "mq-flag", text: t("mq_small_denominator",
          { n: denominator, share: pct(one) }) }));
      }
    }
    active = activePositions(payload, state);
    const activeSet = new Set(active);
    const hidden = payload.positions.length - active.length;
    const parsed = parseQuery(state.query, known, numbering);
    /* A query arriving from the address may separate its tokens with `+` and give them in any
       order. Show it in the form the panel itself writes — but only while the field is not being
       typed in, and only when everything in it parsed: a typo has to stay on screen where it can
       be corrected, not be tidied out of sight. */
    if (document.activeElement !== queryInput) {
      const canonical = parsed.bad.length || parsed.retired.length
        ? state.query : queryText(parsed.groups);
      if (queryInput.value !== canonical) queryInput.value = canonical;
    }
    const spec = specificity(payload, state.scope, parsed.groups, activeSet);
    lastSpec = spec;
    drawSpecificity(spec, parsed);
    drawPositions(spec, parsed, active, hidden);
    drawMotifCards(activeSet);
    if (!parsed.groups.length) {
      clear(familyBox); clear(receptorBox); clear(heatBox); clear(aside); aside.hidden = true;
      return;
    }
    const agg = aggregate(payload, parsed.groups, posIndex, spec, state.scope);
    const rows = sortReceptors(agg.receptors, state.sort, nameOf, state.uniq);
    const previousScroll = receptorBox.querySelector(".mq-table-scroll");
    const keptScroll = previousScroll ? previousScroll.scrollTop : 0;
    const sameList = drawnSignature === listSignature(state);
    drawnSignature = listSignature(state);
    drawFamilies(agg);
    drawReceptors(agg, rows);
    if (sameList && keptScroll) {
      const rebuilt = receptorBox.querySelector(".mq-table-scroll");
      if (rebuilt) rebuilt.scrollTop = keptScroll;
    }
    drawHeatmap(rows, parsed);
    drawDetail(agg, parsed, rows);
  }

  /* Selecting a residue at the foot of the page changes the answer at the head of it, and a
     reader who has scrolled down to the reference has no way of knowing that. The button appears
     exactly when the query summary is off screen above and there is a query to go back to, and
     it takes them there. */
  const backUp = el("button", { class: "mq-backup", type: "button", hidden: true,
    "aria-label": t("mq_back_to_query"), title: t("mq_back_to_query") }, [
    el("span", { class: "mq-backup-arrow", "aria-hidden": "true", text: "\u2191" }),
    el("span", { text: t("mq_back_to_query_short") })]);
  backUp.addEventListener("click", () => specBox.scrollIntoView({ behavior: "smooth", block: "start" }));
  wrap.appendChild(backUp);
  if ("IntersectionObserver" in window) {
    const watch = new IntersectionObserver(entries => {
      const summaryVisible = entries[0].isIntersecting;
      const hasQuery = !!parseQuery(state.query, known, numbering).groups.length;
      backUp.hidden = summaryVisible || !hasQuery;
    }, { threshold: 0 });
    watch.observe(specBox);
  }

  mounted = { node: wrap, setRoute };
  draw();
  return wrap;
}
