#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_SOURCE=ROOT/'development'/'v0.13.17'/'hca_shared.py'

OLD_VISUAL='''    product_images=[]
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
'''
NEW_VISUAL='''    product_images=[]
    product_image_by_id={}
    for row in product.get("images") or []:
        src=str(row.get("src") or "").strip() if isinstance(row,dict) else ""
        if src and src not in product_images:
            product_images.append(src)
        if isinstance(row,dict) and src and str(row.get("id") or "").strip():
            product_image_by_id[str(row.get("id")).strip()]=src
    meta=_meta_dict(product)
    colors=[]
    for row in _as_data(meta.get("werbeartikel_colors"),[]) or []:
        if not isinstance(row,dict):
            continue
        name=str(row.get("name") or row.get("color") or "").strip()
        raw_image=row.get("image") or row.get("image_url") or ""
        if isinstance(raw_image,dict):
            image=str(raw_image.get("src") or raw_image.get("url") or raw_image.get("image") or "").strip()
        else:
            image=str(raw_image or "").strip()
        image_id=str(row.get("image_id") or row.get("attachment_id") or "").strip()
        if not image and image_id:
            image=product_image_by_id.get(image_id,"")
        key=(name,image)
        if (name or image) and key not in [(x["name"],x["image"]) for x in colors]:
            colors.append({"name":name,"image":image,"image_id":image_id,"erp_code":str(row.get("CodeERP") or row.get("erp_code") or "").strip(),"hex":str(row.get("hex") or row.get("color_hex") or "").strip()})
'''

OLD_ENDPOINT='''        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        return {"ok": True, **data, "source": "woocommerce-wizard"}
'''
NEW_ENDPOINT='''        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        # The WK endpoint contains the calculation configuration, while image URLs
        # are exposed through the regular WooCommerce product response. Merge both
        # read-only sources so HCA can resolve colour attachment IDs reliably.
        meta_product_id = _shop_int(data.get("meta_product_id"), product_id)
        try:
            product = await asyncio.to_thread(_woo_json, f"/products/{meta_product_id}")
            if isinstance(product, dict):
                meta = _meta_dict(product)
                details = {
                    **_hca137_product_details(product),
                    "name": str(product.get("name") or data.get("name") or ""),
                    "sku": str(product.get("sku") or data.get("sku") or ""),
                    "manufacturer": _product_manufacturer(meta, product),
                    "weight": str(product.get("weight") or ""),
                    "dimensions": product.get("dimensions") if isinstance(product.get("dimensions"), dict) else {},
                }
                data["product_details"] = details
        except Exception as visual_error:
            # Pricing must remain available even if a product image cannot be read.
            data["product_details_warning"] = str(visual_error)
        return {"ok": True, **data, "source": "woocommerce-wizard"}
'''

def patch_text(text:str)->str:
    if text.count(OLD_VISUAL)!=1:raise RuntimeError('Bildauflösungsblock nicht eindeutig gefunden')
    if text.count(OLD_ENDPOINT)!=1:raise RuntimeError('Wizard-Endpunkt nicht eindeutig gefunden')
    return text.replace(OLD_VISUAL,NEW_VISUAL).replace(OLD_ENDPOINT,NEW_ENDPOINT)

def main()->None:
    source=Path(sys.argv[1]) if len(sys.argv)>1 else DEFAULT_SOURCE
    target=Path(sys.argv[2]) if len(sys.argv)>2 else source.with_name('hca_shared_v01321.py')
    target.write_text(patch_text(source.read_text(encoding='utf-8')),encoding='utf-8')
    print(target)

if __name__=='__main__':main()
