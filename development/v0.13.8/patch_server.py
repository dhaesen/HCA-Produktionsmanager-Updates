#!/usr/bin/env python3
"""Apply HCA v0.13.8 customer-facing product visuals and datasheet corrections."""
from pathlib import Path
import sys

path=Path(sys.argv[1])
s=path.read_text(encoding="utf-8")

def one(old,new,label):
    global s
    count=s.count(old)
    if count!=1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    s=s.replace(old,new,1)

visual_helper='''def _hca138_product_visuals(product: dict[str, Any]) -> dict[str, Any]:
    """Return customer-facing main, gallery, colour and refinement images."""
    product_images=[]
    for row in product.get("images") or []:
        src=str(row.get("src") or "").strip() if isinstance(row,dict) else ""
        if src and src not in product_images:
            product_images.append(src)
    meta=_meta_dict(product)
    colors=[]
    for row in _as_data(meta.get("werbeartikel_colors"),[]) or []:
        if not isinstance(row,dict):
            continue
        name=str(row.get("name") or row.get("color") or "").strip()
        image=str(row.get("image") or row.get("image_url") or "").strip()
        key=(name,image)
        if (name or image) and key not in [(x["name"],x["image"]) for x in colors]:
            colors.append({"name":name,"image":image,"image_id":row.get("image_id"),"erp_code":str(row.get("CodeERP") or row.get("erp_code") or "").strip(),"hex":str(row.get("hex") or row.get("color_hex") or "").strip()})
    areas=[]
    for row in _as_data(meta.get("werbeartikel_areas"),[]) or []:
        if not isinstance(row,dict):
            continue
        raw_images=row.get("images") if isinstance(row.get("images"),list) else []
        images=[]
        for value in [row.get("image"),*raw_images]:
            src=str(value.get("src") or value.get("url") or "").strip() if isinstance(value,dict) else str(value or "").strip()
            if src and src not in images:
                images.append(src)
        areas.append({"id":row.get("id"),"name":str(row.get("name") or row.get("position") or "").strip(),"position":str(row.get("position") or "").strip(),"image":images[0] if images else "","images":images,"print_area":row.get("print_area") if isinstance(row.get("print_area"),dict) else {},"assignments":row.get("assignments") if isinstance(row.get("assignments"),list) else []})
    return {"main_image":product_images[0] if product_images else "","gallery_images":product_images[1:10],"color_images":colors,"refinement_areas":areas}


'''
one('def _wsk_product_configs(product: dict[str, Any]) -> list[dict[str, Any]]:\n',visual_helper+'def _wsk_product_configs(product: dict[str, Any]) -> list[dict[str, Any]]:\n',"visual metadata helper")
one('        "permalink": str(product.get("permalink") or ""),\n    }\n\n\ndef _hca138_product_visuals', '        "permalink": str(product.get("permalink") or ""),\n        **_hca138_product_visuals(product),\n    }\n\n\ndef _hca138_product_visuals',"attach visual metadata")
one('("Artikelnummer",sku),("Hersteller",details.get("manufacturer")),("Lieferant",details.get("supplier")),','("Artikelnummer",sku),("Hersteller / Marke",details.get("manufacturer")),',"remove supplier from datasheet")
one('BT /F2 15 Tf 1 0 0 1 46 672 Tm (PRODUKTBILDER) Tj ET','BT /F2 15 Tf 1 0 0 1 46 672 Tm (HAUPTBILD UND PRODUKTBILDER) Tj ET',"product image heading")

extras=r'''
def _hca138_image_url(value: Any) -> str:
    if isinstance(value,dict):
        return str(value.get("image") or value.get("src") or value.get("url") or "").strip()
    return str(value or "").strip()


def _hca138_method_names(assignments: Any) -> list[str]:
    names=[]
    for assignment in assignments if isinstance(assignments,list) else []:
        if not isinstance(assignment,dict):
            continue
        candidates=[]
        method=assignment.get("method")
        if isinstance(method,dict): candidates.append(method)
        elif isinstance(method,list): candidates.extend(x for x in method if isinstance(x,dict))
        for row in candidates:
            value=str(row.get("name") or row.get("label") or row.get("code") or "").strip()
            if value and value not in names: names.append(value)
        if not candidates:
            value=str(assignment.get("druckart_name") or assignment.get("druckart_code") or assignment.get("druckart_id") or "").strip()
            if value and value not in names: names.append(value)
    return names


def _hca138_extra_datasheet_specs(document: dict[str, Any]) -> list[dict[str, Any]]:
    specs=[]
    for item in document.get("items") or []:
        cfg=item.get("config") if isinstance(item.get("config"),dict) else {}
        if not cfg.get("datasheet_enabled"):
            continue
        details=cfg.get("product_details") if isinstance(cfg.get("product_details"),dict) else {}
        name=str(details.get("name") or item.get("description") or "Artikel")
        colors=details.get("color_images") if isinstance(details.get("color_images"),list) else []
        for offset in range(0,len(colors),12):
            chunk=colors[offset:offset+12]
            commands=["0 0 0 rg","BT /F2 15 Tf 1 0 0 1 46 672 Tm (FARBVARIANTEN) Tj ET",f"BT /F2 11 Tf 1 0 0 1 46 648 Tm ({_delivery_pdf_escape(name)}) Tj ET"]
            images=[]
            for index,row in enumerate(chunk):
                col=index%3; grid_row=index//3; x=46+col*170; y=470-grid_row*132
                commands.append(f"0.78 0.78 0.75 RG 0.6 w {x:g} {y:g} 158 120 re S")
                src=_hca138_image_url(row); image=_hca137_image(src) if src else None
                if image:
                    image_name=f"C{offset+index+1}"; ix,iy,iw,ih=_hca137_fit(image,(x+8,y+28,142,82))
                    commands.append(f"q {iw:g} 0 0 {ih:g} {ix:g} {iy:g} cm /{image_name} Do Q")
                    images.append({"name":image_name,**image})
                else:
                    commands.append(f"BT /F1 7 Tf 1 0 0 1 {x+55:g} {y+66:g} Tm (Kein Bild) Tj ET")
                label=str(row.get("name") or "Farbvariante") if isinstance(row,dict) else "Farbvariante"
                commands.append(f"BT /F2 8 Tf 1 0 0 1 {x+8:g} {y+10:g} Tm ({_delivery_pdf_escape(label[:35])}) Tj ET")
            specs.append({"body":"\n".join(commands).encode("cp1252","replace"),"first":False,"images":images})
        wizard=cfg.get("wizard_config") if isinstance(cfg.get("wizard_config"),dict) else {}
        areas=wizard.get("areas") if isinstance(wizard.get("areas"),list) else details.get("refinement_areas")
        areas=areas if isinstance(areas,list) else []
        for offset in range(0,len(areas),3):
            chunk=areas[offset:offset+3]
            commands=["0 0 0 rg","BT /F2 15 Tf 1 0 0 1 46 672 Tm (MOEGLICHE VEREDELUNGEN) Tj ET",f"BT /F2 11 Tf 1 0 0 1 46 648 Tm ({_delivery_pdf_escape(name)}) Tj ET"]
            images=[]
            for index,area in enumerate(chunk):
                if not isinstance(area,dict): continue
                y=462-index*170
                commands.append(f"0.78 0.78 0.75 RG 0.6 w 46 {y:g} 503 152 re S")
                source=_hca138_image_url(area)
                if not source and isinstance(area.get("images"),list) and area["images"]: source=_hca138_image_url(area["images"][0])
                image=_hca137_image(source) if source else None
                if image:
                    image_name=f"P{offset+index+1}"; ix,iy,iw,ih=_hca137_fit(image,(56,y+16,120,112))
                    commands.append(f"q {iw:g} 0 0 {ih:g} {ix:g} {iy:g} cm /{image_name} Do Q")
                    images.append({"name":image_name,**image})
                title=str(area.get("name") or area.get("position") or "Veredelungsposition")
                commands.append(f"BT /F2 10 Tf 1 0 0 1 190 {y+124:g} Tm ({_delivery_pdf_escape(title)}) Tj ET")
                print_area=area.get("print_area") if isinstance(area.get("print_area"),dict) else {}
                size=" x ".join(str(print_area.get(k) or "").strip() for k in ("width","height") if str(print_area.get(k) or "").strip())
                if size: commands.append(f"BT /F1 8 Tf 1 0 0 1 190 {y+106:g} Tm (Max. Druckflaeche: {_delivery_pdf_escape(size)} mm) Tj ET")
                methods=_hca138_method_names(area.get("assignments"))
                lines=_delivery_wrap("Veredelungsarten: "+(", ".join(methods) if methods else "gemaess Produktkonfiguration"),56)
                for line_no,line in enumerate(lines[:5]):
                    commands.append(f"BT /F1 8 Tf 1 0 0 1 190 {y+86-line_no*14:g} Tm ({_delivery_pdf_escape(line)}) Tj ET")
            specs.append({"body":"\n".join(commands).encode("cp1252","replace"),"first":False,"images":images})
    return specs


'''
one('def _hca137_quote_pdf(page_contents: list[bytes], document: dict[str, Any]) -> bytes:\n',extras+'def _hca137_quote_pdf(page_contents: list[bytes], document: dict[str, Any]) -> bytes:\n',"extra datasheet pages")
one('    datasheets=_hca137_datasheet_specs(document)\n','    datasheets=_hca137_datasheet_specs(document)+_hca138_extra_datasheet_specs(document)\n',"include visual datasheet pages")

path.write_text(s,encoding="utf-8")
