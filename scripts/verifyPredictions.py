# -*- coding: utf-8 -*-
# verifyPredictions.py
# predictions/YYYYMMDD.json(朝の見立て) と results/YYYYMMDD.json(夜の結果) を
# 場コード×レースで突き合わせ、verify_log.csv に1レース1行で追記する。
# 確定保存の鉄則: predictions は結果を見る前の値。ここでは読むだけで一切書き換えない。
# 検証: 環境変数 HD で対象日付(YYYYMMDD)を指定。未指定なら当日(JST)。
import io
import os
import csv
import json
import datetime

HARAN_TH = 5000   # 3連単この額以上を「荒れ」と固定(設計書の目安)。以後動かさない。
LOG = "verify_log.csv"


def load(path):
    if not os.path.exists(path):
        return None
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        # 破損JSON（例: 衝突マーカー混入）でも全体を落とさず、その日をスキップ。
        print("load失敗(スキップ):", path, e)
        return None


def main():
    hd_env = os.environ.get("HD", "").strip()
    if hd_env:
        days = [x.strip() for x in hd_env.replace("、", ",").split(",") if x.strip()]
    else:
        # 直近N日の窓（既定3）を照合。スケジュール遅延で発火がJST早朝にずれ込み
        # 「当日のみ」だと終了済みの日を照合し損ねる問題への対策。
        # 追記は (日付,場,レース) で重複排除＝冪等。予測or結果が無い日は自動スキップ。
        win = max(1, int(os.environ.get("VERIFY_WINDOW", "3")))
        today = (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).date()
        days = [(today - datetime.timedelta(days=i)).strftime("%Y%m%d") for i in range(win)]
    for hd in days:
        verify_one(hd)


def verify_one(hd):
    pred = load(os.path.join("predictions", "%s.json" % hd))
    res = load(os.path.join("results", "%s.json" % hd))
    if not pred or not res:
        print("missing", hd, "pred", bool(pred), "res", bool(res))
        return

    rmap = {}
    for r in res["結果"]:
        rmap[(r["場コード"], r["レース"])] = r

    done = set()
    new_file = not os.path.exists(LOG)
    if not new_file:
        with io.open(LOG, "r", encoding="utf-8") as f:
            rd = csv.reader(f)
            next(rd, None)
            for row in rd:
                if len(row) >= 3:
                    done.add((row[0], row[1], row[2]))

    out = io.open(LOG, "a", encoding="utf-8", newline="")
    w = csv.writer(out)
    if new_file:
        w.writerow(["日付", "場コード", "レース", "判定", "主役艇", "スコア",
                    "着順", "配当", "波乱正誤", "主役正誤"])

    n = 0
    hit_haran = tot_haran = 0
    hit_main = tot_main = 0
    for p in pred["予測"]:
        key = (p["場コード"], p["レース"])
        if key not in rmap:
            continue
        if (hd, p["場コード"], p["レース"]) in done:
            continue
        r = rmap[key]
        judge = p["判定"]
        main = int(p["主役艇"])
        pay = int(r["三連単配当"])
        top3 = [int(x) for x in r["着順"].split("-")]

        if judge == "波乱":
            hj = "○" if pay >= HARAN_TH else "×"
            tot_haran += 1
            hit_haran += hj == "○"
        elif judge == "堅め":
            hj = "○" if pay < HARAN_TH else "×"
            tot_haran += 1
            hit_haran += hj == "○"
        else:
            hj = "-"

        if main == top3[0]:
            hm = "◎"
        elif main in top3:
            hm = "○"
        else:
            hm = "×"
        if hm != "×":
            hit_main += 1
        tot_main += 1

        w.writerow([hd, p["場コード"], p["レース"], judge, main, p["スコア"],
                    r["着順"], pay, hj, hm])
        n += 1

    out.close()
    hr = "%.0f%%" % (100 * hit_haran / tot_haran) if tot_haran else "-"
    mr = "%.0f%%" % (100 * hit_main / tot_main) if tot_main else "-"
    print("appended", n, "rows | 波乱堅め的中", hr, "| 主役連対", mr)


if __name__ == "__main__":
    main()
