#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrapeLiveWeather.py
boatrace.jp 公式 直前情報(beforeinfo) の「水面気象情報」= 実況値（予報でない）を、
当日開催場のみ高頻度で取得し docs/data/liveWeather.json に出力する。
既存 weather.json(Open-Meteo予報) とは別系統。買い目・予想は出さず、実測の水面気象のみ。

出力: {updated, updatedJst, stadiums:{jcd:{場名, レース, 時刻, 天候, 風速m, 風向, 波高cm, 気温, 水温}}}
使い方: python scripts/scrapeLiveWeather.py [racers_csv] [out_json]
"""
import csv, json, sys, re, time, datetime, urllib.request, ssl
RACERS = sys.argv[1] if len(sys.argv) > 1 else "docs/racers/racers_today.csv"
OUT    = sys.argv[2] if len(sys.argv) > 2 else "docs/data/liveWeather.json"
SLEEP  = 1.0
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
def jst_now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))

def fetch(jcd, rno, hd):
    url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={rno}&jcd={jcd}&hd={hd}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as r:
        return r.read().decode("utf-8", "replace")

def parse_weather(html):
    """weather1ブロックから実況気象を辞書で返す。取得不能はNone。"""
    if 'class="weather1"' not in html:
        return None
    w = {}
    # 実況時刻：weather1_title 内の HH:MM（"現在"有無・全半角空白差を許容）
    tm = re.search(r'weather1_title">[^<]*?(\d{1,2}:\d{2})', html)
    w["時刻"] = tm.group(1) if tm else None
    # ラベル対（Title→Data）
    pairs = re.findall(
        r'weather1_bodyUnitLabelTitle">([^<]*)</span>\s*'
        r'<span class="weather1_bodyUnitLabelData">([^<]*)</span>', html)
    labels = {t.strip(): d.strip() for t, d in pairs}
    def num(v, unit):
        if not v: return None
        mm = re.search(r'-?\d+(?:\.\d+)?', v.replace(unit, ""))
        return float(mm.group()) if mm else None
    w["気温"]   = num(labels.get("気温", ""), "℃")
    w["水温"]   = num(labels.get("水温", ""), "℃")
    w["風速"]   = num(labels.get("風速", ""), "m")
    w["波高"]   = num(labels.get("波高", ""), "cm")
    # 天候：LabelDataが空でLabelTitleが天候名（雨/晴/曇/雪…）のユニット
    tenkou = None
    for t, d in pairs:
        if not d.strip() and t.strip() in ("晴", "曇", "雨", "雪", "霧", "快晴"):
            tenkou = t.strip(); break
    if tenkou is None:
        wm = re.search(r'weather1_bodyUnitImage is-weather\d+"></p>\s*'
                       r'<div class="weather1_bodyUnitLabel">\s*'
                       r'<span[^>]*>([^<]*)</span>', html)
        tenkou = wm.group(1).strip() if wm else None
    w["天候"] = tenkou
    # 風向：is-directionNN 矢印番号のみ保持（番号→方位のマッピングは未検証のため
    # 方位テキストは出さない。サイト哲学=誤情報を出さない／検証できるまで非表示）。
    dm = re.search(r'weather1_bodyUnitImage is-direction(\d+)', html)
    w["風向番号"] = int(dm.group(1)) if dm else None
    # 天候の &nbsp;（未掲載）は空扱い
    if w.get("天候") in (" ", "&nbsp;", ""):
        w["天候"] = None
    # 有効判定：時刻または風速/天候のいずれか取得できたら有効
    if w.get("時刻") or w.get("風速") is not None or w.get("天候"):
        return w
    return None

def main():
    try:
        with open(RACERS, encoding="utf-8-sig") as fp:
            rows = list(csv.DictReader(fp))
    except Exception as e:
        print("racers読込不可:", e); return
    if not rows:
        print("出走表空"); return
    hd = rows[0].get("開催日", "")
    # 場コード→{レース番号:締切時刻, 場名}
    venues = {}
    for r in rows:
        jcd = r.get("場コード");
        if not jcd: continue
        v = venues.setdefault(jcd, {"場名": r.get("場名", ""), "races": {}})
        try:
            rno = int(str(r.get("レース", "")).replace("R", ""))
        except Exception:
            continue
        v["races"][rno] = r.get("締切時刻", "")
    now = jst_now(); now_min = now.hour * 60 + now.minute
    stad = {}
    for jcd in sorted(venues):
        v = venues[jcd]; races = v["races"]
        if not races: continue
        # 次レース（締切 >= 現在）。無ければ最終レース。
        def close_min(rno):
            t = races.get(rno, "")
            m = re.match(r'(\d{1,2}):(\d{2})', str(t))
            return int(m.group(1)) * 60 + int(m.group(2)) if m else 9999
        upcoming = sorted([rno for rno in races if close_min(rno) >= now_min], key=close_min)
        target = upcoming[0] if upcoming else max(races)
        got = None
        # target から最大3レース遡って実況のある最新を拾う（未掲載対策・取得数を抑制）
        fallback = [x for x in sorted(races, reverse=True) if x < target][:3]
        for rno in [target] + fallback:
            try:
                html = fetch(jcd, rno, hd)
            except Exception as e:
                print(f"  {jcd} {rno}R 取得不可: {e}"); time.sleep(SLEEP); continue
            w = parse_weather(html)
            time.sleep(SLEEP)
            if w:
                w["レース"] = f"{rno}R"; w["場名"] = v["場名"]; got = w; break
        if got:
            stad[jcd] = got
            print(f"  {jcd} {v['場名']} {got['レース']} {got.get('時刻')} 風{got.get('風速')}m(向#{got.get('風向番号')}) {got.get('天候')} 波{got.get('波高')}cm 気温{got.get('気温')} 水温{got.get('水温')}")
    doc = {"updatedJst": now.strftime("%Y-%m-%d %H:%M"), "開催日": hd,
           "source": "boatrace.jp beforeinfo（実況・水面気象）", "stadiums": stad}
    import os
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"OK: {len(stad)}場 → {OUT}")

if __name__ == "__main__":
    main()
