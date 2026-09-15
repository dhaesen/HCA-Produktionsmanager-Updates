#!/usr/bin/env python3
from pathlib import Path
import ast
import json
import re


server = Path(__file__).with_name("hca_shared.py").read_text(encoding="utf-8")
tree = ast.parse(server)
names = {
    "_shop_int",
    "_shop_truthy",
    "_shop_text_key",
    "_shop_configuration_from_hca",
    "_shop_canonical_configuration",
    "_shop_validate_price_result",
}
nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
module = ast.Module(body=nodes, type_ignores=[])
namespace = {"Any": object, "re": re, "json": json, "_woo_form_post": lambda *_args, **_kwargs: None}
exec(compile(ast.fix_missing_locations(module), "pricing-functions", "exec"), namespace)

raw = {
    "config": {
        "color": "Grün",
        "production_steps": [{
            "manual_override": "false",
            "area_id": "front",
            "area_index": 0,
            "position": "Front 35x6mm",
            "druckart_id": "15",
            "cost_id": "0",
            "bearbeitung_cost_id": "0",
            "colors_count": "1",
        }],
    }
}
configuration = namespace["_shop_configuration_from_hca"](raw)
assert len(configuration["positions"]) == 1, 'Textwert "false" darf die Veredelung nicht entfernen'

wizard = {
    "areas": [{
        "id": "front",
        "index": 0,
        "name": "Front 35x6mm",
        "assignments": [{
            "druckart_id": 15,
            "cost_id": 47,
            "bearbeitung_cost_id": 4,
            "method": {"name": "Lasergravur", "code": "LASER"},
        }],
    }]
}
resolved = namespace["_shop_canonical_configuration"](5266, configuration, wizard)
position = resolved["positions"][0]
assert (position["druckartId"], position["costId"], position["bearbeitungCostId"]) == (15, 47, 4)

valid = {"positions": [{"print_per_item": "0.16", "setup_total": "13.87", "bearbeitung_unit": "0.04"}]}
namespace["_shop_validate_price_result"](resolved, valid)

try:
    namespace["_shop_validate_price_result"](resolved, {"positions": [{"print_per_item": "0", "setup_total": "0", "bearbeitung_unit": "0"}]})
except RuntimeError as error:
    assert "Druckart 15" in str(error) and "Einrichtung 47" in str(error) and "Bearbeitung 4" in str(error)
else:
    raise AssertionError("Nullpreise dürfen nicht als erfolgreiche Kalkulation gelten")

print("v0.13.17 NAS pricing tests passed")
