// Application shell: routing, lazy loading, the 3D modal and the accessibility plumbing.
import { t, initLang, setLang, getLang, methodLabel } from "./core/i18n.js";
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
  const globalSearch = document.getElementById("global-search");
  if (globalSearch && globalSearch.parentNode === nav) nav.removeChild(globalSearch);
  clear(nav);
  const r = parseRoute();
  const items = r.family
    ? [["structures", "nav_structures"], ["panels", "nav_panels"], ["ligands", "nav_ligands"],
       ["methods", "nav_methods"], ["sources", "nav_sources"],
       ["references", "nav_references"], ["cite", "nav_cite"]]
    : [["landing", "families"], ["panels", "nav_panels"], ["ligands", "nav_ligands"],
       ["methods", "nav_methods"], ["sources", "nav_sources"],
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
    if (!scored.length) panel.appendChild(el("p", { class:"global-search-message", text:t("global_search_empty") }));
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

async function openModal(pdb, observationId, focusResidue) {
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
  updateModalTitle(meta);
  if (focusResidue && !VIEW.isResidueSelected(focusResidue.chain, focusResidue.seq))
    VIEW.toggleResidue(focusResidue.chain, focusResidue.seq);
  buildViewerSide(meta);
  buildObservationSwitch(meta);
  const note = VIEW.statusMessage();
  st.textContent = note; st.hidden = !note;
  document.getElementById("modal-close").focus();
  const r = parseRoute(); navigate(Object.assign({}, r, { pdb, observation: VIEW.currentObservation(), view: "3d" }), true);
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
  m.hidden = true;
  document.body.classList.remove("modal-open");
  setBackgroundInert(false);
  const r = parseRoute(); delete r.pdb; delete r.observation;
    if (r.view === "3d") r.view = r.family ? "structures" : "landing";
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
  const on = { cartoon: true, ligand: true, contacts: true, motifs: false, motifLabels: true,
    surface: false, surfaceReceptor:false, surfaceLigand:false, lines: true,
    allLigands: false, ions: false, aux: false, spin: false };
  const ctrl = el("div", { class: "viewer-tools" });
  const add = (key, label, disabled) => {
    const b = el("button", { class: "viewer-tool", disabled: !!disabled,
      "aria-pressed": on[key] ? "true" : "false", text: label, onclick: () => {
        on[key] = !on[key]; b.setAttribute("aria-pressed", on[key] ? "true" : "false");
        VIEW.toggles[key](on[key]);
      } });
    ctrl.appendChild(b);
    return b;
  };
  const apo = meta.apo_status === "confirmed_apo";
  const cur = (meta.observations || []).find(o => o.observation_id === VIEW.currentObservation());
  const hasLig = !!(cur && cur.ligand_selection);
  add("cartoon", t("v_cartoon"));
  add("motifLabels", t("v_motif_labels"));
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
  add("spin", t("v_spin"));
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
  side.appendChild(ctrl);
  if (ligandPanel) side.appendChild(ligandPanel);
  side.appendChild(surfacePanel);
  side.appendChild(el("div", { class: "viewer-actions" }, [
    el("button", { class: "btn", text: t("v_pocket"), onclick: () => VIEW.focusPocket() })
  ]));

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
  motifSection.appendChild(el("button", { class: "clear-selection", text: t("v_clear_selection"),
    onclick: () => { VIEW.clearSelections(); buildViewerSide(meta); } }));

  const contacts = VIEW.contactResidues();
  if (contacts.length) {
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
      case "ligands": {
        const available = Object.keys(L.getManifest().ligand_files || {});
        const cls = available.includes(r.ligand) ? r.ligand
          : (available.includes("agonist") ? "agonist" : available[0]);
        if (!cls) { fatal(t("err_route")); return; }
        node = await V.structures(main, null, openModal, null, r.pdb, { ligandSlug: cls }); break;
      }
      case "evidence": node = await V.evidence(main, r.family, r.open === "1"); break;
      case "contacts": case "interfaces": case "motifs": case "compare":
        navigate(r.family ? { family: r.family, view: "structures" } : { view: "landing" }, true); return;
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
