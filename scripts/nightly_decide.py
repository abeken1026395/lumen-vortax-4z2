#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nightly_decide.py — 夜間パイプラインの自己判断（壁時計非依存＋現物比較）

racers_today.csv / highlights.json / results/ の現物から、この run で
(a) 当日モードで highlights.json を切り替えるか（DO_SWITCH）
(b) 翌日モード(HL_MODE=next)を回すか（HAS_NEXT）
を決める。GITHUB_ENV があれば書き出し、無ければ標準出力に表示（ローカル検証用）。

当日切替の安全判定（司令塔裁定）:
  基本 = ①②③ の AND
    ① csvDates に todayDate より後の日 D が存在
    ② その D に「6艇構成レースが1R以上ある場」が存在（規定12Rはpartial参考／短縮番組を弾かない）
    ③ D の前日(=todayDate)の結果が results/ に確定済み
  フォールバック：JST壁時計が D の0時を過ぎていれば ①② のみで切替可
    （切替遅延事故の防止。0時以降の先食いは物理的に不可能）

翌日追記(HAS_NEXT) = csvDates に todayDate より後の日が存在（=翌日モードのtargetが立つ）。
  ※翌日モード自体も内部で SKIP ガードを持つため、HAS_NEXT は「回す価値がある」の目安。

テスト用の環境変数上書き:
  NIGHTLY_HL / NIGHTLY_CSV / NIGHTLY_RESULTS_DIR / NIGHTLY_NOW(YYYYMMDD)
"""
import os
import io
import csv
import json
import datetime
from collections import defaultdict

JST = datetime.timezone(datetime.timedelta(hours=9))

HL = os.environ.get("NIGHTLY_HL", "docs/highlights/highlights.json")
CSV = os.environ.get("NIGHTLY_CSV", "docs/racers/racers_today.csv")
RESULTS_DIR = os.environ.get("NIGHTLY_RESULTS_DIR", "results")


def wall_ymd():
    n = os.environ.get("NIGHTLY_NOW")
    if n:
        return n.strip()
    return datetime.datetime.now(JST).strftime("%Y%m%d")


def today_date():
    try:
        with io.open(HL, encoding="utf-8") as f:
            return (json.load(f).get("開催日") or "").strip()
    except Exception:
        return ""


def csv_rows():
    try:
        with io.open(CSV, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def csv_dates(rows):
    return {(r.get("開催日") or "").strip() for r in rows if (r.get("開催日") or "").strip()}


def has_six_boat_venue(rows, date8):
    """date8 の場で6艇構成レースが1R以上ある場が存在するか（②の下限）。"""
    by = defaultdict(lambda: defaultdict(int))
    for r in rows:
        if (r.get("開催日") or "").strip() != date8:
            continue
        by[r.get("場コード")][r.get("レース")] += 1
    for _jcd, races in by.items():
        if any(cnt == 6 for cnt in races.values()):
            return True
    return False


def decide():
    today = today_date()
    rows = csv_rows()
    cds = csv_dates(rows)
    future = sorted(d for d in cds if (not today) or d > today)
    D = future[0] if future else None

    do_switch = 0
    cond2 = cond3 = past_mid = None
    if D:
        cond2 = has_six_boat_venue(rows, D)                              # ②
        cond3 = os.path.exists(os.path.join(RESULTS_DIR, today + ".json")) if today else False  # ③
        past_mid = wall_ymd() >= D                                       # フォールバック（Dの0時通過）
        if cond2 and (cond3 or past_mid):                               # ①(D存在)∧②∧(③∨フォールバック)
            do_switch = 1

    has_next = 1 if (today and any(d > today for d in cds)) or (not today and cds) else 0

    return {
        "today": today, "D": D, "csvDates": sorted(cds),
        "cond1_Dexists": bool(D), "cond2_sixboat": cond2, "cond3_prevResults": cond3,
        "fallback_pastMidnight": past_mid, "now": wall_ymd(),
        "DO_SWITCH": do_switch, "HAS_NEXT": has_next,
    }


def main():
    r = decide()
    ge = os.environ.get("GITHUB_ENV")
    if ge:
        with open(ge, "a") as e:
            e.write("DO_SWITCH={}\n".format(r["DO_SWITCH"]))
            e.write("HAS_NEXT={}\n".format(r["HAS_NEXT"]))
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
