// CSV export with an explicit metadata header. Column order is deterministic.
export function toCSV(columns, rows, meta) {
  const esc = v => {
    if (v === null || v === undefined) return "";
    const s = Array.isArray(v) ? v.join(";") : String(v);
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const out = [];
  if (meta) for (const k of Object.keys(meta)) out.push("# " + k + ": " + esc(meta[k]));
  out.push(columns.map(c => esc(c.label || c.key)).join(","));
  for (const r of rows) out.push(columns.map(c => esc(typeof c.get === "function" ? c.get(r) : r[c.key])).join(","));
  return out.join("\n") + "\n";
}
export function download(name, text) {
  const b = new Blob([text], { type: "text/csv;charset=utf-8" });
  const u = URL.createObjectURL(b);
  const a = document.createElement("a");
  a.href = u; a.download = name; document.body.appendChild(a); a.click();
  setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(u); }, 0);
}
