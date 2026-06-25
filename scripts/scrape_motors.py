#!/usr/bin/env python3
"""
競艇モーター成績スクレイパー (GitHub Actions自動実行版)
毎日boatrace.jp公式から全24場のモーターデータを取得し、
docs/ フォルダに index.html (ビューワー) と motors_all.csv を出力する。
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
import time
import re
import datetime
import os

VENUES = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

OUTPUT_DIR = os.path.join("docs", "motor")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "template.html")

JST = datetime.timezone(datetime.timedelta(hours=9))


def target_date():
    """対象開催日。GitHub ActionsはUTCなのでJSTに直して判定。
    出走表と揃える：JST18時以降の夜実行は翌日分、日中は当日分。"""
    now = datetime.datetime.now(JST)
    if now.hour >= 18:
        return now.date() + datetime.timedelta(days=1)
    return now.date()


def get_open_venues(hd):
    """本日（対象日）開催している場コードの集合。非開催場の前節データ混入を防ぐ。
    取得できなければ None（呼び出し側は全場試行にフォールバック）。"""
    url = "https://www.boatrace.jp/owpc/pc/race/index?hd={}".format(hd)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        # 生HTMLでは & が &amp; になるため両対応
        found = set(re.findall(r"jcd=(\d{2})&(?:amp;)?hd=" + re.escape(hd), resp.text))
        return found if found else None
    except Exception:
        return None


def parse_motor_table(soup):
    records = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 5:
                continue
            texts = [c.get_text(strip=True) for c in cells]
            if not texts or not texts[0].isdigit():
                continue
            toban = name = rank = motor_no = motor_rate = ""
            for i, t in enumerate(texts):
                if re.match(r"^\d{4}$", t) and not toban:
                    toban = t
                    if i + 1 < len(texts):
                        name = texts[i + 1]
            for t in texts:
                if t in ("A1", "A2", "B1", "B2"):
                    rank = t
                    break
            for i, t in enumerate(texts):
                if re.match(r"^\d+\.\d+%$", t) and i > 0:
                    prev = texts[i - 1]
                    if re.match(r"^\d{1,3}$", prev):
                        motor_no = prev
                        motor_rate = t
                        break
            if toban and motor_no:
                records.append({
                    "順位": texts[0], "登録番号": toban, "選手名": name,
                    "級別": rank, "モーター番号": motor_no,
                    "モーター2連対率": motor_rate.replace("%", ""),
                })
    return records


def find_open_date(jcd):
    # 対象日のみ。前後日(-9〜9)を探すと非開催場が前節データを拾うため[0]に限定。
    today = target_date()
    candidates = [0]
    for sign in candidates:
        d = today + datetime.timedelta(days=sign)
        hd = d.strftime("%Y%m%d")
        url = "https://www.boatrace.jp/owpc/pc/race/rankingmotor?jcd={}&hd={}".format(jcd, hd)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            records = parse_motor_table(soup)
            if records:
                return hd, records
        except Exception:
            continue
        time.sleep(0.3)
    return None, []


def main():
    print("競艇モーター成績スクレイパー (自動実行)")
    print("実行日時:", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print()

    today_hd = target_date().strftime("%Y%m%d")
    open_venues = get_open_venues(today_hd)
    if open_venues:
        print("対象日 {} の開催場: {} 場 ({})".format(today_hd, len(open_venues), " ".join(sorted(open_venues))))
    else:
        print("対象日 {} 開催場リスト取得失敗 → 全場を試行".format(today_hd))
    print()

    all_records = []
    for jcd, name in VENUES.items():
        if open_venues is not None and jcd not in open_venues:
            print("[{}] {} ... 非開催（スキップ）".format(jcd, name))
            continue
        print("[{}] {} ...".format(jcd, name), end=" ", flush=True)
        hd, records = find_open_date(jcd)
        if not records:
            print("開催情報なし")
            continue
        for r in records:
            r["場コード"] = jcd
            r["場名"] = name
            r["開催日"] = hd
        all_records.extend(records)
        print("OK ({} 件 / {})".format(len(records), hd))
        time.sleep(0.8)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if not all_records:
        print("\nデータを取得できませんでした。")
        if os.path.exists(os.path.join(OUTPUT_DIR, "index.html")):
            return

    df = pd.DataFrame(all_records)
    df.to_csv(os.path.join(OUTPUT_DIR, "motors_all.csv"), index=False, encoding="utf-8-sig")
    print("\nCSV保存: {}/motors_all.csv ({}件)".format(OUTPUT_DIR, len(df)))

    cols = [str(c) for c in df.columns.tolist()]
    data = df.fillna("").values.tolist()
    updated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    data_json = json.dumps(
        {"columns": cols, "data": data, "venues": dict(VENUES), "updated": updated},
        ensure_ascii=False, default=str,
    )

    # テンプレートを読み込んでデータを埋め込む
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()
    html = template.replace("__DATA_PLACEHOLDER__", data_json)

    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("ビューワー保存: {}/index.html".format(OUTPUT_DIR))
    print("完了!")


if __name__ == "__main__":
    main()
