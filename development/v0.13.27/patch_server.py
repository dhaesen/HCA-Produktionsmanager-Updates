#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


IMAGE_TIMEOUT_OLD = "        with urllib.request.urlopen(request, timeout=12) as response:\n"
IMAGE_TIMEOUT_NEW = "        with urllib.request.urlopen(request, timeout=3) as response:\n"

OLD_DETAILS_START = "def _hca1326_datasheet_details(item: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:\n"
OLD_DETAILS_END = "\n\ndef _hca1310_datasheet_specs(document: dict[str, Any]) -> list[dict[str, Any]]:\n"

FAST_DETAILS = '''def _hca1327_datasheet_details(item: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """Use the visual data already loaded by the editor without blocking PDF creation."""
    details = dict(cfg.get("product_details")) if isinstance(cfg.get("product_details"), dict) else {}
    details.pop("supplier", None)
    details.pop("lieferant", None)
    return details
'''

IMAGE_CODE = r'''

def _hca1327_cache_file(value: Any) -> Path | None:
    url = _hca138_image_url(value)
    if not url or url.lower().startswith("data:"):
        return None
    return DATA_DIR / "hca_datasheet_images" / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".jpg")


def _hca1327_jpeg_image(raw: bytes) -> dict[str, Any] | None:
    jpeg = _hca137_jpeg_info(raw)
    if not jpeg:
        return None
    width, height, components = jpeg
    return {"width": width, "height": height,
            "colorspace": "/DeviceGray" if components == 1 else "/DeviceRGB",
            "filter": "/DCTDecode", "data": raw, "decode": ""}


def _hca1327_datasheet_image(value: Any) -> dict[str, Any] | None:
    url = _hca138_image_url(value)
    if not url:
        return None
    if url.lower().startswith("data:image/jpeg;base64,"):
        try:
            raw = base64.b64decode(url.split(",", 1)[1], validate=True)
            return _hca1327_jpeg_image(raw)
        except Exception:
            return None
    cache_file = _hca1327_cache_file(url)
    if cache_file and cache_file.is_file():
        try:
            return _hca1327_jpeg_image(cache_file.read_bytes())
        except Exception:
            pass
    # One short fallback only. Never make the PDF wait for several dead URLs.
    return _hca137_image(url)


def _hca1327_public_image_url(url: str) -> str:
    import ipaddress
    import socket
    parsed = urllib.parse.urlsplit(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Ungültige Bildadresse")
    if parsed.port not in (None, 80, 443):
        raise ValueError("Nicht erlaubter Bild-Port")
    for info in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM):
        address = ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast:
            raise ValueError("Private Bildadresse ist nicht erlaubt")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _hca1327_fetch_raw_image(url: str) -> tuple[bytes, str]:
    clean = _hca1327_public_image_url(url)
    parsed = urllib.parse.urlsplit(clean)
    request = urllib.request.Request(clean, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 HCA/0.13.27",
        "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.1",
        "Referer": urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/", "", "")),
    })
    with urllib.request.urlopen(request, timeout=5) as response:
        content_type = str(response.headers.get("Content-Type") or "application/octet-stream").split(";", 1)[0].strip().lower()
        raw = response.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError("Artikelbild ist größer als 10 MB")
    if not content_type.startswith("image/"):
        raise ValueError("Adresse liefert kein Bild")
    return raw, content_type


@router.get("/media/image-proxy", dependencies=auth)
async def hca1327_image_proxy(url: str = "") -> Response:
    try:
        cached = _hca1327_cache_file(url)
        if cached and cached.is_file():
            raw = cached.read_bytes()
            if _hca137_jpeg_info(raw):
                return Response(raw, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
        raw, content_type = await asyncio.wait_for(asyncio.to_thread(_hca1327_fetch_raw_image, url), timeout=6)
        return Response(raw, media_type=content_type, headers={"Cache-Control": "private, max-age=86400"})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Artikelbild konnte nicht geladen werden: {exc}") from exc


@router.post("/media/image-cache", dependencies=auth)
async def hca1327_image_cache(request: Request) -> dict[str, Any]:
    payload = await request.json()
    rows = payload.get("images") if isinstance(payload, dict) and isinstance(payload.get("images"), list) else []
    cache_dir = DATA_DIR / "hca_datasheet_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for row in rows[:80]:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        data_url = str(row.get("data") or "")
        if not url or not data_url.lower().startswith("data:image/jpeg;base64,") or len(data_url) > 2_000_000:
            continue
        try:
            raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
            if not _hca137_jpeg_info(raw):
                continue
            target = _hca1327_cache_file(url)
            if target is None:
                continue
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(raw)
            temporary.replace(target)
            saved += 1
        except Exception:
            continue
    return {"ok": True, "saved": saved}
'''


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: erwartet 1 Fundstelle, gefunden {count}")
    return source.replace(old, new, 1)


def patch(source: str) -> str:
    source = replace_once(source, IMAGE_TIMEOUT_OLD, IMAGE_TIMEOUT_NEW, "Bild-Timeout")
    start = source.index(OLD_DETAILS_START)
    end = source.index(OLD_DETAILS_END, start)
    source = source[:start] + FAST_DETAILS + source[end:]
    source = replace_once(
        source,
        '        details=_hca1326_datasheet_details(item,cfg)\n',
        '        details=_hca1327_datasheet_details(item,cfg)\n',
        "Datenblattdetails",
    )
    source = replace_once(
        source,
        '            frame(x,y,w,h);image=_hca1326_datasheet_image(source)\n',
        '            frame(x,y,w,h);image=_hca1327_datasheet_image(source)\n',
        "Datenblattbilder",
    )
    marker = '\n\n@router.get("/woocommerce/products/search", dependencies=auth)\n'
    source = replace_once(source, marker, IMAGE_CODE + marker, "Bildproxy")
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.write_text(patch(args.source.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
