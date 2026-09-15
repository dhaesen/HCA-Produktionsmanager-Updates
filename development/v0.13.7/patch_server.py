#!/usr/bin/env python3
"""Apply HCA v0.13.7 product metadata and combined quote datasheet PDF support."""
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

helper='''def _hca137_product_details(product: dict[str, Any]) -> dict[str, Any]:
    """Return stable product content used by the HCA search and quote datasheets."""
    images = []
    for row in product.get("images") or []:
        src = str(row.get("src") or "").strip() if isinstance(row, dict) else ""
        if src and src not in images:
            images.append(src)
    attributes = []
    for row in product.get("attributes") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        options = row.get("options") if isinstance(row.get("options"), list) else []
        value = ", ".join(str(x).strip() for x in options if str(x).strip())
        if name and value:
            attributes.append({"name": name, "value": value})
    categories = [str(x.get("name") or "").strip() for x in product.get("categories") or [] if isinstance(x, dict) and str(x.get("name") or "").strip()]
    return {
        "images": images[:10],
        "description": str(product.get("description") or ""),
        "short_description": str(product.get("short_description") or ""),
        "attributes": attributes,
        "categories": categories,
        "permalink": str(product.get("permalink") or ""),
    }


'''
one('def _wsk_product_configs(product: dict[str, Any]) -> list[dict[str, Any]]:\n',helper+'def _wsk_product_configs(product: dict[str, Any]) -> list[dict[str, Any]]:\n',"product detail helper")
one('common = {"product_id": product_id, "name": name, "sku": sku,', 'common = {**_hca137_product_details(product), "product_id": product_id, "name": name, "sku": sku,',"WSK product metadata")
one('return [{\n            "key": f"{product_id}:simple",', 'return [{\n            **_hca137_product_details(product),\n            "key": f"{product_id}:simple",',"simple product metadata")
one('configs.append({\n            "key": f"{product_id}:{color or \'-\'}",', 'configs.append({\n            **_hca137_product_details(product),\n            "key": f"{product_id}:{color or \'-\'}",',"variable product metadata")

pdf_helpers=r'''
_HCA137_IMAGE_CACHE: dict[str, dict[str, Any] | None] = {}


def _hca137_plain_text(value: Any) -> str:
    text = re.sub(r"<\s*br\s*/?>", "\n", str(value or ""), flags=re.I)
    text = re.sub(r"</\s*(p|div|li|h[1-6])\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    return "\n".join(re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if re.sub(r"\s+", " ", line).strip())


def _hca137_jpeg_info(raw: bytes) -> tuple[int, int, int] | None:
    if not raw.startswith(b"\xff\xd8"):
        return None
    pos = 2
    while pos + 9 < len(raw):
        if raw[pos] != 0xFF:
            pos += 1
            continue
        marker = raw[pos + 1]
        pos += 2
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            continue
        if pos + 2 > len(raw):
            break
        size = int.from_bytes(raw[pos:pos + 2], "big")
        if size < 2 or pos + size > len(raw):
            break
        if marker in (0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF):
            height = int.from_bytes(raw[pos + 3:pos + 5], "big")
            width = int.from_bytes(raw[pos + 5:pos + 7], "big")
            components = int(raw[pos + 7])
            return width, height, components
        pos += size
    return None


def _hca137_png_info(raw: bytes) -> tuple[int, int, int, bytes] | None:
    if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) < 33:
        return None
    import struct
    width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", raw[16:29])
    if bit_depth != 8 or interlace != 0 or color_type not in (0, 2):
        return None
    chunks=[]; pos=8
    while pos+12<=len(raw):
        length=int.from_bytes(raw[pos:pos+4],"big"); kind=raw[pos+4:pos+8]; data=raw[pos+8:pos+8+length]
        if kind==b"IDAT": chunks.append(data)
        pos += 12 + length
        if kind==b"IEND": break
    if not chunks:
        return None
    return width, height, 1 if color_type==0 else 3, b"".join(chunks)


def _hca137_image(url: str) -> dict[str, Any] | None:
    url = str(url or "").strip()
    if not url or not url.lower().startswith(("http://","https://")):
        return None
    if url in _HCA137_IMAGE_CACHE:
        return _HCA137_IMAGE_CACHE[url]
    result = None
    try:
        import urllib.request
        request = urllib.request.Request(url, headers={"User-Agent":"HCA-Produktionsmanager/0.13.7","Accept":"image/jpeg,image/png,image/*;q=0.5"})
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read(12 * 1024 * 1024 + 1)
        if len(raw) > 12 * 1024 * 1024:
            raise ValueError("Artikelbild ist größer als 12 MB")
        jpeg = _hca137_jpeg_info(raw)
        if jpeg:
            width,height,components=jpeg
            result={"width":width,"height":height,"colorspace":"/DeviceGray" if components==1 else "/DeviceRGB","filter":"/DCTDecode","data":raw,"decode":""}
        else:
            png = _hca137_png_info(raw)
            if png:
                width,height,colors,data=png
                result={"width":width,"height":height,"colorspace":"/DeviceGray" if colors==1 else "/DeviceRGB","filter":"/FlateDecode","data":data,
                        "decode":f" /DecodeParms << /Predictor 15 /Colors {colors} /BitsPerComponent 8 /Columns {width} >>"}
        if result is None:
            try:
                from PIL import Image
                import io
                source=Image.open(io.BytesIO(raw)).convert("RGB")
                if source.width>1800 or source.height>1800:
                    source.thumbnail((1800,1800))
                output=io.BytesIO(); source.save(output,format="JPEG",quality=88,optimize=True)
                result={"width":source.width,"height":source.height,"colorspace":"/DeviceRGB","filter":"/DCTDecode","data":output.getvalue(),"decode":""}
            except Exception:
                result=None
    except Exception:
        result=None
    if len(_HCA137_IMAGE_CACHE) >= 64:
        _HCA137_IMAGE_CACHE.pop(next(iter(_HCA137_IMAGE_CACHE)), None)
    _HCA137_IMAGE_CACHE[url]=result
    return result


def _hca137_fit(image: dict[str, Any], box: tuple[float,float,float,float]) -> tuple[float,float,float,float]:
    x,y,w,h=box
    iw=max(1,float(image["width"])); ih=max(1,float(image["height"]))
    scale=min(w/iw,h/ih); rw=iw*scale; rh=ih*scale
    return x+(w-rw)/2,y+(h-rh)/2,rw,rh


def _hca137_datasheet_specs(document: dict[str, Any]) -> list[dict[str, Any]]:
    specs=[]
    for item in document.get("items") or []:
        cfg=item.get("config") if isinstance(item.get("config"),dict) else {}
        if not cfg.get("datasheet_enabled"):
            continue
        details=cfg.get("product_details") if isinstance(cfg.get("product_details"),dict) else {}
        name=str(details.get("name") or item.get("description") or "Artikel")
        sku=str(details.get("sku") or item.get("sku") or "")
        lines=[]
        for label,value in (
            ("Artikelnummer",sku),("Hersteller",details.get("manufacturer")),("Lieferant",details.get("supplier")),
            ("Gewicht",str(details.get("weight") or "")+(" kg" if details.get("weight") else "")),
            ("Produktgruppen",", ".join(str(x) for x in details.get("categories") or [])),
        ):
            if str(value or "").strip(): lines.append(f"{label}: {value}")
        dimensions=details.get("dimensions") if isinstance(details.get("dimensions"),dict) else {}
        dims=" × ".join(str(dimensions.get(k) or "").strip() for k in ("length","width","height") if str(dimensions.get(k) or "").strip())
        if dims: lines.append("Maße: "+dims+" cm")
        for attr in details.get("attributes") or []:
            if isinstance(attr,dict) and str(attr.get("name") or "").strip() and str(attr.get("value") or "").strip():
                lines.append(f"{attr['name']}: {attr['value']}")
        description=_hca137_plain_text(details.get("description") or details.get("short_description") or "")
        description_lines=[]
        for paragraph in description.splitlines():
            description_lines.extend(_delivery_wrap(paragraph,92))
        content=[("detail",x) for x in lines]+([("space","")] if lines and description_lines else [])+[("description",x) for x in description_lines]
        chunks=[content[i:i+34] for i in range(0,len(content),34)] or [[]]
        for chunk_index,chunk in enumerate(chunks):
            commands=["0 0 0 rg"]
            def put(text: Any,x:float,y:float,size:float=9,bold:bool=False)->None:
                commands.append(f"BT /{'F2' if bold else 'F1'} {size:g} Tf 1 0 0 1 {x:g} {y:g} Tm ({_delivery_pdf_escape(text)}) Tj ET")
            put("ARTIKELDATENBLATT",46,672,15,True)
            put(name,46,646,12,True)
            if sku: put("Art.-Nr. "+sku,46,628,9)
            if chunk_index: put("Fortsetzung",470,646,8,True)
            y=600
            for kind,line in chunk:
                if kind=="space": y-=8; continue
                put(line,46,y,8.5,kind=="detail"); y-=13
            specs.append({"body":"\n".join(commands).encode("cp1252","replace"),"first":False,"images":[]})
        urls=[]
        for url in cfg.get("datasheet_images") or []:
            url=str(url or "").strip()
            if url and url not in urls: urls.append(url)
        urls=urls[:5]
        loaded=[image for image in (_hca137_image(url) for url in urls) if image]
        if loaded:
            commands=["0 0 0 rg","BT /F2 15 Tf 1 0 0 1 46 672 Tm (PRODUKTBILDER) Tj ET",
                      f"BT /F2 11 Tf 1 0 0 1 46 646 Tm ({_delivery_pdf_escape(name)}) Tj ET"]
            if len(loaded)==1: boxes=[(46,150,503,450)]
            elif len(loaded)==2: boxes=[(46,180,245,400),(304,180,245,400)]
            elif len(loaded)<=4: boxes=[(46,380,245,210),(304,380,245,210),(46,145,245,210),(304,145,245,210)][:len(loaded)]
            else: boxes=[(46,410,503,180),(46,255,245,130),(304,255,245,130),(46,105,245,130),(304,105,245,130)]
            images=[]
            for index,(image,box) in enumerate(zip(loaded,boxes),1):
                x,y,w,h=_hca137_fit(image,box); name_id=f"IMG{index}"
                commands.append(f"0.82 0.82 0.80 RG 0.5 w {box[0]:g} {box[1]:g} {box[2]:g} {box[3]:g} re S")
                commands.append(f"q {w:g} 0 0 {h:g} {x:g} {y:g} cm /{name_id} Do Q")
                images.append({"name":name_id,**image})
            specs.append({"body":"\n".join(commands).encode("cp1252","replace"),"first":False,"images":images})
    return specs


def _hca137_build_pdf(page_specs: list[dict[str, Any]]) -> bytes:
    asset_dir=Path(__file__).resolve().parent/"assets"
    first_image=(asset_dir/"briefpapier-seite1.jpg").read_bytes()
    continuation_image=(asset_dir/"briefpapier-seite2.jpg").read_bytes()
    objects: dict[int,bytes]={
        1:b"<< /Type /Catalog /Pages 2 0 R >>",
        3:f"<< /Type /XObject /Subtype /Image /Width 2480 /Height 3508 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(first_image)} >>\nstream\n".encode()+first_image+b"\nendstream",
        4:f"<< /Type /XObject /Subtype /Image /Width 2480 /Height 3508 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(continuation_image)} >>\nstream\n".encode()+continuation_image+b"\nendstream",
        5:b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        6:b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    }
    next_id=7; pages=[]
    for spec in page_specs:
        page_id=next_id; content_id=next_id+1; next_id+=2; image_refs=[]
        for image in spec.get("images") or []:
            image_id=next_id; next_id+=1; data=image["data"]
            objects[image_id]=(f"<< /Type /XObject /Subtype /Image /Width {image['width']} /Height {image['height']} /ColorSpace {image['colorspace']} /BitsPerComponent 8 /Filter {image['filter']}{image.get('decode','')} /Length {len(data)} >>\nstream\n".encode()+data+b"\nendstream")
            image_refs.append((image["name"],image_id))
        pages.append((page_id,content_id,spec,image_refs))
    objects[2]=("<< /Type /Pages /Kids ["+" ".join(f"{p[0]} 0 R" for p in pages)+f"] /Count {len(pages)} >>").encode()
    total=len(pages)
    for page_no,(page_id,content_id,spec,image_refs) in enumerate(pages,1):
        bg=3 if spec.get("first") else 4
        body=spec["body"].decode("cp1252","replace")
        body=re.sub(r"BT /F1 7 Tf 1 0 0 1 490 88 Tm \(Seite .*?\) Tj ET","",body)
        prefix=b"q 595.276 0 0 841.89 0 0 cm /BG Do Q\n"
        footer=("\n".join(_letterhead_footer_commands(page_no))+"\n").encode("cp1252","replace")
        number=f"BT /F1 7 Tf 1 0 0 1 490 88 Tm (Seite {page_no} von {total}) Tj ET\n".encode("cp1252")
        content=prefix+footer+body.encode("cp1252","replace")+b"\n"+number
        xobjects=" ".join([f"/BG {bg} 0 R"]+[f"/{name} {oid} 0 R" for name,oid in image_refs])
        objects[page_id]=f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595.276 841.89] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> /XObject << {xobjects} >> >> /Contents {content_id} 0 R >>".encode()
        objects[content_id]=f"<< /Length {len(content)} >>\nstream\n".encode()+content+b"\nendstream"
    max_id=max(objects)
    result=bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"); offsets=[0]
    for oid in range(1,max_id+1):
        offsets.append(len(result)); result.extend(f"{oid} 0 obj\n".encode()); result.extend(objects[oid]); result.extend(b"\nendobj\n")
    xref=len(result); result.extend(f"xref\n0 {max_id+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer\n<< /Size {max_id+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(result)


def _hca137_quote_pdf(page_contents: list[bytes], document: dict[str, Any]) -> bytes:
    datasheets=_hca137_datasheet_specs(document)
    if not datasheets:
        return _letterhead_pdf(page_contents)
    document_specs=[{"body":body,"first":index==0,"images":[]} for index,body in enumerate(page_contents)]
    return _hca137_build_pdf(document_specs+datasheets)


'''
one('def _commercial_pdf_bytes(kind: str, document: dict[str, Any], address: dict[str, Any]) -> bytes:\n',pdf_helpers+'def _commercial_pdf_bytes(kind: str, document: dict[str, Any], address: dict[str, Any]) -> bytes:\n',"datasheet PDF helpers")
start=s.index('def _commercial_pdf_bytes(')
end=s.index('\n\n@router.post("/sales/quotes/preview"',start)
block=s[start:end]
old='    return _letterhead_pdf(page_contents)'
if block.count(old)!=1:
    raise SystemExit(f"commercial PDF return: expected one match, got {block.count(old)}")
block=block.replace(old,'    return _hca137_quote_pdf(page_contents, document) if is_quote else _letterhead_pdf(page_contents)',1)
s=s[:start]+block+s[end:]

path.write_text(s,encoding="utf-8")
