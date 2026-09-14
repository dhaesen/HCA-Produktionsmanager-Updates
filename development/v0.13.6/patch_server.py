#!/usr/bin/env python3
"""Apply the reviewed HCA v0.13.6 NAS changes to the materialized v0.13.5 server."""
from pathlib import Path
import re, sys

path=Path(sys.argv[1])
s=path.read_text(encoding="utf-8")

def one(old,new,label):
    global s
    count=s.count(old)
    if count!=1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    s=s.replace(old,new,1)

one('CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_article_woo ON inventory_articles(woo_product_id) WHERE woo_product_id<>\'\';',
'''DROP INDEX IF EXISTS ux_inventory_article_woo;
        CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_article_woo_sku ON inventory_articles(woo_product_id,sku) WHERE woo_product_id<>'' OR sku<>'';''',
"inventory identity index")

pattern=r'def _ensure_inventory_article\(conn: sqlite3\.Connection, \*, woo_product_id: str, name: str, sku: str, manufacturer: str = "", supplier: str = "", image_url: str = "", raw: Any = None, preserve_existing_raw: bool = False\) -> str:\n.*?\n    return article_id\n'
replacement='''def _ensure_inventory_article(conn: sqlite3.Connection, *, woo_product_id: str, name: str, sku: str, manufacturer: str = "", supplier: str = "", image_url: str = "", raw: Any = None, preserve_existing_raw: bool = False) -> str:
    """Keep every real SKU as its own article identity; equal names never merge records."""
    now = _now()
    woo = str(woo_product_id or "").strip()
    sku_value = str(sku or "").strip()
    existing = None
    if woo or sku_value:
        existing = conn.execute(
            "SELECT id,raw_json FROM inventory_articles WHERE woo_product_id=? AND sku=?",
            (woo, sku_value),
        ).fetchone()
    identity = f"{woo}|{sku_value}" if (woo or sku_value) else str(uuid.uuid4())
    article_id = str(existing["id"]) if existing else str(uuid.uuid5(uuid.NAMESPACE_URL, "hca-article:" + identity.lower()))
    raw_json = str(existing["raw_json"] or "{}") if preserve_existing_raw and existing else _json(raw or {})
    conn.execute("""INSERT INTO inventory_articles(id,woo_product_id,name,sku,manufacturer,supplier,image_url,raw_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    name=CASE WHEN excluded.name<>'' THEN excluded.name ELSE inventory_articles.name END,
                    sku=excluded.sku,woo_product_id=excluded.woo_product_id,
                    manufacturer=CASE WHEN excluded.manufacturer<>'' THEN excluded.manufacturer ELSE inventory_articles.manufacturer END,
                    supplier=CASE WHEN excluded.supplier<>'' THEN excluded.supplier ELSE inventory_articles.supplier END,
                    image_url=CASE WHEN excluded.image_url<>'' THEN excluded.image_url ELSE inventory_articles.image_url END,
                    raw_json=excluded.raw_json,updated_at=excluded.updated_at""",
                 (article_id,woo,str(name),sku_value,str(manufacturer),str(supplier),str(image_url),raw_json,now,now))
    return article_id
'''
s,n=re.subn(pattern,replacement,s,count=1,flags=re.S)
if n!=1: raise SystemExit(f"ensure article: expected 1 match, got {n}")

one('"motif":str((step or {}).get("motif") or ""),"shipping_group":"","product_id":str(item["product_id"] or "")})',
    '"motif":str((step or {}).get("motif") or ""),"shipping_group":"","product_id":str(item["product_id"] or ""),"packaging_unit":max(1,int(float(config.get("packaging_unit") or 1))),"production_mode":str(config.get("production_mode") or "")})',
    "production row metadata")

one('base_payload={"order_no":pno,"customer":order["customer_name"],"title":title,"due_date":order["due_date"],"items":rows}',
'''shipping = _loads(order["shipping_json"], {}) if "shipping_json" in order.keys() else {}
        shipping = shipping if isinstance(shipping, dict) else {}
        street, house = _split_street_house(str(shipping.get("street") or ""), "")
        base_payload={"order_no":pno,"customer":order["customer_name"],"title":title,"due_date":order["due_date"],"items":rows,
                      "recipient_name":str(shipping.get("attention") or shipping.get("name") or order["customer_name"] or ""),
                      "company":str(shipping.get("name") or order["customer_name"] or ""),
                      "address_line_1":street,"house_number":house,"postal_code":str(shipping.get("zip") or ""),
                      "city":str(shipping.get("city") or ""),"country_code":_country_code(shipping.get("country") or "DE"),
                      "email":str(shipping.get("email") or ""),"phone":str(shipping.get("phone") or ""),
                      "shipping_address":shipping}''',
    "production shipping address")

one('r["description"],r["quantity"],r["unit"],r["unit_price"],r["discount_pct"],r["tax_rate"],r["config_json"],now,now))',
    'r["description"],*_hca136_quote_tier_values(r,payload.get("selected_quantity_tier")),r["discount_pct"],r["tax_rate"],_json(_hca136_quote_tier_config(r,payload.get("selected_quantity_tier"))),now,now))',
    "quote refinements and selected tier conversion")

needle='''    pages: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []; used = 0.0
'''
insert='''    if is_quote:
        tier_quantities = sorted({
            int(float(tier.get("quantity") or 0))
            for item in items
            for tier in ((item.get("config") or {}).get("quote_quantity_tiers") or [])
            if isinstance(tier, dict) and float(tier.get("quantity") or 0) > 0
        })
        for tier_quantity in tier_quantities:
            tier_net = tier_tax = tier_gross = 0.0
            for item in items:
                config = item.get("config") if isinstance(item.get("config"), dict) else {}
                snapshot = next((x for x in (config.get("quote_quantity_tiers") or [])
                                 if isinstance(x, dict) and int(float(x.get("quantity") or 0)) == tier_quantity), None)
                if snapshot:
                    tier_net += float(snapshot.get("net") or 0)
                    tier_tax += float(snapshot.get("tax") or 0)
                    tier_gross += float(snapshot.get("gross") or 0)
            position_no += 1
            text = f"Mengenstaffel {tier_quantity:g} Stück · netto {_document_money(tier_net)} · MwSt. {_document_money(tier_tax)} · brutto {_document_money(tier_gross)}"
            rows.append({"index": position_no, "sku": "", "lines": _delivery_wrap(text, 82),
                         "quantity": 0, "unit": "", "unit_price": 0, "net_total": 0,
                         "text": True, "optional": False})

    pages: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []; used = 0.0
'''
one(needle,insert,"quote tier PDF")

if 'HCA_BUSINESS_SCHEMA_VERSION = "0.13.5"' in s:
    s=s.replace('HCA_BUSINESS_SCHEMA_VERSION = "0.13.5"','HCA_BUSINESS_SCHEMA_VERSION = "0.13.6"',1)

append=r'''

# ---------------------------------------------------------------------------
# HCA v0.13.6 · SKU identity, address checking, packaging units and shipment links
# ---------------------------------------------------------------------------
_HCA136_PRODUCT_SEARCH = _woo_search_products
_HCA136_ADDRESS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

def _hca136_normalize_config(value: Any) -> dict[str, Any]:
    config = value if isinstance(value, dict) else {}
    config = dict(config)
    steps = config.get("production_steps")
    if not isinstance(steps, list):
        for key in ("refinements", "productionSteps", "veredelungen"):
            candidate = config.get(key)
            if isinstance(candidate, list):
                steps = candidate
                break
    normalized=[]
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        item=dict(step)
        technique=item.get("technique")
        if isinstance(technique, list):
            item["technique"]=str(next((x for x in technique if str(x).strip()), ""))
        elif isinstance(technique, dict):
            item["technique"]=str(technique.get("slug") or technique.get("name") or technique.get("label") or "")
        normalized.append(item)
    config["production_steps"]=normalized
    config["packaging_unit"]=max(1,int(float(config.get("packaging_unit") or 1)))
    return config

def _hca136_quote_tier_config(row: sqlite3.Row, selected: Any) -> dict[str, Any]:
    config=_hca136_normalize_config(_loads(row["config_json"],{}))
    try: quantity=int(float(selected or 0))
    except Exception: quantity=0
    if quantity>0:
        snapshot=next((x for x in (config.get("quote_quantity_tiers") or [])
                       if isinstance(x,dict) and int(float(x.get("quantity") or 0))==quantity),None)
        if snapshot and isinstance(snapshot.get("production_steps"),list):
            config["production_steps"]=snapshot["production_steps"]
        config["selected_quantity_tier"]=quantity
    return config

def _hca136_quote_tier_values(row: sqlite3.Row, selected: Any) -> tuple[float,str,float]:
    try: quantity=int(float(selected or 0))
    except Exception: quantity=0
    config=_loads(row["config_json"],{})
    snapshot=next((x for x in ((config if isinstance(config,dict) else {}).get("quote_quantity_tiers") or [])
                   if isinstance(x,dict) and int(float(x.get("quantity") or 0))==quantity),None) if quantity>0 else None
    return (float(quantity if quantity>0 else row["quantity"]),str(row["unit"] or "Stk."),
            float(snapshot.get("unit_price") if snapshot and snapshot.get("unit_price") is not None else row["unit_price"]))

def _woo_search_products(query: str, limit: int = 24) -> list[dict[str, Any]]:
    rows=_HCA136_PRODUCT_SEARCH(query,limit)
    unique: dict[tuple[str,str,str,str],dict[str,Any]]={}
    for row in rows:
        if not isinstance(row,dict):
            continue
        sku=str(row.get("sku") or row.get("matched_sku") or "").strip().lower()
        product_id=str(row.get("product_id") or row.get("id") or "").strip()
        key=str(row.get("key") or "").strip()
        color=str(row.get("color") or "").strip().lower()
        identity=(product_id,sku,key,color)
        unique.setdefault(identity,row)
    return list(unique.values())

def _hca136_address_lookup(country: str, postal_code: str, street: str = "") -> dict[str, Any]:
    import urllib.request
    cc=str(country or "DE").strip().lower()
    postal=re.sub(r"\s+","",str(postal_code or ""))
    if cc=="de" and not re.fullmatch(r"\d{5}",postal):
        raise HTTPException(status_code=400,detail="Eine deutsche PLZ muss aus genau fünf Ziffern bestehen.")
    cache_key=f"{cc}|{postal}|{str(street or '').strip().lower()}"
    cached=_HCA136_ADDRESS_CACHE.get(cache_key)
    if cached and time.time()-cached[0] < 86400:
        return cached[1]
    base=f"https://openplzapi.org/{urllib.parse.quote(cc)}/Localities?postalCode={urllib.parse.quote(postal)}&pageSize=50"
    try:
        req=urllib.request.Request(base,headers={"Accept":"application/json","User-Agent":"HCA-Produktionsmanager/0.13.6"})
        with urllib.request.urlopen(req,timeout=5) as response:
            localities=json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=503,detail=f"PLZ-Dienst vorübergehend nicht erreichbar: {exc}") from exc
    cities=sorted({str(x.get("name") or "").strip() for x in localities if isinstance(x,dict) and str(x.get("name") or "").strip()})
    streets: list[str]=[]
    street_value=str(street or "").strip()
    if street_value and len(street_value)>=2:
        url=f"https://openplzapi.org/{urllib.parse.quote(cc)}/Streets?postalCode={urllib.parse.quote(postal)}&name={urllib.parse.quote('^'+street_value)}&pageSize=100"
        try:
            req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"HCA-Produktionsmanager/0.13.6"})
            with urllib.request.urlopen(req,timeout=5) as response:
                data=json.loads(response.read().decode("utf-8"))
            streets=sorted({str(x.get("name") or "").strip() for x in data if isinstance(x,dict) and str(x.get("name") or "").strip()})
        except Exception:
            streets=[]
    result={"ok":True,"country":cc.upper(),"postal_code":postal,"cities":cities,"streets":streets,"verified":bool(cities)}
    _HCA136_ADDRESS_CACHE[cache_key]=(time.time(),result)
    return result

@router.get("/address/lookup", dependencies=auth)
async def hca136_address_lookup(country: str = "DE", postal_code: str = "", street: str = "") -> dict[str, Any]:
    return await asyncio.to_thread(_hca136_address_lookup,country,postal_code,street)

def _hca136_task_settings_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS production_task_settings(
        task_id TEXT PRIMARY KEY, packaging_unit INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL
    )""")

@router.get("/production/task-settings", dependencies=auth)
async def hca136_task_settings_list() -> dict[str, Any]:
    with _db() as conn:
        _hca136_task_settings_schema(conn)
        return {"ok":True,"items":[dict(x) for x in conn.execute("SELECT * FROM production_task_settings").fetchall()]}

@router.put("/production/task-settings/{task_id}", dependencies=auth)
async def hca136_task_settings_put(task_id: str, request: Request) -> dict[str, Any]:
    body=await request.json(); body=body if isinstance(body,dict) else {}
    unit=max(1,int(float(body.get("packaging_unit") or 1)))
    with _db() as conn:
        _hca136_task_settings_schema(conn)
        conn.execute("""INSERT INTO production_task_settings(task_id,packaging_unit,updated_at) VALUES(?,?,?)
                        ON CONFLICT(task_id) DO UPDATE SET packaging_unit=excluded.packaging_unit,updated_at=excluded.updated_at""",
                     (str(task_id),unit,_now()))
    return {"ok":True,"task_id":str(task_id),"packaging_unit":unit}

_HCA136_DELIVERY_FROM_SHIPMENT = _delivery_from_shipment_blocking
def _delivery_from_shipment_blocking(shipment_id: str) -> dict[str, Any]:
    shipment=_shipment_by_id(shipment_id)
    with _db() as conn:
        exact=conn.execute("SELECT * FROM delivery_notes WHERE shipment_id=?",(shipment_id,)).fetchone()
        if exact:
            conn.execute("UPDATE delivery_notes SET carrier_name=?,tracking_number=?,tracking_url=?,status=CASE WHEN ?<>'' OR ?<>'' THEN 'shipped' ELSE status END,updated_at=? WHERE id=?",
                         (str(shipment.get("carrier_name") or ""),str(shipment.get("tracking_number") or ""),
                          str(shipment.get("tracking_url") or ""),str(shipment.get("tracking_number") or ""),
                          str(shipment.get("tracking_url") or ""),_now(),exact["id"]))
            return _delivery_note_dict(conn,conn.execute("SELECT * FROM delivery_notes WHERE id=?",(exact["id"],)).fetchone(),True)
        link=conn.execute("SELECT sales_order_id FROM production_order_links WHERE base_order_id=? ORDER BY created_at DESC LIMIT 1",
                          (str(shipment.get("order_id") or ""),)).fetchone()
        sales_order_id=str(link["sales_order_id"] or "") if link else ""
        if sales_order_id:
            available=conn.execute("""SELECT * FROM delivery_notes n
                WHERE n.sales_order_id=? AND n.status<>'cancelled' AND COALESCE(n.shipment_id,'')=''
                AND NOT EXISTS(SELECT 1 FROM delivery_notes x WHERE x.shipment_id=?)
                ORDER BY CASE n.status WHEN 'ready' THEN 0 ELSE 1 END,n.created_at DESC LIMIT 1""",
                (sales_order_id,shipment_id)).fetchone()
            if available:
                tracking=str(shipment.get("tracking_number") or ""); link_url=str(shipment.get("tracking_url") or "")
                conn.execute("""UPDATE delivery_notes SET shipment_id=?,source_type='shipment',source_id=?,carrier_name=?,
                    tracking_number=?,tracking_url=?,status=CASE WHEN ?<>'' OR ?<>'' THEN 'shipped' ELSE status END,updated_at=? WHERE id=?""",
                    (shipment_id,shipment_id,str(shipment.get("carrier_name") or ""),tracking,link_url,tracking,link_url,_now(),available["id"]))
                return _delivery_note_dict(conn,conn.execute("SELECT * FROM delivery_notes WHERE id=?",(available["id"],)).fetchone(),True)
    return _HCA136_DELIVERY_FROM_SHIPMENT(shipment_id)

_HCA136_ENSURE_SHIPMENT = _delivery_ensure_shipment
def _delivery_ensure_shipment(delivery_note_id: str, parcel: dict[str, Any] | None = None) -> dict[str, Any]:
    with _db() as conn:
        note=conn.execute("SELECT * FROM delivery_notes WHERE id=?",(delivery_note_id,)).fetchone()
        if not note:
            raise HTTPException(status_code=404,detail="Lieferschein nicht gefunden.")
        if not str(note["shipment_id"] or ""):
            candidate=conn.execute("SELECT * FROM shipments WHERE shipment_key=? ORDER BY updated_at DESC LIMIT 1",
                                   (f"DELIVERY:{note['delivery_note_no']}",)).fetchone()
            if not candidate and str(note["sales_order_id"] or ""):
                base_ids=[str(x["base_order_id"]) for x in conn.execute("SELECT base_order_id FROM production_order_links WHERE sales_order_id=?",(note["sales_order_id"],)).fetchall() if str(x["base_order_id"] or "")]
                if base_ids:
                    marks=",".join("?" for _ in base_ids)
                    candidate=conn.execute(f"""SELECT s.* FROM shipments s WHERE s.order_id IN ({marks})
                        AND NOT EXISTS(SELECT 1 FROM delivery_notes d WHERE d.shipment_id=s.id)
                        ORDER BY s.updated_at DESC LIMIT 1""",base_ids).fetchone()
            if candidate:
                conn.execute("UPDATE delivery_notes SET shipment_id=?,updated_at=? WHERE id=?",(candidate["id"],_now(),delivery_note_id))
                if parcel is not None:
                    conn.execute("UPDATE shipments SET parcel_json=?,updated_at=? WHERE id=?",(_json(_clean_parcel(parcel)),_now(),candidate["id"]))
                return _shipment_by_id(str(candidate["id"]))
    return _HCA136_ENSURE_SHIPMENT(delivery_note_id,parcel)
'''
s += append
path.write_text(s,encoding="utf-8")
