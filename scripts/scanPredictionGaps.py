#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scanPredictionGaps.py
predictions生成の絶対防衛 4/4「夜間の欠番台帳スキャン（検知・記録専用）」。

全レース終了後（夜）に、前日からN日前まで(既定3日)の predictions/YYYYMMDD.json を検査し、
欠落/無効な日を predictions_gaps.csv に「欠番」として記録する。
（当日は朝生成前/ドリフト時に未生成が正常なため対象外＝誤検知を避ける。）

役割分担（点2 昼監視との住み分け）:
  ・当日・日中の救済は点2(monitorPredictions.py)＋通常生成が担う。
  ・本スクリプトは生成・埋め戻しを一切しない。過去日を含む欠番の“台帳化”のみ。
  ・夜間は出走表が翌日分へ更新され build_highlights は日付ガードで当日生成できないため、
    夜に生成機能を持たせても実質無効。よって検知・記録に純化する。

厳守:
  ・既存predictionsには一切触れない（読むだけ）。埋め戻し禁止。
  ・同一対象日が既に記録済みなら再記録しない（重複スキップ）。

使い方: python scripts/scanPredictionGaps.py
  環境変数 GAP_WINDOW でN日を上書き（既定3）。GAPLOG で台帳パスを上書き。
"""
import os
import csv
import json
import datetime

GAPLOG = os.environ.get("GAPLOG", "predictions_gaps.csv")
WINDOW = max(1, int(os.environ.get("GAP_WINDOW", "3")))


def jst_now():
    return datetime.datetime.utcnow() + datetime.timedelta(hours=9)


def valid_pred(path):
    """predictions/YYYYMMDD.json が開けて『予測』が非空なら True。"""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return bool(d.get("予測"))
    except Exception:
        return False


def recorded_days():
    """台帳に既に記録済みの対象日の集合（重複記録の防止）。"""
    days = set()
    if not os.path.exists(GAPLOG):
        return days
    try:
        with open(GAPLOG, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                d = (row.get("対象日") or "").strip()
                if d:
                    days.add(d)
    except Exception as e:
        print("台帳読込警告:", e)
    return days


def main():
    # 当日は朝の通常生成の前（早朝実行やスケジュール・ドリフト時）だと未生成が正常なため、
    # 欠番判定から除外する。対象は「前日〜N日前」の“生成が完了しているべき”日のみ。
    # 当日の欠落は点2(昼監視)＋通常生成が担う。
    today = jst_now().date()
    days = [(today - datetime.timedelta(days=i)).strftime("%Y%m%d") for i in range(1, WINDOW + 1)]
    already = recorded_days()

    missing = []
    for day in days:
        path = os.path.join("predictions", "%s.json" % day)
        if valid_pred(path):
            continue
        missing.append(day)

    to_add = [d for d in missing if d not in already]
    ok_days = [d for d in days if d not in missing]

    print("スキャン対象(直近%d日): %s" % (WINDOW, " ".join(days)))
    print("  正常: %s" % (" ".join(ok_days) if ok_days else "なし"))
    print("  欠番検知: %s" % (" ".join(missing) if missing else "なし"))
    print("  既記録(重複スキップ): %s" % (" ".join(d for d in missing if d in already) or "なし"))

    if not to_add:
        print("台帳追記なし（新規欠番なし）")
        return

    ts = jst_now().strftime("%Y-%m-%d %H:%M")
    new = not os.path.exists(GAPLOG)
    with open(GAPLOG, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["検知日時JST", "対象日", "状態"])
        for d in to_add:
            w.writerow([ts, d, "夜間スキャン検知（欠番・埋め戻し禁止）"])
    print("台帳追記: %d日 → %s（%s）" % (len(to_add), GAPLOG, " ".join(to_add)))


if __name__ == "__main__":
    main()
