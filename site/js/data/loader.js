// Lazy payload loader with an LRU cache keyed on schema + data version + payload hash.
// The initial page loads only the global manifest and the landing payload.
import { t } from "../core/i18n.js";

const MAX_FAMILY_ENTRIES = 3;      // explicit eviction: large contact payloads are released
const MAX_BUNDLE_ENTRIES = 4;
const famCache = new Map();
const bundleCache = new Map();
let manifest = null;
let searchIndexPromise = null;
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
  searchIndexPromise = loadManifest().then(async m => {
    const families = m.families || [];
    const payloads = await Promise.all(families.map(async family => ({
      family, data: await loadFamilyFile(family.slug, "structures.json")
    })));
    const rows = payloads.flatMap(({ family, data }) => (data && data.structures || [])
      .filter(x => !x.superseded_by).map(x => ({
      pdb_id:x.pdb_id, family_slug:family.slug, family_name:family.name,
      receptor_name:x.receptor_name, receptor_entry_name:x.receptor_entry_name,
      aliases:x.pdb_id === "8IA7" ? ["7XOX"] : [],
      ligands:Array.from(new Set((x.observations || []).map(o => o.ligand_name).filter(Boolean)))
    })));
  }).catch(e => { searchIndexPromise=null; throw e; });
  return searchIndexPromise;
}

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
export function errorMessage(err) {
  if (!(err instanceof LoadError)) return String(err && err.message || err);
  switch (err.kind) {
    case "file": return t("err_file");
    case "schema": return t("err_schema") + " — " + err.detail;
    case "version": return t("err_hash") + " — " + err.detail;
    case "parse": return t("err_parse") + " — " + err.detail;
    case "family_unknown": return t("err_family") + " — " + err.detail;
    default: return t("err_family") + " — " + err.detail;
  }
}
