"""Residue-copy curation for ligand observations.

A deposition can contain several copies of one chemical component where only some of them are
the ligand under study. `config/curated_ligand_copies.json` names the copies that are, and this
applies that record wherever contacts are read, so the viewer, the pocket detail and the
headline counts cannot disagree about what the ligand is.

The filter only ever withholds rows. It never adds a contact, and an entity with no entry is
returned untouched.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[2] / "config/curated_ligand_copies.json"


@lru_cache(maxsize=1)
def _kept() -> dict[str, set[tuple[str, str]]]:
    if not CONFIG.exists():
        return {}
    record = json.loads(CONFIG.read_text(encoding="utf-8"))
    return {e["ligand_entity_id"]: {(c[0], str(c[1])) for c in e["keep"]}
            for e in record.get("entries", [])}


def curated_entities() -> set[str]:
    """Ligand entity ids the record speaks about."""
    return set(_kept())


def keeps(ligand_entity_id: str, chain, seq) -> bool:
    """Whether this residue copy is part of the curated ligand.

    True for every entity the record does not mention, so callers can apply it unconditionally.
    """
    allowed = _kept().get(ligand_entity_id)
    if allowed is None:
        return True
    return (str(chain), str(seq)) in allowed


def filter_contacts(rows: list[dict]) -> list[dict]:
    """Drop contact rows belonging to withheld copies.

    Expects the residue_pair_contacts fields: `ligand_entity_id`, `ligand_auth_asym_id`,
    `ligand_auth_seq_id`.
    """
    if not _kept():
        return rows
    return [r for r in rows
            if keeps(r.get("ligand_entity_id"), r.get("ligand_auth_asym_id"),
                     r.get("ligand_auth_seq_id"))]


def filter_residues(ligand_entity_id: str, residues) -> list:
    """Drop withheld copies from a [[chain, seq], …] selection list."""
    if not residues or _kept().get(ligand_entity_id) is None:
        return residues
    return [r for r in residues if keeps(ligand_entity_id, r[0], r[1])]
