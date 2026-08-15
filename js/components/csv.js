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
export function downloadBlob(name, blob) {
  const u = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = u; a.download = name; document.body.appendChild(a); a.click();
  setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(u); }, 0);
}
/* Written with a byte-order mark. The tables carry Greek letters in receptor names — beta-2,
   kappa, mu — and Turkish characters in the headings when the interface is in Turkish. Without the
   mark Excel on Windows reads a UTF-8 file as ANSI and turns every one of them into mojibake,
   which is the state a reader would then try to clean up by hand. The cost is that a naive
   pandas.read_csv keeps the mark on the first heading unless it is told encoding="utf-8-sig";
   that is one argument against a whole file of corrupted names. */
export function download(name, text) {
  downloadBlob(name, new Blob(["\ufeff", text], { type: "text/csv;charset=utf-8" }));
}
