"""Minimal JSON-schema validation for model outputs.

Supports exactly the subset the pipeline's schemas use: type
(object/array/string), required, properties, items. Anything else in
a schema is ignored. Raises SchemaError naming the first problem —
callers fail loudly rather than render a malformed artifact.
"""


class SchemaError(Exception):
    pass


def _type_name(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "null"


def validate(obj, schema, path="$"):
    want = schema.get("type")
    if want and _type_name(obj) != want:
        raise SchemaError(f"{path}: expected {want}, got {_type_name(obj)}")
    if want == "object" or (not want and isinstance(obj, dict)):
        for key in schema.get("required", []):
            if not isinstance(obj, dict) or key not in obj:
                raise SchemaError(f"{path}: missing required {key!r}")
        if schema.get("additionalProperties") is False and isinstance(obj, dict):
            allowed = set(schema.get("properties", {}))
            for key in obj:
                if key not in allowed:
                    raise SchemaError(f"{path}: unexpected {key!r}")
        for key, subschema in schema.get("properties", {}).items():
            if isinstance(obj, dict) and key in obj:
                validate(obj[key], subschema, f"{path}.{key}")
    if want == "array" or (not want and isinstance(obj, list)):
        items = schema.get("items")
        if items is not None and isinstance(obj, list):
            for i, item in enumerate(obj):
                validate(item, items, f"{path}[{i}]")
    if schema.get("minLength") and isinstance(obj, str):
        if len(obj.strip()) < schema["minLength"]:
            raise SchemaError(f"{path}: below minLength")
    return True
