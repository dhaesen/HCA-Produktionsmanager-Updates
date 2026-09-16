#!/usr/bin/env python3
from __future__ import annotations
import ast,base64,hashlib,tempfile,zipfile
from pathlib import Path
from patch_server import patch

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT.parent/'build'/'HCA_NAS_Erweiterung_v0.13.26.zip'
with zipfile.ZipFile(BASE) as package:source=patch(package.read('app/hca_shared.py').decode('utf-8'))
compile(source,'hca_shared.py','exec')
assert 'timeout=3' in source
assert '_woo_product_variations(product_id)' not in source[source.index('def _hca1327_datasheet_details'):source.index('def _hca1310_datasheet_specs')]
assert 'details=_hca1327_datasheet_details(item,cfg)' in source
assert 'image=_hca1327_datasheet_image(source)' in source
assert '@router.get("/media/image-proxy"' in source and '@router.post("/media/image-cache"' in source
assert 'if cached and cached.is_file()' in source

tree=ast.parse(source);wanted={'_hca1327_jpeg_image','_hca1327_cache_file','_hca1327_datasheet_image','_hca1327_datasheet_details'}
module=ast.Module(body=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in wanted],type_ignores=[])
with tempfile.TemporaryDirectory() as tmp:
    env={'Any':object,'Path':Path,'DATA_DIR':Path(tmp),'hashlib':hashlib,'base64':base64,'_hca138_image_url':lambda value:str(value or ''),'_hca137_jpeg_info':lambda raw:(20,10,3) if raw.startswith(b'JPEG') else None,'_hca137_image':lambda url:None}
    exec(compile(module,'<test>','exec'),env)
    details=env['_hca1327_datasheet_details']({}, {'product_details':{'name':'Jacke','supplier':'Falk & Ross','color_images':[{'name':'Rot','image':'red.webp'}]}})
    assert details['name']=='Jacke' and details['color_images'][0]['name']=='Rot' and 'supplier' not in details
    raw=b'JPEG-test';data='data:image/jpeg;base64,'+base64.b64encode(raw).decode()
    assert env['_hca1327_datasheet_image'](data)['width']==20
print('v0.13.27 server tests: OK')
