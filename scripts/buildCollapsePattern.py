#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""buildCollapsePattern.py — ①(枠1)が崩れたレースの「崩れ方」を場別に実数集計

過去の確定結果 docs/results/data/YYYYMMDD.json（ファイル名が8桁日付のもののみ）を全走査し、
①＝枠1 の着が4以上（＝着外）だったレースを抽出。場別に「勝者艇(枠)×決まり手」の分布と
決まり手合計を集計して docs/data/collapsePattern.json に出力する。標準ライブラリのみ。

方針：確率・買い目・予想は出さない。あくまで「①が着外だったレースの内訳（実数）」であり、
全レースに対する発生率ではない（誤読防止のため inOutRate を別掲）。

使い方: python scripts/buildCollapsePattern.py
"""
import io
import os
import re
import json
import glob
import datetime

RESULTS_DIR = "docs/results/data"
OUT_PATH = "docs/data/collapsePattern.json"
MIN_N = 200          # 崩れ方分布を出す最小母数（①着外レース数）
TOP_PATTERNS = 5     # patterns は上位5件まで


def load(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def waku1_finish(race):
    """枠1 の着（int）を返す。見つからない/非intは None。"""
    for b in race.get("艇", []) or []:
        if b.get("枠") == 1:
            f = b.get("着")
            return f if isinstance(f, int) else None
    return None


def main():
    files = sorted(
        f for f in glob.glob(os.path.join(RESULTS_DIR, "*.json"))
        if re.match(r"\d{8}\.json$", os.path.basename(f))
    )
    # 場コード -> {"total": n(枠1着が確定した全レース), "collapse": n(枠1着外),
    #             "pat": {(boat,kimarite): count}}
    agg = {}
    for path in files:
        try:
            d = load(path)
        except Exception:
            continue
        for v in d.get("場", []) or []:
            jcd = str(v.get("場コード") or "").zfill(2)
            if not jcd or jcd == "00":
                continue
            a = agg.setdefault(jcd, {"total": 0, "collapse": 0, "pat": {}})
            for r in v.get("レース", []) or []:
                f1 = waku1_finish(r)
                if f1 is None:
                    continue
                a["total"] += 1
                if f1 < 4:
                    continue
                # ①着外＝崩れ
                a["collapse"] += 1
                boat = r.get("1着")
                kim = r.get("決まり手")
                if not isinstance(boat, int) or not isinstance(kim, str) or not kim:
                    continue
                key = (boat, kim)
                a["pat"][key] = a["pat"].get(key, 0) + 1

    venues = {}
    for jcd, a in sorted(agg.items()):
        total = a["total"]
        coll = a["collapse"]
        in_out = round(100.0 * coll / total, 1) if total else 0.0
        if coll < MIN_N:
            venues[jcd] = {"n": coll, "inOutRate": in_out,
                           "patterns": None, "kimariteSum": {}}
            continue
        # 勝者艇×決まり手の分布（①着外レースを母数）
        pats = []
        ksum = {}
        for (boat, kim), c in a["pat"].items():
            pct = round(100.0 * c / coll, 1)
            pats.append({"boat": boat, "kimarite": kim, "pct": pct, "_c": c})
            ksum[kim] = ksum.get(kim, 0) + c
        pats.sort(key=lambda x: (-x["_c"], x["boat"]))
        pats = [{"boat": p["boat"], "kimarite": p["kimarite"], "pct": p["pct"]}
                for p in pats[:TOP_PATTERNS]]
        kimarite_sum = {k: round(100.0 * c / coll, 1)
                        for k, c in sorted(ksum.items(), key=lambda kv: -kv[1])}
        venues[jcd] = {"n": coll, "inOutRate": in_out,
                       "patterns": pats, "kimariteSum": kimarite_sum}

    out = {"updated": datetime.date.today().strftime("%Y-%m-%d"), "venues": venues}
    with io.open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    # サマリ（stdout）
    npat = sum(1 for v in venues.values() if v["patterns"] is not None)
    nnull = sum(1 for v in venues.values() if v["patterns"] is None)
    print("venues=%d  patterns算出=%d  null(母数不足<%d)=%d  -> %s"
          % (len(venues), npat, MIN_N, nnull, OUT_PATH))


if __name__ == "__main__":
    main()
