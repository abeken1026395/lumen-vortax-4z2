# -*- coding: utf-8 -*-
"""
24場 3連単「最多出目」集計。
docs/payouts/*Payouts.csv の combo 列を場ごとに集計し、
過去に最も多く出現した3連単（出目）とその回数・全レース数・出現割合・対象期間を
docs/payouts/trifectaTop.json に出力する。

方針上の重要な制約（CLAUDE.md 準拠）:
  - これは「過去に出た回数」の可視化であり、買い目・確率・予想ではない。
  - 「狙い目」「来やすい」等の推奨表現・確率提示はしない。
  - 出力の note に誤読対策の一文を必ず持たせ、HTML 側でも明示する。

新規データ収集は不要（既存の払戻CSVのみを入力）。
"""
import os
import csv
import glob
import json
import re

PAYDIR = os.path.join("docs", "payouts")
OUT = os.path.join(PAYDIR, "trifectaTop.json")

# CSVファイル名 slug → (jcd, 場名)。buildPayoutsSummary.py の SLUG と対応。
SLUG2VENUE = {
    "kiryu": (1, "桐生"), "toda": (2, "戸田"), "edogawa": (3, "江戸川"),
    "heiwajima": (4, "平和島"), "tamagawa": (5, "多摩川"), "hamanako": (6, "浜名湖"),
    "gamagori": (7, "蒲郡"), "tokoname": (8, "常滑"), "tsu": (9, "津"),
    "mikuni": (10, "三国"), "biwako": (11, "びわこ"), "suminoe": (12, "住之江"),
    "amagasaki": (13, "尼崎"), "naruto": (14, "鳴門"), "marugame": (15, "丸亀"),
    "kojima": (16, "児島"), "miyajima": (17, "宮島"), "tokuyama": (18, "徳山"),
    "shimonoseki": (19, "下関"), "wakamatsu": (20, "若松"), "ashiya": (21, "芦屋"),
    "fukuoka": (22, "福岡"), "karatsu": (23, "唐津"), "omura": (24, "大村"),
}

COMBO_RE = re.compile(r"^[1-6]-[1-6]-[1-6]$")


def fmt(ymd):
    return ymd[0:4] + "/" + ymd[4:6] + "/" + ymd[6:8]


def build_one(path):
    counts = {}
    days = set()
    total = 0
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            combo = (row.get("combo") or "").strip()
            hd = (row.get("hd") or "").strip()
            if not COMBO_RE.match(combo):
                continue
            counts[combo] = counts.get(combo, 0) + 1
            total += 1
            if len(hd) == 8:
                days.add(hd)
    if total == 0 or not counts:
        return None
    # 最多出目（同数は出目文字列で昇順に固定してタイを解消）
    combo, cnt = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    hds = sorted(days)
    period = {"from": fmt(hds[0]), "to": fmt(hds[-1]), "days": len(hds)} if hds else None
    return {
        "combo": combo,
        "count": cnt,
        "races": total,
        "share": round(cnt / total * 100, 1),
        "period": period,
    }


def main():
    venues = {}
    for path in sorted(glob.glob(os.path.join(PAYDIR, "*Payouts.csv"))):
        base = os.path.basename(path)
        slug = base[:-len("Payouts.csv")]
        meta = SLUG2VENUE.get(slug)
        if not meta:
            continue
        res = build_one(path)
        if not res:
            continue
        jcd, name = meta
        code = "%02d" % jcd
        venues[code] = {"stadium": name, "jcd": jcd, "slug": slug, **res}

    out = {
        "title": "3連単 最多出目（過去実績）",
        "source": "公式競走成績（3連単払戻の集計）",
        "note": "過去に出た回数であり、次のレースの予想ではありません。",
        "venueCount": len(venues),
        "venues": venues,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=2))
    print("venues:", len(venues))
    for code in sorted(venues):
        v = venues[code]
        print(code, v["stadium"], v["combo"], v["count"], "/", v["races"], v["share"], "%")


if __name__ == "__main__":
    main()
