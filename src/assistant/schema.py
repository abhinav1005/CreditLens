"""Inline `$ref`/`$defs` in a Pydantic JSON Schema.

Schemas we send to a model API (tool inputs, structured output) are flattened so they
don't depend on the provider supporting references. Our models have no recursive types.
"""

import copy


def inline_refs(schema: dict) -> dict:
    defs = schema.get("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                merged = {
                    **resolve(copy.deepcopy(defs[name])),
                    **{k: v for k, v in node.items() if k != "$ref"},
                }
                return merged
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(v) for v in node]
        return node

    return resolve(schema)
