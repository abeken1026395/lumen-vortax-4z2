#!/usr/bin/env python3
"""
Phase2（今節成績）パース検証テスト

⚠️ 位置づけ:
  この環境は boatrace.jp へ到達できないため live HTML を取得できない。
  本テストは phase2Spec.md に記載された「実データから読み取ったデータ構造」を
  忠実に再現したフィクスチャ HTML で parse_racelist / parse_shussetsu を通す。
  = 構造・複数走分離ロジックのリグレッション検証であり、
    本番反映前の live 1件確認（Code/ローカル環境で requests 取得）は別途必須。

検証観点:
  - 単走日: 'NR/進入/ST/着' に整形できる
  - 複数走日: 列方向グルーピング（仕様「4行1組」）で 2走を正しく分離
  - 未出走日: 空文字（漢数字着との混同なし）
  - STは先頭ドット表記のまま保持 / 着順は漢数字のまま保持
  - parse_racelist 経由で 1日目成績〜6日目成績 列が rec に入る
  - 防御性: 構造が想定外/空セルは空文字（例外で scrape を壊さない）

実行: python scripts/testPhase2.py
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from bs4 import BeautifulSoup
import scrape_racers as sr


PASS = 0
FAIL = 0


def check(cond, label, got=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  PASS:", label)
    else:
        FAIL += 1
        print("  FAIL:", label, "-> got:", repr(got))


def cell(text):
    """今節成績の1日セルを、トークンをスペース区切りで並べた <td> にする。
    仕様の列方向グルーピング（レースNo群→進入群→ST群→着順群）を再現。"""
    return "<td>{}</td>".format(text)


def build_racer_tr(shussetsu_cells):
    """1選手行 <tr> を組み立てる。td並びは td構成コメントに準拠:
    [枠, 写真, info, F/L/ST, 全国, 当地, モーター, ボート, 今節day1..day6]"""
    tds = [
        "<td>1</td>",                                   # 0 枠
        "<td><img></td>",                               # 1 写真
        # 2 info: toban/級別/氏名(リンク)/支部/出身/年齢
        '<td>4212 / A1 <a href="/owpc/pc/data/racersearch/profile?toban=4212">岩田 凌</a> '
        '愛知/愛知 30歳/52.0kg F0</td>',
        "<td>F0 L0 0.15</td>",                          # 3 F/L/平均ST
        "<td>6.50 45.00 65.00</td>",                    # 4 全国
        "<td>5.00 30.00 50.00</td>",                    # 5 当地
        "<td>34 40.00 55.00</td>",                      # 6 モーター
        "<td>56 35.00 48.00</td>",                      # 7 ボート
    ]
    for c in shussetsu_cells:
        tds.append(cell(c))
    return "<table><tr>{}</tr></table>".format("".join(tds))


def main():
    # ---- 1) parse_shussetsu_cell 単体 ----
    print("[1] _parse_shussetsu_cell 単体")
    C = sr._parse_shussetsu_cell

    def td(t):
        return BeautifulSoup("<td>{}</td>".format(t), "html.parser").td

    # 単走
    check(C(td("8 2 .16 一")) == "8R/2/.16/一", "単走 8R/2コース/.16/一着", C(td("8 2 .16 一")))
    # 複数走（列方向: レースNo群 2,12 → 進入群 6,3 → ST群 .15,.08 → 着群 六,三）
    got = C(td("2 12 6 3 .15 .08 六 三"))
    check(got == "2R/6/.15/六 12R/3/.08/三", "2走を列方向グルーピングで分離", got)
    # R付きレースNo
    check(C(td("2R 6 .15 六")) == "2R/6/.15/六", "R付きレースNo", C(td("2R 6 .15 六")))
    # 未出走（空）
    check(C(td("")) == "", "空セル → 空", C(td("")))
    # 着順なし（数字だけ）→ 空（防御）
    check(C(td("3 5")) == "", "着順なしは空", C(td("3 5")))
    # ST本数不一致 → 空（防御）
    check(C(td("2 6 .15 六 三")) == "", "ST本数不一致は空", C(td("2 6 .15 六 三")))
    # STは先頭ドット保持
    check(".15" in C(td("2 6 .15 六")), "STは先頭ドット表記のまま", C(td("2 6 .15 六")))

    # ---- 2) parse_shussetsu（6日ぶんの位置取り） ----
    print("[2] parse_shussetsu（info_idx+6 以降の6日）")
    # info_idx=2 相当の td 列を直接作る
    html = build_racer_tr(["2 12 6 3 .15 .08 六 三", "8 2 .16 一", "", "", "", ""])
    tr = BeautifulSoup(html, "html.parser").find("tr")
    tds = tr.find_all("td")
    days = sr.parse_shussetsu(tds, 2)
    check(days[0] == "2R/6/.15/六 12R/3/.08/三", "初日=2走", days[0])
    check(days[1] == "8R/2/.16/一", "2日目=単走", days[1])
    check(days[2:] == ["", "", "", ""], "3〜6日目=空", days[2:])

    # ---- 3) parse_racelist 経由（実運用パス・岩田凌ケース） ----
    print("[3] parse_racelist 経由で rec に成績列が入る")
    recs = sr.parse_racelist(html, "07", "蒲郡", "20260707", 3)
    check(len(recs) == 1, "1選手行を抽出", len(recs))
    if recs:
        r = recs[0]
        check(r["氏名"] == "岩田 凌", "氏名", r["氏名"])
        check(r["登録番号"] == "4212", "登録番号", r["登録番号"])
        check(r["モーター2連率"] == "40.00", "モーター2連率（既存パス不変）", r["モーター2連率"])
        check(r["1日目成績"] == "2R/6/.15/六 12R/3/.08/三", "1日目成績", r["1日目成績"])
        check(r["2日目成績"] == "8R/2/.16/一", "2日目成績", r["2日目成績"])
        check(r["6日目成績"] == "", "6日目成績=空", r["6日目成績"])
        # CSV_COLUMNS に成績6列が含まれる
        need = ["1日目成績", "2日目成績", "3日目成績", "4日目成績", "5日目成績", "6日目成績"]
        check(all(c in sr.CSV_COLUMNS for c in need), "CSV_COLUMNSに成績6列")
        check(all(c in r for c in need), "recに成績6列")

    # ---- 4) 今節成績が全く無い行でも壊れない ----
    print("[4] 今節成績なし行の防御")
    html2 = build_racer_tr([])  # 成績セルを付けない
    recs2 = sr.parse_racelist(html2, "07", "蒲郡", "20260707", 3)
    check(len(recs2) == 1 and recs2[0]["1日目成績"] == "", "成績列なし→空・例外なし",
          recs2[0]["1日目成績"] if recs2 else None)

    print()
    print("結果: {} PASS / {} FAIL".format(PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
