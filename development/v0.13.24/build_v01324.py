#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,tempfile,zipfile
from pathlib import Path
from patch_server import patch_text

ROOT=Path(__file__).resolve().parents[2]
BUILD=ROOT.parent/'build'
BASE_CLIENT=BUILD/'HCA_Update_v0.13.23.hcaupdate'
BASE_NAS=BUILD/'HCA_NAS_Erweiterung_v0.13.22.zip'
SOURCE=ROOT/'development'/'v0.13.24'
CLIENT=BUILD/'HCA_Update_v0.13.24.hcaupdate'
NAS=BUILD/'HCA_NAS_Erweiterung_v0.13.24.zip'

def extract(archive:Path,destination:Path)->None:
    root=destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target=(destination/member.filename).resolve()
            if target!=root and root not in target.parents:raise RuntimeError(f'Unsicherer ZIP-Pfad: {member.filename}')
        package.extractall(destination)

def digest(path:Path)->str:
    value=hashlib.sha256(path.read_bytes()).hexdigest()
    stem=path.name[:-10] if path.name.endswith('.hcaupdate') else path.stem
    (BUILD/(stem+'.sha256')).write_text(f'{value}  {path.name}\n',encoding='ascii')
    return value

def build_client()->str:
    if not BASE_CLIENT.exists():raise SystemExit(f'Basispaket fehlt: {BASE_CLIENT}')
    with tempfile.TemporaryDirectory(prefix='hca-v01324-client-') as tmp:
        work=Path(tmp);extract(BASE_CLIENT,work);payload=work/'payload';html_path=payload/'index.html';html=html_path.read_text(encoding='utf-8')
        # Drei alte Paketierungsschritte hatten ein sichtbares "\\n" statt eines
        # echten Zeilenumbruchs in index.html hinterlassen.
        html=html.replace('\\n','\n')
        script_marker='  <script src="/hca-v01323.js?v=0.13.23"></script>\n'
        style_marker='  <link rel="stylesheet" href="/hca-v01323.css?v=0.13.23">\n'
        if script_marker not in html or style_marker not in html:raise RuntimeError('v0.13.23-Basismarker fehlen')
        html=html.replace(style_marker,style_marker+'  <link rel="stylesheet" href="/hca-v01324.css?v=0.13.24">\n')
        html=html.replace(script_marker,script_marker+'  <script src="/hca-v01324.js?v=0.13.24"></script>\n')
        if html.count('hca-v01324.js?v=0.13.24')!=1 or html.count('hca-v01324.css?v=0.13.24')!=1:raise RuntimeError('v0.13.24 nicht eindeutig eingebunden')
        html_path.write_text(html,encoding='utf-8')
        for name in ('hca-v01324.js','hca-v01324.css','AENDERUNGEN_v0.13.24.txt'):(payload/name).write_bytes((SOURCE/name).read_bytes())
        (payload/'version.json').write_text(json.dumps({'version':'0.13.24','channel':'test','released':'2026-09-16'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (work/'hca-update.json').write_text(json.dumps({'product':'HCA Produktionsmanager','version':'0.13.24','description':'Lieferadressen, durchsuchbare Produktionsaufträge und personalisierte Serienproduktion.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        with zipfile.ZipFile(CLIENT,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as package:
            for path in sorted(work.rglob('*')):
                if path.is_file():package.write(path,path.relative_to(work).as_posix())
    with zipfile.ZipFile(CLIENT) as package:
        if package.testzip():raise RuntimeError('Client-ZIP beschädigt')
        required={'payload/hca-v01324.js','payload/hca-v01324.css','payload/version.json','hca-update.json'}
        if not required.issubset(package.namelist()):raise RuntimeError('Clientdateien fehlen')
        html=package.read('payload/index.html').decode('utf-8')
        if '\\n' in html:raise RuntimeError('Sichtbare \\n-Zeichenfolge verblieben')
    return digest(CLIENT)

def build_nas()->str:
    if not BASE_NAS.exists():raise SystemExit(f'NAS-Basispaket fehlt: {BASE_NAS}')
    with tempfile.TemporaryDirectory(prefix='hca-v01324-nas-') as tmp:
        work=Path(tmp);extract(BASE_NAS,work);server=work/'app'/'hca_shared.py';server.write_text(patch_text(server.read_text(encoding='utf-8')),encoding='utf-8')
        with zipfile.ZipFile(NAS,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as package:
            package.write(server,'app/hca_shared.py');package.write(SOURCE/'INSTALLATION_NAS_v0.13.24.txt','INSTALLATION_v0.13.24.txt')
    with zipfile.ZipFile(NAS) as package:
        if package.testzip():raise RuntimeError('NAS-ZIP beschädigt')
        if set(package.namelist())!={'app/hca_shared.py','INSTALLATION_v0.13.24.txt'}:raise RuntimeError('Unerwarteter NAS-Paketinhalt')
    return digest(NAS)

if __name__=='__main__':
    BUILD.mkdir(parents=True,exist_ok=True)
    print(CLIENT,build_client());print(NAS,build_nas())
