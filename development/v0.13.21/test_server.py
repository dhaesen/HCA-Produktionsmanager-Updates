from __future__ import annotations
import ast
from pathlib import Path
from patch_server import DEFAULT_SOURCE,patch_text

SOURCE=DEFAULT_SOURCE
patched=patch_text(SOURCE.read_text(encoding="utf-8"))
tree=ast.parse(patched)
names={"_as_data","_meta_dict","_hca138_product_visuals"}
nodes=[node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names]
module=ast.Module(body=nodes,type_ignores=[])
namespace={"Any":object,"json":__import__("json")}
exec(compile(module,str(SOURCE),"exec"),namespace)

product={
    "images":[{"id":11,"src":"https://shop/main.jpg"},{"id":22,"src":"https://shop/red.jpg"},{"id":33,"src":"https://shop/blue.jpg"}],
    "meta_data":[{"key":"werbeartikel_colors","value":[{"name":"Rot","image_id":22},{"name":"Blau","image_id":"33"}]}],
}
result=namespace["_hca138_product_visuals"](product)
assert result["main_image"]=="https://shop/main.jpg"
assert result["color_images"]==[
    {"name":"Rot","image":"https://shop/red.jpg","image_id":"22","erp_code":"","hex":""},
    {"name":"Blau","image":"https://shop/blue.jpg","image_id":"33","erp_code":"","hex":""},
]
assert 'data["product_details"] = details' in patched
assert 'data["product_details_warning"]' in patched
print("v0.13.21 server visual regression test passed")
