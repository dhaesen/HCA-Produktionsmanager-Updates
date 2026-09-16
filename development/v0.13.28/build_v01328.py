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
SOURCE=ROOT/'development'/'v0.13.28'
CLIENT_BASE=BUILD/'published-v01327'/'HCA_Update_v0.13.27.hcaupdate'
NAS_BASE=BUILD/'published-v01327'/'HCA_NAS_Erweiterung_v0.13.27.zip'
CLIENT=BUILD/'HCA_Update_v0.13.28.hcaupdate'
NAS=BUILD/'HCA_NAS_Erweiterung_v0.13.28.zip'
CLIENT_BASE_SHA='a4ca6b8c4c74af157f92a394f669d890210753935b3730a536d375bb9048c299'
NAS_BASE_SHA='d05cb2a2d4aeedd515d565f7d4e32ae533404af7969c95eabc05da9c748bfe26'

def verify(path:Path,expected:str)->None:
    actual=hashlib.sha256(path.read_bytes()).hexdigest()
    if actual!=expected:raise RuntimeError(f'Falsches Basispaket {path.name}: {actual}')

def extract(archive:Path,destination:Path)->None:
    root=destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target=(destination/member.filename).resolve()
            if target!=root and root not in target.parents:raise RuntimeError(f'Unsicherer ZIP-Pfad: {member.filename}')
        package.extractall(destination)

def patcher():
    spec=importlib.util.spec_from_file_location('patch_server_v01328',SOURCE/'patch_server.py')
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
    verify(CLIENT_BASE,CLIENT_BASE_SHA);verify(NAS_BASE,NAS_BASE_SHA)
    with tempfile.TemporaryDirectory(prefix='hca-v01328-client-') as tmp:
        work=Path(tmp);extract(CLIENT_BASE,work);payload=work/'payload'
        app_path=payload/'app.js';app=app_path.read_text(encoding='utf-8')
        old="const pairUrl=mobileUrl.split('#')[0]+`#pair=${encodeURIComponent(token)}`;"
        new="const pairUrl=mobileUrl.split(/[?#]/)[0]+`?pair=${encodeURIComponent(token)}`;"
        if app.count(old)!=1:raise RuntimeError(f'Pairing-Link: erwartet 1 Fundstelle, gefunden {app.count(old)}')
        app_path.write_text(app.replace(old,new,1),encoding='utf-8')
        (payload/'AENDERUNGEN_v0.13.28.txt').write_bytes((SOURCE/'AENDERUNGEN_v0.13.28.txt').read_bytes())
        (payload/'version.json').write_text(json.dumps({'version':'0.13.28','channel':'test','released':'2026-09-16'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (work/'hca-update.json').write_text(json.dumps({'product':'HCA Produktionsmanager','version':'0.13.28','description':'Zuverlässige Kopplung der mobilen Lager-App per QR-Code und API-Schlüssel.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        client_hash=pack(work,CLIENT)
    with tempfile.TemporaryDirectory(prefix='hca-v01328-nas-') as tmp:
        work=Path(tmp);extract(NAS_BASE,work);server=work/'app'/'hca_shared.py'
        server.write_text(patcher().patch(server.read_text(encoding='utf-8')),encoding='utf-8')
        for path in work.glob('INSTALLATION_v*.txt'):path.unlink()
        for path in work.glob('AENDERUNGEN_v*.txt'):path.unlink()
        (work/'INSTALLATION_v0.13.28.txt').write_bytes((SOURCE/'INSTALLATION_NAS_v0.13.28.txt').read_bytes())
        (work/'AENDERUNGEN_v0.13.28.txt').write_bytes((SOURCE/'AENDERUNGEN_v0.13.28.txt').read_bytes())
        compile(server.read_text(encoding='utf-8'),str(server),'exec');nas_hash=pack(work,NAS)
    return client_hash,nas_hash

if __name__=='__main__':
    BUILD.mkdir(parents=True,exist_ok=True);print(build())
