#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 一時プローブ：open-meteo Marine の sea_level_height_msl(潮位)が過去日で取れるか疎通確認。
# うねり(wave_height/swell_wave_height)も併せて確認。会場座標はregenのCOORD相当。
import json, urllib.request, urllib.parse, ssl
BASES = ["https://marine-api.open-meteo.com/v1/marine"]
# 潮汐が効く代表場（海水/汽水）：徳山18(34.051,131.809), 大村24(32.921,129.961), 江戸川03(35.694,139.873)
SPOTS = {"18徳山": (34.051, 131.809), "24大村": (32.921, 129.961), "03江戸川": (35.694, 139.873)}
def http(url, t=40):
    with urllib.request.urlopen(url, timeout=t, context=ssl.create_default_context()) as r:
        return r.getcode(), r.read().decode("utf-8", "replace")
for name, (lat, lon) in SPOTS.items():
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "hourly": "sea_level_height_msl,wave_height,swell_wave_height",
        "timezone": "Asia/Tokyo",
        "start_date": "2026-07-01", "end_date": "2026-07-02"})
    url = f"{BASES[0]}?{q}"
    try:
        code, body = http(url)
    except Exception as e:
        print(f"{name}: ERR {e}"); continue
    print(f"\n==== {name} HTTP{code} ====")
    try:
        d = json.loads(body)
        h = d.get("hourly", {})
        print("hourlyキー:", list(h.keys()))
        t = h.get("time", []) or []
        sl = h.get("sea_level_height_msl", []) or []
        wv = h.get("wave_height", []) or []
        sw = h.get("swell_wave_height", []) or []
        print("時間数:", len(t))
        for i in range(0, min(len(t), 26), 6):
            print(f"  {t[i]}  潮位={sl[i] if i<len(sl) else '-'}  波高={wv[i] if i<len(wv) else '-'}  うねり={sw[i] if i<len(sw) else '-'}")
        units = d.get("hourly_units", {})
        print("単位:", units)
    except Exception as e:
        print("parse失敗:", e, body[:300])
print("\n--- marine probe done ---")
