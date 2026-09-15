#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT.parent / "build" / "HCA_Update_v0.13.16.hcaupdate"
OUT_DIR = ROOT.parent / "build"
OUT = OUT_DIR / "HCA_Update_v0.13.18.hcaupdate"
HASH = OUT_DIR / "HCA_Update_v0.13.18.sha256"
SOURCE = ROOT / "development" / "v0.13.18"


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
    with tempfile.TemporaryDirectory(prefix="hca-v01318-") as temporary:
        work = Path(temporary)
        safe_extract(BASE, work)
        payload = work / "payload"
        html_path = payload / "index.html"
        html = html_path.read_text(encoding="utf-8")
        html = html.replace('  <link rel="stylesheet" href="/hca-v01310.css?v=0.13.12">\n', "")
        html = html.replace('  <script src="/hca-v01310.js?v=0.13.12"></script>\n', "")
        html = html.replace(
            '  <script src="/hca-v01316.js?v=0.13.16"></script>\n',
            '  <script src="/hca-v01318.js?v=0.13.18"></script>\n',
        )
        if "hca-v01310" in html or "hca-v01316.js" in html:
            raise RuntimeError("Alte Preis-/Mengenfelder-Skripte wurden nicht vollständig entfernt")
        if html.count("hca-v01318.js?v=0.13.18") != 1:
            raise RuntimeError("Neues Preis-Script wurde nicht eindeutig eingebunden")
        html_path.write_text(html, encoding="utf-8")

        (payload / "hca-v01318.js").write_bytes((SOURCE / "hca-v01318.js").read_bytes())
        (payload / "AENDERUNGEN_v0.13.18.txt").write_bytes((SOURCE / "AENDERUNGEN_v0.13.18.txt").read_bytes())
        for obsolete in ("hca-v01310.js", "hca-v01310.css", "hca-v01316.js"):
            path = payload / obsolete
            if path.exists():
                path.unlink()

        (payload / "version.json").write_text(
            json.dumps({"version": "0.13.18", "channel": "test", "released": "2026-09-15"}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (work / "hca-update.json").write_text(
            json.dumps(
                {
                    "product": "HCA Produktionsmanager",
                    "version": "0.13.18",
                    "description": "Rückbau der fehlerhaften Mengenfelder und Reparatur der WooCommerce-Veredelungspreise.",
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

        javascript = "\n".join(path.read_text(encoding="utf-8") for path in sorted(payload.glob("*.js")))
        if "data-h1310-quantity" in javascript or "quantity_option_generated" in javascript:
            raise RuntimeError("Mengenfelder-Code ist noch im Paket enthalten")

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
        names = set(package.namelist())
        if "payload/hca-v01310.js" in names or "payload/hca-v01310.css" in names:
            raise RuntimeError("Mengenfelder-Dateien sind noch im Update")
    print(OUT)
    print(digest)


if __name__ == "__main__":
    main()
