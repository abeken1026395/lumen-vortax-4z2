# -*- coding: utf-8 -*-
"""
kdata/ の月別 entries（13列・完全版）を hd,jcd,rno,waku 昇順で単純結合し、
kdata/entriesFull.csv を生成する。ヘッダは1行のみ。

安全策:
  - 全月別ファイルのヘッダが完全に同一であることを検証してから結合する。
  - 結合後の行数が EXPECTED(328,176) と一致することを検証する。
    不一致なら entriesFull.csv を書かずに異常終了する（コミット前提を壊さない）。

使い方: python scripts/kdataMergeEntries.py
"""
import os
import csv
import glob
import sys

KDATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kdata")
OUT = os.path.join(KDATA, "entriesFull.csv")
EXPECTED = 328176


def main():
    files = sorted(glob.glob(os.path.join(KDATA, "entries2*.csv")))
    if not files:
        print("月別 entries が見つからない:", KDATA)
        return 2

    # 1) ヘッダ一致検証
    headers = []
    for p in files:
        with open(p, encoding="utf-8") as f:
            headers.append(f.readline().rstrip("\n").rstrip("\r"))
    if len(set(headers)) != 1:
        print("ヘッダ不一致のため中止:")
        for p, h in zip(files, headers):
            print("  %s : %s" % (os.path.basename(p), h))
        return 2
    header = headers[0]
    cols = header.split(",")
    print("月別 %d ファイル / 共通ヘッダ(%d列)= %s" % (len(files), len(cols), header))

    # 2) 全行収集
    rows = []
    for p in files:
        with open(p, encoding="utf-8") as f:
            r = csv.reader(f)
            next(r)  # skip header
            for row in r:
                rows.append(row)

    # 3) hd, jcd, rno, waku 昇順（rno/waku は数値順）
    idx = {c: i for i, c in enumerate(cols)}
    def keyfn(row):
        def num(v):
            return int(v) if v.isdigit() else 10 ** 9
        return (row[idx["hd"]], row[idx["jcd"]], num(row[idx["rno"]]), num(row[idx["waku"]]))
    rows.sort(key=keyfn)

    # 4) 行数検証
    if len(rows) != EXPECTED:
        print("行数不一致: %d != EXPECTED %d → entriesFull.csv を書かずに中止" % (len(rows), EXPECTED))
        return 2

    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)

    print("生成: %s  rows=%d  size=%d B" % (OUT, len(rows), os.path.getsize(OUT)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
