#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT.parent / "build" / "HCA_Update_v0.13.15.hcaupdate"
OUT_DIR = ROOT.parent / "build"
OUT = OUT_DIR / "HCA_Update_v0.13.16.hcaupdate"
HASH = OUT_DIR / "HCA_Update_v0.13.16.sha256"
SOURCE = ROOT / "development" / "v0.13.16"


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
    with tempfile.TemporaryDirectory(prefix="hca-v01316-") as temporary:
        work = Path(temporary)
        safe_extract(BASE, work)
        payload = work / "payload"
        html_path = payload / "index.html"
        html = html_path.read_text(encoding="utf-8")
        html = html.replace(
            '  <script src="/hca-v01315.js?v=0.13.15"></script>\n',
            '  <script src="/hca-v01316.js?v=0.13.16"></script>\n',
            1,
        )
        if "hca-v01316.js?v=0.13.16" not in html or "hca-v01315.js?v=0.13.15" in html:
            raise RuntimeError("Preis-Script konnte nicht eindeutig ersetzt werden")
        html_path.write_text(html, encoding="utf-8")
        shutil.copy2(SOURCE / "hca-v01316.js", payload / "hca-v01316.js")
        shutil.copy2(SOURCE / "AENDERUNGEN_v0.13.16.txt", payload / "AENDERUNGEN_v0.13.16.txt")
        old_override = payload / "hca-v01315.js"
        if old_override.exists():
            old_override.unlink()
        (payload / "version.json").write_text(
            json.dumps({"version": "0.13.16", "channel": "test", "released": "2026-09-15"}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (work / "hca-update.json").write_text(
            json.dumps(
                {
                    "product": "HCA Produktionsmanager",
                    "version": "0.13.16",
                    "description": "Exakte Wiederherstellung der funktionierenden WooCommerce-Veredelungspreisfunktion aus v0.13.6.1.",
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as package:
            for path in sorted(work.rglob("*")):
                if path.is_file():
                    package.write(path, path.relative_to(work).as_posix())
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    HASH.write_text(f"{digest}  {OUT.name}\n", encoding="ascii")
    with zipfile.ZipFile(OUT) as package:
        bad = package.testzip()
        if bad:
            raise RuntimeError(f"Beschädigter ZIP-Eintrag: {bad}")
    print(OUT)
    print(digest)


if __name__ == "__main__":
    main()
