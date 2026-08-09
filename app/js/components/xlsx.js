// Minimal XLSX writer. The atlas ships offline with no CDN and no bundler, so a spreadsheet
// library is not available — but an .xlsx is just a ZIP of XML parts, and a ZIP written with
// the "store" method needs no compressor. Only what Excel/LibreOffice require to open a sheet
// is emitted: inline strings, numbers, and one worksheet per table.

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    table[i] = c >>> 0;
  }
  return table;
})();

function crc32(bytes) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}

const utf8 = new TextEncoder();

function xmlEscape(value) {
  return String(value)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&apos;")
    // Excel rejects most control characters outright.
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, "");
}

/* A1-style reference: column 1 -> A, 27 -> AA. */
function cellRef(col, row) {
  let name = "";
  for (let n = col; n > 0; n = Math.floor((n - 1) / 26)) {
    name = String.fromCharCode(65 + ((n - 1) % 26)) + name;
  }
  return name + row;
}

function isNumeric(value) {
  return typeof value === "number" && isFinite(value);
}

function sheetXml(columns, rows) {
  const parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'];
  const emit = (values, rowIndex) => {
    parts.push('<row r="' + rowIndex + '">');
    values.forEach((value, i) => {
      if (value === null || value === undefined || value === "") return;
      const ref = cellRef(i + 1, rowIndex);
      if (isNumeric(value)) parts.push('<c r="' + ref + '"><v>' + value + '</v></c>');
      else parts.push('<c r="' + ref + '" t="inlineStr"><is><t xml:space="preserve">' +
        xmlEscape(Array.isArray(value) ? value.join("; ") : value) + '</t></is></c>');
    });
    parts.push("</row>");
  };
  emit(columns.map(c => c.label || c.key), 1);
  rows.forEach((row, i) => emit(columns.map(c =>
    typeof c.get === "function" ? c.get(row) : row[c.key]), i + 2));
  parts.push("</sheetData></worksheet>");
  return parts.join("");
}

/* Excel forbids : \ / ? * [ ] in sheet names and caps them at 31 characters. */
function safeSheetName(name, index) {
  const cleaned = String(name || ("Sheet" + (index + 1))).replace(/[:\\/?*\[\]]/g, "-").slice(0, 31);
  return cleaned || ("Sheet" + (index + 1));
}

function zip(files) {
  const encoder = [], central = [];
  let offset = 0;
  const u16 = v => [v & 0xFF, (v >>> 8) & 0xFF];
  const u32 = v => [v & 0xFF, (v >>> 8) & 0xFF, (v >>> 16) & 0xFF, (v >>> 24) & 0xFF];
  for (const file of files) {
    const nameBytes = utf8.encode(file.name);
    const body = utf8.encode(file.data);
    const sum = crc32(body);
    // Flag bit 11 marks the name as UTF-8. Timestamps are fixed so output is byte-reproducible.
    const header = [...u32(0x04034b50), ...u16(20), ...u16(0x0800), ...u16(0), ...u16(0), ...u16(0),
      ...u32(sum), ...u32(body.length), ...u32(body.length), ...u16(nameBytes.length), ...u16(0)];
    encoder.push(new Uint8Array(header), nameBytes, body);
    central.push({ name: nameBytes, crc: sum, size: body.length, offset });
    offset += header.length + nameBytes.length + body.length;
  }
  const dir = [];
  for (const entry of central) {
    dir.push(new Uint8Array([...u32(0x02014b50), ...u16(20), ...u16(20), ...u16(0x0800), ...u16(0),
      ...u16(0), ...u16(0), ...u32(entry.crc), ...u32(entry.size), ...u32(entry.size),
      ...u16(entry.name.length), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(0),
      ...u32(entry.offset)]), entry.name);
  }
  const dirSize = dir.reduce((n, part) => n + part.length, 0);
  const end = new Uint8Array([...u32(0x06054b50), ...u16(0), ...u16(0),
    ...u16(central.length), ...u16(central.length), ...u32(dirSize), ...u32(offset), ...u16(0)]);
  return new Blob([...encoder, ...dir, end], { type:
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

/* sheets: [{ name, columns, rows }] — columns use the same {key,label,get} shape as toCSV. */
export function toXLSX(sheets) {
  const named = sheets.map((sheet, i) => ({ ...sheet, name: safeSheetName(sheet.name, i) }));
  const files = [
    { name: "[Content_Types].xml", data: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
      '<Default Extension="xml" ContentType="application/xml"/>' +
      '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
      named.map((s, i) => '<Override PartName="/xl/worksheets/sheet' + (i + 1) +
        '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>').join("") +
      '</Types>' },
    { name: "_rels/.rels", data: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>' +
      '</Relationships>' },
    { name: "xl/workbook.xml", data: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ' +
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' +
      named.map((s, i) => '<sheet name="' + xmlEscape(s.name) + '" sheetId="' + (i + 1) +
        '" r:id="rId' + (i + 1) + '"/>').join("") + '</sheets></workbook>' },
    { name: "xl/_rels/workbook.xml.rels", data: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      named.map((s, i) => '<Relationship Id="rId' + (i + 1) +
        '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet' +
        (i + 1) + '.xml"/>').join("") + '</Relationships>' }
  ];
  named.forEach((sheet, i) => files.push({ name: "xl/worksheets/sheet" + (i + 1) + ".xml",
    data: sheetXml(sheet.columns, sheet.rows) }));
  return zip(files);
}

export function downloadXLSX(name, sheets) {
  const url = URL.createObjectURL(toXLSX(sheets));
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click();
  setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 0);
}
