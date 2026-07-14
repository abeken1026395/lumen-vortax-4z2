#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kansenki_pubplan.py — 前夜便/回収便のための「掲載日 決定」と「場単位 執筆計画」

掲載日は **CSV最大開催日**（壁時計非依存）で決める。souce/{掲載日}.json を読み、
各場を「今すぐ書ける(toWrite)／まだ書けない(skip)／既に書いた(done)」に分類する。

書ける条件（前夜便・回収便で追記してよい場）:
  todayProgram あり ∧（results非空 または dayNum==1[初日]）
  ＝ 第1部(前日振り返り)の材料が確定済み、または初日で第1部が構造上無い、かつ
     第2部(きょうの注目)の材料(todayProgram)がある場。
  ※ 前夜便は souce が育つ途中で走る。当日結果が未取得(results空)の非初日場は
    「まだ書けない」＝後続の回収便に持ち越す（早すぎる第1部欠落記事を作らない）。

未執筆場だけを toWrite に出す（既存記事は決して上書きしない）。

出力: stdout に JSON
  {pubdate, source, dayMax(csv最大開催日), toWrite:[jcd..],
   skip:[{jcd,venue,reason}..], done:[jcd..], counts:{...}}
使い方:
  python scripts/kansenki_pubplan.py                        # CSVから掲載日を自動決定
  python scripts/kansenki_pubplan.py --pubdate 20260714     # 掲載日を明示
  python scripts/kansenki_pubplan.py --csv path --source-dir dir --articles-dir dir
"""
import sys
import os
import io
import csv
import json

CSV_DEFAULT = "docs/racers/racers_today.csv"
SOURCE_DIR_DEFAULT = "docs/data/kansenki/source"
ARTICLES_DIR_DEFAULT = "docs/data/kansenki/articles"
HIGHLIGHTS_DEFAULT = "docs/highlights/highlights.json"


def _opt(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def csv_max_hd(csv_path):
    """racers_today.csv の開催日カラムの最大値(8桁)。壁時計に依らず掲載日を決める根拠。"""
    if not os.path.exists(csv_path):
        return None
    mx = None
    with io.open(csv_path, encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            hd = (row.get("開催日") or "").strip()
            if len(hd) == 8 and hd.isdigit():
                if mx is None or hd > mx:
                    mx = hd
    return mx


def highlights_hd(path):
    try:
        with io.open(path, encoding="utf-8") as f:
            return str(json.load(f).get("開催日") or "") or None
    except Exception:
        return None


def load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def writable(v):
    """この場を今すぐ書けるか、書けない場合の理由。"""
    if not v.get("todayProgram"):
        return False, "第2部材料なし(todayProgram無)"
    results = v.get("results") or []
    day1 = (v.get("dayNum") == 1) or (v.get("dayLabel") == "初日")
    if results:
        return True, ""
    if day1:
        return True, ""  # 初日は前日結果が構造上0＝第1部なしで書く
    return False, "前日結果未確定(results空・非初日)＝回収便に持ち越し"


def plan_for(pubdate, source_dir, articles_dir):
    src_path = os.path.join(source_dir, "%s.json" % pubdate)
    if not os.path.exists(src_path):
        return {"pubdate": pubdate, "source": None, "toWrite": [], "skip": [],
                "done": [], "counts": {"venues": 0, "toWrite": 0, "skip": 0, "done": 0},
                "note": "source無し"}
    src = load(src_path)
    to_write, skip, done = [], [], []
    for v in src.get("venues", []):
        jcd = v.get("jcd")
        venue = v.get("venue")
        art = os.path.join(articles_dir, "%s-%s.json" % (pubdate, jcd))
        if os.path.exists(art):
            done.append(jcd)
            continue
        ok, reason = writable(v)
        if ok:
            to_write.append(jcd)
        else:
            skip.append({"jcd": jcd, "venue": venue, "reason": reason})
    return {
        "pubdate": pubdate, "source": src_path,
        "toWrite": to_write, "skip": skip, "done": done,
        "counts": {"venues": len(src.get("venues", [])),
                   "toWrite": len(to_write), "skip": len(skip), "done": len(done)},
    }


def resolve_pubdate(csv_path, source_dir, highlights_path):
    """掲載日=CSV最大開催日。無ければ highlights.json 開催日にフォールバック。"""
    hd = csv_max_hd(csv_path)
    if hd:
        return hd, "csv-max"
    hd = highlights_hd(highlights_path)
    if hd:
        return hd, "highlights"
    return None, "none"


def main():
    csv_path = _opt("--csv", CSV_DEFAULT)
    source_dir = _opt("--source-dir", SOURCE_DIR_DEFAULT)
    articles_dir = _opt("--articles-dir", ARTICLES_DIR_DEFAULT)
    highlights_path = _opt("--highlights", HIGHLIGHTS_DEFAULT)
    pubdate = _opt("--pubdate")

    day_max = csv_max_hd(csv_path)
    src = "explicit"
    if not pubdate:
        pubdate, src = resolve_pubdate(csv_path, source_dir, highlights_path)
    if not pubdate:
        print(json.dumps({"pubdate": None, "error": "掲載日を決定できない(CSV/highlights共に不在)",
                          "dayMax": day_max}, ensure_ascii=False))
        sys.exit(0)

    res = plan_for(pubdate, source_dir, articles_dir)
    res["dayMax"] = day_max
    res["pubdateSource"] = src
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
