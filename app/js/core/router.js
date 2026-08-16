// Hash-based routing. No backend, no history rewriting beyond the hash.
const listeners = [];
export function parseRoute() {
  const h = (location.hash || "").replace(/^#/, "");
  const out = {};
  for (const part of h.split("&")) {
    if (!part) continue;
    const i = part.indexOf("=");
    if (i < 0) { out[decodeURIComponent(part)] = true; continue; }
    out[decodeURIComponent(part.slice(0, i))] = decodeURIComponent(part.slice(i + 1));
  }
  if (!out.view) out.view = out.family ? "structures" : "landing";
  return out;
}
export function buildHash(state) {
  // `motif` was reserved here long before anything wrote it. The motif query panel now keeps its
  // whole state in the address — the query, the scope it is read over, the selected receptor, the
  // sort and the row count — so those keys are ordered too and a pasted address restores a panel
  // exactly. Ordering is cosmetic: an unlisted key is still emitted, just after these.
  const order = ["family", "view", "pool", "site", "motif", "scope", "class", "minfreq",
                 "hit", "sort", "top", "uniq", "pdb", "observation", "receptor"];
  const parts = [];
  for (const k of order) if (state[k] !== undefined && state[k] !== null && state[k] !== "")
    parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(state[k]));
  for (const k of Object.keys(state)) if (order.indexOf(k) < 0 && state[k] !== undefined &&
    state[k] !== null && state[k] !== "")
    parts.push(encodeURIComponent(k) + "=" + encodeURIComponent(state[k]));
  return "#" + parts.join("&");
}
export function navigate(state, replace) {
  const h = buildHash(state);
  if (location.hash === h) { emit(); return; }
  if (replace) history.replaceState(null, "", h); else location.hash = h;
}
export function onRoute(fn) { listeners.push(fn); }
function emit() { const r = parseRoute(); for (const fn of listeners) fn(r); }
export function startRouter() {
  window.addEventListener("hashchange", emit);
  emit();
}
