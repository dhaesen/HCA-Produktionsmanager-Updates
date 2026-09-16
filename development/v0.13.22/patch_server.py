#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = ROOT / 'development' / 'v0.13.17' / 'hca_shared.py'


def _v21_patch(text: str) -> str:
    path = ROOT / 'development' / 'v0.13.21' / 'patch_server.py'
    spec = importlib.util.spec_from_file_location('hca_v01321_patch_server', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('v0.13.21 NAS-Patch konnte nicht geladen werden')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.patch_text(text)


OLD_START = '''    rows: list[dict[str, Any]] = []
    position_no = 0
    for item in items:
        item_type = str(item.get("item_type") or "product").strip().lower()
        is_optional = item_type == "optional"
        if item_type == "text":
            position_no += 1
            rows.append({"index": position_no, "sku": "", "lines": _delivery_wrap(str(item.get("description") or ""), 82),
                         "quantity": 0, "unit": "", "unit_price": 0, "net_total": 0, "text": True, "optional": False})
            continue
        config = item.get("config") if isinstance(item.get("config"), dict) else {}
'''
NEW_START = '''    rows: list[dict[str, Any]] = []
    group_no = 0
    for item in items:
        item_type = str(item.get("item_type") or "product").strip().lower()
        is_optional = item_type == "optional"
        config = item.get("config") if isinstance(item.get("config"), dict) else {}
        if any(config.get(key) in (True, 1, "1", "true", "yes", "ja", "on") for key in
               ("quantity_option_generated", "alternative_quantity_generated", "hca_quantity_option")):
            continue
        group_no += 1
        sub_no = 1
        if item_type == "text":
            rows.append({"index": f"{group_no}.{sub_no}", "group": group_no, "sku": "", "lines": _delivery_wrap(str(item.get("description") or ""), 82),
                         "quantity": 0, "unit": "", "unit_price": 0, "net_total": 0, "text": True, "optional": False})
            continue
'''

OLD_PRODUCT = '''        position_no += 1
        rows.append({"index": position_no, "sku": str(item.get("sku") or ""), "lines": wrapped, "quantity": quantity,
                     "unit": str(item.get("unit") or "Stk."), "unit_price": unit_price * discount_factor, "net_total": quantity * unit_price * discount_factor,
                     "text": False, "optional": is_optional})
'''
NEW_PRODUCT = '''        rows.append({"index": f"{group_no}.{sub_no}", "group": group_no, "sku": str(item.get("sku") or ""), "lines": wrapped, "quantity": quantity,
                     "unit": str(item.get("unit") or "Stk."), "unit_price": unit_price * discount_factor, "net_total": quantity * unit_price * discount_factor,
                     "text": False, "optional": is_optional})
'''

OLD_PRINT = '''                position_no += 1
                label = technique + (" · " + " · ".join(refinement_details) if refinement_details else "")
                rows.append({"index": position_no, "sku": "", "lines": _delivery_wrap(label, 47), "quantity": quantity,
                             "unit": "Stk.", "unit_price": print_unit * discount_factor, "net_total": quantity * print_unit * discount_factor,
                             "text": False, "optional": is_optional})
'''
NEW_PRINT = '''                sub_no += 1
                label = technique + (" · " + " · ".join(refinement_details) if refinement_details else "")
                rows.append({"index": f"{group_no}.{sub_no}", "group": group_no, "sku": "", "lines": _delivery_wrap(label, 47), "quantity": quantity,
                             "unit": "Stk.", "unit_price": print_unit * discount_factor, "net_total": quantity * print_unit * discount_factor,
                             "text": False, "optional": is_optional})
'''

OLD_SETUP = '''                position_no += 1
                setup_label = str(step.get("setup_label") or "").strip()
'''
NEW_SETUP = '''                sub_no += 1
                setup_label = str(step.get("setup_label") or "").strip()
'''

OLD_SETUP_ROW = '''                rows.append({"index": position_no, "sku": "", "lines": _delivery_wrap(setup_label, 47), "quantity": 1,
                             "unit": "Pausch.", "unit_price": setup_total, "net_total": setup_total,
                             "text": False, "optional": is_optional})
'''
NEW_SETUP_ROW = '''                rows.append({"index": f"{group_no}.{sub_no}", "group": group_no, "sku": "", "lines": _delivery_wrap(setup_label, 47), "quantity": 1,
                             "unit": "Pausch.", "unit_price": setup_total, "net_total": setup_total,
                             "text": False, "optional": is_optional})
'''

OLD_HANDLING = '''                position_no += 1
                handling_label = "Bearbeitungskosten/Artikel"
'''
NEW_HANDLING = '''                sub_no += 1
                handling_label = "Bearbeitungskosten/Artikel"
'''

OLD_HANDLING_ROW = '''                rows.append({"index": position_no, "sku": "", "lines": _delivery_wrap(handling_label, 47), "quantity": quantity,
                             "unit": "Stk.", "unit_price": handling_unit * discount_factor, "net_total": quantity * handling_unit * discount_factor,
                             "text": False, "optional": is_optional})
'''
NEW_HANDLING_ROW = '''                rows.append({"index": f"{group_no}.{sub_no}", "group": group_no, "sku": "", "lines": _delivery_wrap(handling_label, 47), "quantity": quantity,
                             "unit": "Stk.", "unit_price": handling_unit * discount_factor, "net_total": quantity * handling_unit * discount_factor,
                             "text": False, "optional": is_optional})
'''

OLD_PAGES = '''    pages: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []; used = 0.0
    for row in rows:
        height = 24.0 + max(0, len(row["lines"]) - 1) * 11.0 + (11.0 if row["sku"] else 0.0)
        if current and used + height > 295:
            pages.append(current); current = []; used = 0.0
        current.append(row); used += height
    pages.append(current)
'''
NEW_PAGES = '''    pages: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []; used = 0.0
    grouped_rows: list[list[dict[str, Any]]] = []
    for row in rows:
        if not grouped_rows or grouped_rows[-1][0].get("group") != row.get("group"):
            grouped_rows.append([])
        grouped_rows[-1].append(row)
    def row_height(row: dict[str, Any]) -> float:
        return 24.0 + max(0, len(row["lines"]) - 1) * 11.0 + (11.0 if row["sku"] else 0.0)
    for group_rows in grouped_rows:
        height = sum(row_height(row) for row in group_rows)
        if current and used + height > 295:
            pages.append(current); current = []; used = 0.0
        if height <= 295:
            current.extend(group_rows); used += height
            continue
        for row in group_rows:
            height = row_height(row)
            if current and used + height > 295:
                pages.append(current); current = []; used = 0.0
            current.append(row); used += height
    pages.append(current)
'''

OLD_RENDER = '''        row_top = header_bottom
        for row in page_rows:
            row_height = 24.0 + max(0, len(row["lines"]) - 1) * 11.0 + (11.0 if row["sku"] else 0.0)
            row_bottom = row_top - row_height
            y = row_top - 17
            if row["index"] % 2 == 0:
                commands.append(f"0.985 0.985 0.975 rg 46 {row_bottom:g} 503 {row_height:g} re f 0 0 0 rg")
            put(row["index"], 51, y, 8.2)
            put(row["lines"][0], 80, y, 8.5, True)
            if not row.get("text"):
                put(f'{row["quantity"]:g}', 350, y, 8.5)
                put(row["unit"], 394, y, 8.5)
                unit_price_text = _document_money(row["unit_price"])
                net_total_text = _document_money(row["net_total"])
                if row.get("optional"):
                    unit_price_text = f"({unit_price_text})"
                    net_total_text = f"({net_total_text})"
                put(unit_price_text, 434, y, 7.7)
                put(net_total_text, 491, y, 7.7, True)
            y -= 12
            for line in row["lines"][1:]: put(line, 80, y, 7.8); y -= 11
            if row["sku"]: put(f'Art.-Nr. {row["sku"]}', 80, y, 7); y -= 11
            draw_line(46,row_bottom,549,row_bottom,0.4)
            for x in (46,75,345,390,430,487,549): draw_line(x,row_top,x,row_bottom,0.4)
            row_top = row_bottom
'''
NEW_RENDER = '''        row_top = header_bottom
        for row_index, row in enumerate(page_rows):
            row_height = 24.0 + max(0, len(row["lines"]) - 1) * 11.0 + (11.0 if row["sku"] else 0.0)
            row_bottom = row_top - row_height
            y = row_top - 17
            group = int(row.get("group") or 0)
            last_in_group = row_index == len(page_rows) - 1 or page_rows[row_index + 1].get("group") != row.get("group")
            if group % 2 == 0:
                commands.append(f"0.985 0.985 0.975 rg 46 {row_bottom:g} 503 {row_height:g} re f 0 0 0 rg")
            put(row["index"], 51, y, 8.2)
            put(row["lines"][0], 80, y, 8.5, True)
            if not row.get("text"):
                put(f'{row["quantity"]:g}', 350, y, 8.5)
                put(row["unit"], 394, y, 8.5)
                unit_price_text = _document_money(row["unit_price"])
                net_total_text = _document_money(row["net_total"])
                if row.get("optional"):
                    unit_price_text = f"({unit_price_text})"
                    net_total_text = f"({net_total_text})"
                put(unit_price_text, 434, y, 7.7)
                put(net_total_text, 491, y, 7.7, True)
            y -= 12
            for line in row["lines"][1:]: put(line, 80, y, 7.8); y -= 11
            if row["sku"]: put(f'Art.-Nr. {row["sku"]}', 80, y, 7); y -= 11
            if last_in_group:
                draw_line(46,row_bottom,549,row_bottom,0.7)
            for x in (46,75,345,390,430,487,549): draw_line(x,row_top,x,row_bottom,0.4)
            row_top = row_bottom
'''


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'{label} nicht eindeutig gefunden: {count}')
    return text.replace(old, new)


def patch_text(text: str) -> str:
    text = _v21_patch(text)
    for old, new, label in (
        (OLD_START, NEW_START, 'Positionsstart'),
        (OLD_PRODUCT, NEW_PRODUCT, 'Produktzeile'),
        (OLD_PRINT, NEW_PRINT, 'Veredelungszeile'),
        (OLD_SETUP, NEW_SETUP, 'Einrichtungsnummer'),
        (OLD_SETUP_ROW, NEW_SETUP_ROW, 'Einrichtungszeile'),
        (OLD_HANDLING, NEW_HANDLING, 'Bearbeitungsnummer'),
        (OLD_HANDLING_ROW, NEW_HANDLING_ROW, 'Bearbeitungszeile'),
        (OLD_PAGES, NEW_PAGES, 'Gruppen-Seitenumbruch'),
        (OLD_RENDER, NEW_RENDER, 'Gruppendarstellung'),
    ):
        text = _replace_once(text, old, new, label)
    return text


def main() -> None:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    target = Path(sys.argv[2]) if len(sys.argv) > 2 else source.with_name('hca_shared_v01322.py')
    target.write_text(patch_text(source.read_text(encoding='utf-8')), encoding='utf-8')
    print(target)


if __name__ == '__main__':
    main()
