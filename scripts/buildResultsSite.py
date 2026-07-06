# -*- coding: utf-8 -*-
# buildResultsSite.py
# results/YYYYMMDD.json(リポジトリ直下・GitHub Pages非配信)を、
# 結果表ページ docs/results/ から読める公開用データに変換する。
#   出力: docs/results/data/YYYYMMDD.json  … 1日分(コンパクト)
#         docs/results/data/index.json     … 日付一覧(新しい順)+開催場数
#
# 元データは buildResults.py が BoatraceOpenAPI から生成したもので、
# 着順・決まり手・全式別払戻・艇別を含む。ここでは表示に必要な項目を
# そのまま公開領域(docs/)へコピーするだけ(判定・予想は元から無い)。
#
# 使い方: python scripts/buildResultsSite.py
#   ・results/*.json 全てを対象に docs/results/data/ を再生成する。
import io
import os
import re
import json
import glob

SRC_DIR = "results"
OUT_DIR = os.path.join("docs", "results", "data")

# 場コード → 場名(build_arare.py と同一)
STADIUM = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島", "05": "多摩川",
    "06": "浜名湖", "07": "蒲郡", "08": "常滑", "09": "津", "10": "三国",
    "11": "びわこ", "12": "住之江", "13": "尼崎", "14": "鳴門", "15": "丸亀",
    "16": "児島", "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}


def race_no(r):
    """'11R' → 11。並べ替え用。"""
    m = re.match(r"(\d+)", str(r.get("レース", "")))
    return int(m.group(1)) if m else 0


def build_day(path):
    """1日分の results JSON を公開用の辞書に整形して返す。"""
    d = json.load(io.open(path, encoding="utf-8"))
    hd = d.get("開催日") or os.path.basename(path)[:8]
    races = d.get("結果", []) or []
    # 場コード → レース配列
    venues = {}
    for r in races:
        jcd = str(r.get("場コード", "")).zfill(2)
        venues.setdefault(jcd, []).append(r)
    stadiums = []
    for jcd in sorted(venues.keys()):
        rs = sorted(venues[jcd], key=race_no)
        stadiums.append({
            "場コード": jcd,
            "場名": STADIUM.get(jcd, jcd),
            "レース": rs,
        })
    return {
        "開催日": hd,
        "取得時刻": d.get("取得時刻"),
        "レース数": len(races),
        "場数": len(stadiums),
        "場": stadiums,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    index = []
    for path in sorted(glob.glob(os.path.join(SRC_DIR, "*.json"))):
        hd = os.path.basename(path)[:8]
        if not re.match(r"^\d{8}$", hd):
            continue
        try:
            day = build_day(path)
        except Exception as e:
            print("skip", hd, e)
            continue
        outpath = os.path.join(OUT_DIR, "%s.json" % hd)
        with io.open(outpath, "w", encoding="utf-8") as f:
            json.dump(day, f, ensure_ascii=False, separators=(",", ":"))
        index.append({"開催日": hd, "場数": day["場数"], "レース数": day["レース数"]})
    index.sort(key=lambda x: x["開催日"], reverse=True)
    with io.open(os.path.join(OUT_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"件数": len(index), "日付": index}, f, ensure_ascii=False, separators=(",", ":"))
    print("wrote", len(index), "days to", OUT_DIR)


if __name__ == "__main__":
    main()
