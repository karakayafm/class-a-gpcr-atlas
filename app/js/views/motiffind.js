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
import { t, getLang } from "../core/i18n.js";
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
    pool: POOLS[route.pool] ? route.pool : "motif",
    tab: TABS.includes(route.tab) ? route.tab : "",
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
    if (state.pool !== "motif") r.pool = state.pool;
    if (state.tab) r.tab = state.tab;
    if (state.open) r.open = state.open;
    navigate(r, true);
  }
  function set(patch) {
    Object.assign(state, patch);
    writeRoute();
    draw();
  }

  /* ------------------------------------------------------------ 1. the question */
  wrap.appendChild(el("div", { class: "mf-head" }, [
    el("h2", { text: t("mf_title") }),
    el("span", { class: "mf-beta", text: t("mf_prototype") })]));
  wrap.appendChild(el("p", { class: "muted mf-lede", text: t("mf_lede") }));

  const input = el("input", { type: "text", class: "mf-input", spellcheck: "false",
    value: state.query, placeholder: t("mf_placeholder"), "aria-label": t("mf_title") });
  input.addEventListener("input", debounce(() => set({ query: input.value, open: "", tab: "" }), 250));
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

  const chips = el("div", { class: "mf-chips" });
  wrap.appendChild(chips);

  // Advanced: which position set the motifs and the field read from. Folded: the default answers
  // the question most readers arrive with.
  const poolSelect = el("select", { "aria-label": t("mq_pool") });
  for (const [v, k] of [["motif", "mq_pool_motif"], ["pocket", "mq_pool_pocket"], ["receptor", "mq_pool_receptor"]])
    poolSelect.appendChild(el("option", { value: v, text: t(k) }));
  poolSelect.value = state.pool;
  poolSelect.addEventListener("change", async () => {
    state.pool = poolSelect.value; state.open = ""; state.tab = "";
    await loadPool(); writeRoute(); draw();
  });
  const fullLink = el("a", { class: "mf-full-link" });
  wrap.appendChild(el("details", { class: "mf-advanced" }, [
    el("summary", { text: t("mf_advanced") }),
    el("div", { class: "mf-advanced-body" }, [
      el("label", { class: "filter-field" }, [el("span", { text: t("mq_pool") }), poolSelect]),
      el("p", { class: "muted small" }, [el("span", { text: t("mf_full_panel_note") + " " }), fullLink])])]));

  /* ------------------------------------------------------------ 2. what was asked */
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
  function drawChips(parsed) {
    clear(chips);
    chips.appendChild(el("span", { class: "muted small mf-chips-label", text: t("mf_ready") }));
    const held = new Set(parsed.groups.map(g => g.position));
    for (const m of payload.motifs || []) {
      const tokens = consensusTokens(m);
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
      chips.appendChild(chip);
    }
  }

  function drawCards(parsed, spec) {
    clear(cards); clear(problems);
    if (parsed.bad.length) problems.appendChild(el("p", { class: "motif-bad",
      text: t("motif_query_bad", { tokens: parsed.bad.join(", ") }) }));
    for (const item of parsed.translated || [])
      problems.appendChild(el("p", { class: "muted small",
        text: t("mq_bw_translated", { pairs: item.from + " → " + item.to }) }));
    if (!parsed.groups.length) return;
    for (const a of spec.asked) {
      const c = commonness(a.frequency);
      const residues = [...a.residues].sort().join(" / ");
      const remove = el("button", { class: "mf-card-x", type: "button", text: "×",
        title: t("mf_remove_position", { position: a.position }),
        "aria-label": t("mf_remove_position", { position: a.position }),
        onclick: () => {
          const next = queryText(parsed.groups.filter(g => g.position !== a.position));
          input.value = next; set({ query: next, open: "", tab: "" });
        } });
      cards.appendChild(el("div", { class: "mf-card mf-common-" + c.cls }, [
        remove,
        el("div", { class: "mf-card-pos" }, [el("strong", { text: a.position }),
          el("span", { class: "muted small", text: " " + (payload.segments[a.position] || "") })]),
        el("div", { class: "mf-card-res", text: residues }),
        el("div", { class: "mf-card-freq" }, [
          el("strong", { text: a.frequency === null ? "—" : pct(a.frequency) }),
          el("span", { class: "muted small", text: " " + t("mf_of_receptors") })]),
        el("div", { class: "mf-card-word", text: t(c.key) })]));
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

  function drawAnswer(parsed, agg) {
    clear(answer);
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

    answer.appendChild(el("h3", { class: "mf-answer-title",
      text: t("mf_answer_title", { n: groups.exact.length, total }) }));
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
      const main = el("button", { type: "button", class: "mf-row-main", "aria-expanded": opened ? "true" : "false",
        onclick: () => set({ open: opened ? "" : r.receptor }) }, [
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

  function draw() {
    const parsed = parseQuery(state.query, known, numbering);
    if (document.activeElement !== input && !parsed.bad.length) input.value = queryText(parsed.groups) || state.query;
    const spec = specificity(payload, state.scope, parsed.groups, null);
    fullLink.href = "#" + buildHash({ view: "motifsearch", family: route.family, motif: queryText(parsed.groups) || null,
      scope: state.scope !== "class_a" ? state.scope : null, pool: state.pool !== "motif" ? state.pool : null }).slice(1);
    fullLink.textContent = t("mf_full_panel");
    drawChips(parsed);
    drawCards(parsed, spec);
    const agg = parsed.groups.length ? aggregate(payload, parsed.groups, posIndex, spec, state.scope) : null;
    drawAnswer(parsed, agg);
  }
  draw();
  return wrap;
}
