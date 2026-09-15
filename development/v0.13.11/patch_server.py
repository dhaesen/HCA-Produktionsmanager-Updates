#!/usr/bin/env python3
"""Prevent silent zero refinement prices in HCA v0.13.11."""
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text(encoding="utf-8")
old = '''    except Exception as exc:
        # Sicherer Fallback auf den WooCommerce-Produktpreis, falls ein Produkt den WSK-Rechner nicht nutzt.
        try:
            p=await asyncio.to_thread(_woo_json,f"/products/{pid}")
'''
new = '''    except Exception as exc:
        # Bei gewählten Veredelungen darf ein Ausfall des WSK-Rechners niemals als
        # scheinbar erfolgreicher Artikelpreis mit 0,00-Euro-Veredelungen erscheinen.
        if isinstance(configuration,dict) and configuration.get("positions"):
            raise HTTPException(status_code=502,detail=f"Veredelungspreise konnten nicht vollständig geladen werden: {exc}")
        # Nur bei reinen Produktpositionen ist der WooCommerce-Produktpreis ein zulässiger Fallback.
        try:
            p=await asyncio.to_thread(_woo_json,f"/products/{pid}")
'''
count = source.count(old)
if count != 1:
    raise SystemExit(f"shop-price fallback: expected one match, got {count}")
path.write_text(source.replace(old, new, 1), encoding="utf-8")
