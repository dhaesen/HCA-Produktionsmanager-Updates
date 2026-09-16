#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


OLD_PAIRING_HELPERS = '''def _cleanup_mobile_pairings() -> None:
    now = time.time()
    for token, expires_at in list(MOBILE_PAIRINGS.items()):
        if expires_at <= now:
            MOBILE_PAIRINGS.pop(token, None)
'''

NEW_PAIRING_HELPERS = '''def _mobile_pairing_table(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS mobile_pairings(
        token_hash TEXT PRIMARY KEY,
        expires_at INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )""")


def _cleanup_mobile_pairings(conn: sqlite3.Connection) -> None:
    _mobile_pairing_table(conn)
    conn.execute("DELETE FROM mobile_pairings WHERE expires_at<=?", (int(time.time()),))
'''

OLD_CREATE = '''@router.post("/mobile/pairing/create", dependencies=auth)
async def mobile_pairing_create() -> dict[str, Any]:
    _cleanup_mobile_pairings()
    token = uuid.uuid4().hex[:12].upper()
    MOBILE_PAIRINGS[token] = time.time() + MOBILE_PAIRING_TTL_SECONDS
    return {"ok": True, "token": token, "expires_in": MOBILE_PAIRING_TTL_SECONDS}
'''

NEW_CREATE = '''@router.post("/mobile/pairing/create", dependencies=auth)
async def mobile_pairing_create() -> dict[str, Any]:
    token = uuid.uuid4().hex[:12].upper()
    expires_at = int(time.time()) + MOBILE_PAIRING_TTL_SECONDS
    with _db() as conn:
        _cleanup_mobile_pairings(conn)
        conn.execute(
            "INSERT OR REPLACE INTO mobile_pairings(token_hash,expires_at,created_at) VALUES(?,?,?)",
            (_mobile_device_hash(token), expires_at, _now()),
        )
    return {"ok": True, "token": token, "expires_in": MOBILE_PAIRING_TTL_SECONDS}
'''

OLD_REDEEM_HEAD = '''    device_token=supplied_device or cookie_device
    _cleanup_mobile_pairings()

    if action == "revoke":
'''

NEW_REDEEM_HEAD = '''    device_token=supplied_device or cookie_device

    if action == "revoke":
'''

OLD_REDEEM_PAIR = '''    if pair_token:
        expires_at = MOBILE_PAIRINGS.pop(pair_token, None)
        if not expires_at or expires_at <= time.time():
            raise HTTPException(status_code=401, detail="Pairing-Code ist ungültig oder abgelaufen.")
        device_token=secrets.token_urlsafe(32)
        now=_now(); ua=str(request.headers.get("user-agent") or "")[:500]
        with _db() as conn:
            conn.execute("INSERT OR REPLACE INTO mobile_devices(token_hash,label,user_agent,active,created_at,last_seen_at) VALUES(?,?,?,?,?,?)", (_mobile_device_hash(device_token),"Mobile-Device",ua,1,now,now))
'''

NEW_REDEEM_PAIR = '''    if pair_token:
        device_token=secrets.token_urlsafe(32)
        now=_now(); ua=str(request.headers.get("user-agent") or "")[:500]
        with _db() as conn:
            _cleanup_mobile_pairings(conn)
            pair_hash=_mobile_device_hash(pair_token)
            row=conn.execute("SELECT expires_at FROM mobile_pairings WHERE token_hash=?", (pair_hash,)).fetchone()
            if not row or int(row["expires_at"] or 0) <= int(time.time()):
                raise HTTPException(status_code=401, detail="Pairing-Code ist ungültig oder abgelaufen.")
            conn.execute("DELETE FROM mobile_pairings WHERE token_hash=?", (pair_hash,))
            conn.execute("INSERT OR REPLACE INTO mobile_devices(token_hash,label,user_agent,active,created_at,last_seen_at) VALUES(?,?,?,?,?,?)", (_mobile_device_hash(device_token),"Mobile-Device",ua,1,now,now))
'''


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: erwartet 1 Fundstelle, gefunden {count}")
    return source.replace(old, new, 1)


def patch(source: str) -> str:
    source = replace_once(source, OLD_PAIRING_HELPERS, NEW_PAIRING_HELPERS, "Pairing-Speicher")
    source = replace_once(source, OLD_CREATE, NEW_CREATE, "Pairing-Erzeugung")
    source = replace_once(source, OLD_REDEEM_HEAD, NEW_REDEEM_HEAD, "Pairing-Aufruf")
    source = replace_once(source, OLD_REDEEM_PAIR, NEW_REDEEM_PAIR, "Pairing-Einlösung")
    source = replace_once(
        source,
        '<button class="btn primary" id="saveKey">API-Schlüssel verwenden</button><button class="btn" id="pasteKey">Einfügen</button>',
        '<button class="btn primary" id="saveKey" type="button">API-Schlüssel verwenden</button><button class="btn" id="pasteKey" type="button">Einfügen</button>',
        "Mobile Buttons",
    )
    source = replace_once(
        source,
        "const $=s=>document.querySelector(s);\nlet apiKey='',deviceToken=localStorage.getItem('hcaMobileDeviceToken')||'',manualKey=localStorage.getItem('hcaMobileKey')||'',mode='putaway'",
        "const $=s=>document.querySelector(s);\nfunction storageGet(key){try{return window['localStorage'].getItem(key)||''}catch{return ''}}\nfunction storageSet(key,value){try{window['localStorage'].setItem(key,value)}catch{}}\nfunction storageRemove(key){try{window['localStorage'].removeItem(key)}catch{}}\nlet apiKey='',deviceToken=storageGet('hcaMobileDeviceToken'),manualKey=storageGet('hcaMobileKey'),mode='putaway'",
        "Speicher-Fallback",
    )
    source = source.replace("localStorage.setItem(", "storageSet(")
    source = source.replace("localStorage.removeItem(", "storageRemove(")
    source = replace_once(
        source,
        "$('#saveKey').onclick=async()=>{manualKey=$('#key').value.trim();apiKey=manualKey;if(manualKey)storageSet('hcaMobileKey',manualKey);await testSession()};",
        "async function useManualKey(){const button=$('#saveKey'),st=$('#loginStatus');manualKey=$('#key').value.trim();if(!manualKey){showLogin('Bitte den HCA API-Schlüssel eingeben.');return}apiKey=manualKey;storageSet('hcaMobileKey',manualKey);if(button){button.disabled=true;button.textContent='Verbindung wird geprüft …'}if(st){st.textContent='API-Schlüssel wird geprüft …';st.className='status'}try{await testSession()}finally{if(button){button.disabled=false;button.textContent='API-Schlüssel verwenden'}}}\n$('#saveKey').addEventListener('click',useManualKey);\n$('#key').addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();useManualKey()}});",
        "API-Schlüssel bestätigen",
    )
    source = replace_once(
        source,
        "(async()=>{const hash=new URLSearchParams(location.hash.replace(/^#/,''));const pair=hash.get('pair'),fromHash=hash.get('device');",
        "(async()=>{const query=new URLSearchParams(location.search),hash=new URLSearchParams(location.hash.replace(/^#/,''));const pair=query.get('pair')||hash.get('pair'),fromHash=hash.get('device');",
        "Pairing-URL lesen",
    )
    source = replace_once(
        source,
        "history.replaceState(null,'',location.pathname+location.search+'#device='+encodeURIComponent(deviceToken));",
        "history.replaceState(null,'',location.pathname+'#device='+encodeURIComponent(deviceToken));",
        "Pairing-URL bereinigen",
    )
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    args.destination.write_text(patch(args.source.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
