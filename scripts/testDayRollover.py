#!/usr/bin/env python3
"""
日またぎ検証テスト（scrape_racers.py の target_dates / merge_with_existing）

検証観点:
  - 過去日破棄       : keep_dates(当日+翌日) より前の開催日は結果から消える
  - 当日切替         : 時刻が翌日へ進むと、旧「当日」が過去日となり破棄される
  - 翌日繰上げ       : 時刻が翌日へ進むと、旧「翌日」が新「当日」として保持される
  - 既存の当日データ保持: 新規取得が空でも、既存CSVの当日+翌日分は保持される
  - 新規優先(keep=last): 同一キーは新規取得側の値で上書きされる

実行: python scripts/testDayRollover.py
依存: pandas（本番と同じ merge_with_existing を直接呼ぶため）
ネットワーク不要・冪等。scrape_racers.target_date を固定日に差し替えて検証する。
"""

import os
import sys
import datetime
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import pandas as pd
import scrape_racers as sr


def set_today(d):
    """scrape_racers.target_date を固定日に差し替える。
    target_dates() / merge_with_existing() はいずれも target_date() を
    モジュール名で参照するため、この差し替えだけで基準日を制御できる。"""
    sr.target_date = lambda: d


def row(hd, jcd="01", rno="1R", waku="1", name="選手A"):
    """CSV_COLUMNS に沿った1行dictを作る（検証に無関係な列は空でよい）。"""
    r = {c: "" for c in sr.CSV_COLUMNS}
    r.update({"開催日": hd, "場コード": jcd, "レース": rno, "枠": waku, "氏名": name})
    return r


def hds(result):
    """結果DataFrameに含まれる開催日の集合を返す。"""
    return set(result["開催日"].astype(str).tolist()) if len(result) else set()


def name_of(result, hd, jcd, rno, waku):
    """指定キーの氏名を返す（無ければ None）。"""
    m = result[
        (result["開催日"].astype(str) == hd)
        & (result["場コード"].astype(str) == jcd)
        & (result["レース"].astype(str) == rno)
        & (result["枠"].astype(str) == waku)
    ]
    return m.iloc[0]["氏名"] if len(m) else None


def write_old_csv(path, rows):
    df = pd.DataFrame(rows, columns=sr.CSV_COLUMNS)
    df.to_csv(path, index=False, encoding="utf-8-sig")


PASS = 0
FAIL = 0


def check(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS:", label)
    else:
        FAIL += 1
        print("  FAIL:", label)


def main():
    D0 = datetime.date(2026, 7, 7)          # 当日
    Dm1 = D0 - datetime.timedelta(days=1)   # 前日（過去日になるべき）
    Dp1 = D0 + datetime.timedelta(days=1)   # 翌日
    Dp2 = D0 + datetime.timedelta(days=2)   # 翌々日
    f = lambda d: d.strftime("%Y%m%d")

    tmp = tempfile.mkdtemp(prefix="dayroll_")
    csv_path = os.path.join(tmp, "racers_today.csv")

    # ---- 前提: target_dates() の形 ----
    print("[0] target_dates() の基本形")
    set_today(D0)
    td = sr.target_dates()
    check(td == [D0, Dp1], "target_dates() == [当日, 翌日]")

    # ---- テストA: 過去日破棄 & 当日+翌日保持 ----
    print("[A] 過去日破棄 + 当日/翌日保持")
    set_today(D0)
    old_rows = [row(f(Dm1)), row(f(D0)), row(f(Dp1))]
    write_old_csv(csv_path, old_rows)
    # 新規は当日+翌日のみ取得（前日は取得しない）
    new_df = pd.DataFrame([row(f(D0)), row(f(Dp1))], columns=sr.CSV_COLUMNS)
    res = sr.merge_with_existing(new_df, csv_path)
    check(hds(res) == {f(D0), f(Dp1)}, "結果の開催日が {当日, 翌日} のみ（前日破棄）")
    check(f(Dm1) not in hds(res), "前日(過去日)が破棄されている")

    # ---- テストB: 新規優先(keep='last') ----
    print("[B] 同一キーは新規取得で上書き")
    set_today(D0)
    write_old_csv(csv_path, [row(f(D0), name="旧名")])
    new_df = pd.DataFrame([row(f(D0), name="新名")], columns=sr.CSV_COLUMNS)
    res = sr.merge_with_existing(new_df, csv_path)
    check(name_of(res, f(D0), "01", "1R", "1") == "新名", "当日の同一キーが新規値で上書き")

    # ---- テストC: 既存の当日データ保持（新規が空/欠け） ----
    print("[C] 新規取得が空でも既存の当日+翌日を保持")
    set_today(D0)
    write_old_csv(csv_path, [row(f(D0), name="既存当日"), row(f(Dp1), name="既存翌日")])
    empty_df = pd.DataFrame(columns=sr.CSV_COLUMNS)
    res = sr.merge_with_existing(empty_df, csv_path)
    check(hds(res) == {f(D0), f(Dp1)}, "新規空でも {当日, 翌日} が残る")
    check(name_of(res, f(D0), "01", "1R", "1") == "既存当日", "既存の当日データが保持される")

    # ---- テストD: 日またぎ（当日切替 + 翌日繰上げ） ----
    print("[D] 日またぎ: 当日がDpにロールオーバー")
    # 前回実行(当日=D0)で CSV に D0 と Dp1 が入っている状態を作る
    set_today(D0)
    write_old_csv(csv_path, [row(f(D0), name="旧当日"), row(f(Dp1), name="旧翌日")])
    # 時刻が翌日(Dp1)へ進む。0時台の初回巡回で新規取得はまだ空とする。
    set_today(Dp1)  # keep_dates は {Dp1, Dp2} になる
    empty_df = pd.DataFrame(columns=sr.CSV_COLUMNS)
    res = sr.merge_with_existing(empty_df, csv_path)
    check(f(D0) not in hds(res), "旧当日(D0)が過去日として破棄（当日切替）")
    check(f(Dp1) in hds(res), "旧翌日(Dp1)が新当日として保持（翌日繰上げ）")
    check(name_of(res, f(Dp1), "01", "1R", "1") == "旧翌日", "繰上がった当日データの中身が保持される")
    check(hds(res) == {f(Dp1)}, "結果はDp1のみ（Dp2は未取得なので不在で正しい）")

    print()
    print("結果: {} PASS / {} FAIL".format(PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
