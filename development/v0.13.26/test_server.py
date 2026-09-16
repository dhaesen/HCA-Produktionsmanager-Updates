#!/usr/bin/env python3
from __future__ import annotations

import ast
import tempfile
import zipfile
from pathlib import Path

from patch_server import patch

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT.parent / "build" / "HCA_NAS_Erweiterung_v0.13.24.published.zip"


def function_module(source: str, names: set[str]):
    tree = ast.parse(source)
    body = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    module = ast.Module(body=body, type_ignores=[])
    env = {"Any": object}
    exec(compile(module, "<hca1326-test>", "exec"), env)
    return env


with zipfile.ZipFile(BASE) as package:
    original = package.read("app/hca_shared.py").decode("utf-8")
patched = patch(original)
compile(patched, "hca_shared.py", "exec")
assert patched.count("details=_hca1326_datasheet_details(item,cfg)") == 1
assert patched.count("image=_hca1326_datasheet_image(source)") == 1

env = function_module(patched, {"_hca1326_image_candidates", "_hca1326_datasheet_details"})
env["_hca138_image_url"] = lambda value: str(value.get("image") or value.get("src") or "") if isinstance(value, dict) else str(value or "")
env["urllib"] = __import__("urllib")
import urllib.parse
env["urllib"].parse = urllib.parse

candidates = env["_hca1326_image_candidates"]("https://shop.test/uploads/jacke.jpg.webp?x=1")
assert candidates[0].endswith("jacke.jpg.webp?x=1")
assert any(value.endswith("jacke.jpg?x=1") for value in candidates)

env.update({
    "_safe_int": lambda value, default=0: int(value or default),
    "_meta_dict": lambda product: {"manufacturer": "Marke A", "supplier": "Lieferant X"},
    "_product_manufacturer": lambda meta, product: "Marke A",
    "_slug_text": lambda value: str(value or "").lower(),
    "_woo_attr_values": lambda attrs: {str(row.get("name") or "").lower(): str(row.get("option") or "") for row in attrs},
    "_hca137_product_details": lambda product: {"main_image": "main.jpg", "gallery_images": [], "color_images": []},
    "_woo_json": lambda path: {"id": 42, "type": "variable", "name": "Jacke", "sku": "J-1", "meta_data": [], "weight": "1", "dimensions": {}},
    "_woo_product_variations": lambda product_id: [
        {"attributes": [{"name": "color", "option": "Rot"}], "image": {"id": 7, "src": "red.jpg"}},
        {"attributes": [{"name": "color", "option": "Rot"}], "image": {"id": 7, "src": "red.jpg"}},
        {"attributes": [{"name": "color", "option": "Blau"}], "image": {"id": 8, "src": "blue.webp"}},
    ],
})
details = env["_hca1326_datasheet_details"]({"product_id": 42}, {"main_product_id": 42, "product_details": {"supplier": "Nicht zeigen"}})
assert [(row["name"], row["image"]) for row in details["color_images"]] == [("Rot", "red.jpg"), ("Blau", "blue.webp")]
assert details["manufacturer"] == "Marke A"
assert "supplier" not in details and "lieferant" not in details
print("v0.13.26 server tests: OK")
