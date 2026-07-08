#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
monitorPredictions.py
predictions生成の絶対防衛 2/4「昼の監視」。

JST昼の定期実行で、当日(JST)のpredictionsが存在し中身が妥当かを検査する。
欠落/無効なら「当日に限り」build_highlights.pyで再生成を試行する。
  ・生成は build_highlights.py の鉄則に従い「無い場合のみ」＝既存predictionsには一切触れない。
  ・日付をまたいだ欠番は対象外（当日のみ扱う）。埋め戻し（過去日の生成）は禁止。
再生成しても当日分が揃わない場合は、埋め戻さず predictions_gaps.csv に欠番として記録する。

使い方: python scripts/monitorPredictions.py
  環境変数で入力パスを上書き可（既定は update_highlights.yml と同じ）。
終了コード: 0=正常/救済/欠番記録（監視自体は成功）。監視の異常時のみ非ゼロ。
"""
import os
import sys
import csv
import json
import subprocess
import datetime

RACERS = os.environ.get("RACERS", "docs/racers/racers_today.csv")
MOTORS = os.environ.get("MOTORS", "docs/motor/motors_all.csv")
HL     = os.environ.get("HL", "docs/highlights/highlights.json")
KIM    = os.environ.get("KIM", "docs/players/racerKimarite.csv")
WX     = os.environ.get("WX", "docs/data/weather.json")
GAPLOG = os.environ.get("GAPLOG", "predictions_gaps.csv")
BH     = os.environ.get("BH", "scripts/build_highlights.py")


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


def record_gap(day, state):
    """埋め戻さず欠番として記録（append-only）。過去の記録は書き換えない。"""
    new = not os.path.exists(GAPLOG)
    ts = jst_now().strftime("%Y-%m-%d %H:%M")
    with open(GAPLOG, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["検知日時JST", "対象日", "状態"])
        w.writerow([ts, day, state])
    print("GAP記録: {} {} → {}".format(day, state, GAPLOG))


def main():
    day = jst_now().strftime("%Y%m%d")
    path = os.path.join("predictions", "%s.json" % day)

    if valid_pred(path):
        print("OK: predictions/%s.json あり・妥当（監視正常）" % day)
        return

    # 当日分が欠落/無効 → 当日に限り再生成を試行。
    # build_highlights は開催日==本日 かつ 未生成のときだけ predictions を書く（鉄則）。
    print("WARN: 当日predictions欠落/無効 → 当日中の再生成を試行: %s" % path)
    try:
        subprocess.run([sys.executable, BH, RACERS, MOTORS, HL, KIM, WX], check=False)
    except Exception as e:
        print("再生成の起動に失敗:", e)

    if valid_pred(path):
        print("RESCUED: predictions/%s.json を当日中に再生成（既存には触れていない）" % day)
        return

    # まだ揃わない＝当日出走表が未取得/開催日不一致など。埋め戻さず欠番として記録。
    print("GAP: 当日中に再生成できず。埋め戻しはせず欠番として記録する。")
    record_gap(day, "当日再生成不可（欠番記録・埋め戻し禁止）")


if __name__ == "__main__":
    main()
