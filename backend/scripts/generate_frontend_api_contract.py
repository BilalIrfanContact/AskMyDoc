from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.main import app

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "api-contract.ts"

CORE_OPERATIONS = [
    ("UploadPdfRequestBody", "/upload", "post", "request"),
    ("UploadPdfResponse", "/upload", "post", "response"),
    ("UploadPdfErrorResponse", "/upload", "post", "error"),
    ("ChatRequestBody", "/chat", "post", "request"),
    ("ChatResponseBody", "/chat", "post", "response"),
    ("CreateConversationRequestBody", "/conversations", "post", "request"),
    ("CreateConversationResponseBody", "/conversations", "post", "response"),
    ("GetUserConversationsResponseBody", "/conversations", "get", "response"),
    (
        "GetConversationMessagesResponseBody",
        "/conversations/{conversation_id}/messages",
        "get",
        "response",
    ),
    ("GetUserDocumentsResponseBody", "/documents", "get", "response"),
    ("DeleteUserDocumentResponseBody", "/documents/{document_id}", "delete", "response"),
    ("DeleteUserDocumentErrorResponse", "/documents/{document_id}", "delete", "error"),
]


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _quote(value: str) -> str:
    return json.dumps(value)


def _extract_json_schema(content: dict[str, Any]) -> dict[str, Any] | None:
    for media_type in ("application/json", "multipart/form-data"):
        media = content.get(media_type)
        if media and "schema" in media:
            return media["schema"]
    return None


def _operation_request_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    request_body = operation.get("requestBody")
    if not request_body:
        return None
    return _extract_json_schema(request_body.get("content", {}))


def _operation_success_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    for status_code in ("200", "201"):
        response = operation.get("responses", {}).get(status_code)
        if response:
            schema = _extract_json_schema(response.get("content", {}))
            if schema:
                return schema
    return None


def _operation_error_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    schemas: list[dict[str, Any]] = []
    for status_code, response in operation.get("responses", {}).items():
        if status_code.startswith("2"):
            continue
        schema = _extract_json_schema(response.get("content", {}))
        if schema:
            schemas.append(schema)

    if not schemas:
        return None

    unique_schemas: list[dict[str, Any]] = []
    seen = set()
    for schema in schemas:
        key = json.dumps(schema, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique_schemas.append(schema)

    if len(unique_schemas) == 1:
        return unique_schemas[0]

    return {"anyOf": unique_schemas}


def _render_type(schema: dict[str, Any]) -> str:
    ref = schema.get("$ref")
    if ref:
        return _ref_name(ref)

    if "const" in schema:
        return _quote(schema["const"])

    any_of = schema.get("anyOf")
    if any_of:
        return " | ".join(_render_type(option) for option in any_of)

    one_of = schema.get("oneOf")
    if one_of:
        return " | ".join(_render_type(option) for option in one_of)

    all_of = schema.get("allOf")
    if all_of:
        return " & ".join(_render_type(option) for option in all_of)

    enum_values = schema.get("enum")
    if enum_values:
        return " | ".join(_quote(value) for value in enum_values)

    schema_type = schema.get("type")

    if isinstance(schema_type, list):
        return " | ".join(_render_type({"type": item}) for item in schema_type)

    if schema_type == "array":
        items = schema.get("items", {})
        item_type = _render_type(items)
        if " | " in item_type or " & " in item_type:
            item_type = f"({item_type})"
        return f"{item_type}[]"

    if schema_type == "object" or "properties" in schema or "additionalProperties" in schema:
        properties = schema.get("properties")
        if properties:
            return _render_object(properties, schema.get("required", []))

        additional_properties = schema.get("additionalProperties")
        if isinstance(additional_properties, dict):
            return f"Record<string, {_render_type(additional_properties)}>"

        return "Record<string, unknown>"

    if schema_type == "string":
        if schema.get("format") == "binary":
            return "Blob"
        return "string"

    if schema_type in {"integer", "number"}:
        return "number"

    if schema_type == "boolean":
        return "boolean"

    if schema_type == "null":
        return "null"

    return "unknown"


def _render_object(properties: dict[str, Any], required: list[str]) -> str:
    required_fields = set(required)
    lines = ["{"]
    for name in sorted(properties):
        field_schema = properties[name]
        optional = "?" if name not in required_fields else ""
        lines.append(f"  {_quote(name)}{optional}: {_render_type(field_schema)};")
    lines.append("}")
    return "\n".join(lines)


def _render_schema_declarations(openapi_schema: dict[str, Any]) -> str:
    component_schemas = openapi_schema.get("components", {}).get("schemas", {})
    declarations: list[str] = []

    for name in sorted(component_schemas):
        schema = component_schemas[name]
        schema_type = schema.get("type")
        if schema_type == "object" or "properties" in schema:
            declarations.append(f"export interface {name} {_render_object(schema.get('properties', {}), schema.get('required', []))}")
        else:
            declarations.append(f"export type {name} = {_render_type(schema)};")

    return "\n\n".join(declarations)


def _operation_alias_source(openapi_schema: dict[str, Any], path: str, method: str, kind: str) -> str:
    operation = openapi_schema["paths"][path][method]

    if kind == "request":
        schema = _operation_request_schema(operation)
    elif kind == "response":
        schema = _operation_success_schema(operation)
    elif kind == "error":
        schema = _operation_error_schema(operation)
    else:
        raise ValueError(f"Unknown alias kind: {kind}")

    if schema is None:
        return "never"

    return _render_type(schema)


def render_frontend_contract() -> str:
    openapi_schema = app.openapi()
    header = "// Generated from backend FastAPI OpenAPI schema. Do not edit by hand."
    schema_declarations = _render_schema_declarations(openapi_schema)

    alias_lines = []
    for alias_name, path, method, kind in CORE_OPERATIONS:
        alias_lines.append(
            f"export type {alias_name} = {_operation_alias_source(openapi_schema, path, method, kind)};"
        )

    return "\n\n".join([header, schema_declarations, "\n".join(alias_lines)]) + "\n"


def write_frontend_contract() -> Path:
    contract = render_frontend_contract()
    OUTPUT_PATH.write_text(contract, encoding="utf-8")
    return OUTPUT_PATH


if __name__ == "__main__":
    output_path = write_frontend_contract()
    print(output_path)
