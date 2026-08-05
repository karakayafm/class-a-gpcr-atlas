"""Minimal mmCIF reader for the categories Phase 3 actually needs.

Handles the two shapes that matter: `loop_` tables and single-value items, with quoting
(single, double and semicolon-delimited text fields). It is not a general CIF parser and does
not pretend to be — it reads `_atom_site`, `_pdbx_poly_seq_scheme`, `_struct_conn`,
`_pdbx_struct_assembly*`, `_exptl` and `_entity_poly`, and ignores everything else.
"""
from __future__ import annotations

import gzip
from pathlib import Path

PARSER_VERSION = "mmcif-reader-1.0.0"


def _split(line: str) -> list[str]:
    out, i, n = [], 0, len(line)
    while i < n:
        while i < n and line[i] in " \t":
            i += 1
        if i >= n:
            break
        q = line[i]
        if q in "'\"":
            i += 1
            start = i
            while i < n:
                if line[i] == q and (i + 1 >= n or line[i + 1] in " \t"):
                    break
                i += 1
            out.append(line[start:i])
            i += 1
        else:
            start = i
            while i < n and line[i] not in " \t":
                i += 1
            out.append(line[start:i])
    return out


def read(path: Path, wanted: set[str]) -> dict[str, list[dict]]:
    """Return {category: [row dicts]} for the requested categories only."""
    data = gzip.decompress(path.read_bytes()).decode("utf-8", "replace")
    lines = data.splitlines()
    out: dict[str, list[dict]] = {w: [] for w in wanted}
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        if s.startswith("loop_"):
            i += 1
            tags = []
            while i < n and lines[i].strip().startswith("_"):
                tags.append(lines[i].strip().split()[0])
                i += 1
            cat = tags[0].split(".")[0] if tags else ""
            keep = cat in wanted
            names = [t.split(".", 1)[1] for t in tags]
            rows = out[cat] if keep else None
            buf: list[str] = []
            while i < n:
                ln = lines[i]
                t = ln.strip()
                if t.startswith(("loop_", "#", "data_")) or (t.startswith("_") and not buf):
                    break
                if t.startswith(";"):
                    txt = [t[1:]]
                    i += 1
                    while i < n and not lines[i].startswith(";"):
                        txt.append(lines[i])
                        i += 1
                    i += 1
                    buf.append("\n".join(txt))
                else:
                    buf.extend(_split(ln))
                    i += 1
                while len(buf) >= len(names):
                    vals, buf = buf[:len(names)], buf[len(names):]
                    if keep:
                        rows.append(dict(zip(names, vals)))
            continue
        if s.startswith("_"):
            parts = _split(s)
            tag = parts[0]
            cat = tag.split(".")[0]
            if cat in wanted:
                if len(parts) > 1:
                    val = parts[1]
                    i += 1
                else:
                    i += 1
                    if i < n and lines[i].startswith(";"):
                        txt = [lines[i][1:]]
                        i += 1
                        while i < n and not lines[i].startswith(";"):
                            txt.append(lines[i])
                            i += 1
                        i += 1
                        val = "\n".join(txt)
                    else:
                        val = lines[i].strip() if i < n else "?"
                        i += 1
                name = tag.split(".", 1)[1]
                if not out[cat]:
                    out[cat].append({})
                out[cat][0][name] = val
                continue
        i += 1
    return out


HYDROGEN = {"H", "D", "T"}


def atoms(rows: list[dict]) -> list[dict]:
    """Normalised heavy atoms from `_atom_site`, water excluded."""
    out = []
    for r in rows:
        el = (r.get("type_symbol") or "").strip().upper()
        if el in HYDROGEN:
            continue
        comp = (r.get("label_comp_id") or "").strip()
        if comp in ("HOH", "DOD"):
            continue
        try:
            x = float(r["Cartn_x"]); y = float(r["Cartn_y"]); z = float(r["Cartn_z"])
        except (KeyError, ValueError):
            continue
        occ = r.get("occupancy", "1.0")
        try:
            occ = float(occ)
        except ValueError:
            occ = 1.0
        alt = (r.get("label_alt_id") or ".").strip()
        ins = (r.get("pdbx_PDB_ins_code") or "?").strip()
        out.append({
            "group": r.get("group_PDB", "ATOM"),
            "atom_id": (r.get("label_atom_id") or "").strip(),
            "alt": "" if alt in (".", "?") else alt,
            "comp": comp,
            "label_asym": (r.get("label_asym_id") or "").strip(),
            "auth_asym": (r.get("auth_asym_id") or r.get("label_asym_id") or "").strip(),
            "label_seq": (r.get("label_seq_id") or ".").strip(),
            "auth_seq": (r.get("auth_seq_id") or "").strip(),
            "ins": "" if ins in ("?", ".") else ins,
            "entity": (r.get("label_entity_id") or "").strip(),
            "model": int(r.get("pdbx_PDB_model_num", "1") or 1),
            "occ": occ, "el": el, "x": x, "y": y, "z": z,
        })
    return out
