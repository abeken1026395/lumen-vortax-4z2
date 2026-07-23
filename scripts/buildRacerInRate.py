# -*- coding: utf-8 -*-
# buildRacerInRate.py
# 選手別「①(進入コース1)からの1着率」を過去結果から因果的に集計する。
# docs/results/data/*.json を全走査し、各レースの艇のうち コース==1 の選手について
# 1着だったかを数え、docs/data/racerInRate.json に出力する。
#
# 用途: ①着外予測の下振れ要因（見どころの事実提示）で「①のinWinRate」を使う。
# スコア・閾値・判定・検証ループには一切関与しない。純粋な集計出力。
#
# 出力: {"updated":"YYYY-MM-DD","racers":{"登番":{"inN":進入数,"inWin":1着数,"rate":百分率}}}
#   - inN < 20 は rate=null（母数不足で率を出さない）
import os
import re
import json
import glob
import datetime

JST = datetime.timezone(datetime.timedelta(hours=9))
DATA_DIR = os.path.join("docs", "results", "data")
OUT = os.path.join("docs", "data", "racerInRate.json")
MIN_N = 20   # 母数不足の閾値（未満は rate=null）


def iter_boats(day):
    """1日分JSON → 各レースの艇dictを yield（場→レース→艇）。"""
    for venue in day.get("場", []) or []:
        for race in venue.get("レース", []) or []:
            for boat in race.get("艇", []) or []:
                yield boat


def main():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*.json")))
    agg = {}   # 登番 -> [inN, inWin]
    scanned = skipped = 0
    for p in files:
        try:
            with open(p, "r", encoding="utf-8") as fp:
                day = json.load(fp)
        except Exception as e:
            skipped += 1
            print("  [skip] {}: {}".format(os.path.basename(p), str(e)[:50]))
            continue
        scanned += 1
        for boat in iter_boats(day):
            # 進入コース1の艇のみ対象
            if str(boat.get("コース")) != "1":
                continue
            toban = str(boat.get("登番") or "").strip()
            if not toban:
                continue
            rec = agg.setdefault(toban, [0, 0])
            rec[0] += 1                                   # inN
            if str(boat.get("着")) == "1":               # 1着
                rec[1] += 1                               # inWin
    racers = {}
    rated = nulls = 0
    for toban, (inN, inWin) in agg.items():
        if inN >= MIN_N:
            rate = round(inWin / inN * 100, 1)
            rated += 1
        else:
            rate = None
            nulls += 1
        racers[toban] = {"inN": inN, "inWin": inWin, "rate": rate}
    out = {
        "updated": datetime.datetime.now(JST).strftime("%Y-%m-%d"),
        "racers": racers,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fp:
        json.dump(out, fp, ensure_ascii=False, indent=1)
    print("走査 {}ファイル / スキップ {}".format(scanned, skipped))
    print("選手数 {} / rate算出 {} / null(母数<{}) {}".format(len(racers), rated, MIN_N, nulls))
    print("保存: {}".format(OUT))


if __name__ == "__main__":
    main()
