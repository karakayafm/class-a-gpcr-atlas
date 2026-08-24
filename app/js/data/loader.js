// Lazy payload loader with an LRU cache keyed on schema + data version + payload hash.
// The initial page loads only the global manifest and the landing payload.
import { t } from "../core/i18n.js";

const MAX_FAMILY_ENTRIES = 3;      // explicit eviction: large contact payloads are released
const MAX_BUNDLE_ENTRIES = 4;
const famCache = new Map();
const bundleCache = new Map();
let manifest = null;
let searchIndexPromise = null;
let panelsPromise = null;
export let isFileProtocol = location.protocol === "file:";

function lru(map, max) {
  while (map.size > max) { const k = map.keys().next().value; map.delete(k); }
}
function touch(map, key, val) { map.delete(key); map.set(key, val); }

export class LoadError extends Error {
  constructor(kind, detail) { super(kind); this.kind = kind; this.detail = detail; }
}

async function getJSON(url) {
  let res;
  try { res = await fetch(url, { cache: "no-cache" }); }
  catch (e) { throw new LoadError(isFileProtocol ? "file" : "network", url); }
  if (!res.ok) throw new LoadError("http_" + res.status, url);
  try { return await res.json(); }
  catch (e) { throw new LoadError("parse", url); }
}

export function base() {
  const b = document.body.getAttribute("data-payload-base");
  return b ? b.replace(/\/?$/, "/") : "../data/web/";
}

export async function loadManifest() {
  if (manifest) return manifest;
  const m = await getJSON(base() + "global/manifest.json");
  if (!m.schema_version) throw new LoadError("schema", "global/manifest.json");
  manifest = m;
  return m;
}
export function getManifest() { return manifest; }

export function loadSearchIndex() {
  if (searchIndexPromise) return searchIndexPromise;
  searchIndexPromise = loadGlobal("search_index.json")
    .then(data => data.structures || [])
    .catch(e => { searchIndexPromise=null; throw e; });
  return searchIndexPromise;
}

// Deliberately separate from boot/landing: the 2.8 MB panel payload is requested only when the
// user opens the panel workspace.
/* Per-panel structure list: every structure in one transducer panel, across families.
   Keyed on the manifest checksum like the family payloads, so a rebuilt payload is never
   served from a stale cache entry. */
export async function loadPanelStructures(panelSlug) {
  const entry = (getManifest().panel_files || {})[panelSlug];
  if (!entry) throw new LoadError("schema", "panels/" + panelSlug);
  const key = "panel:" + panelSlug + ":" + entry.sha256;
  if (famCache.has(key)) { const v = famCache.get(key); touch(famCache, key, v); return v; }
  const d = await getJSON(base() + entry.url);
  checkSchema(d, "panels/" + panelSlug);
  touch(famCache, key, d);
  lru(famCache, MAX_FAMILY_ENTRIES * 4);
  return d;
}
/* Ligand chemistry and its pattern catalogue. Keyed on the manifest checksum like the other
   payloads, and fetched only when a chemistry filter is first opened, so the landing payload
   is unaffected. */
async function loadGlobalChecked(name) {
  const entry = (getManifest().global_files || {})[name];
  if (!entry) throw new LoadError("schema", "global/" + name);
  const key = "gf:" + name + ":" + entry.sha256;
  if (famCache.has(key)) { const v = famCache.get(key); touch(famCache, key, v); return v; }
  const d = await getJSON(base() + "global/" + name);
  touch(famCache, key, d);
  lru(famCache, MAX_FAMILY_ENTRIES * 4);
  return d;
}
export function loadLigandChemistry() { return loadGlobalChecked("ligand_chemistry.json"); }
export function loadChemistryCatalog() { return loadGlobalChecked("chemistry_catalog.json"); }
export function loadLigandFingerprints() { return loadGlobalChecked("ligand_fingerprints.json"); }
export function loadMotifSearch() { return loadGlobalChecked("motif_search.json"); }
/* The pocket half of the same index: the positions a ligand is in contact with, in the
   motif_search schema so one panel reads both. Fetched only when that scope is chosen. */
export function loadPocketSearch() { return loadGlobalChecked("pocket_search.json"); }
/* Withdrawn PDB entries and what replaced them. Fetched only when a search finds nothing, which
   is the only moment it can say anything useful. */
export function loadSupersessions() { return loadGlobalChecked("supersessions.json"); }
/* The third pool: every generic position, not only the ones a ligand touches or the ones that
   move on activation. Same schema again, so the panel switches to it with a control and no code.
   1.5 MB, so it is fetched only when that scope is chosen. */
export function loadReceptorSearch() { return loadGlobalChecked("receptor_search.json"); }
/* Ballesteros-Weinstein labels for the positions both pools use. A side file rather than an
   edit to either payload: motif_search.json is frozen, and a label is not worth reissuing it. */
export function loadGenericNumbering() { return loadGlobalChecked("generic_numbering.json"); }
/* Reported affinity, from the one BindingDB subset whose licence allows redistribution.
   It covers a small share of the components, so callers show it where it exists and state
   the coverage rather than implying a value is missing when none was ever published. */
export function loadBindingAffinity() { return loadGlobalChecked("binding_affinity.json"); }

/* Per-pharmacology-class structure list: every structure carrying a ligand of that class,
   across families. */
export async function loadLigandStructures(classSlug) {
  const entry = (getManifest().ligand_files || {})[classSlug];
  if (!entry) throw new LoadError("schema", "ligands/" + classSlug);
  const key = "ligand:" + classSlug + ":" + entry.sha256;
  if (famCache.has(key)) { const v = famCache.get(key); touch(famCache, key, v); return v; }
  const d = await getJSON(base() + entry.url);
  checkSchema(d, "ligands/" + classSlug);
  touch(famCache, key, d);
  lru(famCache, MAX_FAMILY_ENTRIES * 4);
  return d;
}
export function loadPanels() {
  if (panelsPromise) return panelsPromise;
  panelsPromise = loadGlobal("panels.json").catch(e => { panelsPromise=null; throw e; });
  return panelsPromise;
}

// Family residue detail is likewise opt-in; loading a family structure index does not fetch it.
export function loadPocketDetail(slug) { return loadFamilyFile(slug, "pocket_detail.json"); }
export function loadFamilyReferences(slug) { return loadFamilyFile(slug, "references.json"); }
export function loadFamilyEvidence(slug) { return loadFamilyFile(slug, "evidence.json"); }
export function loadLigandXrefs(slug) { return loadFamilyFile(slug, "ligand_xrefs.json"); }

export async function loadGlobal(name) {
  const m = await loadManifest();
  const key = "global:" + name;
  if (famCache.has(key)) { const v = famCache.get(key); touch(famCache, key, v); return v; }
  const d = await getJSON(base() + "global/" + name);
  checkSchema(d, name);
  touch(famCache, key, d); lru(famCache, MAX_FAMILY_ENTRIES + 6);
  return d;
}

function checkSchema(d, what) {
  const m = getManifest();
  if (!d || !d.schema_version) throw new LoadError("schema", what);
  if (m && m.schema_versions && m.schema_versions.payloads &&
      d.schema_version !== m.schema_versions.payloads)
    throw new LoadError("schema", what + " (" + d.schema_version + ")");
}

export async function loadFamilyManifest(slug) {
  const m = await loadManifest();
  const fam = (m.families || []).find(f => f.slug === slug);
  if (!fam) throw new LoadError("family_unknown", slug);
  const key = "fm:" + slug;
  if (famCache.has(key)) { const v = famCache.get(key); touch(famCache, key, v); return v; }
  const d = await getJSON(base() + fam.manifest_url);
  checkSchema(d, slug + "/manifest.json");
  if (d.data_version !== m.data_version) throw new LoadError("version", slug);
  touch(famCache, key, d); lru(famCache, MAX_FAMILY_ENTRIES + 6);
  return d;
}

export async function loadFamilyFile(slug, name) {
  const fm = await loadFamilyManifest(slug);
  const entry = (fm.files || []).find(f => f.name === name);
  if (!entry) return null;
  const key = "ff:" + slug + ":" + name + ":" + entry.sha256;
  if (famCache.has(key)) { const v = famCache.get(key); touch(famCache, key, v); return v; }
  const d = await getJSON(base() + "families/" + entry.url.replace(/^families\//, ""));
  checkSchema(d, slug + "/" + name);
  touch(famCache, key, d);
  lru(famCache, MAX_FAMILY_ENTRIES * 4);
  return d;
}

// Overlay payloads (Phase 6A.1 review gate and validation disclosure). They live beside the
// Phase 5 payload tree rather than inside it, because the Phase 5 tree is frozen. A missing
// overlay file is not an error: it means this build carries no overlay.
export async function loadOverlay(path) {
  const key = "ov:" + path;
  if (famCache.has(key)) { const v = famCache.get(key); touch(famCache, key, v); return v; }
  let d = null;
  try { d = await getJSON(base() + "overlay/" + path); }
  catch (e) { d = null; }
  touch(famCache, key, d); lru(famCache, MAX_FAMILY_ENTRIES * 4);
  return d;
}

/* Every generic-numbered residue of one structure's receptor chain, for the whole-receptor view.
   An overlay rather than part of the bundle: the bundle is fetched every time a structure opens,
   and this is wanted only when a reader asks to look outside the pocket. `loadOverlay` returns
   null where the file does not exist, which is the honest answer for the handful of structures
   whose residue mapping the pipeline could not resolve. */
export function loadReceptorResidues(pdb) {
  return loadOverlay("structures/" + pdb + "/receptor_residues.json");
}

export async function loadBundleMeta(pdb) {
  const key = "bm:" + pdb;
  if (bundleCache.has(key)) { const v = bundleCache.get(key); touch(bundleCache, key, v); return v; }
  const d = await getJSON(base() + "structures/" + pdb + "/viewer_meta.json");
  touch(bundleCache, key, d); lru(bundleCache, MAX_BUNDLE_ENTRIES);
  return d;
}
export function bundleCifUrl(pdb) { return base() + "structures/" + pdb + "/viewer.cif"; }

export function evictFamily(slug) {
  for (const k of Array.from(famCache.keys()))
    if (k.startsWith("ff:" + slug + ":") || k === "fm:" + slug) famCache.delete(k);
}
export function cacheStats() {
  return { family: famCache.size, bundle: bundleCache.size,
           maxFamily: MAX_FAMILY_ENTRIES * 4, maxBundle: MAX_BUNDLE_ENTRIES };
}
/* The reload hint, on the failures a stale cache actually causes.
 *
 * The payload loader checks that every file's schema and data version match the manifest, and that
 * check is right — mixing payloads from two builds would show numbers from one against labels from
 * another. What it cannot tell is *why* they disagree, and the common reason is not a broken build:
 * it is a browser holding one file from the previous deploy and fetching the next from the network.
 * A reload with the cache bypassed fixes it, and until now nothing said so. A wrong address is a
 * different failure — reloading a family that does not exist reloads nothing — so `family_unknown`
 * is left without the hint. */
function reloadKeys() {
  const p = (navigator.userAgentData && navigator.userAgentData.platform) ||
            navigator.platform || "";
  return /mac/i.test(p) ? "⇧ ⌘ R" : "Ctrl + Shift + R";
}
/* Every failure a reload can plausibly fix. `getJSON` reports a failed request as `network`, a bad
   status as `http_404` and friends, and unreadable content as `parse`; the manifest checks add
   `schema` and `version`. A 404 or a version mismatch right after a deploy is the stale-cache case
   exactly. `family_unknown` is the one left out — the address names a family that does not exist,
   and reloading it reloads nothing. */
export function isStaleCacheError(err) {
  return err instanceof LoadError && err.kind !== "family_unknown";
}
export function reloadHint() { return t("err_stale_cache", { keys: reloadKeys() }); }

export function errorMessage(err) {
  if (!(err instanceof LoadError)) return String(err && err.message || err);
  const hint = isStaleCacheError(err) ? " " + reloadHint() : "";
  if (err.kind.startsWith("http_"))
    return t("err_http", { code: err.kind.slice(5) }) + " — " + err.detail + hint;
  switch (err.kind) {
    case "file": return t("err_file") + hint;
    case "network": return t("err_network") + " — " + err.detail + hint;
    case "schema": return t("err_schema") + " — " + err.detail + hint;
    case "version": return t("err_hash") + " — " + err.detail + hint;
    case "parse": return t("err_parse") + " — " + err.detail + hint;
    case "family_unknown": return t("err_family") + " — " + err.detail;
    default: return t("err_family") + " — " + err.detail + hint;
  }
}
