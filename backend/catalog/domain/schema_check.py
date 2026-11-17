"""Check a draft against the shipped JSON Schema. No third-party package.

The keyword set is the one used by backend/catalog/contracts. A keyword outside
that set is reported, so a schema edit cannot silently skip a rule.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_IGNORED = {"$schema", "$id", "$defs", "title", "description", "version"}
_IMPLEMENTED = _IGNORED | {
    "$ref",
    "type",
    "const",
    "enum",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "minItems",
    "maxItems",
    "minimum",
    "minLength",
    "pattern",
    "allOf",
    "oneOf",
    "if",
    "then",
    "else",
}
_CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
QUESTION_SCHEMA_ID = (
    "https://github.com/wisdom-km/k12-qbank/contracts/k12-question-draft.v1.schema.json"
)
ANSWER_SCHEMA_ID = (
    "https://github.com/wisdom-km/k12-qbank/contracts/k12-answer-draft.v1.schema.json"
)
_VERSIONS = {
    (QUESTION_SCHEMA_ID, 1): "k12-question-draft.v1.schema.json",
    (ANSWER_SCHEMA_ID, 1): "k12-answer-draft.v1.schema.json",
}


def schema_problems(schema: dict, instance: object) -> list[str]:
    """Return human-readable shape errors. An empty list means the shape matches."""
    return _check(schema, instance, "$", schema)


def unknown_schema_keywords(schema: object) -> list[str]:
    """Keywords this checker would not apply. Property names under properties are data."""
    found: list[str] = []

    def walk(node: object) -> None:
        if not isinstance(node, dict):
            return
        for key, value in node.items():
            if key not in _IMPLEMENTED:
                found.append(key)
                continue
            if key == "properties" and isinstance(value, dict):
                for child in value.values():
                    walk(child)
            elif key == "$defs" and isinstance(value, dict):
                for child in value.values():
                    walk(child)
            elif key in {"items", "if", "then", "else"} and isinstance(value, dict):
                walk(value)
            elif key == "additionalProperties" and isinstance(value, dict):
                walk(value)
            elif key in {"allOf", "oneOf"} and isinstance(value, list):
                for child in value:
                    walk(child)

    walk(schema)
    return found


@lru_cache(maxsize=4)
def load_contract_schema(file_name: str) -> dict:
    """Read one schema shipped in backend/catalog/contracts. This is not a user file."""
    return json.loads((_CONTRACTS / file_name).read_text(encoding="utf-8"))


def dispatched_schema(schema_id: str, payload: object) -> dict | str:
    """Pick a shipped schema by its $id and the draft's schema_version.

    A string result is a not_draft message and names the version that arrived.
    A value that is not an object keeps version 1, so the shape check can name
    the type. A page block list still fails as a shape error.
    """
    if not isinstance(payload, dict):
        fallback = _VERSIONS.get((schema_id, 1))
        if fallback is None:
            return "收到的版本是（没有 schema_version）。"
        return load_contract_schema(fallback)
    if "schema_version" not in payload:
        return "收到的版本是（没有 schema_version）。"
    received = payload["schema_version"]
    if type(received) is not int:
        return f"收到的版本是 {received}。"
    file_name = _VERSIONS.get((schema_id, received))
    if file_name is None:
        return f"收到的版本是 {received}。"
    schema = load_contract_schema(file_name)
    if schema.get("$id") != schema_id or schema.get("version") != received:
        return f"收到的版本是 {received}。"
    return schema


def _check(schema: dict, instance: object, path: str, root: dict) -> list[str]:
    unknown = [key for key in schema if key not in _IMPLEMENTED]
    if unknown:
        return [f"{path}：契约用了未实现的关键字 {unknown[0]}"]
    if "$ref" in schema:
        return _ref(schema["$ref"], instance, path, root)
    if "type" in schema and not _type_ok(schema["type"], instance):
        if isinstance(instance, bool) and _expects_number(schema["type"]):
            return [f"{path}：布尔值不能当作数字"]
        return [f"{path}：类型应为 {_type_label(schema['type'])}"]
    if "const" in schema and not _same(schema["const"], instance):
        return [f"{path}：必须是 {_literal(schema['const'])}"]
    if "enum" in schema and not any(_same(item, instance) for item in schema["enum"]):
        return [f"{path}：不在允许的取值里"]
    errors: list[str] = []
    if "minimum" in schema and isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if instance < schema["minimum"]:
            errors.append(f"{path}：必须大于或等于 {schema['minimum']}")
    if "minLength" in schema and isinstance(instance, str) and len(instance) < schema["minLength"]:
        errors.append(f"{path}：太短")
    if "pattern" in schema and isinstance(instance, str) and re.search(schema["pattern"], instance) is None:
        errors.append(f"{path}：格式不符合")
    errors.extend(_object(schema, instance, path, root))
    errors.extend(_array(schema, instance, path, root))
    for sub in schema.get("allOf", []):
        errors.extend(_check(sub, instance, path, root))
    if "oneOf" in schema:
        errors.extend(_one_of(schema["oneOf"], instance, path, root))
    if "if" in schema:
        matched = not _check(schema["if"], instance, path, root)
        if matched and "then" in schema:
            errors.extend(_check(schema["then"], instance, path, root))
        if not matched and "else" in schema:
            errors.extend(_check(schema["else"], instance, path, root))
    return errors


def _ref(ref: object, instance: object, path: str, root: dict) -> list[str]:
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        return [f"{path}：契约内部引用无法解析"]
    name = ref.removeprefix("#/$defs/")
    target = root.get("$defs", {}).get(name)
    if not isinstance(target, dict):
        return [f"{path}：契约内部引用无法解析"]
    return _check(target, instance, path, root)


def _object(schema: dict, instance: object, path: str, root: dict) -> list[str]:
    if not any(key in schema for key in ("properties", "required", "additionalProperties")):
        return []
    if not isinstance(instance, dict):
        return []
    errors: list[str] = []
    properties = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in instance:
            errors.append(f"{path}.{name}：缺少")
    additional = schema.get("additionalProperties", True)
    for name, value in instance.items():
        child = f"{path}.{name}"
        if name in properties:
            errors.extend(_check(properties[name], value, child, root))
        elif additional is False:
            errors.append(f"{child}：不允许的字段")
        elif isinstance(additional, dict):
            errors.extend(_check(additional, value, child, root))
    return errors


def _array(schema: dict, instance: object, path: str, root: dict) -> list[str]:
    if not any(key in schema for key in ("items", "minItems", "maxItems")):
        return []
    if not isinstance(instance, list):
        return []
    errors: list[str] = []
    if "minItems" in schema and len(instance) < schema["minItems"]:
        errors.append(f"{path}：至少要有 {schema['minItems']} 项")
    if "maxItems" in schema and len(instance) > schema["maxItems"]:
        errors.append(f"{path}：最多只能有 {schema['maxItems']} 项")
    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(instance):
            errors.extend(_check(item_schema, item, f"{path}[{index}]", root))
    return errors


def _one_of(options: list, instance: object, path: str, root: dict) -> list[str]:
    matched = 0
    notes: list[str] = []
    for option in options:
        if not _check(option, instance, path, root):
            matched += 1
        elif isinstance(option, dict) and isinstance(option.get("description"), str):
            notes.append(option["description"])
    if matched == 1:
        return []
    detail = "；".join(notes) if notes else "没有匹配的形状"
    return [f"{path}：必须恰有一种形状（{detail}）"]


def _type_ok(expected: object, instance: object) -> bool:
    names = expected if isinstance(expected, list) else [expected]
    return any(_one_type(name, instance) for name in names)


def _one_type(name: object, instance: object) -> bool:
    if name == "object":
        return isinstance(instance, dict)
    if name == "array":
        return isinstance(instance, list)
    if name == "string":
        return isinstance(instance, str)
    if name == "boolean":
        return isinstance(instance, bool)
    if name == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if name == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if name == "null":
        return instance is None
    return False


def _expects_number(expected: object) -> bool:
    names = expected if isinstance(expected, list) else [expected]
    return any(name in {"integer", "number"} for name in names)


def _same(left: object, right: object) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    return left == right


def _type_label(expected: object) -> str:
    if isinstance(expected, list):
        return " 或 ".join(str(item) for item in expected)
    return str(expected)


def _literal(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)
