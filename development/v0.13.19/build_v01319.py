#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT.parent / "build" / "HCA_Update_v0.13.18.hcaupdate"
OUT_DIR = ROOT.parent / "build"
OUT = OUT_DIR / "HCA_Update_v0.13.19.hcaupdate"
HASH = OUT_DIR / "HCA_Update_v0.13.19.sha256"
SOURCE = ROOT / "development" / "v0.13.19"

def safe_extract(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"Unsicherer ZIP-Pfad: {member.filename}")
        package.extractall(destination)

def main() -> None:
    if not BASE.exists():
        raise SystemExit(f"Basispaket fehlt: {BASE}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hca-v01319-") as temporary:
        work = Path(temporary)
        safe_extract(BASE, work)
        payload = work / "payload"
        html_path = payload / "index.html"
        html = html_path.read_text(encoding="utf-8")
        marker = '  <script src="/hca-v01318.js?v=0.13.18"></script>\n'
        replacement = marker + '  <script src="/hca-v01319.js?v=0.13.19"></script>\n'
        if marker not in html:
            raise RuntimeError("v0.13.18-Basis-Script fehlt")
        html = html.replace(marker, replacement)
        if html.count("hca-v01319.js?v=0.13.19") != 1:
            raise RuntimeError("v0.13.19-Script wurde nicht eindeutig eingebunden")
        html_path.write_text(html, encoding="utf-8")
        (payload / "hca-v01319.js").write_bytes((SOURCE / "hca-v01319.js").read_bytes())
        (payload / "AENDERUNGEN_v0.13.19.txt").write_bytes((SOURCE / "AENDERUNGEN_v0.13.19.txt").read_bytes())
        (payload / "version.json").write_text(json.dumps({"version":"0.13.19","channel":"test","released":"2026-09-15"},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        (work / "hca-update.json").write_text(json.dumps({"product":"HCA Produktionsmanager","version":"0.13.19","description":"Bestandspositionen und WooCommerce-Veredelungspreise repariert."},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        with zipfile.ZipFile(OUT,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as package:
            for path in sorted(work.rglob("*")):
                if path.is_file(): package.write(path,path.relative_to(work).as_posix())
    digest=hashlib.sha256(OUT.read_bytes()).hexdigest()
    HASH.write_text(f"{digest}  {OUT.name}\n",encoding="ascii")
    with zipfile.ZipFile(OUT) as package:
        if package.testzip(): raise RuntimeError("ZIP-Integritätsprüfung fehlgeschlagen")
        names=set(package.namelist())
        if "payload/hca-v01319.js" not in names: raise RuntimeError("Preisreparatur fehlt im Paket")
    print(OUT)
    print(digest)

if __name__ == "__main__": main()
