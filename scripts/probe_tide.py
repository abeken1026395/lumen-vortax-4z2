#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 診断：Marine の過去日(区間別)で潮位が取れるか・所要時間・データ点数を確認。
import json, ssl, time, urllib.request, urllib.parse
MARINE = "https://marine-api.open-meteo.com/v1/marine"
LAT, LON = 35.6940, 139.8730  # 江戸川
CHUNKS = [("2025-07-15","2025-10-15"),("2025-10-16","2026-01-15"),
          ("2026-01-16","2026-04-15"),("2026-04-16","2026-07-05"),
          ("2026-06-20","2026-07-05")]  # 直近も対照
def get(url, t):
    t0=time.time()
    with urllib.request.urlopen(url, timeout=t, context=ssl.create_default_context()) as r:
        return r.getcode(), r.read().decode("utf-8","replace"), time.time()-t0
for s,e in CHUNKS:
    q=urllib.parse.urlencode({"latitude":LAT,"longitude":LON,
        "hourly":"sea_level_height_msl","timezone":"Asia/Tokyo","start_date":s,"end_date":e})
    try:
        code,body,dt=get(f"{MARINE}?{q}", 25)
        try:
            d=json.loads(body); h=d.get("hourly",{}) or {}
            tv=[x for x in (h.get("sea_level_height_msl",[]) or []) if isinstance(x,(int,float))]
            print(f"{s}~{e}: HTTP{code} {dt:.1f}s 時間{len(h.get('time',[]) or [])} 潮位有効{len(tv)} 例{tv[:2]}")
        except Exception as pe:
            print(f"{s}~{e}: HTTP{code} {dt:.1f}s parse? body={body[:200]}")
    except Exception as ex:
        print(f"{s}~{e}: ERR {ex}")
print("--- tide probe done ---")
