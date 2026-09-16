#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,tempfile,zipfile
from pathlib import Path
from patch_server import patch_text

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT.parent/'build'/'HCA_Update_v0.13.21.hcaupdate'
OUT_DIR=ROOT.parent/'build'
CLIENT=OUT_DIR/'HCA_Update_v0.13.22.hcaupdate'
CLIENT_HASH=OUT_DIR/'HCA_Update_v0.13.22.sha256'
NAS=OUT_DIR/'HCA_NAS_Erweiterung_v0.13.22.zip'
NAS_HASH=OUT_DIR/'HCA_NAS_Erweiterung_v0.13.22.sha256'
SOURCE=ROOT/'development'/'v0.13.22'

def extract(archive:Path,destination:Path)->None:
    root=destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target=(destination/member.filename).resolve()
            if target!=root and root not in target.parents:raise RuntimeError(f'Unsicherer ZIP-Pfad: {member.filename}')
        package.extractall(destination)

def digest(path:Path,output:Path)->str:
    value=hashlib.sha256(path.read_bytes()).hexdigest();output.write_text(f'{value}  {path.name}\n',encoding='ascii');return value

def build_client()->str:
    if not BASE.exists():raise SystemExit(f'Basispaket fehlt: {BASE}')
    with tempfile.TemporaryDirectory(prefix='hca-v01322-') as tmp:
        work=Path(tmp);extract(BASE,work);payload=work/'payload';html_path=payload/'index.html';html=html_path.read_text(encoding='utf-8')
        script_marker='  <script src="/hca-v01321.js?v=0.13.21"></script>\n'
        style_marker='  <link rel="stylesheet" href="/hca-v01321.css?v=0.13.21">\n'
        if script_marker not in html or style_marker not in html:raise RuntimeError('v0.13.21-Basismarker fehlen')
        html=html.replace(style_marker,style_marker+'  <link rel="stylesheet" href="/hca-v01322.css?v=0.13.22">\n')
        html=html.replace(script_marker,script_marker+'  <script src="/hca-v01322.js?v=0.13.22"></script>\n')
        if html.count('hca-v01322.js?v=0.13.22')!=1 or html.count('hca-v01322.css?v=0.13.22')!=1:raise RuntimeError('v0.13.22 nicht eindeutig eingebunden')
        html_path.write_text(html,encoding='utf-8')
        for name in ('hca-v01322.js','hca-v01322.css','AENDERUNGEN_v0.13.22.txt'):(payload/name).write_bytes((SOURCE/name).read_bytes())
        (payload/'version.json').write_text(json.dumps({'version':'0.13.22','channel':'test','released':'2026-09-16'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (work/'hca-update.json').write_text(json.dumps({'product':'HCA Produktionsmanager','version':'0.13.22','description':'Mengenstaffel entfernt und Dokumentpositionen als zusammengehörige Gruppen dargestellt.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        with zipfile.ZipFile(CLIENT,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as package:
            for path in sorted(work.rglob('*')):
                if path.is_file():package.write(path,path.relative_to(work).as_posix())
    with zipfile.ZipFile(CLIENT) as package:
        if package.testzip():raise RuntimeError('Client-ZIP beschädigt')
        if not {'payload/hca-v01322.js','payload/hca-v01322.css','payload/version.json'}.issubset(package.namelist()):raise RuntimeError('Clientdateien fehlen')
    return digest(CLIENT,CLIENT_HASH)

def build_nas()->str:
    server=patch_text((ROOT/'development'/'v0.13.17'/'hca_shared.py').read_text(encoding='utf-8'))
    with zipfile.ZipFile(NAS,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as package:
        package.writestr('app/hca_shared.py',server);package.write(SOURCE/'INSTALLATION_NAS_v0.13.22.txt','INSTALLATION_v0.13.22.txt')
    with zipfile.ZipFile(NAS) as package:
        if package.testzip():raise RuntimeError('NAS-ZIP beschädigt')
        if set(package.namelist())!={'app/hca_shared.py','INSTALLATION_v0.13.22.txt'}:raise RuntimeError('Unerwarteter NAS-Paketinhalt')
    return digest(NAS,NAS_HASH)

def main()->None:
    OUT_DIR.mkdir(parents=True,exist_ok=True);print(CLIENT,build_client());print(NAS,build_nas())

if __name__=='__main__':main()
