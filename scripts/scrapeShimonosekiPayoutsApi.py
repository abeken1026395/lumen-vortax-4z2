# -*- coding: utf-8 -*-
"""
下関（jcd=19）3連単払戻データ収集（クラウド到達可能ソース版）

mbrace公式LZHはクラウドIPから遮断されるため、クラウド環境でも到達できる
非公式ミラー BoatraceOpenAPI（GitHub Pages 上の公式競走成績JSON）を参照する。
  ソース: https://github.com/BoatraceOpenAPI/results （gh-pages / docs/v2）
  ※ 非公式ミラー。元データは BOAT RACE 公式の競走成績。値は同一。

出力: docs/payouts/shimonosekiPayouts.csv （列: hd, rno, combo, payout）
      ※ mbrace版 scrapeKaratsuPayouts.py と同一スキーマ。相互に追記・共存可。

v2 スキーマ: results[].race_stadium_number / race_number /
             payouts.trifecta[0].combination(例 "1-5-6") / .payout

環境変数:
  START … 'YYYYMMDD' 収集開始日（既定 20250715 = v2の最古提供日）
  END   … 'YYYYMMDD' 収集終了日（既定 昨日）
"""
import os
import csv
import json
import time
import datetime
import urllib.request

JCD = 19  # 下関（公式場コード19）
RAW = "https://raw.githubusercontent.com/BoatraceOpenAPI/results/gh-pages/docs/v2/{y}/{ymd}.json"
OUT = "docs/payouts/shimonosekiPayouts.csv"

SLEEP = 0.2
TIMEOUT = 30
UA = "Mozilla/5.0 boatrace-data-collector"


def fetch_day(d):
    """その日のv2 JSONを返す。存在しない(404=非配信日)ならNone。"""
    ymd = d.strftime("%Y%m%d")
    url = RAW.format(y=d.strftime("%Y"), ymd=ymd)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def extract_shimonoseki(doc):
    """下関(19)の各レースから 3連単組番と配当を取り出す。"""
    out = []
    for rec in doc.get("results", []):
        if rec.get("race_stadium_number") != JCD:
            continue
        rno = rec.get("race_number")
        tri = (rec.get("payouts") or {}).get("trifecta") or []
        if not rno or not tri:
            continue  # 中止・返還などで3連単不成立の場合はスキップ
        t = tri[0]
        combo = t.get("combination")
        payout = t.get("payout")
        if not combo or payout is None:
            continue
        out.append((int(rno), combo, int(payout)))
    return out


def load_existing():
    done = set()
    rows = []
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            r = csv.reader(f)
            next(r, None)
            for row in r:
                if len(row) >= 4:
                    rows.append(row)
                    done.add((row[0], row[1]))
    return done, rows


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    done, rows = load_existing()

    start_s = os.environ.get("START", "").strip() or "20250715"  # 空文字(schedule時)も既定へ
    start = datetime.date(int(start_s[0:4]), int(start_s[4:6]), int(start_s[6:8]))
    end_s = os.environ.get("END", "").strip()
    if end_s:
        end = datetime.date(int(end_s[0:4]), int(end_s[4:6]), int(end_s[6:8]))
    else:
        end = datetime.date.shimonosekiy() - datetime.timedelta(days=1)

    got = 0
    days = 0
    d = start
    while d <= end:
        hd = d.strftime("%Y%m%d")
        d += datetime.timedelta(days=1)
        if (hd, "1") in done:
            continue
        try:
            doc = fetch_day(datetime.datetime.strptime(hd, "%Y%m%d").date())
        except Exception as e:
            print("skip", hd, repr(e))
            time.sleep(SLEEP)
            continue
        if doc is None:
            continue
        recs = extract_shimonoseki(doc)
        if recs:
            for rno, combo, payout in recs:
                rows.append([hd, str(rno), combo, str(payout)])
            got += len(recs)
            days += 1
            print("ok", hd, len(recs))
        time.sleep(SLEEP)

    rows.sort(key=lambda x: (x[0], int(x[1])))
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hd", "rno", "combo", "payout"])
        w.writerows(rows)
    print("done. new records:", got, "new days:", days, "total rows:", len(rows))


if __name__ == "__main__":
    main()
