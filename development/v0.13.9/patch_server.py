#!/usr/bin/env python3
"""Apply HCA v0.13.9 compact single-page product datasheets."""
from pathlib import Path
import sys

path=Path(sys.argv[1]); s=path.read_text(encoding="utf-8")

def one(old,new,label):
    global s
    count=s.count(old)
    if count!=1: raise SystemExit(f"{label}: expected exactly one match, got {count}")
    s=s.replace(old,new,1)

helper=r'''
def _hca139_datasheet_specs(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Build exactly one compact customer-facing PDF page per selected article."""
    specs=[]
    for item in document.get("items") or []:
        cfg=item.get("config") if isinstance(item.get("config"),dict) else {}
        if not cfg.get("datasheet_enabled"): continue
        details=cfg.get("product_details") if isinstance(cfg.get("product_details"),dict) else {}
        name=str(details.get("name") or item.get("description") or "Artikel")
        sku=str(details.get("sku") or item.get("sku") or "")
        commands=["0 0 0 rg"]; images=[]
        def put(text: Any,x:float,y:float,size:float=8,bold:bool=False)->None:
            commands.append(f"BT /{'F2' if bold else 'F1'} {size:g} Tf 1 0 0 1 {x:g} {y:g} Tm ({_delivery_pdf_escape(text)}) Tj ET")
        def draw(source: Any,box: tuple[float,float,float,float],image_name: str)->bool:
            image=_hca137_image(_hca138_image_url(source))
            commands.append(f"0.82 0.82 0.79 RG 0.5 w {box[0]:g} {box[1]:g} {box[2]:g} {box[3]:g} re S")
            if not image: return False
            x,y,w,h=_hca137_fit(image,box);commands.append(f"q {w:g} 0 0 {h:g} {x:g} {y:g} cm /{image_name} Do Q");images.append({"name":image_name,**image});return True
        put("ARTIKELDATENBLATT",46,672,15,True);put(name,46,650,11,True)
        selected=[]
        for source in cfg.get("datasheet_images") or []:
            source=_hca138_image_url(source)
            if source and source not in selected:selected.append(source)
        main=_hca138_image_url(details.get("main_image")) or (selected[0] if selected else "")
        draw(main,(46,430,238,195),"MAIN")
        put("EIGENSCHAFTEN",306,622,9,True)
        facts=[]
        if sku:facts.append("Artikelnummer: "+sku)
        manufacturer=str(details.get("manufacturer") or "").strip()
        if manufacturer:facts.append("Hersteller / Marke: "+manufacturer)
        if details.get("weight"):facts.append("Gewicht: "+str(details.get("weight"))+" kg")
        dimensions=details.get("dimensions") if isinstance(details.get("dimensions"),dict) else {}
        dims=" x ".join(str(dimensions.get(k) or "").strip() for k in ("length","width","height") if str(dimensions.get(k) or "").strip())
        if dims:facts.append("Maße: "+dims+" cm")
        categories=", ".join(str(x) for x in details.get("categories") or [])
        if categories:facts.append("Produktgruppe: "+categories)
        for attr in details.get("attributes") or []:
            if isinstance(attr,dict) and str(attr.get("name") or "").strip() and str(attr.get("value") or "").strip():facts.append(str(attr["name"])+": "+str(attr["value"]))
        detail_lines=[]
        for fact in facts:detail_lines.extend(_delivery_wrap(fact,49))
        description=_hca137_plain_text(details.get("description") or details.get("short_description") or "")
        if description:
            detail_lines.append("")
            for paragraph in description.splitlines():detail_lines.extend(_delivery_wrap(paragraph,49))
        for line_no,line in enumerate(detail_lines[:24]):put(line,306,604-line_no*7.2,6.3,line_no<len(facts) and ":" in line)
        galleries=[]
        for source in [*selected,*(details.get("gallery_images") or [])]:
            source=_hca138_image_url(source)
            if source and source!=main and source not in galleries:galleries.append(source)
        galleries=galleries[:5]
        put("GALERIEBILDER",46,412,8,True)
        for index,source in enumerate(galleries):draw(source,(46+index*48,352,43,52),f"G{index+1}")
        colors=details.get("color_images") if isinstance(details.get("color_images"),list) else []
        if colors:
            put("FARBVARIANTEN",306,412,8,True)
            count=len(colors);cols=min(8,max(1,count));rows=(count+cols-1)//cols;cell_w=243/cols;cell_h=min(55,58/max(1,rows))
            for index,row in enumerate(colors):
                col=index%cols;rr=index//cols;x=306+col*cell_w;y=350+(rows-1-rr)*cell_h
                draw(row,(x,y+9,cell_w-4,max(12,cell_h-12)),f"C{index+1}")
                label=str(row.get("name") or "Farbe") if isinstance(row,dict) else "Farbe";put(label[:15],x,y+2,4.5)
        wizard=cfg.get("wizard_config") if isinstance(cfg.get("wizard_config"),dict) else {}
        areas=wizard.get("areas") if isinstance(wizard.get("areas"),list) else details.get("refinement_areas")
        areas=areas if isinstance(areas,list) else []
        put("MÖGLICHE VEREDELUNGEN",46,326,9,True)
        if not areas:put("Für diesen Artikel sind keine produktspezifischen Veredelungspositionen hinterlegt.",46,309,7)
        else:
            cols=2;rows=(len(areas)+1)//2;card_h=min(66,190/max(1,rows))
            for index,area in enumerate(areas):
                if not isinstance(area,dict):continue
                col=index%2;rr=index//2;x=46+col*254;y=292-rr*card_h-card_h
                commands.append(f"0.84 0.84 0.81 RG 0.5 w {x:g} {y:g} 245 {card_h-5:g} re S")
                source=_hca138_image_url(area)
                if not source and isinstance(area.get("images"),list) and area["images"]:source=_hca138_image_url(area["images"][0])
                image_w=min(52,card_h-13);draw(source,(x+5,y+5,image_w,card_h-15),f"P{index+1}")
                tx=x+image_w+11;put(str(area.get("name") or area.get("position") or "Veredelungsposition")[:38],tx,y+card_h-19,7,True)
                methods=", ".join(_hca138_method_names(area.get("assignments"))) or "gemäß Produktkonfiguration"
                for line_no,line in enumerate(_delivery_wrap("Veredelungsarten: "+methods,36)[:3]):put(line,tx,y+card_h-31-line_no*8,5.8)
        specs.append({"body":"\n".join(commands).encode("cp1252","replace"),"first":False,"images":images})
    return specs


'''
one('def _hca137_quote_pdf(page_contents: list[bytes], document: dict[str, Any]) -> bytes:\n',helper+'def _hca137_quote_pdf(page_contents: list[bytes], document: dict[str, Any]) -> bytes:\n',"single-page datasheet helper")
one('    datasheets=_hca137_datasheet_specs(document)+_hca138_extra_datasheet_specs(document)\n','    datasheets=_hca139_datasheet_specs(document)\n',"use single-page datasheets")
path.write_text(s,encoding="utf-8")
