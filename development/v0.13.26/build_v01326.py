#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT.parent / "build"
SOURCE = ROOT / "development" / "v0.13.26"
BASE = BUILD / "HCA_NAS_Erweiterung_v0.13.24.published.zip"
OUTPUT = BUILD / "HCA_NAS_Erweiterung_v0.13.26.zip"
HASH = BUILD / "HCA_NAS_Erweiterung_v0.13.26.sha256"
BASE_SHA256 = "88e294bedffc5b1839a7e69c291c9f2926b110ecd77c12cd24351c03c3936188"


def extract(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"Unsicherer ZIP-Pfad: {member.filename}")
        package.extractall(destination)


def load_patcher():
    spec = importlib.util.spec_from_file_location("patch_server_v01326", SOURCE / "patch_server.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Patchmodul konnte nicht geladen werden")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build() -> str:
    if not BASE.exists():
        raise SystemExit(f"Basispaket fehlt: {BASE}")
    actual = hashlib.sha256(BASE.read_bytes()).hexdigest()
    if actual != BASE_SHA256:
        raise RuntimeError(f"Falsches Basispaket: {actual}")
    patcher = load_patcher()
    with tempfile.TemporaryDirectory(prefix="hca-v01326-nas-") as tmp:
        work = Path(tmp)
        extract(BASE, work)
        server = work / "app" / "hca_shared.py"
        server.write_text(patcher.patch(server.read_text(encoding="utf-8")), encoding="utf-8")
        (work / "INSTALLATION_v0.13.24.txt").unlink(missing_ok=True)
        (work / "INSTALLATION_v0.13.26.txt").write_bytes((SOURCE / "INSTALLATION_NAS_v0.13.26.txt").read_bytes())
        (work / "AENDERUNGEN_v0.13.26.txt").write_bytes((SOURCE / "AENDERUNGEN_v0.13.26.txt").read_bytes())
        compile(server.read_text(encoding="utf-8"), str(server), "exec")
        with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as package:
            for path in sorted(work.rglob("*")):
                if path.is_file():
                    package.write(path, path.relative_to(work).as_posix())
    with zipfile.ZipFile(OUTPUT) as package:
        if package.testzip():
            raise RuntimeError("NAS-ZIP beschädigt")
        required = {"app/hca_shared.py", "INSTALLATION_v0.13.26.txt", "AENDERUNGEN_v0.13.26.txt"}
        if not required.issubset(package.namelist()):
            raise RuntimeError("NAS-Paket unvollständig")
        server_text = package.read("app/hca_shared.py").decode("utf-8")
        for marker in ("_hca1326_datasheet_details", "_hca1326_datasheet_image", "HCA/0.13.26"):
            if marker not in server_text:
                raise RuntimeError(f"Servermarker fehlt: {marker}")
    value = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    HASH.write_text(f"{value}  {OUTPUT.name}\n", encoding="ascii")
    return value


if __name__ == "__main__":
    BUILD.mkdir(parents=True, exist_ok=True)
    print(OUTPUT, build())
