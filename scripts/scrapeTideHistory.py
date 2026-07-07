#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrapeTideHistory.py
open-meteo Marine から各場の潮位(sea_level_height_msl)・波高(wave_height)・うねり
(swell_wave_height)を過去354日分、日付レンジ一括で取得し tideHistory/{jcd}.json に保存。
潮汐実測（締切潮位帯・潮位変化・うねり × 波乱率）の土台。COORDは24場全て（干満差の
有無は取得後の潮位レンジで実測判定できる）。天候履歴と同様、Actions経由で一度取得しコミット。
"""
import json, os, ssl, time, urllib.request, urllib.parse
MARINE = "https://marine-api.open-meteo.com/v1/marine"
OUTDIR = "tideHistory"
SLEEP = 0.5
COORD = {"01":(36.4205,139.3320),"02":(35.8108,139.6890),"03":(35.6940,139.8730),
         "04":(35.5790,139.7460),"05":(35.6620,139.5090),"06":(34.7130,137.6080),
         "07":(34.8200,137.2200),"08":(34.8830,136.8330),"09":(34.7330,136.5230),
         "10":(36.2210,136.1490),"11":(35.0480,135.9020),"12":(34.6100,135.4790),
         "13":(34.7110,135.4080),"14":(34.1720,134.6100),"15":(34.2940,133.7900),
         "16":(34.4620,133.7900),"17":(34.3030,132.3110),"18":(34.0510,131.8090),
         "19":(33.9610,130.9300),"20":(33.9080,130.8100),"21":(33.9120,130.6620),
         "22":(33.6010,130.4010),"23":(33.4520,129.9720),"24":(32.9210,129.9610)}
JNAME = {"01":"桐生","02":"戸田","03":"江戸川","04":"平和島","05":"多摩川","06":"浜名湖",
         "07":"蒲郡","08":"常滑","09":"津","10":"三国","11":"びわこ","12":"住之江","13":"尼崎",
         "14":"鳴門","15":"丸亀","16":"児島","17":"宮島","18":"徳山","19":"下関","20":"若松",
         "21":"芦屋","22":"福岡","23":"唐津","24":"大村"}
CHUNKS = [("2025-07-15","2025-10-15"),("2025-10-16","2026-01-15"),
          ("2026-01-16","2026-04-15"),("2026-04-16","2026-07-05")]

def http(url, t=90):
    with urllib.request.urlopen(url, timeout=t, context=ssl.create_default_context()) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    os.makedirs(OUTDIR, exist_ok=True)
    ok = 0
    for jcd, (lat, lon) in COORD.items():
        times, tide, wave, swell = [], [], [], []
        fail = 0
        for s, e in CHUNKS:
            q = urllib.parse.urlencode({
                "latitude": lat, "longitude": lon,
                "hourly": "sea_level_height_msl,wave_height,swell_wave_height",
                "timezone": "Asia/Tokyo", "start_date": s, "end_date": e})
            try:
                d = http(f"{MARINE}?{q}")
                h = d.get("hourly", {}) or {}
                times += h.get("time", []) or []
                tide  += h.get("sea_level_height_msl", []) or []
                wave  += h.get("wave_height", []) or []
                swell += h.get("swell_wave_height", []) or []
            except Exception as ex:
                fail += 1
                print(f"  {jcd}{JNAME[jcd]} {s}: NG {ex}")
            time.sleep(SLEEP)
        # 潮位の有効数と干満差（max-min）を記録
        tv = [x for x in tide if isinstance(x, (int, float))]
        rng = (max(tv) - min(tv)) if tv else None
        doc = {"場名": JNAME[jcd], "lat": lat, "lon": lon,
               "time": times, "tide": tide, "wave": wave, "swell": swell,
               "潮位有効数": len(tv), "干満差m": round(rng, 2) if rng is not None else None}
        with open(os.path.join(OUTDIR, f"{jcd}.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        print(f"{jcd}{JNAME[jcd]}: 時間{len(times)} 潮位有効{len(tv)} 干満差{doc['干満差m']}m fail{fail}")
        ok += 1
    print(f"完了: {ok}場 → {OUTDIR}/")

if __name__ == "__main__":
    main()
