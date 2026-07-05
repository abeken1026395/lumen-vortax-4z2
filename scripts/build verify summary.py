#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_verify_summary.py
非公開の verify_log.csv を集計し、公開用の docs/data/verify_summary.json を出力する。
生ログ（1レース1行）は公開せず、集計値だけを公開する。

verify_log.csv の列：
  日付, 場コード, レース, 判定, 主役艇, スコア, 着順, 配当, 波乱正誤, 主役正誤

出力する集計：
  - 総レース数・集計期間
  - 判定別の的中率（波乱/堅め/混戦それぞれ）
  - 主役艇の◎(1着)率・連対率
  - スコア帯 × 荒れ率（スコアが荒れの先行指標か）
  - 直近ログ（最新20行・場コードは場名に変換）
"""

import csv
import json
import os
from collections import defaultdict

LOG = "verify_log.csv"
OUT = "docs/data/verify_summary.json"

JCD = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島", "05": "多摩川",
    "06": "浜名湖", "07": "蒲郡", "08": "常滑", "09": "津", "10": "三国",
    "11": "びわこ", "12": "住之江", "13": "尼崎", "14": "鳴門", "15": "丸亀",
    "16": "児島", "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}


def to_float(s):
    try:
        return float(str(s).strip())
    except Exception:
        return None


def to_int(s):
    try:
        return int(str(s).strip())
    except Exception:
        return None


def main():
    if not os.path.exists(LOG):
        # ログがまだ無い場合も空サマリを出して後段(commit)を止めない
        summary = {
            "総レース数": 0, "集計期間": None,
            "判定別的中率": {}, "主役": {"◎率": None, "連対率": None},
            "スコア帯別荒れ率": [], "直近ログ": [],
            "note": "verify_log.csv が未生成。照合が回れば集計されます。",
        }
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print("no log yet -> empty summary written")
        return

    rows = []
    with open(LOG, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    n = len(rows)

    # 判定別の的中率（波乱正誤 = ◯/✕）
    judge_tot = defaultdict(int)
    judge_hit = defaultdict(int)
    for r in rows:
        j = (r.get("判定") or "").strip()
        if not j:
            continue
        judge_tot[j] += 1
        if (r.get("波乱正誤") or "").strip() in ("◯", "○", "OK", "1", "True"):
            judge_hit[j] += 1

    judge_rate = {}
    for j in judge_tot:
        judge_rate[j] = {
            "件数": judge_tot[j],
            "的中率": round(100 * judge_hit[j] / judge_tot[j], 1) if judge_tot[j] else None,
        }

    # 主役艇の◎(1着)率・連対率（主役正誤 = ◎/◯/✕）
    m_tot = 0
    m_win = 0   # ◎ = 1着
    m_ren = 0   # ◎ または ◯ = 連対
    for r in rows:
        mk = (r.get("主役正誤") or "").strip()
        if not mk:
            continue
        m_tot += 1
        if mk in ("◎",):
            m_win += 1
            m_ren += 1
        elif mk in ("◯", "○"):
            m_ren += 1
    main_stats = {
        "◎率": round(100 * m_win / m_tot, 1) if m_tot else None,
        "連対率": round(100 * m_ren / m_tot, 1) if m_tot else None,
        "件数": m_tot,
    }

    # スコア帯 × 荒れ率（配当がHARAN_TH以上を荒れとする。閾値はログ側と揃え5000）
    HARAN_TH = 5000
    bands = [
        ("スコア -3以下", lambda s: s <= -3),
        ("スコア -3〜-1", lambda s: -3 < s <= -1),
        ("スコア -1〜+1", lambda s: -1 < s < 1),
        ("スコア +1〜+3", lambda s: 1 <= s < 3),
        ("スコア +3以上", lambda s: s >= 3),
    ]
    band_tot = defaultdict(int)
    band_haran = defaultdict(int)
    for r in rows:
        s = to_float(r.get("スコア"))
        pay = to_int(r.get("配当"))
        if s is None:
            continue
        for label, cond in bands:
            if cond(s):
                band_tot[label] += 1
                if pay is not None and pay >= HARAN_TH:
                    band_haran[label] += 1
                break

    score_bands = []
    for label, _ in bands:
        t = band_tot[label]
        if t:
            score_bands.append({
                "帯": label, "件数": t,
                "荒れ率": round(100 * band_haran[label] / t, 1),
            })

    # 直近ログ（最新20行・場コード→場名）
    recent = []
    for r in rows[-20:][::-1]:
        recent.append({
            "日付": r.get("日付", ""),
            "場": JCD.get((r.get("場コード") or "").zfill(2), r.get("場コード", "")),
            "レース": r.get("レース", ""),
            "判定": r.get("判定", ""),
            "主役艇": r.get("主役艇", ""),
            "スコア": r.get("スコア", ""),
            "着順": r.get("着順", ""),
            "配当": r.get("配当", ""),
            "波乱正誤": r.get("波乱正誤", ""),
            "主役正誤": r.get("主役正誤", ""),
        })

    dates = sorted(set(r.get("日付", "") for r in rows if r.get("日付")))
    summary = {
        "総レース数": n,
        "集計期間": {"開始": dates[0], "終了": dates[-1]} if dates else None,
        "判定別的中率": judge_rate,
        "主役": main_stats,
        "スコア帯別荒れ率": score_bands,
        "直近ログ": recent,
        "万舟閾値": HARAN_TH,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"summary written: {n} rows -> {OUT}")


if __name__ == "__main__":
    main()
