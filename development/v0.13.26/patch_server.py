#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


IMAGE_REQUEST_OLD = '''        request = urllib.request.Request(url, headers={"User-Agent":"HCA-Produktionsmanager/0.13.7","Accept":"image/jpeg,image/png,image/*;q=0.5"})
        with urllib.request.urlopen(request, timeout=12) as response:
'''

IMAGE_REQUEST_NEW = '''        parsed = urllib.parse.urlsplit(url)
        referer = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))
        request = urllib.request.Request(url, headers={
            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 HCA/0.13.26",
            "Accept":"image/jpeg,image/png;q=0.95,image/webp;q=0.8,image/*;q=0.5,*/*;q=0.1",
            "Referer":referer,
        })
        with urllib.request.urlopen(request, timeout=12) as response:
'''

IMAGE_HELPERS = r'''

def _hca1326_image_candidates(value: Any) -> list[str]:
    """Return safe original-file alternatives used by common WordPress image converters."""
    url = _hca138_image_url(value)
    if not url:
        return []
    candidates = [url]
    try:
        parsed = urllib.parse.urlsplit(url)
        path = parsed.path
        lower = path.lower()
        alternatives: list[str] = []
        if lower.endswith(".webp"):
            without_webp = path[:-5]
            alternatives.append(without_webp)
            if not without_webp.lower().endswith((".jpg", ".jpeg", ".png")):
                alternatives.extend([without_webp + ".jpg", without_webp + ".jpeg", without_webp + ".png"])
        elif lower.endswith(".avif"):
            without_avif = path[:-5]
            alternatives.append(without_avif)
            if not without_avif.lower().endswith((".jpg", ".jpeg", ".png")):
                alternatives.extend([without_avif + ".jpg", without_avif + ".jpeg", without_avif + ".png"])
        for alternative in alternatives:
            candidate = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, alternative, parsed.query, parsed.fragment))
            if candidate and candidate not in candidates:
                candidates.append(candidate)
    except Exception:
        pass
    return candidates


def _hca1326_datasheet_image(value: Any) -> dict[str, Any] | None:
    for candidate in _hca1326_image_candidates(value):
        image = _hca137_image(candidate)
        if image:
            return image
    return None
'''

DETAIL_HELPER = r'''

def _hca1326_datasheet_details(item: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """Enrich saved datasheet data with live Woo variation images.

    Werbeartikel store colours in ``werbeartikel_colors`` on the parent product.
    Textile imports normally store their colour image on each Woo variation instead.
    Older quotes therefore need a server-side lookup when the PDF is generated.
    """
    current = dict(cfg.get("product_details")) if isinstance(cfg.get("product_details"), dict) else {}
    wizard = cfg.get("wizard_config") if isinstance(cfg.get("wizard_config"), dict) else {}
    product_id = _safe_int(cfg.get("main_product_id") or wizard.get("meta_product_id") or item.get("product_id"), 0)
    if product_id <= 0:
        return current
    try:
        product = _woo_json(f"/products/{product_id}")
    except Exception:
        return current
    if not isinstance(product, dict):
        return current

    fresh = _hca137_product_details(product)
    meta = _meta_dict(product)
    fresh.update({
        "name": str(product.get("name") or "").strip(),
        "sku": str(product.get("sku") or "").strip(),
        "manufacturer": _product_manufacturer(meta, product),
        "weight": str(product.get("weight") or "").strip(),
        "dimensions": product.get("dimensions") if isinstance(product.get("dimensions"), dict) else {},
    })

    variation_colours: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in fresh.get("color_images") or []:
        if not isinstance(row, dict):
            continue
        key = (_slug_text(row.get("name")), _hca138_image_url(row))
        if key not in seen:
            seen.add(key)
            variation_colours.append(row)
    if str(product.get("type") or "").strip().lower() == "variable":
        try:
            variations = _woo_product_variations(product_id)
        except Exception:
            variations = []
        for variation in variations:
            if not isinstance(variation, dict):
                continue
            image = variation.get("image") if isinstance(variation.get("image"), dict) else {}
            source = str(image.get("src") or "").strip()
            if not source:
                continue
            attrs = _woo_attr_values(variation.get("attributes"))
            colour = str(attrs.get("color") or "").strip()
            if not colour:
                colour = next((str(value).strip() for key, value in attrs.items() if "farb" in key or "color" in key), "")
            key = (_slug_text(colour), source)
            if key in seen:
                continue
            seen.add(key)
            variation_colours.append({
                "name": colour or "Farbvariante",
                "image": source,
                "image_id": str(image.get("id") or "").strip(),
            })
    if variation_colours:
        fresh["color_images"] = variation_colours

    merged = dict(fresh)
    for key, value in current.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    if variation_colours:
        combined: list[dict[str, Any]] = []
        combined_seen: set[tuple[str, str]] = set()
        for row in [*(current.get("color_images") or []), *variation_colours]:
            if not isinstance(row, dict):
                continue
            key = (_slug_text(row.get("name")), _hca138_image_url(row))
            if key in combined_seen:
                continue
            combined_seen.add(key)
            combined.append(row)
        merged["color_images"] = combined
    # Customer-facing datasheets intentionally never expose supplier data.
    merged.pop("supplier", None)
    merged.pop("lieferant", None)
    return merged
'''


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"{label}: erwartet 1 Fundstelle, gefunden {source.count(old)}")
    return source.replace(old, new, 1)


def patch(source: str) -> str:
    source = replace_once(source, IMAGE_REQUEST_OLD, IMAGE_REQUEST_NEW, "Bildabruf")
    source = replace_once(source, "\n\ndef _hca137_fit(image:", IMAGE_HELPERS + "\n\ndef _hca137_fit(image:", "Bildhelfer")
    source = replace_once(source, "\n\ndef _hca1310_datasheet_specs(document:", DETAIL_HELPER + "\n\ndef _hca1310_datasheet_specs(document:", "Datenblatthelfer")
    start = source.index("def _hca1310_datasheet_specs(document:")
    end = source.index("\ndef _hca137_quote_pdf(", start)
    datasheet = source[start:end]
    datasheet = replace_once(
        datasheet,
        '        details=cfg.get("product_details") if isinstance(cfg.get("product_details"),dict) else {}\n',
        '        details=_hca1326_datasheet_details(item,cfg)\n',
        "Datenblattdetails",
    )
    datasheet = replace_once(
        datasheet,
        '            frame(x,y,w,h);image=_hca137_image(_hca138_image_url(source))\n',
        '            frame(x,y,w,h);image=_hca1326_datasheet_image(source)\n',
        "Datenblattbild",
    )
    source = source[:start] + datasheet + source[end:]
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.write_text(patch(args.source.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
