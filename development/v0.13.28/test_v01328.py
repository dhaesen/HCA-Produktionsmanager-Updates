#!/usr/bin/env python3
from __future__ import annotations

import ast
import sqlite3
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from patch_server import patch

ROOT=Path(__file__).resolve().parents[2]
NAS=ROOT.parent/'build'/'published-v01327'/'HCA_NAS_Erweiterung_v0.13.27.zip'
CLIENT=ROOT.parent/'build'/'published-v01327'/'HCA_Update_v0.13.27.hcaupdate'

with zipfile.ZipFile(NAS) as package:server=patch(package.read('app/hca_shared.py').decode('utf-8'))
compile(server,'hca_shared.py','exec')
assert 'CREATE TABLE IF NOT EXISTS mobile_pairings' in server
assert 'MOBILE_PAIRINGS.pop(pair_token, None)' not in server
assert "query.get('pair')||hash.get('pair')" in server
assert "function storageGet(key)" in server
assert "$('#saveKey').addEventListener('click',useManualKey)" in server
assert 'id="saveKey" type="button"' in server

tree=ast.parse(server);mobile_html=''
for node in tree.body:
    if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=='MOBILE_HTML' for target in node.targets):
        mobile_html=ast.literal_eval(node.value);break
assert mobile_html
script=mobile_html.rsplit('<script>',1)[1].split('</script>',1)[0]
assert 'localStorage.' not in script
assert "window['localStorage']" in script
with tempfile.NamedTemporaryFile('w',suffix='.js',encoding='utf-8') as handle:
    handle.write(script);handle.flush();subprocess.run(['node','--check',handle.name],check=True)

helpers={'_mobile_pairing_table','_cleanup_mobile_pairings'}
helper_module=ast.Module(body=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in helpers],type_ignores=[])
env={'sqlite3':sqlite3,'time':time}
exec(compile(helper_module,'<pairing-test>','exec'),env)
with tempfile.NamedTemporaryFile(suffix='.sqlite') as database:
    conn=sqlite3.connect(database.name)
    conn.row_factory=sqlite3.Row
    env['_mobile_pairing_table'](conn)
    now=int(time.time())
    conn.execute("INSERT INTO mobile_pairings VALUES(?,?,?)",('expired',now-1,'now'))
    conn.execute("INSERT INTO mobile_pairings VALUES(?,?,?)",('valid',now+300,'now'))
    env['_cleanup_mobile_pairings'](conn)
    assert [row['token_hash'] for row in conn.execute("SELECT token_hash FROM mobile_pairings")]==['valid']
    conn.close()

with zipfile.ZipFile(CLIENT) as package:app=package.read('payload/app.js').decode('utf-8')
assert "const pairUrl=mobileUrl.split('#')[0]+`#pair=${encodeURIComponent(token)}`;" in app
print('v0.13.28 pairing tests: OK')
