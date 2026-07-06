#!/usr/bin/env python3
"""
Phase2（今節成績）パース検証テスト — 実データ構造ベース

フィクスチャは Actions 経由で取得した実HTML（桐生 2026-07-07 1R・1号艇 中野和裕の
tbody）をそのまま埋め込んでいる。公式racelistの今節成績は tbody 内 4行グリッド:
  tr0 非rowspanセル=レースNo / tr1=進入コース / tr2=ST / tr3=着(全角数字＋raceresult
  リンク hd=YYYYMMDD)。列は「日」ではなく「実施レース」単位、日付はリンク hd から取る。

中野は 7/5 に 2走(R1,R7)あり → 複数走日の集約もこの実データで検証できる。

検証観点:
  - parse_shussetsu_grid: 4行グリッドから実施レース(hd/rno/course/st/chaku)を抽出
  - 全角数字の着順を半角化 / 未実施(空)列をスキップ
  - shussetsu_days: 節初日起点の day_index で日別集約、複数走は併記
  - parse_racelist: 既存の基本項目(氏名/登番/モーター/ボート)が不変
  - 防御: 4行未満/空グリッドで空、例外で落ちない

実行: python scripts/testPhase2.py
"""

import os
import sys
import datetime

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


# 実HTML（Actions取得・桐生 20260707 1R 1号艇 中野和裕の tbody をそのまま）
REAL_TBODY = """
<tbody class="is-fs12">
<tr>
<td class="is-boatColor1 is-fs14" rowspan="4">１</td>
<td rowspan="4"><a href="/owpc/pc/data/racersearch/profile?toban=3459"><img alt="" height="95" src="/racerphoto/3459.jpg" width="67"/></a></td>
<td rowspan="4"><div class="is-fs11">3459 / <span class="">B1</span></div>
<div class="is-fs18 is-fBold"><a href="/owpc/pc/data/racersearch/profile?toban=3459">中野　　和裕</a></div>
<div class="is-fs11">佐賀/佐賀<br/>59歳/53.0kg</div></td>
<td class="is-lineH2" rowspan="4">F0<br/>L0<br/>0.17</td>
<td class="is-lineH2" rowspan="4">3.44<br/>12.50<br/>23.75</td>
<td class="is-lineH2" rowspan="4">0.00<br/>0.00<br/>0.00</td>
<td class="is-lineH2" rowspan="4">58<br/>22.92<br/>36.46</td>
<td class="is-lineH2" rowspan="4">70<br/>30.50<br/>47.52</td>
<td rowspan="4"> </td>
<td class="is-boatColor5">6</td>
<td class=""> </td>
<td class="is-boatColor2">1</td>
<td class="is-boatColor6">7</td>
<td class="is-boatColor4">6</td>
<td class=""> </td>
<td class=""> </td>
<td class=""> </td>
<td class=""> </td>
<td class=""> </td>
<td class=""> </td>
<td class=""> </td>
<td class="is-outColor"> </td>
<td class="is-outColor"> </td>
<td rowspan="4"><a class="number2__add2020 is-type3" href="/owpc/pc/race/racelist?rno=5&amp;jcd=01&amp;hd=20260707">5R</a></td>
</tr>
<tr>
<td class="">5</td><td class=""> </td><td class="">2</td><td class="">6</td><td class="">4</td>
<td class=""> </td><td class=""> </td><td class=""> </td><td class=""> </td><td class=""> </td>
<td class=""> </td><td class=""> </td><td class="is-outColor"> </td><td class="is-outColor"> </td>
</tr>
<tr>
<td class="">.18</td><td class=""> </td><td class="">.24</td><td class="">.17</td><td class="">.12</td>
<td class=""> </td><td class=""> </td><td class=""> </td><td class=""> </td><td class=""> </td>
<td class=""> </td><td class=""> </td><td class="is-outColor"> </td><td class="is-outColor"> </td>
</tr>
<tr class="is-fBold">
<td class=""><a href="/owpc/pc/race/raceresult?rno=6&amp;jcd=01&amp;hd=20260704">６</a></td>
<td class=""><a href="/owpc/pc/race/raceresult"></a></td>
<td class=""><a href="/owpc/pc/race/raceresult?rno=1&amp;jcd=01&amp;hd=20260705">５</a></td>
<td class=""><a href="/owpc/pc/race/raceresult?rno=7&amp;jcd=01&amp;hd=20260705">６</a></td>
<td class=""><a href="/owpc/pc/race/raceresult?rno=6&amp;jcd=01&amp;hd=20260706">６</a></td>
<td class=""><a href="/owpc/pc/race/raceresult"></a></td>
<td class=""><a href="/owpc/pc/race/raceresult"></a></td>
<td class=""><a href="/owpc/pc/race/raceresult"></a></td>
<td class=""><a href="/owpc/pc/race/raceresult"></a></td>
<td class=""><a href="/owpc/pc/race/raceresult"></a></td>
<td class=""><a href="/owpc/pc/race/raceresult"></a></td>
<td class=""><a href="/owpc/pc/race/raceresult"></a></td>
<td class="is-outColor"><a href="/owpc/pc/race/raceresult"></a></td>
<td class="is-outColor"><a href="/owpc/pc/race/raceresult"></a></td>
</tr>
</tbody>
"""


def main():
    tbody = BeautifulSoup(REAL_TBODY, "html.parser").find("tbody")
    trs = tbody.find_all("tr", recursive=False)

    # ---- 1) grid 抽出 ----
    print("[1] parse_shussetsu_grid（実データ）")
    res = sr.parse_shussetsu_grid(trs)
    check(len(res) == 4, "実施4レースを抽出", len(res))
    if len(res) == 4:
        check(res[0] == {"hd": "20260704", "rno": "6", "course": "5", "st": ".18", "chaku": "6"},
              "初日 7/4 R6 進入5 ST.18 着6", res[0])
        check(res[1]["hd"] == "20260705" and res[1]["rno"] == "1" and res[1]["chaku"] == "5",
              "7/5 R1 着5", res[1])
        check(res[2]["hd"] == "20260705" and res[2]["rno"] == "7", "7/5 R7（同日2走目）", res[2])
        check(res[3] == {"hd": "20260706", "rno": "6", "course": "4", "st": ".12", "chaku": "6"},
              "7/6 R6 進入4 ST.12 着6", res[3])
    check(all(r["chaku"].isascii() for r in res), "着順は半角化されている")

    # ---- 2) 日別集約 ----
    print("[2] shussetsu_days（節初日=7/4起点で日別集約）")
    start = datetime.date(2026, 7, 4)
    days = sr.shussetsu_days(res, start)
    check(days[0] == "6R/5/.18/6", "1日目(7/4)", days[0])
    check(days[1] == "1R/2/.24/5 7R/6/.17/6", "2日目(7/5)=2走を併記", days[1])
    check(days[2] == "6R/4/.12/6", "3日目(7/6)", days[2])
    check(days[3:] == ["", "", ""], "4〜6日目=空", days[3:])

    # ---- 3) parse_racelist 経由（基本項目の不変＋成績列） ----
    print("[3] parse_racelist（基本項目不変＋成績列）")
    html = "<table>" + REAL_TBODY + "</table>"
    recs = sr.parse_racelist(html, "01", "桐生", "20260707", 1)
    check(len(recs) == 1, "1選手を抽出", len(recs))
    if recs:
        r = recs[0]
        check(r["氏名"] == "中野　　和裕", "氏名", r["氏名"])
        check(r["登録番号"] == "3459", "登録番号", r["登録番号"])
        check(r["級別"] == "B1", "級別", r["級別"])
        check(r["モーターNo"] == "58" and r["モーター2連率"] == "22.92", "モーター（既存不変）",
              (r["モーターNo"], r["モーター2連率"]))
        check(r["ボートNo"] == "70" and r["ボート2連率"] == "30.50", "ボート（既存不変）",
              (r["ボートNo"], r["ボート2連率"]))
        check(r["枠"] == "1", "枠", r["枠"])
        # 単一選手なので節初日=7/4
        check(r["1日目成績"] == "6R/5/.18/6", "1日目成績", r["1日目成績"])
        check(r["2日目成績"] == "1R/2/.24/5 7R/6/.17/6", "2日目成績（2走併記）", r["2日目成績"])
        check(r["3日目成績"] == "6R/4/.12/6", "3日目成績", r["3日目成績"])
        check(r["4日目成績"] == "" and r["6日目成績"] == "", "4/6日目=空")

    # ---- 4) 防御 ----
    print("[4] 防御（4行未満/空）")
    check(sr.parse_shussetsu_grid(trs[:2]) == [], "4行未満は空リスト", None)
    empty_html = ("<table><tbody><tr><td>1</td><td><img></td>"
                  "<td>0000 / B1 <a href='profile?toban=0000'>試験 太郎</a> 東京/東京 30歳/50.0kg F0</td>"
                  "<td>F0 L0 0.15</td><td>5.0 30 50</td><td>4.0 20 40</td>"
                  "<td>10 30 45</td><td>20 25 40</td></tr></tbody></table>")
    recs2 = sr.parse_racelist(empty_html, "01", "桐生", "20260707", 1)
    check(len(recs2) == 1 and recs2[0]["1日目成績"] == "", "今節グリッド無し→空・例外なし",
          recs2[0]["1日目成績"] if recs2 else None)

    print()
    print("結果: {} PASS / {} FAIL".format(PASS, FAIL))
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
