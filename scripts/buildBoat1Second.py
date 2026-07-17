# -*- coding: utf-8 -*-
"""
24場「1号艇が1着だったときの2着内訳」集計。
docs/payouts/*Payouts.csv の combo 列（3連単の着順 X-Y-Z）から、
1着＝1号艇（combo が "1-" で始まる）のレースだけを抜き出し、
その2着（Y）が2〜6号艇のどれだったかの回数・出現割合を場ごとに集計して
docs/payouts/boat1Second.json に出力する。

方針上の重要な制約（CLAUDE.md 準拠）:
  - これは「過去に出た回数の割合（実績内訳）」の可視化であり、買い目・予想ではない。
  - 公開ページでは確率提示・推奨表現（狙い目/来やすい等）はしない。
  - 出力の note に誤読対策の一文を持たせ、HTML 側でも明示する。

新規データ収集は不要（既存の払戻CSVのみを入力）。
"""
import os
import csv
import glob
import json
import re

PAYDIR = os.path.join("docs", "payouts")
OUT = os.path.join(PAYDIR, "boat1Second.json")

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

COMBO_RE = re.compile(r"^([1-6])-([1-6])-([1-6])$")


def fmt(ymd):
    return ymd[0:4] + "/" + ymd[4:6] + "/" + ymd[6:8]


def build_one(path):
    total = 0            # 3連単が確定した全レース数
    first1 = 0           # うち1着＝1号艇
    second = {b: 0 for b in range(2, 7)}   # 1着1号艇のときの2着号艇分布
    days = set()
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            m = COMBO_RE.match((row.get("combo") or "").strip())
            if not m:
                continue
            total += 1
            hd = (row.get("hd") or "").strip()
            if len(hd) == 8:
                days.add(hd)
            if m.group(1) == "1":
                first1 += 1
                second[int(m.group(2))] += 1
    if total == 0 or first1 == 0:
        return None
    hds = sorted(days)
    period = {"from": fmt(hds[0]), "to": fmt(hds[-1]), "days": len(hds)} if hds else None
    dist = [
        {"boat": b, "count": second[b], "share": round(second[b] / first1 * 100, 1)}
        for b in range(2, 7)
    ]
    return {
        "races": total,
        "firstBoat1": first1,
        "firstBoat1Rate": round(first1 / total * 100, 1),
        "second": dist,
        "period": period,
    }


def main():
    venues = {}
    for path in sorted(glob.glob(os.path.join(PAYDIR, "*Payouts.csv"))):
        slug = os.path.basename(path)[:-len("Payouts.csv")]
        meta = SLUG2VENUE.get(slug)
        if not meta:
            continue
        res = build_one(path)
        if not res:
            continue
        jcd, name = meta
        venues["%02d" % jcd] = {"stadium": name, "jcd": jcd, "slug": slug, **res}

    out = {
        "title": "1号艇が1着だったときの2着内訳（過去実績）",
        "source": "公式競走成績（3連単払戻の集計）",
        "note": "過去に出た回数の割合であり、次のレースの予想ではありません。",
        "venueCount": len(venues),
        "venues": venues,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=2))
    print("venues:", len(venues))
    for code in sorted(venues):
        v = venues[code]
        dist = " ".join("%d:%.1f%%" % (d["boat"], d["share"]) for d in v["second"])
        print(code, v["stadium"], "1着1号艇=%d/%d(%.1f%%)" % (v["firstBoat1"], v["races"], v["firstBoat1Rate"]), "2着", dist)


if __name__ == "__main__":
    main()
