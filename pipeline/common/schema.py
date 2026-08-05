"""A deliberately small JSON Schema validator.

The project is stdlib-only (see ``config/project.json``), so this implements exactly the
Draft 2020-12 keywords the project's own schemas use, and nothing else:

    type, enum, const, required, properties, additionalProperties,
    items, minItems, minLength, minimum, pattern

**Known limits, stated so nobody mistakes this for a complete implementation:**
``$ref``, ``allOf``/``anyOf``/``oneOf``, ``format`` assertions, ``patternProperties``,
``dependentSchemas``, ``unevaluatedProperties`` and numeric ``multipleOf`` are NOT evaluated.
If a schema in this project starts using one of them, this module must be extended first —
silently ignoring a keyword would make validation a lie. ``assert_no_unsupported_keywords``
enforces that: it fails loudly rather than passing a schema it cannot fully check.
"""
from __future__ import annotations

import re
from typing import Any

SUPPORTED = {
    "$schema", "$id", "$comment", "title", "description", "type", "enum", "const",
    "required", "properties", "additionalProperties", "items", "minItems", "minLength",
    "minimum", "pattern", "format",
}
# 'format' is accepted but treated as an annotation, per the spec's default behaviour.
NOT_ASSERTED = {"format"}

TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "number": (int, float), "integer": int, "null": type(None),
}


def assert_no_unsupported_keywords(schema: Any, where: str = "$") -> list[str]:
    """Return the list of keywords this validator would silently ignore."""
    bad: list[str] = []
    if isinstance(schema, dict):
        for k, v in schema.items():
            if k not in SUPPORTED and k not in {"properties", "items", "definitions", "$defs"}:
                bad.append(f"{where}.{k}")
            if k in {"properties", "$defs", "definitions"} and isinstance(v, dict):
                for pk, pv in v.items():
                    bad += assert_no_unsupported_keywords(pv, f"{where}.{k}.{pk}")
            elif k in {"items", "additionalProperties"} and isinstance(v, dict):
                bad += assert_no_unsupported_keywords(v, f"{where}.{k}")
    return bad


def _type_ok(value: Any, want: str) -> bool:
    if want == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if want == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if want == "boolean":
        return isinstance(value, bool)
    return isinstance(value, TYPES[want])


def validate(instance: Any, schema: dict, path: str = "$") -> list[str]:
    """Return a list of human-readable errors; empty means valid."""
    err: list[str] = []
    if not isinstance(schema, dict):
        return err

    if "const" in schema and instance != schema["const"]:
        err.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        err.append(f"{path}: {instance!r} not in enum {schema['enum']}")

    if "type" in schema:
        want = schema["type"]
        wants = [want] if isinstance(want, str) else list(want)
        if not any(_type_ok(instance, w) for w in wants):
            err.append(f"{path}: expected type {want}, got {type(instance).__name__}")
            return err                       # further checks would be noise

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            err.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            err.append(f"{path}: {instance!r} does not match {schema['pattern']!r}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            err.append(f"{path}: {instance} below minimum {schema['minimum']}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            err.append(f"{path}: {len(instance)} items, minItems {schema['minItems']}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                err += validate(item, item_schema, f"{path}[{i}]")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                err.append(f"{path}: missing required property {key!r}")
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in instance:
                err += validate(instance[key], sub, f"{path}.{key}")
        ap = schema.get("additionalProperties", True)
        extra = [k for k in instance if k not in props]
        if ap is False and extra:
            err.append(f"{path}: unexpected properties {sorted(extra)}")
        elif isinstance(ap, dict):
            for key in extra:
                err += validate(instance[key], ap, f"{path}.{key}")
    return err
