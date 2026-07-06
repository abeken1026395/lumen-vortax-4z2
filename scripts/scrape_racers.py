#!/usr/bin/env python3
"""
出走表スクレイパー (GitHub Actions自動実行版) v3
各選手は1つの<tr>に横並び。tdの位置で項目を特定する。
td構成: [枠, 写真, 登録番号/級別/氏名/支部/年齢体重, F/L/平均ST,
         全国(勝率/2連/3連), 当地(勝率/2連/3連), モーター, ボート, ...]
docs/racers/ に index.html と racers_today.csv を出力。
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

JST = datetime.timezone(datetime.timedelta(hours=9))


def target_date():
    """基準日=当日(JST)を返す。日付が変わるまで当日扱い（ミッドナイト場考慮）。"""
    return datetime.datetime.now(JST).date()

def target_dates():
    """取得候補日リスト。当日と翌日の2日を対象にする（ナイター/デイ混在対策）。"""
    today = target_date()
    return [today, today + datetime.timedelta(days=1)]

OUTPUT_DIR = os.path.join("docs", "racers")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "template_racers.html")


def cell_decimals(td):
    """td内の小数(X.XX)を出現順に返す"""
    return re.findall(r"\d+\.\d+", td.get_text(" ", strip=True))


# 今節成績（Phase2）
SHUSSETSU_MAX_DAYS = 6
_FW2HW = str.maketrans("０１２３４５６７８９", "0123456789")


def _hw(s):
    """全角数字→半角。前後空白除去。"""
    return (s or "").translate(_FW2HW).strip()


def parse_shussetsu_grid(trs):
    """選手tbody（4つの<tr>）から今節成績を「実施レース」の並びで返す。
    公式racelistの今節成績は 14列×4行のグリッドで、
      tr0 の非rowspanセル = レースNo, tr1 = 進入コース, tr2 = ST,
      tr3 = 着順（全角数字＋raceresultリンク hd=YYYYMMDD）。
    列は「日」ではなく「実施レース」単位。日付は着セルのリンク hd から取る。
    戻り値: [{'hd': 'YYYYMMDD', 'rno': '6', 'course': '5', 'st': '.18', 'chaku': '6'}, ...]
    構造不一致（4行未満等）は空リスト（防御）。"""
    if len(trs) < 4:
        return []
    rowA = [td.get_text(" ", strip=True)
            for td in trs[0].find_all("td", recursive=False) if not td.has_attr("rowspan")]
    rowB = [td.get_text(" ", strip=True) for td in trs[1].find_all("td", recursive=False)]
    rowC = [td.get_text(" ", strip=True) for td in trs[2].find_all("td", recursive=False)]
    tds3 = trs[3].find_all("td", recursive=False)
    rowD = [td.get_text(" ", strip=True) for td in tds3]
    rowHd = []
    for td in tds3:
        a = td.find("a", href=True)
        dm = re.search(r"hd=(\d{8})", a["href"]) if a else None
        rowHd.append(dm.group(1) if dm else "")

    n = min(len(rowA), len(rowB), len(rowC), len(rowD))
    out = []
    for i in range(n):
        rno = _hw(rowA[i])
        chaku = _hw(rowD[i])
        hd = rowHd[i]
        # レースNo・着順・日付が揃った列だけが実施レース。未実施/空列はスキップ。
        if not re.match(r"^\d{1,2}$", rno) or not re.match(r"^\d{1,2}$", chaku) or not hd:
            continue
        out.append({"hd": hd, "rno": rno, "course": _hw(rowB[i]),
                    "st": rowC[i].strip(), "chaku": chaku})
    return out


def shussetsu_days(results, meeting_start, max_days=SHUSSETSU_MAX_DAYS):
    """実施レースのリストを日別セル文字列（最大6日）に集約する。
    day_index = (開催日 - 節初日).days（連続開催前提）。
    セル例: '6R/5/.18/6'（複数走は半角スペース区切りで併記）。範囲外/空は ''。"""
    days = [""] * max_days
    if not meeting_start:
        return days
    byday = {}
    for r in results:
        try:
            d = datetime.datetime.strptime(r["hd"], "%Y%m%d").date()
        except Exception:
            continue
        di = (d - meeting_start).days
        if 0 <= di < max_days:
            byday.setdefault(di, []).append(r)
    for di, lst in byday.items():
        days[di] = " ".join(
            "{}R/{}/{}/{}".format(x["rno"], x["course"], x["st"], x["chaku"]) for x in lst)
    return days


def parse_deadlines(soup):
    """ページ上部の「締切予定時刻」行から12レース分のHH:MMを返す"""
    for tr in soup.find_all("tr"):
        txt = tr.get_text(" ", strip=True)
        if "締切予定時刻" in txt:
            return re.findall(r"\d{1,2}:\d{2}", txt)[:12]
    return []


def parse_nichime(soup, hd):
    """開催日タブから当日の日数（初日/２日目/最終日 等）を返す。取れなければ空。
    当日はリンクが無いテキストで並ぶ。日付テキストから日目表記だけ抜く。"""
    y, m, d = hd[:4], str(int(hd[4:6])), str(int(hd[6:8]))
    label = f"{m}月{d}日"
    for el in soup.find_all(["li", "span", "a"]):
        t = el.get_text(" ", strip=True)
        if label in t:
            mm = re.search(r"(初日|最終日|\d+日目|[０-９]+日目)", t)
            if mm:
                return mm.group(1)
    # フォールバック：ページ内の当日ラベル近傍を全文から探す
    txt = soup.get_text(" ", strip=True)
    mm = re.search(re.escape(label) + r"\s*(初日|最終日|\d+日目|[０-９]+日目)", txt)
    return mm.group(1) if mm else ""


def parse_title(soup):
    """節タイトル（例：一般戦、G1〇〇記念）と企画名（例：予選、進入固定）を返す。
    取れなければ空文字。h2=節、h3=各レースの企画名。"""
    setsu = ""; kikaku = ""
    h2 = soup.find("h2")
    if h2:
        setsu = re.sub(r"\s+", " ", h2.get_text(" ", strip=True)).strip()
    h3 = soup.find("h3")
    if h3:
        t = re.sub(r"\s+", " ", h3.get_text(" ", strip=True)).strip()
        # 距離(1800m等)やレース番号を落として企画名だけ残す
        t = re.sub(r"\d+\s*[mMｍ]", "", t)
        t = re.sub(r"^\d+\s*R", "", t)
        kikaku = t.strip()
    return setsu, kikaku


def parse_racelist(html, jcd, venue, hd, rno):
    soup = BeautifulSoup(html, "html.parser")
    records = []

    # このレースの締切予定時刻（締切行の rno 番目）
    deadlines = parse_deadlines(soup)
    deadline = deadlines[rno - 1] if len(deadlines) >= rno else ""

    # 節タイトル・企画名・開催日数（表示用）
    setsu, kikaku = parse_title(soup)
    nichime = parse_nichime(soup, hd)

    # 各選手は1つの<tbody>（4つの<tr>: レースNo/進入/ST/着）で構成される。
    # tr0 に枠/写真/情報/成績/モーター/ボートが rowspan で入る。
    pending = []  # (rec, results) を集めて後段で日別集約
    for tbody in soup.find_all("tbody"):
        trs = tbody.find_all("tr", recursive=False)
        if not trs:
            continue
        tr = trs[0]
        tds = tr.find_all("td")
        if len(tds) < 8:
            continue
        tr_text = tr.get_text(" ", strip=True)
        m = re.search(r"(\d{4})\s*/\s*(A1|A2|B1|B2)", tr_text)
        if not m:
            continue

        toban = m.group(1)
        rank = m.group(2)

        # 氏名: profileリンクのうち、テキストが数字でない(=写真リンクでない)もの
        name = ""
        for a in tr.find_all("a", href=re.compile(r"toban=\d+")):
            txt = a.get_text(strip=True)
            if txt and not txt.isdigit():
                name = txt
                break

        # 枠番は後で出現順に振るため、ここでは仮置き
        waku = ""

        # F数/L数/平均ST
        f_match = re.search(r"F\s*(\d+)", tr_text)
        l_match = re.search(r"L\s*(\d+)", tr_text)
        f_num = f_match.group(1) if f_match else ""
        l_num = l_match.group(1) if l_match else ""

        # 「登録番号/級別/氏名」のtdを探す → その次から F/L, 全国, 当地 と並ぶ
        # tobanを含むtdのindexを特定
        info_idx = None
        for i, td in enumerate(tds):
            if re.search(r"\d{4}\s*/\s*(A1|A2|B1|B2)", td.get_text(" ", strip=True)):
                info_idx = i
                break

        zen = ["", "", ""]   # 全国 勝率/2連/3連
        toti = ["", "", ""]  # 当地 勝率/2連/3連
        avg_st = ""
        shibu = home = age = ""  # 支部/出身地/年齢
        if info_idx is not None:
            # 支部/出身/年齢: セル例「3388 / A1 今垣 光太郎 福井/石川 56歳/52.0kg」
            # 空白は消さず、漢字ランの区切りとして使う（名前と支部が混ざるのを防ぐ）
            info_text = tds[info_idx].get_text(" ", strip=True)
            mm = re.search(r"([一-龥]+)\s*/\s*([一-龥]+)\s*(\d+)\s*歳", info_text)
            if mm:
                shibu, home, age = mm.group(1), mm.group(2), mm.group(3)
            # info_idx+1 = F/L/平均ST列, +2 = 全国, +3 = 当地 を期待
            if info_idx + 1 < len(tds):
                fl_dec = cell_decimals(tds[info_idx + 1])
                # 平均STは 0.XX
                for d in fl_dec:
                    if re.match(r"^0\.\d+$", d) or re.match(r"^\d\.\d{2}$", d):
                        avg_st = d
                        break
            if info_idx + 2 < len(tds):
                zd = cell_decimals(tds[info_idx + 2])
                for j in range(min(3, len(zd))):
                    zen[j] = zd[j]
            if info_idx + 3 < len(tds):
                td_ = cell_decimals(tds[info_idx + 3])
                for j in range(min(3, len(td_))):
                    toti[j] = td_[j]

        # モーター(info_idx+4)/ボート(info_idx+5): "No 2連率 3連率" の3値
        motor_no = motor_2rt = motor_3rt = ""
        boat_no = boat_2rt = boat_3rt = ""
        if info_idx is not None:
            if info_idx + 4 < len(tds):
                td_m = tds[info_idx + 4]
                txt_m = td_m.get_text(" ", strip=True)
                m_no = re.match(r"^\s*(\d+)", txt_m)
                if m_no:
                    motor_no = m_no.group(1)
                m_dec = cell_decimals(td_m)
                if len(m_dec) >= 1:
                    motor_2rt = m_dec[0]
                if len(m_dec) >= 2:
                    motor_3rt = m_dec[1]
            if info_idx + 5 < len(tds):
                td_b = tds[info_idx + 5]
                txt_b = td_b.get_text(" ", strip=True)
                b_no = re.match(r"^\s*(\d+)", txt_b)
                if b_no:
                    boat_no = b_no.group(1)
                b_dec = cell_decimals(td_b)
                if len(b_dec) >= 1:
                    boat_2rt = b_dec[0]
                if len(b_dec) >= 2:
                    boat_3rt = b_dec[1]

        # 今節成績のグリッド（tbody4行）。構造不一致でも壊れないよう例外は握りつぶす。
        try:
            results = parse_shussetsu_grid(trs)
        except Exception:
            results = []

        rec = {
            "場名": venue, "場コード": jcd, "開催日": hd, "レース": "{}R".format(rno),
            "枠": waku, "登録番号": toban, "級別": rank, "氏名": name,
            "F数": f_num, "L数": l_num, "平均ST": avg_st,
            "全国勝率": zen[0], "全国2連率": zen[1], "全国3連率": zen[2],
            "当地勝率": toti[0], "当地2連率": toti[1], "当地3連率": toti[2],
            "モーターNo": motor_no, "モーター2連率": motor_2rt, "モーター3連率": motor_3rt,
            "ボートNo": boat_no, "ボート2連率": boat_2rt, "ボート3連率": boat_3rt,
            "1日目成績": "", "2日目成績": "", "3日目成績": "",
            "4日目成績": "", "5日目成績": "", "6日目成績": "",
            "支部": shibu, "出身": home, "年齢": age, "締切時刻": deadline,
            "節名": setsu, "企画名": kikaku, "日目": nichime,
        }
        pending.append((rec, results))

    # 節初日 = 全選手の実施レース日付の最小（連続開催前提で day_index を確定）。
    all_dates = []
    for _rec, results in pending:
        for r in results:
            try:
                all_dates.append(datetime.datetime.strptime(r["hd"], "%Y%m%d").date())
            except Exception:
                pass
    meeting_start = min(all_dates) if all_dates else None

    for rec, results in pending:
        days = shussetsu_days(results, meeting_start)
        for k in range(SHUSSETSU_MAX_DAYS):
            rec["{}日目成績".format(k + 1)] = days[k]
        records.append(rec)

    # 枠番を出現順に振り直す（この関数は1レース分なので、出現順=枠順）
    for i, rec in enumerate(records):
        rec["枠"] = str(i + 1)

    return records


def get_open_venues(hd):
    """「本日のレース」一覧から本日開催している場コードの集合を返す。
    非開催場はこの一覧に並ばないため、すり替わり（リダイレクトで別場の直近データ）を防げる。
    取得できなければ None を返し、呼び出し側は従来どおり全場を試す。"""
    url = "https://www.boatrace.jp/owpc/pc/race/index?hd={}".format(hd)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        # 一覧テーブルの各行に jcd=XX&hd=該当日 が埋まっている。該当日のものだけ拾う。
        found = set(re.findall(r"jcd=(\d{2})&hd=" + re.escape(hd), resp.text))
        return found if found else None
    except Exception:
        return None


def find_open_date_and_scrape(jcd, venue, hd):
    """指定した開催日 hd で1R〜12Rを取得。取れなければ (None, [])。"""
    url = "https://www.boatrace.jp/owpc/pc/race/racelist?rno=1&jcd={}&hd={}".format(jcd, hd)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None, []
        recs = parse_racelist(resp.text, jcd, venue, hd, 1)
        if not recs:
            return None, []
        all_recs = list(recs)
        def fetch_race(rno):
            u = "https://www.boatrace.jp/owpc/pc/race/racelist?rno={}&jcd={}&hd={}".format(rno, jcd, hd)
            try:
                r = requests.get(u, headers=HEADERS, timeout=12)
                if r.status_code == 200:
                    return parse_racelist(r.text, jcd, venue, hd, rno)
            except Exception:
                pass
            return []
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as ex:
            for recs_r in ex.map(fetch_race, range(2, 13)):
                all_recs.extend(recs_r)
        return hd, all_recs
    except Exception:
        return None, []


CSV_COLUMNS = [
    "場名", "場コード", "開催日", "レース", "枠", "登録番号", "級別", "氏名",
    "F数", "L数", "平均ST", "全国勝率", "全国2連率", "全国3連率",
    "当地勝率", "当地2連率", "当地3連率",
    "モーターNo", "モーター2連率", "モーター3連率",
    "ボートNo", "ボート2連率", "ボート3連率",
    "1日目成績", "2日目成績", "3日目成績", "4日目成績", "5日目成績", "6日目成績",
    "支部", "出身", "年齢", "締切時刻",
    "節名", "企画名", "日目",
]


def load_existing_csv(path):
    """既存CSVを文字列で読み込む。無ければ None。"""
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig").fillna("")
        if "開催日" not in df.columns or "場コード" not in df.columns:
            return None
        return df
    except Exception:
        return None


def _race_num(v):
    """'7R' → 7。ソート用。失敗時は0。"""
    m = re.search(r"\d+", str(v))
    return int(m.group()) if m else 0


def merge_with_existing(new_df, csv_path):
    """当日+翌日の2日分を保持するマージ。
    - keep_dates は target_dates() の当日+翌日で固定（新規で取れなかった日も既存分を保持）
    - キー「開催日+場コード+レース+枠」で重複排除し、新規取得を優先(keep='last')
    - 過去日(<当日)は破棄
    """
    # 保持対象日は取得成功可否によらず「当日+翌日」で固定
    keep_dates = set(d.strftime("%Y%m%d") for d in target_dates())

    if new_df is None or len(new_df) == 0:
        new_same = pd.DataFrame(columns=CSV_COLUMNS)
    else:
        new_same = new_df[new_df["開催日"].astype(str).isin(keep_dates)].copy()

    old_df = load_existing_csv(csv_path)
    if old_df is not None and len(old_df) > 0:
        old_same = old_df[old_df["開催日"].astype(str).isin(keep_dates)].copy()
    else:
        old_same = pd.DataFrame(columns=CSV_COLUMNS)

    # 旧→新の順に連結し、同一キーは後勝ち(新規優先)で残す
    combined = pd.concat([old_same, new_same], ignore_index=True)
    if len(combined) == 0:
        return combined

    combined["__key"] = (
        combined["開催日"].astype(str) + "_"
        + combined["場コード"].astype(str) + "_"
        + combined["レース"].astype(str) + "_"
        + combined["枠"].astype(str)
    )
    combined = combined.drop_duplicates(subset="__key", keep="last").drop(columns="__key")

    # カラム順を固定し、欠けは空文字で補完
    for c in CSV_COLUMNS:
        if c not in combined.columns:
            combined[c] = ""
    combined = combined[CSV_COLUMNS]

    # 開催日→場コード→レース番号→枠 でソート
    combined["__r"] = combined["レース"].map(_race_num)
    combined["__w"] = pd.to_numeric(combined["枠"], errors="coerce").fillna(0).astype(int)
    combined = combined.sort_values(
        ["開催日", "場コード", "__r", "__w"], kind="stable"
    ).drop(columns=["__r", "__w"]).reset_index(drop=True)

    print("マージ後 保持日={} / {}件".format(
        sorted(keep_dates), len(combined)))
    return combined


def main():
    print("出走表スクレイパー v4 (2日分取得: 当日+翌日)")
    print("実行日時:", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print()

    dates = target_dates()
    open_by_date = {}  # hd -> set(jcd)
    for d in dates:
        hd = d.strftime("%Y%m%d")
        ov = get_open_venues(hd)
        open_by_date[hd] = ov
        if ov:
            print("{}開催場: {} 場 ({})".format(hd, len(ov), " ".join(sorted(ov))))
        else:
            print("{}開催場リスト取得失敗".format(hd))
    print()

    all_records = []
    for d in dates:
        hd = d.strftime("%Y%m%d")
        ov = open_by_date.get(hd)
        for jcd, name in VENUES.items():
            if ov is not None and jcd not in ov:
                continue
            print("[{}][{}] {} ...".format(hd, jcd, name), end=" ", flush=True)
            got_hd, records = find_open_date_and_scrape(jcd, name, hd)
            if not records:
                print("なし")
                continue
            all_records.extend(records)
            print("OK ({}名)".format(len(records)))

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, "racers_today.csv")

    if not all_records:
        print("\n出走表が取得できませんでした。既存CSVを保持します。")
        if os.path.exists(csv_path) or os.path.exists(os.path.join(OUTPUT_DIR, "index.html")):
            return
        df = pd.DataFrame(columns=CSV_COLUMNS)
    else:
        new_df = pd.DataFrame(all_records)
        df = merge_with_existing(new_df, csv_path)

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print("\nCSV保存: {}/racers_today.csv ({}件)".format(OUTPUT_DIR, len(df)))

    cols = [str(c) for c in df.columns.tolist()]
    data = df.fillna("").values.tolist()
    updated = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    data_json = json.dumps(
        {"columns": cols, "data": data, "venues": dict(VENUES), "updated": updated},
        ensure_ascii=False, default=str,
    )
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()
    html = template.replace("__DATA_PLACEHOLDER__", data_json)
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("ビューワー保存: {}/index.html".format(OUTPUT_DIR))
    print("完了!")


if __name__ == "__main__":
    main()
