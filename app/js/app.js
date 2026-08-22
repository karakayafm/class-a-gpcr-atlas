// Application shell: routing, lazy loading, the 3D modal and the accessibility plumbing.
import { t, initLang, setLang, getLang, methodLabel } from "./core/i18n.js";
import { initTheme, setTheme, getTheme, themes } from "./core/theme.js";
import { parseRoute, navigate, onRoute, startRouter } from "./core/router.js";
import * as ST from "./core/state.js";
import * as L from "./data/loader.js";
import { el, clear } from "./components/dom.js";
import { toCSV, download } from "./components/csv.js";
import { downloadXLSX } from "./components/xlsx.js";
import * as V from "./views/views.js";
import { ligandExplorer } from "./views/ligands.js";
import * as MQ from "./views/motifquery.js";
import * as VIEW from "./viewer/viewer.js";
import * as ALIGN from "./viewer/align.js";

const MAIN = () => document.getElementById("main");
let lastFamily = null, modalOpener = null;
/* Which residue list the side panel is showing: the ligand's contact shell, or the whole
   receptor. Kept here rather than in the viewer because it is a property of the panel, not of
   the scene — the viewer draws exactly what is selected either way. Reset per structure, and
   deliberately outside buildViewerSide so a redraw (reset view, clear selection, language
   change) does not throw a reader back to the pocket. */
let wholeReceptor = false;

function setStatus(msg) {
  const s = document.getElementById("status");
  s.textContent = msg || "";
  s.setAttribute("aria-busy", msg ? "true" : "false");
}
function fatal(msg) {
  clear(MAIN());
  MAIN().appendChild(el("section", { class: "view" }, [
    el("h2", { text: t("err_route") }), el("p", { class: "notice", text: msg })]));
}

/* ------------------------------------------------------------------ chrome */
function buildChrome(manifest) {
  const nav = document.getElementById("nav");
  const globalSearch = document.getElementById("global-search");
  if (globalSearch && globalSearch.parentNode === nav) nav.removeChild(globalSearch);
  clear(nav);
  const r = parseRoute();
  const items = r.family
    ? [["structures", "nav_structures"], ["panels", "nav_panels"], ["motifsearch", "nav_motifs"],
       ["ligands", "nav_ligands"],
       ["guide", "nav_guide"], ["methods", "nav_methods"], ["sources", "nav_sources"],
       ["references", "nav_references"], ["cite", "nav_cite"]]
    : [["landing", "families"], ["panels", "nav_panels"], ["motifsearch", "nav_motifs"],
       ["ligands", "nav_ligands"],
       ["guide", "nav_guide"], ["methods", "nav_methods"], ["sources", "nav_sources"],
       ["references", "nav_references"], ["cite", "nav_cite"]];
  for (const [view, key] of items) {
    const on = r.view === view;
    nav.appendChild(el("a", { class: "navlink" + (on ? " active" : ""),
      href: "#" + (r.family && view !== "landing" ? "family=" + r.family + "&" : "") + "view=" + view,
      "aria-current": on ? "page" : null, text: t(key) }));
  }
  if (globalSearch) nav.appendChild(globalSearch);
  const fam = document.getElementById("famlabel");
  clear(fam);
  if (r.family) {
    const f = (manifest.families || []).find(x => x.slug === r.family);
    fam.appendChild(el("a", { class: "crumb", href: "#view=landing", text: t("back_to_families") }));
    fam.appendChild(el("span", { class: "crumb sep", text: "›" }));
    fam.appendChild(el("span", { class: "crumb", text: f ? V.familyDisplayName(f.name) : r.family }));
  }
  // Chrome labels are translated on every render; leaving them as static English text meant
  // "Lang" and "Theme" stayed English while the rest of the page was Turkish.
  const langLabel = document.querySelector(".lang-label");
  if (langLabel) langLabel.title = t("lang");
  const langSelect = document.getElementById("lang");
  if (langSelect) langSelect.setAttribute("aria-label", t("lang"));
  const themeLabel = document.querySelector(".theme-label");
  if (themeLabel) themeLabel.textContent = t("theme");
  const themeSelect = document.getElementById("theme");
  if (themeSelect) {
    themeSelect.setAttribute("aria-label", t("theme"));
    for (const option of themeSelect.options) option.textContent = t("theme_" + option.value);
  }
  // The pre-release banner used to be written once at boot, so it kept the language the page
  // happened to start in. It is part of the chrome and is translated with the rest of it.
  const prerelease = document.getElementById("prerelease");
  if (prerelease) prerelease.textContent = t("prerelease_notice");
  const globalInput = document.getElementById("global-search-input");
  if (globalInput) {
    globalInput.placeholder = t("global_search_placeholder");
    globalInput.setAttribute("aria-label", t("global_search"));
  }
}

/* Answers for the two identifiers a search can legitimately carry and never match: a structure the
   PDB withdrew, and the structure that replaced it. Returns null for anything else, so the ordinary
   empty result is untouched. */
async function supersessionFor(query) {
  const q = String(query || "").trim().toUpperCase();
  if (!/^[0-9A-Z]{4}$/.test(q)) return null;
  let data = null;
  try { data = await L.loadSupersessions(); } catch (e) { return null; }
  const entries = (data && data.entries) || [];
  const withdrawn = entries.find(e => e.pdb_id === q);
  const replaces = entries.find(e => (e.replaced_by || []).includes(q));
  const entry = withdrawn || replaces;
  if (!entry) return null;
  const replacement = (entry.replaced_by || [])[0] || "";
  const line = withdrawn
    ? t(entry.replacement_in_atlas ? "search_withdrawn_here" : "search_withdrawn_elsewhere",
        { pdb: entry.pdb_id, date: entry.remove_date || "", replacement })
    : t(entry.replacement_in_atlas ? "search_replacement_here" : "search_replacement_elsewhere",
        { pdb: q, withdrawn: entry.pdb_id, date: entry.remove_date || "" });
  const box = el("div", { class: "global-search-message search-superseded" },
    [el("p", { text: line })]);
  // Whichever of the two this atlas actually carries is offered as somewhere to go.
  const offer = withdrawn && entry.replacement_in_atlas
    ? { pdb: replacement, family: entry.replacement_family_slug }
    : (entry.withdrawn_in_atlas ? { pdb: entry.pdb_id, family: entry.family_slug } : null);
  if (offer && offer.family) box.appendChild(el("button", { class: "btn small", type: "button",
    text: t("search_open_structure", { pdb: offer.pdb }),
    onclick: () => {
      const input = document.getElementById("global-search-input");
      if (input) input.value = "";
      const panel = document.getElementById("global-search-results");
      if (panel) panel.hidden = true;
      navigate({ family: offer.family, view: "structures", pdb: offer.pdb });
    } }));
  if (entry.source) box.appendChild(el("a", { class: "link small", href: entry.source,
    target: "_blank", rel: "noopener", text: t("search_removal_record") }));
  return box;
}

function setupGlobalSearch() {
  const input = document.getElementById("global-search-input");
  const panel = document.getElementById("global-search-results");
  if (!input || !panel) return;
  let timer = null, request = 0;
  const hide = () => { panel.hidden=true; input.setAttribute("aria-expanded", "false"); };
  const show = () => { panel.hidden=false; input.setAttribute("aria-expanded", "true"); };
  const resultText = row => {
    const receptor = V.plainName(row.receptor_name || row.receptor_entry_name || "—");
    const ligands = (row.ligands || []).map(V.plainName).join(", ");
    return { receptor, ligands };
  };
  const openHit = hit => {
    if (!hit) return;
    input.value=""; hide();
    navigate({ family:hit.row.family_slug, view:"structures", pdb:hit.row.pdb_id });
  };
  const run = async (activateFirst=false) => {
    const raw = input.value.trim(), q = raw.toLocaleLowerCase(getLang() === "tr" ? "tr" : "en");
    const token = ++request;
    clear(panel);
    if (q.length < 2) { hide(); return; }
    panel.appendChild(el("p", { class:"global-search-message", text:t("global_search_loading") }));
    show(); input.setAttribute("aria-busy", "true");
    let index;
    try { index = await L.loadSearchIndex(); }
    catch (e) { if (token === request) { clear(panel); panel.appendChild(el("p", {
      class:"global-search-message", text:L.errorMessage(e) })); } return; }
    finally { if (token === request) input.removeAttribute("aria-busy"); }
    if (token !== request) return;
    const scored = [];
    for (const row of index) {
      const txt = resultText(row), pdb = String(row.pdb_id || "").toLowerCase();
      const aliases = (row.aliases || []).map(x => String(x).toLowerCase());
      const receptor = (txt.receptor + " " + (row.receptor_entry_name || "")).toLocaleLowerCase();
      const ligands = txt.ligands.toLocaleLowerCase();
      let score = pdb === q || aliases.includes(q) ? 0 : pdb.startsWith(q) ||
        aliases.some(x => x.startsWith(q)) ? 1 : receptor.startsWith(q) ? 2 :
        ligands.startsWith(q) ? 3 : (pdb + " " + receptor + " " + ligands).includes(q) ? 4 : 99;
      if (score < 99) scored.push({ row, txt, score });
    }
    scored.sort((a,b) => a.score-b.score || a.row.pdb_id.localeCompare(b.row.pdb_id));
    const exact = scored.find(hit => String(hit.row.pdb_id).toLowerCase() === q ||
      (hit.row.aliases || []).some(alias => String(alias).toLowerCase() === q));
    if (activateFirst) { openHit(exact || scored[0]); return; }
    clear(panel);
    if (!scored.length) {
      /* A withdrawn entry is kept out of the index on purpose — leading a reader to a retracted
         structure is worse than not finding it — and where its replacement is here, the
         replacement carries the old identifier and the search resolves it. Where the replacement
         is *not* here, neither identifier matched anything and the reader got silence from an
         atlas that knows exactly what happened to it. Now it says so. */
      const note = await supersessionFor(q);
      if (note) panel.appendChild(note);
      else panel.appendChild(el("p", { class:"global-search-message", text:t("global_search_empty") }));
    }
    for (const hit of scored.slice(0, 15)) {
      panel.appendChild(el("button", { class:"global-search-result", role:"option",
        onclick:() => openHit(hit) }, [
        el("strong", { text:hit.row.pdb_id }),
        el("span", { text:hit.txt.receptor }),
        el("small", { text:(hit.txt.ligands || t("apo")) + " · " + V.plainName(hit.row.family_name) })
      ]));
    }
    show();
  };
  input.addEventListener("input", () => { clearTimeout(timer); timer=setTimeout(run, 160); });
  input.addEventListener("focus", () => { if (panel.childElementCount && input.value.trim().length >= 2) show(); });
  input.addEventListener("keydown", e => {
    if (e.key === "Escape") { hide(); input.blur(); }
    else if (e.key === "Enter" && input.value.trim().length >= 2) {
      e.preventDefault(); clearTimeout(timer); run(true);
    }
  });
  document.addEventListener("pointerdown", e => {
    const host = document.getElementById("global-search");
    if (host && !host.contains(e.target)) hide();
  });
}

/* Superposition. Its own section rather than a mode like measurement, because an overlay stays on
   screen and goes on being true while the reader does other things — picking residues, measuring,
   switching observation — and a mode would have to be left before any of that. */
function buildAlignSection(meta) {
  const section = el("div", { class: "viewer-section align-section" });
  section.appendChild(el("h3", { text: t("align_title") }));
  section.appendChild(el("p", { class: "muted small", text: t("align_hint") }));
  const status = el("p", { class: "align-status", hidden: true });
  const list = el("div", { class: "align-list" });
  const input = el("input", { type: "search", class: "align-input",
    placeholder: t("align_placeholder"), "aria-label": t("align_placeholder") });
  const addButton = el("button", { class: "btn small", text: t("align_add") });

  const say = (text, isError) => {
    status.textContent = text || "";
    status.hidden = !text;
    status.classList.toggle("align-error", !!isError);
  };
  function paint() {
    clear(list);
    const rows = ALIGN.overlayList();
    if (!rows.length) {
      list.appendChild(el("p", { class: "muted small", text: t("align_none") }));
      return;
    }
    /* The base structure is recoloured the moment the first overlay lands, so it needs a swatch
       here too — otherwise green is the one colour in the scene the panel does not explain. */
    const baseSwatch = el("i", { class: "align-swatch" });
    baseSwatch.style.background = ALIGN.baseColour();
    list.appendChild(el("div", { class: "align-row align-row-base" }, [
      baseSwatch,
      el("div", { class: "align-row-text" }, [
        el("strong", { text: meta.pdb_id }),
        el("span", { class: "muted small", text: V.plainName(meta.receptor_name || "") }),
        el("span", { class: "muted small", text: t("align_reference") })
      ])
    ]));
    for (const row of rows) {
      const swatch = el("i", { class: "align-swatch" });
      // The colour is decided by the align module, so the legend has to be told rather than styled.
      swatch.style.background = "#" + row.colour.toString(16).padStart(6, "0");
      list.appendChild(el("div", { class: "align-row" }, [
        swatch,
        el("div", { class: "align-row-text" }, [
          el("strong", { text: row.pdb }),
          el("span", { class: "muted small", text: V.plainName(row.name || "") }),
          // The fit is only as good as what carried it, so both numbers are always shown.
          el("span", { class: "muted small", text: t("align_rmsd", {
            rmsd: row.rmsd.toFixed(2), n: row.n }) })
        ]),
        el("button", { class: "btn tiny", "aria-label": t("align_remove"), text: "✕",
          // The whole panel is rebuilt, not just this list: the structure switcher and the toggles
          // above describe what is in the scene, and removing a structure changes both.
          onclick: () => { ALIGN.removeOverlay(row.pdb); buildViewerSide(meta); } })
      ]));
    }
    list.appendChild(el("div", { class: "align-row-actions" }, [
      el("button", { class: "btn small", text: t("align_frame"),
        onclick: () => ALIGN.frameAll() }),
      el("button", { class: "btn small", text: t("align_clear"),
        onclick: () => { ALIGN.clearOverlays(); buildViewerSide(meta); } })
    ]));
  }
  const add = async () => {
    const pdb = input.value.trim();
    if (!pdb) return;
    addButton.disabled = true;
    const res = await ALIGN.addOverlay(pdb, text => say(text, false));
    addButton.disabled = false;
    if (res && res.error) { say(res.error, true); return; }
    say("", false);
    input.value = "";
    ALIGN.frameAll();
    // Rebuilt rather than repainted, so the structure switcher appears with the first overlay and
    // the layer toggles start addressing whichever structure is active.
    buildViewerSide(meta);
  };
  addButton.addEventListener("click", add);
  input.addEventListener("keydown", e => {
    if (e.key === "Enter") { e.preventDefault(); add(); }
  });
  section.appendChild(el("div", { class: "align-controls" }, [input, addButton]));
  section.appendChild(status);
  section.appendChild(list);
  paint();
  return section;
}

/* ------------------------------------------------------------------ 3D modal */
function ensureModal() {
  let m = document.getElementById("modal");
  if (m) return m;
  m = el("div", { id: "modal", class: "modal", hidden: true, role: "dialog",
    "aria-modal": "true", "aria-label": t("viewer") });
  m.appendChild(el("div", { class: "modal-inner" }, [
    el("header", { class: "modal-head" }, [
      el("h2", { id: "modal-title", text: t("viewer") }),
      el("button", { class: "btn close", id: "modal-close", "aria-label": "Esc", text: "✕" })
    ]),
    el("div", { class: "modal-body" }, [
      el("div", { class: "viewport-shell" }, [
        el("div", { id: "viewport", class: "viewport" }),
        el("div", { id: "viewer-obs-switch", class: "obs-switch", hidden: true })
      ]),
      el("aside", { id: "viewer-side", class: "viewer-side" })
    ]),
    el("p", { id: "viewer-status", class: "notice", hidden: true })
  ]));
  document.body.appendChild(m);
  m.querySelector("#modal-close").addEventListener("click", closeModal);
  m.addEventListener("keydown", ev => {
    if (ev.key === "Escape") { ev.preventDefault(); closeModal(); return; }
    if (ev.key !== "Tab") return;
    const f = m.querySelectorAll("button, [href], select, input, [tabindex]:not([tabindex='-1'])");
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
    else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
  });
  return m;
}
function setBackgroundInert(on) {
  // Everything except the dialog itself, rather than a list of landmark selectors — a list
  // silently misses whatever gets added later, and it already missed the skip link and the
  // breadcrumb, both of which sit directly on <body>.
  const m = document.getElementById("modal");
  for (const el of Array.from(document.body.children)) {
    if (el === m) continue;
    if (on) { el.setAttribute("inert", ""); el.setAttribute("aria-hidden", "true"); }
    else { el.removeAttribute("inert"); el.removeAttribute("aria-hidden"); }
  }
}

async function openModal(pdb, observationId, focusResidue, opts) {
  const m = ensureModal();
  wholeReceptor = !!(opts && opts.whole);
  modalOpener = document.activeElement;
  m.hidden = false;
  document.body.classList.add("modal-open");
  // The Tab handler below cycles focus inside the dialog, but a screen reader's virtual cursor
  // and find-in-page ignore it and walk straight into the page behind. `inert` is what actually
  // removes that content from the accessibility tree.
  setBackgroundInert(true);
  const st = document.getElementById("viewer-status");
  st.hidden = false; st.textContent = t("loading_structure");
  /* Overlays belong to the stage VIEW.open is about to destroy and rebuild, so they are forgotten
     here rather than removed — the components are already going. Opening a second structure while
     the modal stays open, which changing the address does, comes through here too. */
  ALIGN.reset();
  activeStructure = null;
  // the viewport is visible now; the viewer resizes only after this point
  const meta = await VIEW.open(document.getElementById("viewport"), pdb, observationId,
    msg => { st.textContent = msg; st.hidden = !msg; });
  if (!meta) return;
  updateModalTitle(meta);
  if (focusResidue && !VIEW.isResidueSelected(focusResidue.chain, focusResidue.seq))
    VIEW.toggleResidue(focusResidue.chain, focusResidue.seq);
  // Opening straight into the whole receptor is one fetch and one reframe; both are skipped on
  // the ordinary path, so a reader who came for the pocket pays nothing for this.
  if (wholeReceptor) { await ensureResidueTable(meta); VIEW.frameReceptor(); }
  /* Positions carried over from the motif panel. Applied after the table is loaded, because that
     is what resolves a generic position to an atom, and framed on them: a reader who arrived by
     asking about six positions came to look at those six, not at the default view. */
  const marks = String((opts && opts.mark) || "").split(",").map(x => x.trim()).filter(Boolean);
  if (marks.length) {
    await ensureResidueTable(meta);
    VIEW.setQueryPositions(marks);
    VIEW.frameQuery();
  }
  buildViewerSide(meta);
  buildObservationSwitch(meta);
  const note = VIEW.statusMessage();
  st.textContent = note; st.hidden = !note;
  document.getElementById("modal-close").focus();
  const r = parseRoute(); navigate(Object.assign({}, r, { pdb, observation: VIEW.currentObservation(),
    view: "3d", whole: wholeReceptor ? "1" : null,
    mark: marks.length ? marks.join(",") : null }), true);
}

/* Fetched once per structure and kept by the loader's cache, so toggling the list back and forth
   is not a second request. A structure whose residue mapping the pipeline could not resolve has
   no file; the panel then says so rather than showing seven empty columns. */
async function syncWholeReceptor(want) {
  const meta = VIEW.meta_();
  if (!meta || want === wholeReceptor) return;
  if (want) await ensureResidueTable(meta);
  wholeReceptor = want;
  if (want) VIEW.frameReceptor(); else VIEW.focusPocket();
  buildViewerSide(meta);
}

async function ensureResidueTable(meta) {
  if (VIEW.hasResidueTable()) return true;
  let table = null;
  try { table = await L.loadReceptorResidues(meta.pdb_id); } catch (e) { table = null; }
  VIEW.setResidueTable(table && table.residues);
  return VIEW.hasResidueTable();
}
function updateModalTitle(meta) {
  const title = document.getElementById("modal-title");
  clear(title);
  title.appendChild(el("span", { text:meta.pdb_id + " · " +
    V.plainName(meta.receptor_name || "") + " · " + t("binding_site_workspace") }));
  const current = (meta.observations || []).find(o =>
    o.observation_id === VIEW.currentObservation());
  if (current && current.binding_mode) title.appendChild(el("span", {
    class:"mode-pill modal-mode-pill" + V.modeClass(current.binding_mode),
    text:current.binding_mode
  }));
  if (current && (current.ligand_name || current.ligand_entity_id)) {
    const list = meta.observations || [];
    const label = V.plainName(current.ligand_name || current.ligand_entity_id);
    // With a single ligand the name is just a caption; with several it is the control that
    // advances to the next one, which is where a reader looks first.
    if (list.length < 2) title.appendChild(el("span", { class:"modal-ligand-name", text:label }));
    else {
      const at = currentIndex(meta);
      title.appendChild(el("button", { class:"modal-ligand-name modal-ligand-switch", type:"button",
        title:t("observation_hint"), onclick:() =>
          applyObservation(meta, list[(at + 1) % list.length].observation_id) }, [
        el("span", { text:label }),
        el("span", { class:"obs-switch-count", text:(at + 1) + " / " + list.length })]));
    }
  }
}
function closeModal() {
  const m = document.getElementById("modal");
  if (!m || m.hidden) return;
  VIEW.close();
  ALIGN.reset();
  activeStructure = null;
  m.hidden = true;
  document.body.classList.remove("modal-open");
  setBackgroundInert(false);
  /* The structure stays named in the address. The page behind is showing it — closing the viewer
     is leaving the 3D view, not the structure — and dropping it left an address that no longer
     described the page. The viewer's own keys do go, because nothing behind the modal reads them. */
  const r = parseRoute(); delete r.observation; delete r.whole; delete r.mark;
    if (r.view === "3d") r.view = r.family ? "structures" : "landing";
    if (!r.family) delete r.pdb;
  navigate(r, true);
  if (modalOpener && modalOpener.focus) modalOpener.focus();
  modalOpener = null;
}
/* A structure can hold several ligands, and readers were missing that the view is showing only
   one of them. The choice is offered in three places now — the modal title, the side panel and an
   overlay on the viewer — so they all route through here and refresh each other. */
function applyObservation(meta, id) {
  VIEW.setObservation(id);
  const status = VIEW.statusMessage(), node = document.getElementById("viewer-status");
  node.textContent = status; node.hidden = !status;
  navigate(Object.assign({}, parseRoute(), { observation:id }), true);
  updateModalTitle(meta); buildViewerSide(meta); buildObservationSwitch(meta);
}
function observationList(meta) { return meta.observations || []; }
function observationText(o) { return V.plainName(o.ligand_name || o.ligand_entity_id) + " — " + o.ligand_role; }
/* An observation with no coordinates or no atom selection stays in the list — it is a real
   annotation — but it is labelled, so switching to it does not look like a broken viewer. */
function observationDrawable(o) {
  return o.coordinate_status === "observed" && !!o.ligand_selection;
}
function currentIndex(meta) {
  const list = observationList(meta);
  const at = list.findIndex(o => o.observation_id === VIEW.currentObservation());
  return at < 0 ? 0 : at;
}
/* Overlay in the corner of the canvas: previous / position / next. Stepping through the ligands
   is the common action, so it is one click away without opening any list. */
function buildObservationSwitch(meta) {
  const box = document.getElementById("viewer-obs-switch");
  if (!box) return;
  const list = observationList(meta);
  clear(box);
  box.hidden = list.length < 2;
  if (box.hidden) return;
  const at = currentIndex(meta);
  const step = delta => applyObservation(meta, list[(at + delta + list.length) % list.length].observation_id);
  box.appendChild(el("span", { class:"obs-switch-label", text:t("observation") }));
  box.appendChild(el("button", { class:"obs-switch-step", type:"button",
    "aria-label":t("observation_previous"), text:"‹", onclick:() => step(-1) }));
  box.appendChild(el("span", { class:"obs-switch-count", text:(at + 1) + " / " + list.length }));
  box.appendChild(el("button", { class:"obs-switch-step", type:"button",
    "aria-label":t("observation_next"), text:"›", onclick:() => step(1) }));
  box.appendChild(el("span", { class:"obs-switch-name", title:observationText(list[at]),
    text:V.plainName(list[at].ligand_name || list[at].ligand_entity_id) }));
}
/* Which structure the panel's controls act on. The viewer was written around one structure, so
   every toggle, every list and the whole-receptor columns addressed it implicitly. With something
   superposed there are two, and a reader who wants the other one's side chains, or its positions
   outside the pocket, had no way to say so. Named rather than inferred, so the panel can say which
   structure it is describing. */
let activeStructure = null;
function activePdb(meta) {
  const want = String(activeStructure || "").toUpperCase();
  if (want && want !== String(meta.pdb_id).toUpperCase() && !ALIGN.isOverlaid(want))
    activeStructure = null;         // it was removed while active
  return String(activeStructure || meta.pdb_id).toUpperCase();
}

/* The strip that switches between the structures in the scene. Only drawn once there is more than
   one — with nothing superposed it would be a control with a single option. */
function buildStructureSwitch(meta, onChange) {
  if (!ALIGN.hasOverlays()) return null;
  const active = activePdb(meta);
  const strip = el("div", { class:"structure-switch", role:"group",
    "aria-label":t("v_active_structure") });
  strip.appendChild(el("span", { class:"structure-switch-label", text:t("v_active_structure") }));
  const chip = (pdb, colour, label) => {
    const isActive = pdb === active;
    const b = el("button", { class:"structure-chip" + (isActive ? " selected" : ""), type:"button",
      "aria-pressed":isActive ? "true" : "false", title:label,
      onclick:() => { activeStructure = pdb; onChange(); } });
    const sw = el("i", { class:"structure-chip-swatch" });
    sw.style.background = colour;
    b.appendChild(sw);
    b.appendChild(el("span", { text:pdb }));
    return b;
  };
  strip.appendChild(chip(String(meta.pdb_id).toUpperCase(), ALIGN.baseColour(),
    V.plainName(meta.receptor_name || "")));
  for (const row of ALIGN.overlayList())
    strip.appendChild(chip(row.pdb, "#" + row.colour.toString(16).padStart(6, "0"),
      V.plainName(row.name || "")));
  return strip;
}

function buildViewerSide(meta) {
  const side = document.getElementById("viewer-side");
  clear(side);
  side.appendChild(el("h3", { text: meta.pdb_id + " — " + V.plainName(meta.receptor_name || "") }));
  side.appendChild(el("p", { class: "muted small", text: meta.species + " · " +
    (meta.experimental_method ? methodLabel(meta.experimental_method) : "") + " · " +
    (meta.resolution != null ? meta.resolution + " Å" : "") }));
  if ((meta.observations || []).length > 1) {
    const selectObservation = id => applyObservation(meta, id);
    // Keep a native selector for assistive technology and automated keyboard checks, while the
    // visible disclosure below can wrap very long chemical/peptide names inside the side panel.
    const sel = el("select", { class:"observation-native", "aria-label": t("observation"),
      onchange:e => selectObservation(e.target.value) });
    for (const o of meta.observations) sel.appendChild(el("option", { value: o.observation_id,
      text: (o.ligand_name || o.ligand_entity_id) + " — " + o.ligand_role,
      selected: o.observation_id === VIEW.currentObservation() }));
    const currentObservation = meta.observations.find(o =>
      o.observation_id === VIEW.currentObservation()) || meta.observations[0];
    const picker = el("details", { class:"observation-picker", open:true }, [
      el("summary", { text:observationText(currentObservation) }),
      el("div", { class:"observation-options" }, meta.observations.map(o => el("button", {
        class:"observation-option" + (o === currentObservation ? " selected" : ""),
        type:"button", "aria-current":o === currentObservation ? "true" : null,
        onclick:() => selectObservation(o.observation_id) }, [
        el("span", { text:observationText(o) }),
        observationDrawable(o) ? null
          : el("span", { class:"observation-flag", text:t("observation_undisplayable") })
      ].filter(Boolean))))
    ]);
    side.appendChild(el("label", { class:"observation-heading" }, [
      el("span", { text:t("observation") }),
      el("span", { class:"observation-count", text:String(meta.observations.length) })]));
    side.appendChild(el("p", { class:"observation-hint", text:t("observation_hint") }));
    side.appendChild(sel); side.appendChild(picker);
  }
  const active = activePdb(meta);
  const onBase = active === String(meta.pdb_id).toUpperCase();
  const switcher = buildStructureSwitch(meta, () => buildViewerSide(meta));
  if (switcher) side.appendChild(switcher);
  const on = { cartoon: true, ligand: true, contacts: true, motifs: false, motifLabels: true,
    surface: false, surfaceReceptor:false, surfaceLigand:false, lines: true,
    allLigands: false, ions: false, aux: false, spin: false };
  /* The layers an overlay carries. Anything outside this map is disabled and says why, because a
     toggle that does nothing is worse than one that is visibly unavailable. */
  const OVERLAY_LAYER = { cartoon:"cartoon", contacts:"sidechains", ligand:"ligand",
    motifLabels:"labels", lines:"interactions" };
  if (!onBase) {
    const state = ALIGN.layerState(active) || {};
    for (const [key, layer] of Object.entries(OVERLAY_LAYER)) on[key] = state[layer] !== false;
  }
  const ctrl = el("div", { class: "viewer-tools" });
  const add = (key, label, disabled) => {
    const unsupported = !onBase && !OVERLAY_LAYER[key];
    const b = el("button", { class: "viewer-tool", disabled: !!disabled || unsupported,
      title: unsupported ? t("v_overlay_layer_unsupported", { pdb: active }) : null,
      "aria-pressed": on[key] ? "true" : "false", text: label, onclick: () => {
        on[key] = !on[key]; b.setAttribute("aria-pressed", on[key] ? "true" : "false");
        if (onBase) VIEW.toggles[key](on[key]);
        else ALIGN.setLayer(active, OVERLAY_LAYER[key], on[key]);
      } });
    ctrl.appendChild(b);
    return b;
  };
  const apo = meta.apo_status === "confirmed_apo";
  const cur = (meta.observations || []).find(o => o.observation_id === VIEW.currentObservation());
  const hasLig = !!(cur && cur.ligand_selection);
  add("cartoon", t("v_cartoon"));
  add("motifLabels", t("v_motif_labels"));
  // The contacting side chains were drawn unconditionally; a reader looking at ligand
  // topology alone had no way to clear them.
  add("contacts", t("v_side_chains"), apo || !hasLig);
  const interactionsButton = add("lines", t("v_interactions"), apo || !hasLig);
  let covalentButton = null;
  let ligandPanel = null;
  if (hasLig && VIEW.isPolymerLigand()) {
    ligandPanel = el("div", { class:"ligand-options", hidden:true,
      "aria-label":t("v_ligand") });
    const ligandModeButton = (mode, label, selected) => el("button", {
      class:"viewer-tool ligand-option", "aria-pressed":selected ? "true" : "false",
      text:label, onclick:() => {
        cartoonLigand.setAttribute("aria-pressed", mode === "cartoon" ? "true" : "false");
        licoriceLigand.setAttribute("aria-pressed", mode === "licorice" ? "true" : "false");
        VIEW.toggles.ligandMode(mode);
      }
    });
    const cartoonLigand = ligandModeButton("cartoon", t("v_ligand_cartoon"), true);
    const licoriceLigand = ligandModeButton("licorice", t("v_ligand_licorice"), false);
    const ligandVisibility = el("button", { class:"viewer-tool ligand-visibility",
      "aria-pressed":"true", text:t("v_ligand_hide"), onclick:() => {
        on.ligand = !on.ligand;
        ligandVisibility.setAttribute("aria-pressed", on.ligand ? "true" : "false");
        ligandVisibility.textContent = t(on.ligand ? "v_ligand_hide" : "v_ligand_show");
        cartoonLigand.disabled = !on.ligand;
        licoriceLigand.disabled = !on.ligand;
        on.lines = on.ligand;
        interactionsButton.disabled = !on.ligand;
        interactionsButton.setAttribute("aria-pressed", on.lines ? "true" : "false");
        if (covalentButton) {
          covalentButton.setAttribute("aria-pressed", on.ligand ? "true" : "false");
          covalentButton.classList.toggle("selected", on.ligand);
        }
        VIEW.toggles.ligand(on.ligand);
      } });
    ligandPanel.append(cartoonLigand, licoriceLigand, ligandVisibility);
    const ligandButton = el("button", { class:"viewer-tool", "aria-expanded":"false",
      text:t("v_ligand"), onclick:() => {
        ligandPanel.hidden = !ligandPanel.hidden;
        ligandButton.setAttribute("aria-expanded", ligandPanel.hidden ? "false" : "true");
      } });
    ctrl.appendChild(ligandButton);
  } else {
    const ligandButton = el("button", { class:"viewer-tool", disabled:apo || !hasLig,
      "aria-pressed":hasLig ? "true" : "false", text:t("v_ligand_hide"), onclick:() => {
        on.ligand = !on.ligand;
        ligandButton.setAttribute("aria-pressed", on.ligand ? "true" : "false");
        ligandButton.textContent = t(on.ligand ? "v_ligand_hide" : "v_ligand_show");
        on.lines = on.ligand;
        interactionsButton.disabled = !on.ligand;
        interactionsButton.setAttribute("aria-pressed", on.lines ? "true" : "false");
        if (covalentButton) {
          covalentButton.setAttribute("aria-pressed", on.ligand ? "true" : "false");
          covalentButton.classList.toggle("selected", on.ligand);
        }
        VIEW.toggles.ligand(on.ligand);
      } });
    ctrl.appendChild(ligandButton);
  }
  const surfacePanel = el("div", { class:"surface-options", hidden:true,
    "aria-label":t("v_surface") });
  const surfaceOption = (key, label, toggle) => {
    const b = el("button", { class:"viewer-tool surface-option", "aria-pressed":"false",
      text:label, onclick:() => {
        on[key] = !on[key]; b.setAttribute("aria-pressed", on[key] ? "true" : "false");
        toggle(on[key]);
      } });
    surfacePanel.appendChild(b); return b;
  };
  const receptorSurface = surfaceOption("surfaceReceptor", t("v_surface_receptor"), VIEW.toggles.surfaceReceptor);
  const ligandSurface = surfaceOption("surfaceLigand", t("v_surface_ligand"), VIEW.toggles.surfaceLigand);
  const surfaceMaster = el("button", { class:"viewer-tool", disabled:apo || !hasLig,
    "aria-pressed":"false", text:t("v_surface"), onclick:() => {
      on.surface = !on.surface;
      surfaceMaster.setAttribute("aria-pressed", on.surface ? "true" : "false");
      surfacePanel.hidden = !on.surface;
      on.surfaceReceptor = on.surface; on.surfaceLigand = on.surface;
      receptorSurface.setAttribute("aria-pressed", on.surface ? "true" : "false");
      ligandSurface.setAttribute("aria-pressed", on.surface ? "true" : "false");
      VIEW.toggles.surface(on.surface);
    } });
  ctrl.appendChild(surfaceMaster);
  /* One switch rather than two buttons: the background is either dark or light, and two
     separate controls made it look as though both could be off. */
  const backgroundSwitch = el("button", { class:"viewer-switch", type:"button", role:"switch" },
    [el("span", { class:"viewer-switch-label" }), el("span", { class:"viewer-switch-track" },
      el("span", { class:"viewer-switch-knob" }))]);
  const paintBackground = () => {
    const dark = VIEW.currentBackground() === "black";
    backgroundSwitch.setAttribute("aria-checked", dark ? "true" : "false");
    backgroundSwitch.classList.toggle("is-on", dark);
    backgroundSwitch.querySelector(".viewer-switch-label").textContent =
      dark ? t("v_background_black") : t("v_background_white");
    backgroundSwitch.setAttribute("aria-label", t("v_background_switch"));
  };
  backgroundSwitch.addEventListener("click", () => {
    VIEW.setBackground(VIEW.currentBackground() === "black" ? "white" : "black");
    paintBackground();
  });
  paintBackground();
  ctrl.appendChild(backgroundSwitch);
  ctrl.appendChild(el("button", { class: "viewer-tool", text: t("v_reset"),
    onclick: () => { VIEW.resetView(); buildViewerSide(meta); } }));
  ctrl.appendChild(el("button", { class: "viewer-tool", text: t("v_snapshot"),
    onclick: () => VIEW.snapshot() }));
  /* The switch between the two residue lists. It sits with the other quick controls because that
     is where a reader is already looking when they decide the pocket is not the thing they came
     for; the framing follows, because a position on the intracellular end of TM6 is off screen
     while the camera is still on the ligand. */
  const wholeButton = el("button", { class:"viewer-tool viewer-tool-whole",
    "aria-pressed": wholeReceptor ? "true" : "false",
    text: wholeReceptor ? t("v_back_to_pocket") : t("v_whole_receptor"),
    onclick: async () => {
      const next = !wholeReceptor;
      if (next) {
        wholeButton.disabled = true;
        wholeButton.textContent = t("v_whole_loading");
        await ensureResidueTable(meta);
        wholeButton.disabled = false;
      }
      wholeReceptor = next;
      if (wholeReceptor) VIEW.frameReceptor(); else VIEW.focusPocket();
      buildViewerSide(meta);
      const r = parseRoute();
      if (r.view === "3d") navigate(Object.assign({}, r, { whole: wholeReceptor ? "1" : null }), true);
    } });
  ctrl.appendChild(wholeButton);
  /* Measurement is a mode, not an action: while it is on, a click in the scene picks an atom
     instead of doing nothing, and the panel below reports what the picks add up to. */
  const measureButton = el("button", { class:"viewer-tool viewer-tool-measure",
    "aria-pressed": VIEW.isMeasuring() ? "true" : "false",
    text: t("v_measure"), onclick: () => {
      VIEW.setMeasureMode(!VIEW.isMeasuring(), () => paintMeasure());
      // The overlays switch to ball-and-stick with the base structure, or half the scene stays
      // unclickable in a mode whose whole purpose is clicking atoms.
      ALIGN.refreshStyle();
      paintMeasure();
    } });
  ctrl.appendChild(measureButton);
  side.appendChild(ctrl);
  if (ligandPanel) side.appendChild(ligandPanel);
  side.appendChild(surfacePanel);
  side.appendChild(el("div", { class: "viewer-actions" }, [
    el("button", { class: "btn", text: t("v_pocket"), onclick: () => VIEW.focusPocket() })
  ]));

  /* Redrawn in place rather than by rebuilding the side panel, so picking an atom does not reset
     the scroll position or the disclosure states around it. */
  const measureSection = el("div", { class: "viewer-section measure-section", hidden: true });
  function paintMeasure() {
    const on = VIEW.isMeasuring();
    measureButton.setAttribute("aria-pressed", on ? "true" : "false");
    measureButton.classList.toggle("selected", on);
    measureSection.hidden = !on;
    clear(measureSection);
    if (!on) return;
    measureSection.appendChild(el("h4", { class:"viewer-section-title", text:t("v_measure_title") }));
    const picks = VIEW.measureList();
    const result = VIEW.measureResult();
    const kept = VIEW.measureKeptList();
    const format = r => r.unit === "angstrom"
      ? r.value.toFixed(2) + " Å" : r.value.toFixed(1) + "°";
    /* With something superposed, "F6x52 CE1 — F6x52 CE1" names the same position in two different
       receptors and reads as a measurement from an atom to itself. The structure is prefixed only
       when there is more than one on screen, so the ordinary single-structure readout is unchanged. */
    const many = ALIGN.hasOverlays();
    const atomText = a => (many && a.struct ? a.struct + " " : "") + a.residue + " " +
      (a.atomName || "?");
    const atomsLine = atoms => atoms.map(atomText).join(" — ");
    /* Kept measurements first: they are answers, and they stay on screen while the next question
       is being picked out. */
    if (kept.length) {
      const list = el("div", { class:"measure-kept" });
      kept.forEach(r => list.appendChild(el("div", { class:"measure-kept-row" }, [
        el("div", {}, [
          el("span", { class:"measure-kind", text:t("v_measure_" + r.kind) }),
          el("strong", { class:"measure-kept-value", text:r.value === null ? "—" : format(r) })]),
        el("div", { class:"muted small", text:atomsLine(r.atoms) }),
        el("button", { class:"measure-remove", type:"button", "aria-label":t("v_measure_remove"),
          title:t("v_measure_remove"), text:"×", onclick:() => VIEW.measureRemoveKept(r.id) })])));
      measureSection.appendChild(list);
    }
    measureSection.appendChild(el("p", { class:"muted small",
      text: VIEW.measureFull() ? t("v_measure_full") : t("v_measure_hint") }));
    if (picks.length) {
      const list = el("ol", { class:"measure-picks" });
      for (const p of picks) list.appendChild(el("li", {}, [
        el("strong", { text:(many && p.struct ? p.struct + " " : "") + p.residue }),
        el("span", { class:"muted", text:" · " + (p.atomName || "?") })]));
      measureSection.appendChild(list);
    }
    if (result && result.value !== null) {
      measureSection.appendChild(el("p", { class:"measure-value" }, [
        el("span", { class:"measure-kind", text:t("v_measure_" + result.kind) }),
        el("strong", { text:format(result) })]));
    } else if (picks.length) {
      measureSection.appendChild(el("p", { class:"muted small", text:t("v_measure_need_more") }));
    }
    const actions = el("div", { class:"measure-actions" });
    if (result && result.value !== null) actions.appendChild(el("button",
      { class:"btn small btn-primary", type:"button", text:t("v_measure_keep"),
        title:t("v_measure_keep_hint"), onclick:() => VIEW.measureKeep() }));
    if (picks.length) actions.appendChild(el("button", { class:"btn small", type:"button",
      text:t("v_measure_undo"), onclick:() => VIEW.measureUndo() }));
    if (picks.length || kept.length) actions.appendChild(el("button", { class:"btn small",
      type:"button", text:t("v_measure_clear"), onclick:() => VIEW.measureClear() }));
    /* Everything the panel is showing, in the order it is showing it: the kept measurements and,
       if it resolves, the one still being picked. A reader who took a measurement wants it in a
       notebook, not retyped. */
    const exportable = kept.concat(result && result.value !== null
      ? [Object.assign({ id:null, atoms:picks }, result)] : []);
    if (exportable.length) {
      const options = el("div", { class:"measure-download-options", hidden:true });
      const cell = (r, i) => { const a = r.atoms[i];
        return a ? (a.struct ? a.struct + " " : "") + a.chain + ":" + a.seq + " " +
          a.residue + " " + (a.atomName || "?") : ""; };
      const columns = [
        { key:"n", label:"#", get:(r, i) => i + 1 },
        { key:"type", label:t("v_measure_type"), get:r => r.kind },
        { key:"value", label:t("v_measure_value"),
          get:r => r.unit === "angstrom" ? r.value.toFixed(3) : r.value.toFixed(2) },
        { key:"unit", label:t("v_measure_unit"), get:r => r.unit === "angstrom" ? "angstrom" : "degree" },
        { key:"pdb", label:"PDB", get:() => meta.pdb_id },
        { key:"atoms", label:t("v_measure_atoms"),
          get:r => r.atoms.map(a => (a.struct ? a.struct + " " : "") + a.residue + " " +
            (a.atomName || "?")).join(" — ") },
        { key:"atom1", label:"atom 1", get:r => cell(r, 0) },
        { key:"atom2", label:"atom 2", get:r => cell(r, 1) },
        { key:"atom3", label:"atom 3", get:r => cell(r, 2) },
        { key:"atom4", label:"atom 4", get:r => cell(r, 3) }];
      // toCSV passes only the row, so the running number is materialised here instead.
      const rows = exportable.map((r, i) => Object.assign({}, r, { n:i + 1 }));
      const cols = columns.map(c => c.key === "n"
        ? { key:"n", label:"#", get:r => r.n } : c);
      const metaLines = () => ({
        structure: meta.pdb_id, receptor: V.plainName(meta.receptor_name || ""),
        note: "geometry computed from the deposited coordinates; distances in angstrom, "
            + "angles and dihedrals in degrees" });
      const base = "measurements_" + meta.pdb_id;
      options.appendChild(el("button", { class:"btn small", type:"button", text:t("export_csv"),
        onclick:() => download(base + ".csv", toCSV(cols, rows, metaLines())) }));
      options.appendChild(el("button", { class:"btn small", type:"button", text:t("export_xlsx"),
        onclick:() => downloadXLSX(base + ".xlsx",
          [{ name:t("v_measure_title"), columns:cols, rows }]) }));
      const toggle = el("button", { class:"btn small", type:"button", "aria-expanded":"false",
        text:t("v_measure_download"), onclick:() => {
          options.hidden = !options.hidden;
          toggle.setAttribute("aria-expanded", options.hidden ? "false" : "true");
        } });
      actions.appendChild(toggle);
      measureSection.appendChild(actions);
      measureSection.appendChild(options);
    } else if (actions.childNodes.length) measureSection.appendChild(actions);
  }
  VIEW.setMeasureMode(VIEW.isMeasuring(), () => paintMeasure());

  // The residue list is what a reader works with; the motif shortcuts sit under it.
  const contactSection = el("div", { class: "viewer-section" });
  const motifSection = el("div", { class: "viewer-section" });
  const motifs = VIEW.motifGroups();
  if (motifs.length || VIEW.hasCovalentBond()) {
    motifSection.appendChild(el("h4", { class: "viewer-section-title", text: t("v_motif_shortcuts") }));
    const list = el("div", { class: "motif-picker" });
    if (VIEW.hasCovalentBond()) {
      list.appendChild(el("div", { class:"motif-group-title group-covalent",
        text:t("v_group_covalent") }));
      const row = el("div", { class:"motif-group-row" });
      const b = el("button", { class:"motif-button covalent-button selected",
        "aria-pressed":"true", text:t("v_covalent_toggle"), onclick:() => {
          const on = b.getAttribute("aria-pressed") !== "true";
          b.setAttribute("aria-pressed", on ? "true" : "false");
          b.classList.toggle("selected", on);
          VIEW.toggles.covalent(on);
        } });
      row.appendChild(b); list.appendChild(row);
      covalentButton = b;
    }
    for (const group of ["ligand", "activation", "structural"]) {
      const rows = motifs.filter(m => m.group === group);
      if (!rows.length) continue;
      list.appendChild(el("div", { class: "motif-group-title group-" + group,
        text: t("v_group_" + group) }));
      const row = el("div", { class: "motif-group-row" });
      for (const motif of rows) {
        const b = el("button", { class: "motif-button motif-" + motif.group, "aria-pressed": "false",
          text: motif.label,
          "aria-label":motif.label + " — " + motif.tooltip,
          onclick: () => {
            const selected = VIEW.toggleMotif(motif.id);
            b.classList.toggle("selected", selected);
            b.setAttribute("aria-pressed", selected ? "true" : "false");
            paintFocus();
          } });
        const tip = el("span", { class:"motif-pattern-popover", role:"tooltip" });
        motif.pattern.forEach((token, index) => {
          if (index) tip.appendChild(document.createTextNode(", "));
          if (token.wildcard) tip.appendChild(el("span", { class:"motif-pattern-wildcard",
            text:token.wildcard }));
          else {
            tip.appendChild(el("strong", { text:token.aa }));
            tip.appendChild(el("span", { text:token.position }));
          }
        });
        if (motif.differenceText) tip.appendChild(el("span", {
          class:"motif-pattern-warning", text:motif.differenceText }));
        row.appendChild(el("span", { class:"motif-button-wrap" }, [b, tip]));
      }
      list.appendChild(row);
    }
    motifSection.appendChild(list);
  }
  /* Clears whichever structure is active. Without this, residues picked on an overlay could be
     taken off only one at a time, because this control reached past the switcher to the base
     structure — the same class of bug the switcher was added to end. */
  motifSection.appendChild(el("button", { class: "clear-selection", text: t("v_clear_selection"),
    onclick: () => {
      if (onBase) VIEW.clearSelections(); else ALIGN.clearOverlaySelection(active);
      buildViewerSide(meta);
    } }));

  /* Offered wherever a selection is made, and only while there is one: with nothing selected the
     control would be promising to hide everything. */
  const focusRow = el("div", { class:"focus-row" });
  function paintFocus() {
    clear(focusRow);
    if (!VIEW.hasSelection()) { focusRow.hidden = true; return; }
    focusRow.hidden = false;
    const on = VIEW.isFocusSelection();
    focusRow.appendChild(el("button", { class:"btn small focus-toggle" + (on ? " selected" : ""),
      type:"button", "aria-pressed": on ? "true" : "false", title: t("v_focus_hint"),
      text: on ? t("v_focus_off") : t("v_focus_on"),
      onclick: () => { VIEW.setFocusSelection(!VIEW.isFocusSelection()); buildViewerSide(meta); } }));
  }
  paintFocus();

  const contacts = VIEW.contactResidues();
  if (wholeReceptor) {
    buildReceptorColumns(contactSection, meta, paintFocus);
  } else if (contacts.length) {
    contactSection.appendChild(el("h4", { class: "viewer-section-title", text: t("v_contact_list") }));
    contactSection.appendChild(el("p", { class: "muted small", text: t("v_click_hint") }));
    const list = el("div", { class: "residue-picker" });
    for (const r of contacts) {
      const initiallySelected = VIEW.isResidueSelected(r.chain, r.seq);
      const b = el("button", { class: "residue-button" + (initiallySelected ? " selected" : ""),
        "aria-pressed": initiallySelected ? "true" : "false", onclick: () => {
          const selected = VIEW.toggleResidue(r.chain, r.seq);
          b.classList.toggle("selected", selected);
          b.setAttribute("aria-pressed", selected ? "true" : "false");
          paintFocus();
        } });
      if (r.motif) {
        b.appendChild(el("strong", { class: "residue-motif", text: r.motif }));
        b.appendChild(el("span", { class: "residue-name", text: r.residue }));
        b.appendChild(el("span", { class: "residue-distance", text: r.distance }));
      } else b.textContent = r.label;
      list.appendChild(b);
    }
    contactSection.appendChild(list);
  }
  side.appendChild(focusRow);
  side.appendChild(measureSection);
  paintMeasure();
  side.appendChild(buildAlignSection(meta));
  side.appendChild(contactSection);
  side.appendChild(motifSection);

  const legend = el("div", { class: "viewer-legend" });
  const legendRow = (cls, text) => el("div", { class: "legend-row" }, [
    el("i", { class: "legend-swatch " + cls }), el("span", { text }) ]);
  legend.appendChild(legendRow("ligand", (cur && cur.ligand_name) || t("ligand")));
  legend.appendChild(legendRow("contact", t("v_legend_contact")));
  legend.appendChild(legendRow("selected", t("v_legend_selected")));
  legend.appendChild(legendRow("motif-ligand", t("v_legend_motif_ligand")));
  legend.appendChild(legendRow("motif-activation", t("v_legend_motif_activation")));
  if (cur && cur.binding_site_class === "covalent_core_site")
    legend.appendChild(legendRow("covalent", t("v_legend_covalent")));
  side.appendChild(legend);
  side.appendChild(el("p", { class: "viewer-hint", text: t("v_mouse_hint") }));
  side.appendChild(el("a", { class: "btn link", href: meta.full_structure_url, target: "_blank",
    rel: "noopener", text: t("v_source") }));
  if (!meta.auxiliary_chains_included)
    side.appendChild(el("p", { class: "muted small", text:
      (document.documentElement.lang === "tr" ? meta.auxiliary_note_tr : meta.auxiliary_note_en) ||
      meta.auxiliary_note_en }));
}

/* The whole receptor, as seven columns — one helix each, read from the extracellular end down,
   which is the order the positions themselves are numbered in. A column rather than a single long
   list because the question a reader brings here is almost always about one helix ("what is along
   TM3?"), and a flat list of two hundred and fifty buttons answers it only by scrolling.

   Clicking a position draws that residue and labels it; clicking again takes it away. That is the
   same control the pocket list already offered, so the two lists behave identically and only their
   contents differ. */
/* `onSelectionChange` is passed in rather than reached for: this function lives outside
   buildViewerSide, so the panel's own repaint is not in its scope — a click here was throwing
   silently while every assertion still passed. */
function buildReceptorColumns(container, meta, onSelectionChange) {
  /* Reads whichever structure the switcher has active, so the question "what is along TM6 of the
     structure I superposed" has the same answer path as it does for the base structure. */
  const active = activePdb(meta);
  const onBase = active === String(meta.pdb_id).toUpperCase();
  container.appendChild(el("h4", { class:"viewer-section-title",
    text:t("v_whole_list") + (onBase ? "" : " — " + active) }));
  const segments = onBase ? VIEW.receptorSegments() : ALIGN.segmentsOf(active);
  if (!segments.length) {
    container.appendChild(el("p", { class:"notice small", text:t("v_whole_unavailable") }));
    return;
  }
  const helices = segments.filter(s => s.helix);
  const other = segments.find(s => !s.helix);
  container.appendChild(el("p", { class:"muted small", text:t("v_whole_hint") }));
  // Said once, where a reader can act on it: the green cards are not something they clicked.
  if (onBase && VIEW.hasQueryMarks())
    container.appendChild(el("p", { class:"muted small tm-query-note",
      text:t("v_whole_query_note", { n:VIEW.queryPositionList().length }) }));
  const isSelected = row => onBase ? VIEW.isResidueSelected(row.c, row.n)
    : ALIGN.isOverlayResidueSelected(active, row.c, row.n);
  const toggle = row => onBase ? VIEW.toggleResidue(row.c, row.n)
    : ALIGN.toggleOverlayResidue(active, row.c, row.n);
  const residueButton = row => {
    const selected = isSelected(row);
    const mutated = !!row.w;
    const title = [
      row.a + row.p,
      row.c + ":" + row.n,
      row.query ? t("v_whole_is_query") : null,
      row.contact ? t("v_whole_is_contact") : null,
      mutated ? t("v_whole_mutated", { wild:row.w, construct:row.a }) : null
    ].filter(Boolean).join(" · ");
    const b = el("button", {
      class:"tm-residue" + (selected ? " selected" : "") + (row.contact ? " is-contact" : "") +
        (row.query ? " is-query" : "") + (mutated ? " is-mutated" : ""),
      "aria-pressed":selected ? "true" : "false", title,
      "aria-label":title,
      onclick:() => {
        const on = toggle(row);
        b.classList.toggle("selected", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
        if (onSelectionChange) onSelectionChange();
      } }, [
      el("strong", { class:"tm-residue-aa", text:row.a }),
      el("span", { class:"tm-residue-pos", text:row.p })]);
    return b;
  };
  const grid = el("div", { class:"tm-columns" });
  for (const g of helices) {
    const list = el("div", { class:"tm-column-list" });
    for (const row of g.residues) list.appendChild(residueButton(row));
    grid.appendChild(el("div", { class:"tm-column" }, [
      el("div", { class:"tm-column-head" }, [
        el("span", { class:"tm-column-name", text:g.segment }),
        el("span", { class:"tm-column-count", text:String(g.residues.length) })]),
      list]));
  }
  container.appendChild(grid);
  /* A helix with nothing to list is left out of the grid, and left out silently a reader cannot
     tell "this structure does not resolve TM6" from "the atlas could not number it" — they had to
     ask. It is the second: the residues are usually there in the coordinates, but the alignment
     the generic numbering is derived from did not reach them, so there is no position to click.
     Three structures out of 1346 are in this state, which is exactly why it needs saying: nobody
     will have seen it before and nothing else on the page accounts for the gap. */
  const absent = VIEW.helixOrder().filter(h => !helices.some(g => g.segment === h));
  if (absent.length) container.appendChild(el("p", { class:"notice small tm-missing",
    text:t("v_whole_missing_helices", { list: absent.join(", ") }) }));
  // H8 and the resolved loop residues are as real as the helical ones; they are simply not one of
  // the seven columns, so they get a disclosure of their own instead of being dropped.
  if (other) {
    const list = el("div", { class:"tm-other-list" });
    for (const row of other.residues) list.appendChild(residueButton(row));
    // Open, like the seven columns beside it. A reader who asked for the whole receptor asked for
    // this part of it too; closing it by default would hide the only H8 and loop positions there
    // are behind a disclosure they have no reason to suspect.
    container.appendChild(el("details", { class:"tm-other", open:true }, [
      el("summary", { text:t("v_segment_other") + " (" + other.residues.length + ")" }), list]));
  }
}

/* ------------------------------------------------------------------ render */
async function render(r) {
  const manifest = L.getManifest();
  // The motif query panel keeps its whole state in the address. A route change confined to that
  // panel's own keys is handed to the mounted panel, because re-rendering the view would take
  // the query input out of the document and the caret with it — which is what stopped the panel
  // from being addressable in the first place.
  if (MQ.canUpdateInPlace(r)) { MQ.applyRoute(r); buildChrome(manifest); setStatus(""); return; }
  buildChrome(manifest);
  setStatus(t("loading"));
  const main = MAIN();
  clear(main);
  try {
    if (r.family && r.family !== lastFamily) { ST.resetFilters(); if (lastFamily) L.evictFamily(lastFamily); lastFamily = r.family; }
    let node;
    switch (r.view) {
      case "landing": node = await V.landing(main); break;
      case "overview": navigate({ family: r.family, view: "structures" }, true); return;
      case "structures": node = await V.structures(main, r.family, openModal, r.site, r.pdb); break;
      // The panel view is the same explorer as Yapılar, sourced from a panel payload.
      case "panels": {
        // Fall back to whatever panel this build actually carries; an offline single-family
        // export may not include Gs at all.
        const available = Object.keys(L.getManifest().panel_files || {});
        const panel = available.includes(r.panel) ? r.panel
          : (available.includes("gs") ? "gs" : available[0]);
        if (!panel) { fatal(t("err_route")); return; }
        node = await V.structures(main, null, openModal, null, r.pdb, { panelSlug: panel }); break;
      }
      // The ligand route used to be the structure list with a class filter applied, which made it
      // a second copy of that page and counted a compound once per deposition. It now has its own
      // view, whose unit is the ligand; the class filter it replaced still exists in Structures.
      case "ligands": node = await ligandExplorer(main, r.ligand); break;
      // Rebuilt as its own module: the panel scores receptors rather than filtering depositions,
      // and its state is restored from the route rather than from a closure.
      case "motifsearch": node = await MQ.motifQuery(main, r); break;
      case "evidence": node = await V.evidence(main, r.family, r.open === "1"); break;
      case "contacts": case "interfaces": case "motifs": case "compare":
        navigate(r.family ? { family: r.family, view: "structures" } : { view: "landing" }, true); return;
      case "guide": node = await V.guide(main); break;
      case "methods": node = await V.methods(); break;
      case "sources": node = await V.sources(); break;
      case "references": node = await V.references(main, r.family); break;
      case "cite": node = await V.cite(main, r.pdb, r.family); break;
      case "3d":
        // A deep link may name a structure without naming a family. The modal is the point of
        // the route, so render whatever context we can behind it rather than failing.
        node = r.family ? await V.structures(main, r.family, openModal, r.site, r.pdb) : await V.landing(main);
        break;
      default: node = null;
    }
    if (!node) { fatal(t("err_route")); setStatus(""); return; }
    main.appendChild(node);
    // Re-entering render() while the same structure is already open — which a language change
    // does — must not tear the stage down and rebuild it; the user would lose the camera and
    // every toggle. Only open when the modal is not already showing this structure.
    if (r.view === "3d" && r.pdb) {
      const m = document.getElementById("modal");
      const already = m && !m.hidden && VIEW.meta_() && VIEW.meta_().pdb_id === r.pdb;
      if (!already) await openModal(r.pdb, r.observation, null,
        { whole: r.whole === "1", mark: r.mark });
      /* The address can change while the modal stays open — Back and Forward between the two
         residue lists do exactly that, and so does editing the hash by hand. Without this the
         panel kept whatever the last click left behind and the address quietly lied about it. */
      else await syncWholeReceptor(r.whole === "1");
    }
  } catch (e) {
    fatal(L.errorMessage(e));
  }
  setStatus("");
}

/* ------------------------------------------------------------------ boot */
async function boot() {
  initLang(); initTheme();
  const langSel = document.getElementById("lang");
  const themeSel = document.getElementById("theme");
  for (const l of ["tr", "en"]) langSel.appendChild(el("option", { value: l, text: l.toUpperCase(),
    selected: getLang() === l }));
  for (const th of themes()) themeSel.appendChild(el("option", { value: th,
    text: t("theme_" + th), selected: getTheme() === th }));
  langSel.addEventListener("change", e => {
    setLang(e.target.value);
    // language change must not resize a hidden stage
    VIEW.lifecycle.resizeStageIfVisible();
    render(parseRoute());
    const m = document.getElementById("modal");
    if (m && !m.hidden) { const meta = VIEW.meta_(); if (meta) buildViewerSide(meta); }
  });
  themeSel.addEventListener("change", e => {
    setTheme(e.target.value);
    VIEW.lifecycle.resizeStageIfVisible();
  });
  if (L.isFileProtocol) {
    document.getElementById("filewarn").hidden = false;
    document.getElementById("filewarn").textContent = t("err_file");
  }
  try { await L.loadManifest(); }
  catch (e) { fatal(L.errorMessage(e)); return; }
  const m = L.getManifest();
  setupGlobalSearch();
  // One short line that says what the build is and where the detail lives. The counts and the
  // per-family validation matrix are shown in context — in Methods, in each family overview and
  // in the review-gate panel beside the numbers they qualify — which is where a reader can act
  // on them. A banner long enough to state everything is a banner nobody reads.
  document.getElementById("prerelease").textContent = t("prerelease_notice");
  document.title = m.atlas_title + " — " + m.version;
  onRoute(render);
  startRouter();
}
window.addEventListener("DOMContentLoaded", boot);
window.__atlas = { diagnostics: () => VIEW.lifecycle.diagnostics(), cache: () => L.cacheStats() };
