#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BUILD=ROOT.parent/'build'
SOURCE=ROOT/'development'/'v0.13.27'
CLIENT_BASE=BUILD/'HCA_Update_v0.13.25.hcaupdate'
NAS_BASE=BUILD/'HCA_NAS_Erweiterung_v0.13.26.zip'
CLIENT=BUILD/'HCA_Update_v0.13.27.hcaupdate'
NAS=BUILD/'HCA_NAS_Erweiterung_v0.13.27.zip'

def extract(archive:Path,destination:Path)->None:
    root=destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target=(destination/member.filename).resolve()
            if target!=root and root not in target.parents:raise RuntimeError(f'Unsicherer ZIP-Pfad: {member.filename}')
        package.extractall(destination)

def patcher():
    spec=importlib.util.spec_from_file_location('patch_server_v01327',SOURCE/'patch_server.py')
    if spec is None or spec.loader is None:raise RuntimeError('Patchmodul fehlt')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def pack(folder:Path,target:Path)->str:
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as package:
        for path in sorted(folder.rglob('*')):
            if path.is_file():package.write(path,path.relative_to(folder).as_posix())
    with zipfile.ZipFile(target) as package:
        if package.testzip():raise RuntimeError(f'{target.name} beschädigt')
    value=hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.sha256').write_text(f'{value}  {target.name}\n',encoding='ascii')
    return value

def build()->tuple[str,str]:
    if not CLIENT_BASE.exists() or not NAS_BASE.exists():raise SystemExit('Basispakete fehlen')
    with tempfile.TemporaryDirectory(prefix='hca-v01327-client-') as tmp:
        work=Path(tmp);extract(CLIENT_BASE,work);payload=work/'payload';html_path=payload/'index.html';html=html_path.read_text(encoding='utf-8')
        marker='  <script src="/hca-v01325.js?v=0.13.25"></script>\n'
        if marker not in html:raise RuntimeError('Clientmarker v0.13.25 fehlt')
        html_path.write_text(html.replace(marker,marker+'  <script src="/hca-v01327.js?v=0.13.27"></script>\n',1),encoding='utf-8')
        (payload/'hca-v01327.js').write_bytes((SOURCE/'hca-v01327.js').read_bytes())
        (payload/'AENDERUNGEN_v0.13.27.txt').write_bytes((SOURCE/'AENDERUNGEN_v0.13.27.txt').read_bytes())
        (payload/'version.json').write_text(json.dumps({'version':'0.13.27','channel':'test','released':'2026-09-16'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (work/'hca-update.json').write_text(json.dumps({'product':'HCA Produktionsmanager','version':'0.13.27','description':'Schnelle und kompatible Textilbilder im Artikeldatenblatt.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        client_hash=pack(work,CLIENT)
    with tempfile.TemporaryDirectory(prefix='hca-v01327-nas-') as tmp:
        work=Path(tmp);extract(NAS_BASE,work);server=work/'app'/'hca_shared.py';server.write_text(patcher().patch(server.read_text(encoding='utf-8')),encoding='utf-8')
        for path in work.glob('INSTALLATION_v*.txt'):path.unlink()
        for path in work.glob('AENDERUNGEN_v*.txt'):path.unlink()
        (work/'INSTALLATION_v0.13.27.txt').write_bytes((SOURCE/'INSTALLATION_NAS_v0.13.27.txt').read_bytes())
        (work/'AENDERUNGEN_v0.13.27.txt').write_bytes((SOURCE/'AENDERUNGEN_v0.13.27.txt').read_bytes())
        compile(server.read_text(encoding='utf-8'),str(server),'exec');nas_hash=pack(work,NAS)
    return client_hash,nas_hash

if __name__=='__main__':
    BUILD.mkdir(parents=True,exist_ok=True);print(build())
