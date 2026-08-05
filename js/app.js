// Application shell: routing, lazy loading, the 3D modal and the accessibility plumbing.
import { t, initLang, setLang, getLang } from "./core/i18n.js";
import { initTheme, setTheme, getTheme, themes } from "./core/theme.js";
import { parseRoute, navigate, onRoute, startRouter } from "./core/router.js";
import * as ST from "./core/state.js";
import * as L from "./data/loader.js";
import { el, clear } from "./components/dom.js";
import * as V from "./views/views.js";
import * as VIEW from "./viewer/viewer.js";

const MAIN = () => document.getElementById("main");
let lastFamily = null, modalOpener = null;

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
  clear(nav);
  const r = parseRoute();
  const items = r.family
    ? [["overview", "nav_overview"], ["structures", "nav_structures"], ["contacts", "nav_contacts"],
       ["interfaces", "nav_interfaces"], ["motifs", "nav_motifs"], ["compare", "nav_compare"],
       ["evidence", "nav_evidence"], ["methods", "nav_methods"], ["sources", "nav_sources"],
       ["references", "nav_references"], ["cite", "nav_cite"]]
    : [["landing", "families"], ["compare", "nav_compare"], ["methods", "nav_methods"],
       ["sources", "nav_sources"], ["references", "nav_references"], ["cite", "nav_cite"]];
  for (const [view, key] of items) {
    const on = r.view === view;
    nav.appendChild(el("a", { class: "navlink" + (on ? " active" : ""),
      href: "#" + (r.family && view !== "landing" ? "family=" + r.family + "&" : "") + "view=" + view,
      "aria-current": on ? "page" : null, text: t(key) }));
  }
  const fam = document.getElementById("famlabel");
  clear(fam);
  if (r.family) {
    const f = (manifest.families || []).find(x => x.slug === r.family);
    fam.appendChild(el("a", { class: "crumb", href: "#view=landing", text: t("back_to_families") }));
    fam.appendChild(el("span", { class: "crumb sep", text: "›" }));
    fam.appendChild(el("span", { class: "crumb", text: f ? f.name : r.family }));
  }
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
      el("div", { id: "viewport", class: "viewport" }),
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

async function openModal(pdb, observationId) {
  const m = ensureModal();
  modalOpener = document.activeElement;
  m.hidden = false;
  document.body.classList.add("modal-open");
  // The Tab handler below cycles focus inside the dialog, but a screen reader's virtual cursor
  // and find-in-page ignore it and walk straight into the page behind. `inert` is what actually
  // removes that content from the accessibility tree.
  setBackgroundInert(true);
  const st = document.getElementById("viewer-status");
  st.hidden = false; st.textContent = t("loading_structure");
  // the viewport is visible now; the viewer resizes only after this point
  const meta = await VIEW.open(document.getElementById("viewport"), pdb, observationId,
    msg => { st.textContent = msg; st.hidden = !msg; });
  if (!meta) return;
  buildViewerSide(meta);
  const note = VIEW.statusMessage();
  st.textContent = note; st.hidden = !note;
  document.getElementById("modal-close").focus();
  const r = parseRoute(); navigate(Object.assign({}, r, { pdb, observation: VIEW.currentObservation(), view: "3d" }), true);
}
function closeModal() {
  const m = document.getElementById("modal");
  if (!m || m.hidden) return;
  VIEW.close();
  m.hidden = true;
  document.body.classList.remove("modal-open");
  setBackgroundInert(false);
  const r = parseRoute(); delete r.pdb; delete r.observation;
  if (r.view === "3d") r.view = r.family ? "structures" : "landing";
  navigate(r, true);
  if (modalOpener && modalOpener.focus) modalOpener.focus();
  modalOpener = null;
}
function buildViewerSide(meta) {
  const side = document.getElementById("viewer-side");
  clear(side);
  side.appendChild(el("h3", { text: meta.pdb_id + " — " + (meta.receptor_name || "") }));
  side.appendChild(el("p", { class: "muted small", text: meta.species + " · " +
    (meta.experimental_method || "") + " · " + (meta.resolution != null ? meta.resolution + " Å" : "") }));
  if ((meta.observations || []).length > 1) {
    const sel = el("select", { "aria-label": t("observation"),
      onchange: e => { VIEW.setObservation(e.target.value);
        const n = VIEW.statusMessage(); const st = document.getElementById("viewer-status");
        st.textContent = n; st.hidden = !n;
        const r = parseRoute(); navigate(Object.assign({}, r, { observation: e.target.value }), true); } });
    for (const o of meta.observations) sel.appendChild(el("option", { value: o.observation_id,
      text: (o.ligand_name || o.ligand_entity_id) + " — " + o.ligand_role,
      selected: o.observation_id === VIEW.currentObservation() }));
    side.appendChild(el("label", { text: t("observation") })); side.appendChild(sel);
  }
  const on = { cartoon: true, contacts: true, motifs: false, motifLabels: false,
    surface: false, lines: false, allLigands: false, ions: false, aux: false, spin: false };
  const ctrl = el("div", { class: "toggles" });
  const add = (key, label, disabled) => {
    const id = "tg-" + key;
    const cb = el("input", { type: "checkbox", id, checked: on[key], disabled: !!disabled,
      onchange: e => { on[key] = e.target.checked; VIEW.toggles[key](e.target.checked); } });
    ctrl.appendChild(el("div", { class: "toggle" }, [cb, el("label", { for: id, text: label })]));
  };
  const apo = meta.apo_status === "confirmed_apo";
  const cur = (meta.observations || []).find(o => o.observation_id === VIEW.currentObservation());
  const hasLig = !!(cur && cur.ligand_selection);
  add("cartoon", t("v_cartoon"));
  add("allLigands", t("v_all_ligands"), apo || !hasLig);
  add("contacts", (cur && cur.is_polymer_interface) ? t("v_interface") : t("v_contacts"), apo || !hasLig);
  add("lines", t("v_lines"), apo || !hasLig);
  add("surface", t("v_surface"), apo || !hasLig);
  add("motifs", t("v_motifs"));
  add("motifLabels", t("v_motif_labels"));
  add("ions", t("v_ions"), !(meta.observed_sodium || []).length);
  add("aux", t("v_aux"), !meta.auxiliary_chains_included);
  add("spin", t("v_spin"));
  side.appendChild(ctrl);
  side.appendChild(el("button", { class: "btn", text: t("v_reset"), onclick: () => VIEW.resetView() }));
  side.appendChild(el("a", { class: "btn link", href: meta.full_structure_url, target: "_blank",
    rel: "noopener", text: t("v_source") }));
  if (!meta.auxiliary_chains_included)
    side.appendChild(el("p", { class: "muted small", text: meta.auxiliary_note_en }));
}

/* ------------------------------------------------------------------ render */
async function render(r) {
  const manifest = L.getManifest();
  buildChrome(manifest);
  setStatus(t("loading"));
  const main = MAIN();
  clear(main);
  try {
    if (r.family && r.family !== lastFamily) { ST.resetFilters(); if (lastFamily) L.evictFamily(lastFamily); lastFamily = r.family; }
    let node;
    switch (r.view) {
      case "landing": node = await V.landing(main); break;
      case "overview": node = await V.overview(main, r.family); break;
      case "structures": node = await V.structures(main, r.family, openModal); break;
      case "contacts": node = await V.contacts(main, r.family, r.site, false); break;
      case "interfaces": node = await V.contacts(main, r.family, r.site, true); break;
      case "motifs": node = await V.motifs(main, r.family); break;
      case "compare": node = await V.compare(main); break;
      case "evidence": node = await V.evidence(main, r.family); break;
      case "methods": node = await V.methods(); break;
      case "sources": node = await V.sources(); break;
      case "references": node = await V.references(main, r.family); break;
      case "cite": node = await V.cite(main, r.pdb); break;
      case "3d":
        // A deep link may name a structure without naming a family. The modal is the point of
        // the route, so render whatever context we can behind it rather than failing.
        node = r.family ? await V.structures(main, r.family, openModal) : await V.landing(main);
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
      if (!already) await openModal(r.pdb, r.observation);
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
  // The banner carries the two scope statements a reader needs before any number is read: the
  // release is unreviewed, and the contact rule's validation is not uniform across families.
  document.getElementById("prerelease").textContent =
    t("prerelease_notice") + " (" + m.review_warning_count + " " + t("review_items") + ") — " +
    t("validation_global");
  document.title = m.atlas_title + " — " + m.version;
  onRoute(render);
  startRouter();
}
window.addEventListener("DOMContentLoaded", boot);
window.__atlas = { diagnostics: () => VIEW.lifecycle.diagnostics(), cache: () => L.cacheStats() };
