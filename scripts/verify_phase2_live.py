#!/usr/bin/env python3
"""
Phase2 live 検証（GitHub Actions 上で実行する一時スクリプト）

この対話環境は boatrace.jp へ到達できないため、到達可能な Actions ランナーで
racelist を直接叩き、parse_racelist / parse_shussetsu の実データ挙動を確認する。
get_open_venues には依存せず、到達性を status/len/例外で明示し、開催中の場を
総当りで探して生td構造とパース結果を scripts/_phase2_live_report.md に書き出す。
検証確定後はこのスクリプトごと削除する。
"""

import os
import sys
import datetime
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import requests
from bs4 import BeautifulSoup
import scrape_racers as sr

OUT = os.path.join(SCRIPT_DIR, "_phase2_live_report.md")


def fetch(url):
    """(status, text, err) を返す。到達性の切り分け用に例外文字列も持つ。"""
    try:
        r = requests.get(url, headers=sr.HEADERS, timeout=15)
        return r.status_code, r.text, ""
    except Exception as e:
        return None, "", "{}: {}".format(type(e).__name__, e)


def racer_trs(soup):
    """選手行 <tr> と info_idx を列挙。"""
    out = []
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
        if info_idx is not None:
            out.append((tds, info_idx))
    return out


def main():
    L = []
    w = L.append
    w("# Phase2 live 検証レポート")
    w("")
    w("実行時刻(UTC): {}".format(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
    w("")

    dates = [d.strftime("%Y%m%d") for d in sr.target_dates()]
    w("対象日: {}".format(dates))
    w("")

    # --- 到達性チェック（index 1本） ---
    idx_url = "https://www.boatrace.jp/owpc/pc/race/index?hd={}".format(dates[0])
    st, txt, err = fetch(idx_url)
    w("## 到達性チェック")
    w("- index({}): status={} len={} err={}".format(dates[0], st, len(txt), err or "-"))
    if st is None:
        w("")
        w("**boatrace.jp へ到達不可（例外）。Actions からもブロックされています。**")
        open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
        print("unreachable")
        return 0

    # --- 開催場を総当りで探索（get_open_venues に依存しない） ---
    target = None  # (hd, jcd, venue, tds, info_idx, text)
    tried = []
    for hd in dates:
        for jcd in sr.VENUES:
            url = "https://www.boatrace.jp/owpc/pc/race/racelist?rno=1&jcd={}&hd={}".format(jcd, hd)
            st, txt, err = fetch(url)
            trs = racer_trs(BeautifulSoup(txt, "html.parser")) if st == 200 else []
            tried.append("{}/{}:st={},racers={}".format(hd, jcd, st, len(trs)))
            if trs:
                target = (hd, jcd, sr.VENUES[jcd], txt)
                break
        if target:
            break

    w("")
    w("## 探索ログ（開催場ヒットまで）")
    w("```")
    w(" ".join(tried))
    w("```")

    if not target:
        w("")
        w("**200 は返るが選手行を検出できる開催が見つかりませんでした（当日開催なし or 構造変化）。**")
        open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
        print("no racing found")
        return 0

    hd, jcd, venue, _ = target
    w("")
    w("## 対象: jcd={} {} / hd={}".format(jcd, venue, hd))

    # --- 修正後 parse_racelist の成績テーブルを全6艇×3レースで確認 ---
    for rno in range(1, 4):
        url = "https://www.boatrace.jp/owpc/pc/race/racelist?rno={}&jcd={}&hd={}".format(rno, jcd, hd)
        st, txt, err = fetch(url)
        w("")
        w("### {}R (status={})".format(rno, st))
        if st != 200:
            continue
        recs = sr.parse_racelist(txt, jcd, venue, hd, rno)
        w("| 枠 | 氏名 | 1日目 | 2日目 | 3日目 | 4日目 | 5日目 | 6日目 |")
        w("|---|---|---|---|---|---|---|---|")
        for r in recs:
            w("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
                r.get("枠", ""), r.get("氏名", ""),
                r.get("1日目成績", "") or "·", r.get("2日目成績", "") or "·",
                r.get("3日目成績", "") or "·", r.get("4日目成績", "") or "·",
                r.get("5日目成績", "") or "·", r.get("6日目成績", "") or "·"))

    open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
