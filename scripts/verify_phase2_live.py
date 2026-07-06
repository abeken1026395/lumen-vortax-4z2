#!/usr/bin/env python3
"""
Phase2 live 検証（GitHub Actions 上で実行する一時スクリプト）

この対話環境は boatrace.jp へ到達できないため、到達可能な Actions ランナーで
racelist を数レース取得し、parse_racelist / parse_shussetsu の実データ挙動を
確認する。生td構造とパース結果を scripts/_phase2_live_report.md に書き出し、
ワークフロー側でコミットする。検証完了後はこのスクリプトごと削除する。
"""

import os
import sys
import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import requests
from bs4 import BeautifulSoup
import re
import scrape_racers as sr

OUT = os.path.join(SCRIPT_DIR, "_phase2_live_report.md")


def pick_target():
    """当日+翌日で開催中の場を1つ選ぶ。jcd=07(蒲郡)を優先、無ければ最初の開催場。"""
    for d in sr.target_dates():
        hd = d.strftime("%Y%m%d")
        ov = sr.get_open_venues(hd)
        if ov:
            jcd = "07" if "07" in ov else sorted(ov)[0]
            return jcd, sr.VENUES.get(jcd, jcd), hd
    return None, None, None


def dump_raw_row(tds, info_idx):
    """info_idx+4 以降（モーター/ボート/今節成績）の生td textをindex付きで返す。"""
    lines = []
    for i in range(info_idx + 4, len(tds)):
        txt = tds[i].get_text(" ", strip=True)
        lines.append("    td[info+{}] (abs {}): {!r}".format(i - info_idx, i, txt))
    return lines


def main():
    lines = []
    w = lines.append
    w("# Phase2 live 検証レポート")
    w("")
    w("実行時刻(UTC): {}".format(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))

    jcd, venue, hd = pick_target()
    if not jcd:
        w("")
        w("**開催場が取得できませんでした（get_open_venues が空）。**")
        w("Actions からも boatrace.jp に到達できない可能性があります。")
        open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print("no open venue")
        return 0

    w("対象: jcd={} {} / hd={}".format(jcd, venue, hd))
    w("")

    # 最大3レース確認（1号艇=info構造の把握＋複数走ケースの発見を狙う）
    for rno in range(1, 4):
        url = "https://www.boatrace.jp/owpc/pc/race/racelist?rno={}&jcd={}&hd={}".format(rno, jcd, hd)
        try:
            resp = requests.get(url, headers=sr.HEADERS, timeout=15)
        except Exception as e:
            w("## {}R: 取得失敗 {}".format(rno, e))
            continue
        w("## {}R (status {})".format(rno, resp.status_code))
        if resp.status_code != 200:
            continue

        soup = BeautifulSoup(resp.text, "html.parser")
        # 1号艇（最初の該当tr）の生td構造をダンプ
        dumped = False
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 8:
                continue
            if not re.search(r"\d{4}\s*/\s*(A1|A2|B1|B2)", tr.get_text(" ", strip=True)):
                continue
            info_idx = None
            for i, td in enumerate(tds):
                if re.search(r"\d{4}\s*/\s*(A1|A2|B1|B2)", td.get_text(" ", strip=True)):
                    info_idx = i
                    break
            if info_idx is None:
                continue
            w("- td総数={} / info_idx={}".format(len(tds), info_idx))
            w("- 生td（info+4以降＝モーター/ボート/今節成績）:")
            w("```")
            for ln in dump_raw_row(tds, info_idx):
                w(ln)
            w("```")
            dumped = True
            break
        if not dumped:
            w("(選手行を検出できず)")

        # パース結果（parse_racelist 経由）
        recs = sr.parse_racelist(resp.text, jcd, venue, hd, rno)
        w("- parse結果 {} 名:".format(len(recs)))
        w("")
        w("| 枠 | 氏名 | 1日目 | 2日目 | 3日目 | 4日目 | 5日目 | 6日目 |")
        w("|---|---|---|---|---|---|---|---|")
        for r in recs:
            w("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
                r.get("枠", ""), r.get("氏名", ""),
                r.get("1日目成績", "") or "·", r.get("2日目成績", "") or "·",
                r.get("3日目成績", "") or "·", r.get("4日目成績", "") or "·",
                r.get("5日目成績", "") or "·", r.get("6日目成績", "") or "·"))
        w("")

    open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
