from __future__ import annotations


NEEDLE = '''        with _db() as conn:
            lid=str(uuid.uuid4()); now=_now()
            conn.execute("INSERT INTO production_order_links(id,production_order_no,sales_order_id,base_order_id,technique_group,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(lid,pno,sales_order_id,base_id,group,"planned",now,now))
            created.append({"id":lid,"production_order_no":pno,"sales_order_id":sales_order_id,"base_order_id":base_id,"technique_group":group,"status":"planned"})
'''

REPLACEMENT = '''        # Die Auftragsadresse muss nicht nur an den alten Produktionsserver,
        # sondern auch an die zentrale HCA-Versandverwaltung übergeben werden.
        # Sonst zeigt der Produktionsauftrag trotz vollständigem Kundenauftrag keine
        # Lieferadresse und kann später keine zugehörige Sendung vorbereiten.
        recipient = {
            "recipient_name": str(shipping.get("attention") or shipping.get("name") or order["customer_name"] or ""),
            "company": str(shipping.get("name") or order["customer_name"] or ""),
            "address_line_1": street,
            "house_number": house,
            "address_line_2": str(shipping.get("address_line_2") or ""),
            "postal_code": str(shipping.get("zip") or ""),
            "city": str(shipping.get("city") or ""),
            "country_code": _country_code(shipping.get("country") or "DE"),
            "email": str(shipping.get("email") or ""),
            "phone": str(shipping.get("phone") or ""),
        }
        if base_id and recipient["address_line_1"] and recipient["postal_code"] and recipient["city"]:
            _upsert_meta(base_id, {
                "shipping_mode": "standard",
                "shipping_strategy": "manual_cheapest",
                "recipient": recipient,
                "parcel": {},
            })
        with _db() as conn:
            lid=str(uuid.uuid4()); now=_now()
            conn.execute("INSERT INTO production_order_links(id,production_order_no,sales_order_id,base_order_id,technique_group,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(lid,pno,sales_order_id,base_id,group,"planned",now,now))
            created.append({"id":lid,"production_order_no":pno,"sales_order_id":sales_order_id,"base_order_id":base_id,"technique_group":group,"status":"planned"})
'''


def patch_text(source: str) -> str:
    if 'Die Auftragsadresse muss nicht nur an den alten Produktionsserver' in source:
        return source
    if source.count(NEEDLE) != 1:
        raise RuntimeError('Produktionsauftrag-Einfügepunkt fehlt oder ist nicht eindeutig.')
    return source.replace(NEEDLE, REPLACEMENT)

