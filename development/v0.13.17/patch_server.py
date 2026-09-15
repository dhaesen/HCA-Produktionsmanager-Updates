#!/usr/bin/env python3
"""Repair and validate HCA -> WooCommerce decoration price mappings."""
from pathlib import Path
import sys


path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
start = source.index("def _shop_configuration_from_hca(")
end = source.index('\n@router.get("/mail/settings"', start)

replacement = r'''def _shop_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _shop_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "ja", "on"}


def _shop_text_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", "", str(value or "").strip().lower())


def _shop_configuration_from_hca(raw: dict[str, Any]) -> dict[str, Any]:
    cfg = raw.get("config") if isinstance(raw.get("config"), dict) else {}
    steps = cfg.get("production_steps") if isinstance(cfg.get("production_steps"), list) else []
    positions = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        # JSON-/Formulardaten können "false" als Text enthalten. bool("false")
        # ist in Python True und hat bisher gültige Veredelungen entfernt.
        if _shop_truthy(step.get("manual_override")):
            continue
        positions.append({
            "posNumber": index + 1,
            "areaIndex": _shop_int(step.get("area_index"), index),
            "areaId": str(step.get("area_id") or ""),
            "areaName": str(step.get("position") or step.get("area_name") or ""),
            "druckartId": _shop_int(step.get("druckart_id")),
            "druckartLabel": str(step.get("technique_label") or step.get("technique") or ""),
            "colorsCount": max(1, _shop_int(step.get("colors_count"), 1)),
            "costId": _shop_int(step.get("cost_id")),
            "bearbeitungCostId": _shop_int(step.get("bearbeitung_cost_id")),
        })
    return {"color": cfg.get("color") or "", "positions": positions}


def _shop_canonical_configuration(product_id: int, configuration: dict[str, Any], wizard_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve current setup/handling IDs from the read-only Woo wizard data."""
    result = json.loads(json.dumps(configuration, ensure_ascii=False))
    positions = result.get("positions") if isinstance(result.get("positions"), list) else []
    if not positions:
        return result
    if wizard_data is None:
        response = _woo_form_post("/?wc-ajax=wsk_hca_product_config", {"product_id": product_id})
        if not isinstance(response, dict) or not response.get("success"):
            raise RuntimeError("WooCommerce-Produktkonfiguration konnte nicht geladen werden.")
        wizard_data = response.get("data") if isinstance(response.get("data"), dict) else {}
    areas = wizard_data.get("areas") if isinstance(wizard_data.get("areas"), list) else []
    if not areas:
        raise RuntimeError("WooCommerce hat keine Veredelungspositionen für diesen Artikel geliefert.")

    for position in positions:
        if not isinstance(position, dict):
            continue
        area_id = str(position.get("areaId") or "")
        area_index = _shop_int(position.get("areaIndex"), -1)
        area_name = _shop_text_key(position.get("areaName"))
        area = next((row for row in areas if isinstance(row, dict) and area_id and str(row.get("id") or "") == area_id), None)
        if area is None and area_index >= 0:
            area = next((row for row in areas if isinstance(row, dict) and _shop_int(row.get("index"), -2) == area_index), None)
        if area is None and area_name:
            area = next((row for row in areas if isinstance(row, dict) and area_name in {_shop_text_key(row.get("name")), _shop_text_key(row.get("position"))}), None)
        if area is None and len(areas) == 1:
            area = areas[0]
        assignments = area.get("assignments") if isinstance(area, dict) and isinstance(area.get("assignments"), list) else []
        method_id = _shop_int(position.get("druckartId"))
        method_label = _shop_text_key(position.get("druckartLabel"))
        assignment = next((row for row in assignments if isinstance(row, dict) and method_id > 0 and _shop_int(row.get("druckart_id")) == method_id), None)
        if assignment is None and method_label:
            assignment = next((row for row in assignments if isinstance(row, dict) and method_label in {
                _shop_text_key((row.get("method") or {}).get("name") if isinstance(row.get("method"), dict) else ""),
                _shop_text_key((row.get("method") or {}).get("label") if isinstance(row.get("method"), dict) else ""),
                _shop_text_key((row.get("method") or {}).get("code") if isinstance(row.get("method"), dict) else ""),
            }), None)
        if assignment is None and len(assignments) == 1:
            assignment = assignments[0]
        if not isinstance(area, dict) or not isinstance(assignment, dict):
            raise RuntimeError(f"Veredelungsposition {position.get('posNumber') or '?'} konnte nicht eindeutig der WooCommerce-Druckpreisverwaltung zugeordnet werden.")
        position["areaId"] = str(area.get("id") or position.get("areaId") or "")
        position["areaIndex"] = _shop_int(area.get("index"), area_index if area_index >= 0 else 0)
        position["areaName"] = str(area.get("name") or area.get("position") or position.get("areaName") or "")
        position["druckartId"] = _shop_int(assignment.get("druckart_id"))
        position["costId"] = _shop_int(assignment.get("cost_id"))
        position["bearbeitungCostId"] = _shop_int(assignment.get("bearbeitung_cost_id"))
        method = assignment.get("method") if isinstance(assignment.get("method"), dict) else {}
        position["druckartLabel"] = str(method.get("name") or method.get("label") or position.get("druckartLabel") or "")
    return result


def _shop_validate_price_result(configuration: dict[str, Any], result: dict[str, Any]) -> None:
    requested = configuration.get("positions") if isinstance(configuration.get("positions"), list) else []
    if not requested:
        return
    positions = result.get("positions") if isinstance(result.get("positions"), list) else []
    if len(positions) != len(requested):
        raise RuntimeError(f"WooCommerce lieferte {len(positions)} von {len(requested)} Veredelungspreisen.")
    for index, position in enumerate(positions):
        if not isinstance(position, dict):
            raise RuntimeError(f"WooCommerce lieferte für Veredelung {index + 1} keine Preisdaten.")
        values = (
            float(position.get("print_per_item") or 0),
            float(position.get("setup_total") or 0),
            float(position.get("bearbeitung_unit") or 0),
        )
        if not any(value > 0 for value in values):
            sent = requested[index] if isinstance(requested[index], dict) else {}
            raise RuntimeError(
                "WooCommerce lieferte 0,00 EUR für Druck, Einrichtung und Bearbeitung "
                f"(Druckart {sent.get('druckartId') or 0}, Einrichtung {sent.get('costId') or 0}, "
                f"Bearbeitung {sent.get('bearbeitungCostId') or 0})."
            )


@router.post("/business/shop-price", dependencies=auth)
async def business_shop_price(request: Request) -> dict[str, Any]:
    body = await request.json()
    product_id = _shop_int(body.get("product_id"))
    quantity = max(1, _shop_int(body.get("quantity"), 1))
    if not product_id:
        raise HTTPException(status_code=400, detail="Produkt-ID fehlt.")
    configuration = body.get("configuration") if isinstance(body.get("configuration"), dict) else _shop_configuration_from_hca(body)
    try:
        if configuration.get("positions"):
            configuration = await asyncio.to_thread(_shop_canonical_configuration, product_id, configuration)
        response = await asyncio.to_thread(
            _woo_form_post,
            "/?wc-ajax=wsk_wak_calculate_price",
            {"product_id": product_id, "qty": quantity, "configuration": configuration},
        )
        if not isinstance(response, dict) or not response.get("success"):
            detail = (response or {}).get("data") if isinstance(response, dict) else ""
            if isinstance(detail, dict):
                detail = detail.get("message") or detail.get("code") or ""
            raise RuntimeError(str(detail or "Shopkalkulation fehlgeschlagen"))
        calculated = response.get("data") if isinstance(response.get("data"), dict) else {}
        _shop_validate_price_result(configuration, calculated)
        return {
            "ok": True,
            "product_id": product_id,
            "qty": quantity,
            "base_unit": round(float(calculated.get("base") or 0), 4),
            "unit_netto": round(float(calculated.get("unit_netto") or 0), 4),
            "article_total": round(float(calculated.get("article_total") or 0), 2),
            "print_total": round(float(calculated.get("print_total") or 0), 2),
            "setup_total": round(float(calculated.get("setup_total") or 0), 2),
            "setup_discount_total": round(float(calculated.get("setup_discount_total") or 0), 2),
            "handling_total": round(float(calculated.get("bearbeitung_total") or 0), 2),
            "normal_total": round(float(calculated.get("normal_total") or calculated.get("total_netto") or 0), 2),
            "total_netto": round(float(calculated.get("total_netto") or 0), 2),
            "positions": calculated.get("positions") or [],
            "bundle_applied": calculated.get("bundle_applied"),
            "bundle_suggestion": calculated.get("bundle_suggestion"),
            "source": "woocommerce-wizard",
            "resolved_configuration": configuration,
        }
    except HTTPException:
        raise
    except Exception as exc:
        if isinstance(configuration, dict) and configuration.get("positions"):
            raise HTTPException(status_code=502, detail=f"Veredelungspreise konnten nicht geladen werden: {exc}") from exc
        try:
            product = await asyncio.to_thread(_woo_json, f"/products/{product_id}")
            price = float((product or {}).get("price") or 0)
            return {"ok": True, "product_id": product_id, "qty": quantity, "base_unit": price, "unit_netto": price, "article_total": round(price * quantity, 2), "print_total": 0, "setup_total": 0, "handling_total": 0, "total_netto": round(price * quantity, 2), "positions": [], "source": "woocommerce-product", "warning": str(exc)}
        except Exception as fallback_error:
            raise HTTPException(status_code=502, detail=f"Shoppreis konnte nicht geladen werden: {fallback_error}") from fallback_error

'''

path.write_text(source[:start] + replacement + source[end:], encoding="utf-8")
