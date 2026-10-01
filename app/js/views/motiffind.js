/* Find motif - the simple reading (prototype).
 *
 * The motif query panel answers every question a position set can be asked, and shows all of it at
 * once: the query builder, the specificity statistics and the 21-position reference sit above the
 * answer, which starts two screens down. This view asks one question - which receptors carry this
 * motif? - and answers it first. Nothing is scored differently: parsing, scoring and aggregation
 * are the motif query module's own functions, so a receptor is in the same state here as there.
 *
 *   1. The question: one field, the named motifs as one-click starting points, and the scope.
 *   2. What was asked: one card per position, saying in words how common the residue is.
 *   3. The answer: receptors split into exact, similar, different and no data, each row showing the
 *      receptor's own residues coloured by state, with the structure one click away.
 *
 * The statistics (entropy, weights, enrichment) and the position reference are one link away in
 * the full panel, carrying the same query.
 */
import { t, getLang, siteClassLabel } from "../core/i18n.js";
import { el, clear, pct, debounce } from "../components/dom.js";
import { plainName, familyDisplayName } from "./views.js";
import { toCSV, download } from "../components/csv.js";
import * as L from "../data/loader.js";
import { buildHash, navigate } from "../core/router.js";
import { parseQuery, queryText, specificity, aggregate, granthamDistance } from "./motifquery.js";

const POOLS = { motif: L.loadMotifSearch, pocket: L.loadPocketSearch, receptor: L.loadReceptorSearch };
const TABS = ["exact", "similar", "different", "nodata"];

/* How common the residue asked for is among the receptors in scope, in words. The number is on the
   card as well; the words say what it means for the question - a residue nearly every receptor
   carries cannot tell receptors apart. */
function commonness(freq) {
  if (freq === null || freq === undefined) return { key: "mf_common_unknown", cls: "unknown" };
  if (freq >= 0.9) return { key: "mf_common_nearly_all", cls: "all" };
  if (freq >= 0.5) return { key: "mf_common_most", cls: "most" };
  if (freq >= 0.2) return { key: "mf_common_some", cls: "some" };
  return { key: "mf_common_few", cls: "few" };
}

/* One receptor, one category. Any residue that is chemically different puts it in "different";
   otherwise any conservative substitution makes it "similar"; otherwise every position that could
   be read is exactly what was asked. Positions that could not be read never count against it -
   the row says how many were read. */
function categoryOf(r) {
  const s = r.score;
  if (!s.covered) return "nodata";
  if (s.cells.some(c => c.status === "mismatch")) return "different";
  if (s.conservative > 0) return "similar";
  return "exact";
}

export async function motifFind(root, route) {
  clear(root);
  const wrap = el("section", { class: "view mf" });
  root.appendChild(wrap);

  const state = {
    query: String(route.motif || ""),
    scope: String(route.scope || "class_a"),
    pool: POOLS[route.pool] ? route.pool : "receptor",
    tab: TABS.includes(route.tab) ? route.tab : "",
    // The pocket set lists every position any ligand has touched in any binding site class, which
    // is most of the bundle; it is read through one class and a contact threshold, as in the full
    // panel, so "the pocket" means the positions that class's ligands actually reach.
    siteClass: String(route.class || "canonical_7tm_pocket"),
    minFreq: route.minfreq !== undefined && Number.isFinite(Number(route.minfreq))
      ? Math.max(0, Math.min(1, Number(route.minfreq))) : 0.10,
    // The whole-receptor set holds every position any receptor resolves - 3x17 is in three of 200 -
    // so it is read, as in the full panel, through the share of receptors that have the position.
    minCov: route.mincov !== undefined && Number.isFinite(Number(route.mincov))
      ? Math.max(0, Math.min(1, Number(route.mincov))) : 0.10,
    logo: route.logo === "freq" || route.logo === "bits" ? route.logo : "",
    open: String(route.open || "")
  };
  let payload, numbering = null, posIndex = new Map(), known = new Set();
  try { numbering = await L.loadGenericNumbering(); } catch (e) { numbering = null; }
  async function loadPool() {
    payload = await POOLS[state.pool]();
    posIndex = new Map(payload.positions.map((p, i) => [p, i]));
    known = new Set(payload.positions);
  }
  try { await loadPool(); }
  catch (error) { wrap.appendChild(el("p", { class: "notice", text: L.errorMessage(error) })); return wrap; }
  const families = L.getManifest().families || [];
  const nameOf = new Map(families.map(f => [f.slug, familyDisplayName(f.name)]));

  function writeRoute() {
    const r = { view: "motiffind" };
    if (route.family) r.family = route.family;
    if (state.query) r.motif = state.query;
    if (state.scope !== "class_a") r.scope = state.scope;
    if (state.pool !== "receptor") r.pool = state.pool;
    if (state.pool === "receptor" && state.minCov !== 0.10) r.mincov = String(state.minCov);
    if (state.logo) r.logo = state.logo;
    if (state.pool === "pocket") {
      if (state.siteClass !== "canonical_7tm_pocket") r.class = state.siteClass;
      if (state.minFreq !== 0.10) r.minfreq = String(state.minFreq);
    }
    if (state.tab) r.tab = state.tab;
    if (state.open) r.open = state.open;
    navigate(r, true);
  }
  // A redraw rebuilds the answer, which empties the page for a moment; the reader stays where
  // they were rather than being thrown back to the top.
  function set(patch) {
    Object.assign(state, patch);
    writeRoute();
    const y = window.scrollY;
    draw();
    window.scrollTo(0, y);
  }

  /* ------------------------------------------------------------ 1. the question */
  wrap.appendChild(el("div", { class: "mf-head" }, [
    el("h2", { text: t("mf_title") }),
    el("span", { class: "mf-beta", text: t("mf_prototype") })]));
  wrap.appendChild(el("p", { class: "muted mf-lede", text: t("mf_lede") }));

  const input = el("input", { type: "text", class: "mf-input", spellcheck: "false",
    value: state.query, placeholder: t("mf_placeholder"), "aria-label": t("mf_title") });
  /* Only a real edit resets the reading. An input event also arrives without one - an input method
     (IBus on Linux) sends one when the window regains focus - and treating it as a new query closed
     the receptor the reader had open and sent the tabs back to the first. */
  input.addEventListener("input", debounce(() => {
    if (input.value.trim() === state.query.trim()) return;
    set({ query: input.value, open: "", tab: "" });
  }, 250));
  const clearBtn = el("button", { class: "btn small", type: "button", text: t("mq_clear"),
    onclick: () => { input.value = ""; set({ query: "", open: "", tab: "" }); } });
  const scopeSelect = el("select", { class: "mf-scope", "aria-label": t("motif_scope") });
  scopeSelect.appendChild(el("option", { value: "class_a", text: t("motif_scope_class_a") }));
  for (const f of families) scopeSelect.appendChild(el("option", { value: f.slug, text: familyDisplayName(f.name) }));
  scopeSelect.value = state.scope;
  scopeSelect.addEventListener("change", () => set({ scope: scopeSelect.value, open: "", tab: "" }));

  const ask = el("div", { class: "mf-ask" }, [
    el("div", { class: "mf-ask-row" }, [input, clearBtn]),
    el("label", { class: "mf-scope-field" }, [el("span", { text: t("mf_in") }), scopeSelect])]);
  wrap.appendChild(ask);
  wrap.appendChild(el("p", { class: "muted small mf-hint", text: t("mf_hint") }));

  const chips = el("div", { class: "mf-chip-rows" });
  wrap.appendChild(chips);

  // Advanced: which position set the motifs and the field read from. Folded: the default answers
  // the question most readers arrive with.
  const poolSelect = el("select", { "aria-label": t("mq_pool") });
  for (const [v, k] of [["receptor", "mq_pool_receptor"], ["motif", "mq_pool_motif"], ["pocket", "mq_pool_pocket"]])
    poolSelect.appendChild(el("option", { value: v, text: t(k) }));
  poolSelect.value = state.pool;
  poolSelect.addEventListener("change", async () => {
    state.pool = poolSelect.value; state.open = ""; state.tab = "";
    await loadPool(); writeRoute(); draw();
  });
  const fullLink = el("a", { class: "mf-full-link" });
  const classSelect = el("select", { "aria-label": t("mq_site_class") });
  classSelect.addEventListener("change", () => set({ siteClass: classSelect.value, open: "", tab: "" }));
  const freqSelect = el("select", { "aria-label": t("mq_min_freq") });
  for (const v of [0, 0.01, 0.05, 0.10, 0.25, 0.50])
    freqSelect.appendChild(el("option", { value: String(v), text: v === 0 ? t("mq_min_freq_any") : Math.round(v * 100) + "%" }));
  freqSelect.addEventListener("change", () => set({ minFreq: Number(freqSelect.value), open: "", tab: "" }));
  const covSelect = el("select", { "aria-label": t("mq_min_coverage") });
  for (const v of [0, 0.05, 0.10, 0.25, 0.50, 0.75])
    covSelect.appendChild(el("option", { value: String(v), text: v === 0 ? t("mq_min_coverage_any") : Math.round(v * 100) + "%" }));
  covSelect.addEventListener("change", () => set({ minCov: Number(covSelect.value), open: "", tab: "" }));
  const receptorControls = el("div", { class: "mf-pocket-controls" }, [
    el("label", { class: "filter-field" }, [el("span", { text: t("mq_min_coverage") }), covSelect]),
    el("p", { class: "muted small", text: t("mf_coverage_note") })]);
  const pocketControls = el("div", { class: "mf-pocket-controls" }, [
    el("label", { class: "filter-field" }, [el("span", { text: t("mq_site_class") }), classSelect]),
    el("label", { class: "filter-field" }, [el("span", { text: t("mq_min_freq") }), freqSelect]),
    el("p", { class: "muted small", text: t("mf_pocket_note") })]);
  /* Which positions the chips, ranges and logo offer. Everything for the whole receptor and the
     microswitch set; for the pocket, the positions the chosen class's ligands reach often enough. */
  function activeSet() {
    if (state.pool === "receptor" && payload.position_meta)
      return new Set(payload.positions.filter(p => {
        const meta = payload.position_meta[p];
        return meta && typeof meta.coverage === "number" && meta.coverage >= state.minCov;
      }));
    if (state.pool !== "pocket" || !payload.position_meta) return new Set(payload.positions);
    return new Set(payload.positions.filter(p => {
      const meta = payload.position_meta[p];
      const f = meta && meta.frequency ? meta.frequency[state.siteClass] : undefined;
      return f !== undefined && f >= state.minFreq;
    }));
  }
  // Always open: the position set and its threshold decide what the chips and the logo offer, so
  // they stay in sight rather than behind a disclosure a reader forgets is there.
  wrap.appendChild(el("div", { class: "mf-advanced" }, [
    el("div", { class: "mf-advanced-title", text: t("mf_advanced") }),
    el("div", { class: "mf-advanced-body" }, [
      el("label", { class: "filter-field" }, [el("span", { text: t("mq_pool") }), poolSelect]),
      pocketControls, receptorControls,
      el("p", { class: "muted small" }, [el("span", { text: t("mf_full_panel_note") + " " }), fullLink])])]));

  /* ------------------------------------------------------------ 2. what was asked */
  const logoBox = el("div", { class: "mf-logo-box" });
  wrap.appendChild(logoBox);
  const cards = el("div", { class: "mf-cards" });
  wrap.appendChild(cards);
  const problems = el("div", {});
  wrap.appendChild(problems);

  /* ------------------------------------------------------------ 3. the answer */
  const answer = el("div", { class: "mf-answer" });
  wrap.appendChild(answer);

  function consensusTokens(m) {
    const dist = (payload.variation || {})[state.scope] || {};
    return m.positions.filter(p => dist[p] && dist[p].consensus).map(p => p + dist[p].consensus);
  }
  function motifName(m) {
    const key = "motif_" + m.motif_id, known = t(key);
    if (known !== key) return known;
    if (m.motif_id.startsWith("segment_")) return m.motif_id.slice(8);
    return m.motif_id.replace(/^consensus_/, "").replaceAll("_", " ");
  }
  const SEGMENT_ORDER = ["TM1", "ICL1", "TM2", "ECL1", "TM3", "ICL2", "TM4", "ECL2", "TM5", "ICL3",
    "TM6", "ECL3", "TM7", "H8"];
  /* Segments fill the field position by position with each position's consensus residue in scope,
     like the motif chips. A range (3x21-3x56) is still accepted when typed, for the logo alone. */
  function drawSegmentChips(active, held) {
    const bySeg = new Map();
    for (const p of payload.positions) {
      if (!active.has(p)) continue;
      const seg = payload.segments[p];
      if (!seg) continue;
      if (!bySeg.has(seg)) bySeg.set(seg, []);
      bySeg.get(seg).push(p);
    }
    const row = el("div", { class: "mf-chips mf-seg-chips" },
      [el("span", { class: "muted small mf-chips-label", text: t("mf_segments") })]);
    const segs = [...bySeg.keys()].sort((a, b) =>
      (SEGMENT_ORDER.indexOf(a) + 1 || 99) - (SEGMENT_ORDER.indexOf(b) + 1 || 99));
    for (const seg of segs) {
      const list = bySeg.get(seg).sort((a, b) => orderOf(a) - orderOf(b));
      // Written out position by position with the consensus residue in scope, as the motif chips
      // are, so every position of the segment is in the query and can be edited one by one.
      const dist = (payload.variation || {})[state.scope] || {};
      const token = list.map(p => p + ((dist[p] && dist[p].consensus) || "")).join(" ");
      const current = state.query.trim() === token;
      row.appendChild(el("button", { type: "button", class: "mf-seg" + (current ? " active" : ""),
        title: t("mf_segment_hint", { segment: seg, n: list.length, from: list[0], to: list[list.length - 1] }),
        onclick: () => { const next = current ? "" : token; input.value = next; set({ query: next, open: "", tab: "" }); } },
        [el("span", { text: seg }), el("span", { class: "tab-count", text: String(list.length) })]));
    }
    return row;
  }
  function drawChips(parsed) {
    clear(chips);
    const active = activeSet();
    const named = el("div", { class: "mf-chips" },
      [el("span", { class: "muted small mf-chips-label", text: t("mf_ready") })]);
    chips.appendChild(named);
    const held = new Set(parsed.groups.map(g => g.position));
    for (const m of payload.motifs || []) {
      // The named motifs only. The sets also carry consensus groups per binding site class and
      // per-segment groups; segments get their own row, built from the positions themselves so
      // every set offers the same ones.
      if (t("motif_" + m.motif_id) === "motif_" + m.motif_id) continue;
      if (!m.positions.some(p => active.has(p))) continue;
      const tokens = consensusTokens(m).filter(tok => active.has(tok.replace(/[A-Z]+$/, "")));
      if (!tokens.length) continue;
      const text = tokens.join(" ");
      const current = queryText(parsed.groups) === text;
      const inQuery = m.positions.some(p => held.has(p));
      const chip = el("span", { class: "mf-chip" + (current ? " active" : inQuery ? " partial" : "") });
      chip.appendChild(el("button", { type: "button", class: "mf-chip-main",
        title: t("mf_chip_hint", { motif: motifName(m), tokens: text }),
        onclick: () => { const next = current ? "" : text; input.value = next; set({ query: next, open: "", tab: "" }); } },
        [el("span", { text: motifName(m) })]));
      chip.appendChild(el("button", { type: "button", class: "mf-chip-add", text: "+",
        title: t("mf_chip_add", { motif: motifName(m) }), "aria-label": t("mf_chip_add", { motif: motifName(m) }),
        onclick: () => {
          const add = tokens.filter(tok => !held.has(tok.replace(/[A-Z]+$/, "")));
          const next = (input.value.trim() + " " + add.join(" ")).trim();
          input.value = next; set({ query: next, open: "", tab: "" });
        } }));
      named.appendChild(chip);
    }
    chips.appendChild(drawSegmentChips(active, held));
  }

  function drawCards(parsed, spec, split) {
    clear(cards); clear(problems);
    if (parsed.bad.length) problems.appendChild(el("p", { class: "motif-bad",
      text: t("motif_query_bad", { tokens: parsed.bad.join(", ") }) }));
    for (const item of parsed.translated || [])
      problems.appendChild(el("p", { class: "muted small",
        text: t("mq_bw_translated", { pairs: item.from + " → " + item.to }) }));
    if (!parsed.groups.length) return;
    /* What is scored and what is only shown. A segment opens forty positions in the logo, and a
       letter clicked there puts one position in the query; without saying so, two scored positions
       under a forty-column logo read as a broken query. */
    const logoOnly = split.positions.filter(p => !parsed.groups.some(g => g.position === p));
    const summary = el("div", { class: "mf-asked-summary" }, [
      el("span", { class: "mf-asked-scored", text: t("mf_asked_scored", { n: parsed.groups.length }) })]);
    if (logoOnly.length) summary.appendChild(el("span", { class: "muted small",
      text: " · " + t("mf_asked_logo_only", { n: logoOnly.length, tokens: split.shownTokens.join(" ") }) }));
    cards.appendChild(summary);
    /* Grouped by how common the residue is rather than one card per position: a helix asked for in
       full was forty cards. The rarest first, because those are the positions that select. */
    const bands = new Map();
    for (const a of spec.asked) {
      const c = commonness(a.frequency);
      if (!bands.has(c.cls)) bands.set(c.cls, { key: c.key, items: [] });
      bands.get(c.cls).items.push(a);
    }
    for (const cls of ["few", "some", "most", "all", "unknown"]) {
      const band = bands.get(cls);
      if (!band) continue;
      const row = el("div", { class: "mf-band mf-common-" + cls }, [
        el("span", { class: "mf-band-label", title: t(band.key + "_hint"), text: t(band.key) })]);
      for (const a of band.items) {
        const residues = [...a.residues].sort().join("/");
        row.appendChild(el("span", { class: "mf-tag",
          title: a.position + " " + (payload.segments[a.position] || "") + " · " + residues + " · " +
            (a.frequency === null ? "—" : pct(a.frequency)) + " " + t("mf_of_receptors") }, [
          el("strong", { text: a.position }),
          el("span", { class: "mf-tag-res", text: residues }),
          el("span", { class: "mf-tag-pct", text: a.frequency === null ? "—" : pct(a.frequency) }),
          el("button", { class: "mf-tag-x", type: "button", text: "\u00d7",
            "aria-label": t("mf_remove_position", { position: a.position }),
            title: t("mf_remove_position", { position: a.position }),
            onclick: () => {
              const keep = parsed.groups.filter(g => g.position !== a.position);
              const rest = input.value.split(/[\s,;+]+/).filter(tok => /-|^\d+[x.]\d+$/.test(tok));
              const next = [queryText(keep), ...rest].filter(Boolean).join(" ");
              input.value = next; set({ query: next, open: "", tab: "" });
            } })]));
      }
      cards.appendChild(row);
    }
    if (spec.allLowSpecificity)
      problems.appendChild(el("p", { class: "notice mf-warn", text: t("mf_all_common") }));
  }

  /* The receptor's own residues at the asked positions, one coloured letter each. */
  function residueStrip(r) {
    const strip = el("span", { class: "mf-strip" });
    for (const cell of r.score.cells) {
      const letter = cell.status === "uncovered" ? "·" : cell.wild;
      const title = cell.status === "uncovered"
        ? cell.position + ": " + t("mq_uncovered_" + cell.reason)
        : cell.position + ": " + t("mf_state_" + cell.status, { carried: cell.wild, wanted: cell.wanted.join("/") }) +
          (cell.engineered ? " · " + t("mq_cell_engineered", { construct: cell.construct || "?" }) : "");
      strip.appendChild(el("span", { class: "mf-letter mq-" + cell.status + (cell.engineered ? " mf-eng" : ""),
        title, text: letter }));
    }
    return strip;
  }
  function viewerHash(pdb, family, parsed) {
    return "#" + buildHash({ family, view: "3d", pdb, whole: "1",
      mark: parsed.groups.map(g => g.position).join(",") || null }).slice(1);
  }
  function detailRow(r, parsed) {
    const box = el("div", { class: "mf-detail" });
    const table = el("table", { class: "data compact mf-detail-table" });
    table.appendChild(el("thead", {}, el("tr", {}, [
      el("th", { text: t("motif_position") }), el("th", { text: t("mq_asked_for") }),
      el("th", { text: t("mf_this_receptor") }), el("th", { text: t("mf_verdict") })])));
    const body = el("tbody");
    for (const cell of r.score.cells) {
      let verdict;
      if (cell.status === "uncovered") verdict = t("mq_uncovered_" + cell.reason);
      else if (cell.status === "exact") verdict = t("mf_verdict_exact");
      else verdict = t(cell.status === "conservative" ? "mf_verdict_similar" : "mf_verdict_different",
        { d: cell.distance === null ? "—" : cell.distance.toFixed(0) });
      if (cell.engineered) verdict += " · " + t("mq_engineered_to", { construct: cell.construct || "?" });
      body.appendChild(el("tr", { class: "mq-" + cell.status }, [
        el("td", {}, [el("strong", { text: cell.position }),
          el("span", { class: "muted small", text: " " + (payload.segments[cell.position] || "") })]),
        el("td", { text: cell.wanted.join(" / ") }),
        el("td", {}, [el("strong", { text: cell.status === "uncovered" ? "—" : cell.wild })]),
        el("td", { text: verdict })]));
    }
    table.appendChild(body);
    box.appendChild(table);
    box.appendChild(el("h4", { text: t("mf_structures", { n: r.unique.length, total: r.structureCount }) }));
    const list = el("div", { class: "mf-pdbs" });
    for (const s of r.unique) {
      list.appendChild(el("a", { class: "mf-pdb" + (s === r.representative || s.pdb === r.representative.pdb ? " rep" : ""),
        href: viewerHash(s.pdb, s.record.f, parsed), target: "_blank", rel: "noopener",
        title: t("mq_open_3d_hint", { pdb: s.pdb, n: parsed.groups.length }) + (s.alsoIn && s.alsoIn.length
          ? " · " + t("mf_same_as", { list: s.alsoIn.join(", ") }) : "") }, [
        el("code", { text: s.pdb }),
        s.alsoIn && s.alsoIn.length ? el("span", { class: "muted small", text: " +" + s.alsoIn.length }) : null]));
    }
    box.appendChild(list);
    box.appendChild(el("p", { class: "muted small", text: t("mf_structures_note") }));
    return box;
  }

  function toggleRow(row, r, parsed) {
    const closing = state.open === r.receptor;
    for (const other of answer.querySelectorAll(".mf-row.open")) {
      other.classList.remove("open");
      const d = other.querySelector(".mf-detail"); if (d) d.remove();
      const b = other.querySelector(".mf-row-main"); b.setAttribute("aria-expanded", "false");
      b.querySelector(".mf-row-caret").textContent = "▸";
    }
    state.open = closing ? "" : r.receptor;
    if (!closing) {
      row.classList.add("open");
      const b = row.querySelector(".mf-row-main"); b.setAttribute("aria-expanded", "true");
      b.querySelector(".mf-row-caret").textContent = "▾";
      row.appendChild(detailRow(r, parsed));
    }
    writeRoute();
  }
  function drawAnswer(parsed, agg, logoOnly) {
    clear(answer);
    if (!parsed.groups.length && logoOnly) {
      answer.appendChild(el("p", { class: "muted mf-logo-only", text: t("mf_logo_only") }));
      return;
    }
    if (!parsed.groups.length) {
      answer.appendChild(el("div", { class: "mf-empty" }, [
        el("p", { text: t("mf_empty") }),
        el("p", { class: "muted small", text: t("mf_empty_example") })]));
      return;
    }
    const groups = { exact: [], similar: [], different: [], nodata: [] };
    for (const r of agg.receptors) groups[categoryOf(r)].push(r);
    for (const r of agg.unscored) groups.nodata.push(r);
    const byName = (a, b) => (plainName(a.name) || a.receptor).localeCompare(plainName(b.name) || b.receptor);
    groups.exact.sort((a, b) => b.score.coverage - a.score.coverage || byName(a, b));
    groups.similar.sort((a, b) => b.score.exact - a.score.exact || b.score.coverage - a.score.coverage || byName(a, b));
    groups.different.sort((a, b) => b.score.physPct - a.score.physPct || b.score.exactPct - a.score.exactPct || byName(a, b));
    groups.nodata.sort(byName);
    const tab = state.tab || TABS.find(k => groups[k].length) || "exact";
    const total = agg.receptors.length + agg.unscored.length;

    answer.appendChild(el("h3", { class: "mf-answer-title" }, [
      el("span", { class: "mf-answer-n", text: String(groups.exact.length) }),
      el("span", { text: " " + t("mf_answer_title_rest", { total, n: parsed.groups.length }) }),
      el("code", { class: "mf-answer-query", text: queryText(parsed.groups) })]));
    // Which families carry the motif exactly: the share of each family's receptors in the first tab.
    const fam = new Map();
    for (const r of agg.receptors) {
      if (!fam.has(r.family)) fam.set(r.family, { n: 0, exact: 0 });
      const f = fam.get(r.family); f.n++; if (categoryOf(r) === "exact") f.exact++;
    }
    const famRows = [...fam.entries()].map(([slug, f]) => ({ slug, ...f, share: f.exact / f.n }))
      .sort((a, b) => b.share - a.share || b.n - a.n);
    if (famRows.length > 1) {
      const box = el("details", { class: "mf-families", open: true }, [el("summary", {}, [el("strong", { text: t("mf_families_title") })]),
        el("p", { class: "muted small", text: t("mf_families_note") })]);
      for (const f of famRows)
        box.appendChild(el("div", { class: "mf-fam-row" }, [
          el("span", { class: "mf-fam-name", text: nameOf.get(f.slug) || f.slug }),
          el("span", { class: "mf-fam-track" }, [el("span", { class: "mf-fam-fill",
            style: "width:" + (f.share * 100).toFixed(1) + "%" })]),
          el("span", { class: "mf-fam-value", text: f.exact + " / " + f.n })]));
      answer.appendChild(box);
    }
    const tabs = el("div", { class: "mf-tabs", role: "tablist" });
    for (const k of TABS) {
      tabs.appendChild(el("button", { type: "button", role: "tab", class: "mf-tab mf-tab-" + k + (k === tab ? " active" : ""),
        "aria-selected": k === tab ? "true" : "false", title: t("mf_tab_" + k + "_hint"),
        onclick: () => set({ tab: k, open: "" }) }, [
        el("span", { text: t("mf_tab_" + k) }), el("span", { class: "tab-count", text: String(groups[k].length) })]));
    }
    answer.appendChild(tabs);
    answer.appendChild(el("p", { class: "muted small mf-tab-note", text: t("mf_tab_" + tab + "_hint") }));

    const rows = groups[tab];
    const legend = el("div", { class: "mf-legend muted small" });
    for (const s of ["exact", "conservative", "mismatch", "uncovered"])
      legend.appendChild(el("span", {}, [el("i", { class: "mf-letter mini mq-" + s, text: s === "uncovered" ? "·" : "A" }),
        el("span", { text: " " + t("mf_legend_" + s) })]));
    legend.appendChild(el("span", {}, [el("i", { class: "mf-letter mini mq-exact mf-eng", text: "A" }),
      el("span", { text: " " + t("mf_legend_engineered") })]));
    const exportBtn = el("button", { class: "btn small", type: "button", text: t("export_csv"),
      onclick: () => {
        const cols = [
          { key: "receptor", label: t("col_receptor"), get: r => r.receptor },
          { key: "name", label: t("col_receptor_name"), get: r => plainName(r.name) },
          { key: "family", label: t("col_family"), get: r => nameOf.get(r.family) || r.family },
          { key: "category", label: t("mf_col_category"), get: r => categoryOf(r) },
          ...parsed.groups.map((g, i) => ({ key: g.position, label: g.position + " (" + [...g.residues].sort().join("/") + ")",
            get: r => { const c = r.score.cells[i]; return c.status === "uncovered" ? "" : c.wild + (c.engineered ? "*" : ""); } })),
          { key: "read", label: t("mf_col_read"), get: r => r.score.covered + "/" + r.score.cells.length },
          { key: "representative", label: t("mq_col_representative"), get: r => r.representative ? r.representative.pdb : "" }];
        download("motif_" + tab + ".csv", toCSV(cols, rows, { release: L.getManifest().data_version || "",
          query: queryText(parsed.groups), scope: state.scope, category: tab, rows: rows.length }));
      } });
    answer.appendChild(el("div", { class: "mf-list-head" }, [legend, rows.length ? exportBtn : null]));

    if (!rows.length) { answer.appendChild(el("p", { class: "muted", text: t("mf_tab_empty") })); }
    const list = el("div", { class: "mf-list" });
    for (const r of rows) {
      const opened = state.open === r.receptor;
      const partial = r.score.covered < r.score.cells.length;
      const rep = r.representative;
      const row = el("div", { class: "mf-row" + (opened ? " open" : "") });
      // Opening or closing a receptor changes that row and nothing else - no redraw.
      const main = el("button", { type: "button", class: "mf-row-main", "aria-expanded": opened ? "true" : "false",
        onclick: () => toggleRow(row, r, parsed) }, [
        el("span", { class: "mf-row-name" }, [el("strong", { text: plainName(r.name) || r.receptor }),
          el("small", { class: "muted", text: " " + r.receptor })]),
        el("span", { class: "mf-row-family muted small", text: nameOf.get(r.family) || r.family }),
        r.score.cells.length ? residueStrip(r) : el("span", {}),
        el("span", { class: "mf-row-read small" + (partial ? " partial" : " muted"),
          title: t("mf_read_hint"),
          text: r.score.covered ? t("mf_read", { n: r.score.covered, total: r.score.cells.length }) : t("mf_read_none") }),
        el("span", { class: "mf-row-structs muted small", text: t(r.structureCount === 1 ? "mf_one_structure" : "mf_n_structures", { n: r.structureCount }) }),
        el("span", { class: "mf-row-caret", "aria-hidden": "true", text: opened ? "▾" : "▸" })]);
      row.appendChild(main);
      if (rep) row.appendChild(el("a", { class: "btn small mf-row-3d", href: viewerHash(rep.pdb, rep.record.f, parsed),
        target: "_blank", rel: "noopener", title: t("mq_open_3d_hint", { pdb: rep.pdb, n: parsed.groups.length }),
        text: t("mf_open_3d", { pdb: rep.pdb }) }));
      if (opened) row.appendChild(detailRow(r, parsed));
      list.appendChild(row);
    }
    answer.appendChild(list);

  }

  /* Positions asked for without a residue - `3x50`, or a run such as `3x49-3x53` - are a request
     to see the distribution there, not to match anything, so they go to the logo and not to the
     scorer (which would report them as unreadable). */
  // A third digit is an insertion: 6x461 sits between 6x46 and 6x47, not after 6x66.
  const posNum = d => d.length === 3 ? Number(d) / 10 : Number(d);
  const orderOf = p => { const m = /^(\d+)x(\d+)$/.exec(p); return m ? Number(m[1]) * 1000 + posNum(m[2]) : 1e9; };
  function splitQuery(text) {
    const keep = [], positions = [], shownTokens = [], bad = [];
    const bwIndex = (numbering && numbering.bw_index) || {};
    for (const token of String(text || "").split(/[\s,;+]+/).filter(Boolean)) {
      const range = /^(\d+)x(\d+)-(?:(\d+)x)?(\d+)$/.exec(token);
      const bare = /^(\d+[x.]\d+)$/.exec(token);
      if (range) {
        const helix = range[1], from = posNum(range[2]), to = posNum(range[4]);
        if (range[3] && range[3] !== helix) { keep.push(token); continue; }
        const lo = Math.min(from, to), hi = Math.max(from, to);
        const act = activeSet();
        const found = payload.positions.filter(p => { const m = /^(\d+)x(\d+)$/.exec(p);
          return act.has(p) && m && m[1] === helix && posNum(m[2]) >= lo && posNum(m[2]) <= hi; });
        if (found.length) { positions.push(...found); shownTokens.push(token); } else keep.push(token);
      } else if (bare) {
        let p = bare[1];
        if (p.includes(".")) p = bwIndex[p] || p;
        if (known.has(p)) { positions.push(p); shownTokens.push(token); } else keep.push(token);
      } else keep.push(token);
    }
    return { scored: keep.join(" "), positions: [...new Set(positions)], shownTokens };
  }
  /* The distribution at the positions in view, as a sequence logo: one column per position, the
     residues stacked by frequency among the receptors in scope and the stack as tall as the
     position's information content (log2 20 minus its entropy, in bits) - the conventional logo,
     so a conserved position stands tall and a variable one stays low. Counted per receptor, as
     everything here is. Clicking a letter asks for it. */
  const LOGO_COLOURS = { G:"#0f9d58", S:"#0f9d58", T:"#0f9d58", Y:"#0f9d58", C:"#0f9d58",
    Q:"#8e44ad", N:"#8e44ad", K:"#2563c9", R:"#2563c9", H:"#2563c9", D:"#d23a2f", E:"#d23a2f",
    A:"#222", V:"#222", L:"#222", I:"#222", P:"#222", W:"#222", F:"#222", M:"#222" };
  const MAX_BITS = Math.log2(20);
  function drawLogo(parsed, split) {
    clear(logoBox);
    logoBox.hidden = true;
    const positions = [...new Set([...parsed.groups.map(g => g.position), ...split.positions])]
      .sort((a, b) => orderOf(a) - orderOf(b));
    if (!positions.length) return;
    logoBox.hidden = false;
    const dist = (payload.variation || {})[state.scope] || {};
    const asked = new Map(parsed.groups.map(g => [g.position, g.residues]));
    /* Bits need numbers. With a handful of receptors the small-sample correction is larger than the
       whole scale - two receptors take 6.9 bits off a 4.3-bit maximum - and every column is empty.
       Below ten receptors the logo therefore shows frequencies unless the reader asks otherwise,
       and says so. */
    const scopeN = Math.max(0, ...positions.map(p => ((dist[p] && dist[p].by_receptor) || [])
      .reduce((a, kv) => a + kv[1], 0)));
    const autoFreq = scopeN < 10;
    const freqMode = state.logo ? state.logo === "freq" : autoFreq;
    const NS = "http://www.w3.org/2000/svg";
    const colW = 30, H = 130, top = 8, left = 34, bottom = 44;
    const W = left + positions.length * colW + 8;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + (H + top + bottom));
    svg.setAttribute("width", String(W)); svg.setAttribute("height", String(H + top + bottom));
    svg.setAttribute("class", "mf-logo");
    const mk = (name, attrs, text) => { const n = document.createElementNS(NS, name);
      for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, String(v));
      if (text !== undefined) n.textContent = text; return n; };
    // Axis in bits, or in shares of receptors.
    svg.appendChild(mk("line", { x1: left - 4, y1: top, x2: left - 4, y2: top + H, class: "mf-logo-axis" }));
    const ticks = freqMode ? [[0, "0"], [0.5, "0.5"], [1, "1"]] : [0, 1, 2, 3, 4].map(b => [b / MAX_BITS, String(b)]);
    for (const [f, label] of ticks) {
      const y = top + H - f * H;
      svg.appendChild(mk("line", { x1: left - 8, y1: y, x2: left - 4, y2: y, class: "mf-logo-axis" }));
      svg.appendChild(mk("text", { x: left - 11, y: y + 3.5, class: "mf-logo-tick", "text-anchor": "end" }, label));
    }
    svg.appendChild(mk("text", { x: 9, y: top + H / 2, class: "mf-logo-tick",
      transform: "rotate(-90 9 " + (top + H / 2) + ")", "text-anchor": "middle" },
      t(freqMode ? "mf_logo_freq_axis" : "mf_logo_bits")));
    positions.forEach((p, i) => {
      const x = left + i * colW;
      const rec = dist[p];
      const pairs = (rec && rec.by_receptor) || [];
      const total = pairs.reduce((a, kv) => a + kv[1], 0);
      if (asked.has(p)) {
        svg.appendChild(mk("rect", { x: x + 1, y: top + H + 2, width: colW - 2, height: 4, class: "mf-logo-asked-bar" }));
      }
      if (total) {
        let Hs = 0;
        for (const [, n] of pairs) { const q = n / total; if (q > 0) Hs -= q * Math.log2(q); }
        /* Small-sample correction (Schneider et al. 1986): with few receptors an observed column
           looks more conserved than it is - one receptor gives a single letter and the full 4.3
           bits. e(n) = (20 - 1) / (2 ln2 n) is subtracted, so a sparsely covered position stays low. */
        const ic = freqMode ? MAX_BITS : Math.max(0, MAX_BITS - Hs - 19 / (2 * Math.LN2 * total));
        let y = top + H;
        // Smallest at the bottom, the most common on top, as logos are read.
        for (const [res, n] of pairs.slice().sort((a, b) => a[1] - b[1])) {
          const h = (n / total) * (ic / MAX_BITS) * H;
          if (h < 0.6) { continue; }
          const g = mk("text", { x: 0, y: 0, class: "mf-logo-letter", fill: LOGO_COLOURS[res] || "#666",
            "text-anchor": "middle",
            transform: "translate(" + (x + colW / 2) + " " + y + ") scale(" + (colW / 10 * 0.95).toFixed(3) + " " + (h / 7.3).toFixed(3) + ")" }, res);
          g.appendChild(mk("title", {}, p + " " + res + ": " + n + " / " + total + " " + t("mf_logo_receptors") +
            (freqMode ? "" : " · " + ic.toFixed(2) + " " + t("mf_logo_bits"))));
          g.addEventListener("click", () => {
            const cur = input.value.split(/[\s,;+]+/).filter(Boolean)
              .filter(tok => !new RegExp("^" + p.replace(".", "\\.") + "[A-Za-z]*$").test(tok));
            const next = [...cur, p + res].join(" ");
            input.value = next; set({ query: next, open: "", tab: "" });
          });
          svg.appendChild(g);
          y -= h;
        }
      }
      svg.appendChild(mk("text", { x: x + colW / 2, y: top + H + 12, class: "mf-logo-pos",
        transform: "rotate(-60 " + (x + colW / 2) + " " + (top + H + 12) + ")", "text-anchor": "end" }, p));
    });
    const modeBtn = (mode, label) => el("button", { type: "button",
      class: "mf-logo-mode" + ((mode === "freq") === freqMode ? " active" : ""),
      onclick: () => set({ logo: mode }) }, [el("span", { text: t(label) })]);
    logoBox.appendChild(el("div", { class: "mf-logo-head" }, [
      el("strong", { text: t(freqMode ? "mf_logo_title_freq" : "mf_logo_title") }),
      el("span", { class: "mf-logo-modes" }, [modeBtn("bits", "mf_logo_mode_bits"), modeBtn("freq", "mf_logo_mode_freq")]),
      el("div", { class: "muted small", text: t(freqMode ? "mf_logo_note_freq" : "mf_logo_note") })]));
    if (freqMode && autoFreq && !state.logo)
      logoBox.appendChild(el("p", { class: "mf-logo-auto small", text: t("mf_logo_auto_freq", { n: scopeN }) }));
    logoBox.appendChild(el("div", { class: "mf-logo-scroll" }, [svg]));
  }
  function draw() {
    pocketControls.hidden = state.pool !== "pocket";
    receptorControls.hidden = state.pool !== "receptor";
    covSelect.value = String(state.minCov);
    if (state.pool === "pocket" && payload.pool && payload.pool.site_classes) {
      const classes = Object.keys(payload.pool.site_classes)
        .sort((a, b) => payload.pool.site_classes[b].receptors - payload.pool.site_classes[a].receptors);
      if (!classes.includes(state.siteClass)) state.siteClass = classes[0];
      clear(classSelect);
      for (const c of classes) classSelect.appendChild(el("option", { value: c,
        text: siteClassLabel(c) + " (" + payload.pool.site_classes[c].receptors + ")" }));
      classSelect.value = state.siteClass;
      freqSelect.value = String(state.minFreq);
    }
    const split = splitQuery(state.query);
    const parsed = parseQuery(split.scored, known, numbering);
    if (document.activeElement !== input && !parsed.bad.length)
      input.value = [queryText(parsed.groups), ...split.shownTokens].filter(Boolean).join(" ") || state.query;
    drawLogo(parsed, split);
    const spec = specificity(payload, state.scope, parsed.groups, null);
    fullLink.href = "#" + buildHash({ view: "motifsearch", family: route.family, motif: queryText(parsed.groups) || null,
      scope: state.scope !== "class_a" ? state.scope : null, pool: state.pool !== "motif" ? state.pool : null }).slice(1);
    fullLink.textContent = t("mf_full_panel");
    drawChips(parsed);
    drawCards(parsed, spec, split);
    const agg = parsed.groups.length ? aggregate(payload, parsed.groups, posIndex, spec, state.scope) : null;
    drawAnswer(parsed, agg, split.positions.length > 0);
  }
  draw();
  return wrap;
}
