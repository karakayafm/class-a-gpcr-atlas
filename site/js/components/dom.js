// Tiny DOM helpers. No framework.
export function el(tag, attrs, children) {
  const n = document.createElement(tag);
  if (attrs) for (const k of Object.keys(attrs)) {
    const v = attrs[k];
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k === "html") n.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : String(v));
  }
  if (children) for (const c of [].concat(children)) {
    if (c === null || c === undefined || c === false) continue;
    n.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return n;
}
export function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
export function fmt(x, digits) {
  if (x === null || x === undefined) return "—";
  if (typeof x !== "number") return String(x);
  return x.toFixed(digits === undefined ? 3 : digits);
}
export function pct(x) { return x === null || x === undefined ? "—" : (x * 100).toFixed(1) + "%"; }
// Large tables are rendered in pages; the DOM never receives the whole dataset at once.
export function paginate(rows, page, size) {
  const total = rows.length, pages = Math.max(1, Math.ceil(total / size));
  const p = Math.min(Math.max(0, page), pages - 1);
  return { rows: rows.slice(p * size, (p + 1) * size), page: p, pages, total };
}
export function debounce(fn, ms) {
  let h = null;
  return function () { const a = arguments, c = this;
    clearTimeout(h); h = setTimeout(() => fn.apply(c, a), ms || 180); };
}
