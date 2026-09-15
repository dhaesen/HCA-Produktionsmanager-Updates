#!/usr/bin/env python3
"""Apply HCA v0.13.10 exact one-page customer product datasheets."""
from pathlib import Path
import sys

path=Path(sys.argv[1]);s=path.read_text(encoding="utf-8")

def one(old,new,label):
    global s
    count=s.count(old)
    if count!=1:raise SystemExit(f"{label}: expected exactly one match, got {count}")
    s=s.replace(old,new,1)

# Remove the superseded v0.13.6 quote-tier summary from commercial PDFs.
tier_start=s.index('    if is_quote:\n        tier_quantities = sorted({')
tier_end=s.index('    pages: list[list[dict[str, Any]]] = []',tier_start)
s=s[:tier_start]+s[tier_end:]

helper=r'''
def _hca1310_datasheet_specs(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Create exactly one compact datasheet page for every enabled quote item."""
    specs=[]
    for item in document.get("items") or []:
        cfg=item.get("config") if isinstance(item.get("config"),dict) else {}
        if not cfg.get("datasheet_enabled"):continue
        details=cfg.get("product_details") if isinstance(cfg.get("product_details"),dict) else {}
        title=str(details.get("name") or item.get("description") or "Artikel")
        sku=str(details.get("sku") or item.get("sku") or "")
        commands=["0 0 0 rg"];page_images=[]
        def put(text:Any,x:float,y:float,size:float=7,bold:bool=False)->None:
            commands.append(f"BT /{'F2' if bold else 'F1'} {size:g} Tf 1 0 0 1 {x:g} {y:g} Tm ({_delivery_pdf_escape(text)}) Tj ET")
        def frame(x:float,y:float,w:float,h:float)->None:commands.append(f"0.82 0.82 0.79 RG 0.55 w {x:g} {y:g} {w:g} {h:g} re S")
        def picture(source:Any,x:float,y:float,w:float,h:float,key:str)->bool:
            frame(x,y,w,h);image=_hca137_image(_hca138_image_url(source))
            if not image:return False
            ix,iy,iw,ih=_hca137_fit(image,(x+3,y+3,w-6,h-6));commands.append(f"q {iw:g} 0 0 {ih:g} {ix:g} {iy:g} cm /{key} Do Q");page_images.append({"name":key,**image});return True
        put("ARTIKELDATENBLATT",46,672,15,True);put(title,46,650,11,True)
        selected=[]
        for source in cfg.get("datasheet_images") or []:
            source=_hca138_image_url(source)
            if source and source not in selected:selected.append(source)
        product_images=[]
        for source in cfg.get("product_images") or []:
            source=_hca138_image_url(source)
            if source and source not in product_images:product_images.append(source)
        main=_hca138_image_url(details.get("main_image")) or (selected[0] if selected else "") or (product_images[0] if product_images else "")
        put("HAUPTBILD",46,630,7,True);picture(main,46,438,238,184,"MAIN")
        put("EIGENSCHAFTEN",306,630,7,True);frame(306,438,243,184)
        facts=[]
        if sku:facts.append(("Artikelnummer",sku))
        manufacturer=str(details.get("manufacturer") or "").strip()
        if manufacturer:facts.append(("Hersteller / Marke",manufacturer))
        if details.get("weight"):facts.append(("Gewicht",str(details.get("weight"))+" kg"))
        dimensions=details.get("dimensions") if isinstance(details.get("dimensions"),dict) else {}
        dims=" x ".join(str(dimensions.get(k) or "").strip() for k in ("length","width","height") if str(dimensions.get(k) or "").strip())
        if dims:facts.append(("Maße",dims+" cm"))
        categories=", ".join(str(x) for x in details.get("categories") or [])
        if categories:facts.append(("Produktgruppe",categories))
        for attr in details.get("attributes") or []:
            if isinstance(attr,dict) and str(attr.get("name") or "").strip() and str(attr.get("value") or "").strip():facts.append((str(attr["name"]),str(attr["value"])))
        y=607
        for label,value in facts:
            wrapped=_delivery_wrap(label+": "+value,48)
            for line_no,line in enumerate(wrapped[:2]):put(line,314,y,6.2,line_no==0);y-=8
            if y<524:break
        description=_hca137_plain_text(details.get("description") or details.get("short_description") or "")
        if description and y>=510:
            put("Beschreibung",314,y-2,6.5,True);y-=12
            desc=[]
            for paragraph in description.splitlines():desc.extend(_delivery_wrap(paragraph,51))
            for line in desc[:max(0,int((y-447)/7))]:put(line,314,y,5.8);y-=7
        gallery=[]
        sources=[*selected,*(details.get("gallery_images") if isinstance(details.get("gallery_images"),list) else []),*product_images]
        for source in sources:
            source=_hca138_image_url(source)
            if source and source!=main and source not in gallery:gallery.append(source)
        gallery=gallery[:5];put("GALERIEBILDER",46,424,7,True)
        if gallery:
            cell=46
            for index,source in enumerate(gallery):picture(source,46+index*(cell+2),356,cell,60,f"G{index+1}")
        else:put("Keine weiteren Galeriebilder hinterlegt.",46,397,6)
        colors=details.get("color_images") if isinstance(details.get("color_images"),list) else []
        put("FARBVARIANTEN",306,424,7,True)
        if colors:
            count=len(colors);cols=min(8,count);rows=(count+cols-1)//cols;cell_w=243/cols;cell_h=62/max(1,rows)
            for index,row in enumerate(colors):
                col=index%cols;rr=index//cols;x=306+col*cell_w;y0=354+(rows-1-rr)*cell_h
                picture(row,x,y0+9,max(10,cell_w-3),max(10,cell_h-11),f"C{index+1}")
                name=str(row.get("name") or "Farbe") if isinstance(row,dict) else "Farbe";put(name[:12],x,y0+2,4.2)
        else:put("Keine Farbvarianten hinterlegt.",306,397,6)
        wizard=cfg.get("wizard_config") if isinstance(cfg.get("wizard_config"),dict) else {}
        areas=wizard.get("areas") if isinstance(wizard.get("areas"),list) else details.get("refinement_areas")
        areas=areas if isinstance(areas,list) else []
        put("MÖGLICHE VEREDELUNGEN",46,334,8,True);frame(46,106,503,216)
        if not areas:put("Für diesen Artikel sind keine produktspezifischen Veredelungspositionen hinterlegt.",56,298,7)
        else:
            cols=2;rows=(len(areas)+1)//2;card_h=206/max(1,rows)
            for index,area in enumerate(areas):
                if not isinstance(area,dict):continue
                col=index%2;rr=index//2;x=52+col*248;y0=112+(rows-1-rr)*card_h
                if index>=2:commands.append(f"0.9 0.9 0.88 RG 0.35 w {x:g} {y0+card_h:g} 241 0 re S")
                source=_hca138_image_url(area)
                if not source and isinstance(area.get("images"),list) and area["images"]:source=_hca138_image_url(area["images"][0])
                image_size=max(20,min(54,card_h-12));picture(source,x,y0+5,image_size,image_size,f"P{index+1}")
                tx=x+image_size+8;title_y=y0+card_h-14
                put(str(area.get("name") or area.get("position") or "Veredelungsposition")[:38],tx,title_y,6.6,True)
                print_area=area.get("print_area") if isinstance(area.get("print_area"),dict) else {}
                size=" x ".join(str(print_area.get(k) or "").strip() for k in ("width","height") if str(print_area.get(k) or "").strip())
                methods=", ".join(_hca138_method_names(area.get("assignments"))) or "gemäß Produktkonfiguration"
                info=(("Max. Druckfläche: "+size+" mm · ") if size else "")+"Veredelungsarten: "+methods
                max_lines=max(1,int((card_h-25)/7))
                for line_no,line in enumerate(_delivery_wrap(info,34)[:max_lines]):put(line,tx,title_y-10-line_no*7,5.3)
        specs.append({"body":"\n".join(commands).encode("cp1252","replace"),"first":False,"images":page_images})
    return specs


'''
one('def _hca137_quote_pdf(page_contents: list[bytes], document: dict[str, Any]) -> bytes:\n',helper+'def _hca137_quote_pdf(page_contents: list[bytes], document: dict[str, Any]) -> bytes:\n',"exact datasheet layout")
one('    datasheets=_hca137_datasheet_specs(document)+_hca138_extra_datasheet_specs(document)\n','    datasheets=_hca1310_datasheet_specs(document)\n',"single-page datasheet selection")
path.write_text(s,encoding="utf-8")
