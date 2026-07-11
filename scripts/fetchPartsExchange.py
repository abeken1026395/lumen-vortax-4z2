# -*- coding: utf-8 -*-
# fetchPartsExchange.py
# boatrace.jp公式「直前情報(beforeinfo)」から各レース各艇の部品交換・展示タイム・チルト・
# プロペラ変更を収集し、出走表CSVの登番→モーターNoで紐付けて docs/data/motorParts.json に
# 時系列 append 蓄積する（モーター整備履歴のカルテ化・前節1位機/motorHistoryと同思想）。
#
# 取得元（本体ドメイン。各場サブドメインと異なりActionsから到達可能な想定）:
#   https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={1-12}&jcd={01-24}&hd={YYYYMMDD}
#
# 収集対象は venueMeta.json の開催中の場×全12R。直前情報は結果確定後も残るため夜収集で当日分が揃う。
#
# ハルシネーション防止（絶対）:
#   beforeinfo から読めた実データのみ。部品交換欄が空なら空文字（＝交換なし）として記録し、
#   部品名を創作しない。出典URL・取得日時を必ず保持する。
#
# ※HTML構造（table.is-w748／各艇=1<tbody>／先頭<tr>に9td）は公式beforeinfoの実構造に基づく。
#   セレクタ table.is-w748 とtd位置は推定を含むため、名前セル(登番リンク)を基準に相対で拾う堅牢版。
import io
import os
import re
import csv
import json
import time
import datetime
import urllib.request

from bs4 import BeautifulSoup

JST = datetime.timezone(datetime.timedelta(hours=9))

VENUE_META = os.path.join("docs", "data", "venueMeta.json")
RACERS_CSV = os.path.join("docs", "racers", "racers_today.csv")
OUT = os.path.join("docs", "data", "motorParts.json")

BASE = "https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={rno}&jcd={jcd}&hd={hd}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
SLEEP = float(os.environ.get("PARTS_SLEEP", "0.8"))
TIMEOUT = int(os.environ.get("PARTS_TIMEOUT", "12"))

# 部品凡例（公式固定）。参考メタとして保持（解釈は加えない）。
PARTS_LEGEND = ["ピストン", "リング", "電気", "キャブ", "シリンダ", "シャフト", "ギヤ", "キャリボ", "ペラ"]

TOBAN_RE = re.compile(r"toban=(\d{4})")


def _cell_text(td):
    return re.sub(r"\s+", " ", td.get_text(" ", strip=True)).strip() if td else ""


def parse_beforeinfo(html):
    """beforeinfo のHTMLから各艇の情報を返す。
    返り値: [{枠, 登番, 展示タイム, チルト, プロペラ変更(bool), 部品交換(str)}]
    名前セル（profile?toban=リンク）を基準に、体重→展示→チルト→プロペラ→部品交換を相対で拾う。
    読めない項目は空。部品交換が空欄なら空文字（＝交換なし）。"""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tbody in soup.find_all("tbody"):
        tr = tbody.find("tr")
        if not tr:
            continue
        tds = tr.find_all("td", recursive=False)
        # 名前セル（登番リンクを含むtd）の位置を探す
        name_idx = None
        toban = ""
        for i, td in enumerate(tds):
            a = td.find("a", href=TOBAN_RE)
            if a:
                m = TOBAN_RE.search(a.get("href", ""))
                if m:
                    toban = m.group(1)
                    name_idx = i
                    break
        if name_idx is None or not toban:
            continue  # 選手行でないtbody（ヘッダ等）はスキップ
        # 枠：名前セルより前で最初の数字1-6のtd（rowspanの枠セル）
        waku = ""
        for j in range(0, name_idx):
            t = _cell_text(tds[j])
            if re.fullmatch(r"[1-6]", t):
                waku = t
                break
        # 名前セル基準の相対列：+1体重 +2展示 +3チルト +4プロペラ +5部品交換
        def rel(k):
            idx = name_idx + k
            return _cell_text(tds[idx]) if 0 <= idx < len(tds) else ""
        tenji = rel(2)     # 展示タイム
        tilt = rel(3)      # チルト
        propeller = rel(4)  # プロペラ列（変更時「新」）
        parts = rel(5)     # 部品交換（空欄＝交換なし）
        out.append({
            "枠": waku,
            "登番": toban,
            "展示タイム": tenji,
            "チルト": tilt,
            "プロペラ変更": ("新" in propeller),
            "部品交換": parts,
        })
    return out


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print("  [warn] fetch失敗:", url, e)
        return None


def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_racer_map():
    """racers_today.csv から (jcd, 登番)→(モーターNo, 氏名) を作る。"""
    m = {}
    if not os.path.exists(RACERS_CSV):
        return m
    with open(RACERS_CSV, "r", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            jcd = str(r.get("場コード", "")).zfill(2)
            toban = str(r.get("登録番号", "")).strip()
            if not jcd or not toban:
                continue
            m[(jcd, toban)] = {
                "モーターNo": str(r.get("モーターNo", "")).strip(),
                "氏名": str(r.get("氏名", "")).strip(),
            }
    return m


def probe(jcd, hd):
    """疎通確認：1場1レースを取得してパースできるか。(ok, http状態文字列, 艇数)"""
    url = BASE.format(rno=1, jcd=jcd, hd=hd)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            code = r.getcode()
            html = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return False, "ERR:{}".format(e), 0
    rows = parse_beforeinfo(html)
    return (code == 200 and len(rows) > 0), "HTTP {}".format(code), len(rows)


def main():
    meta = load_json(VENUE_META)
    if not meta or not isinstance(meta.get("venues"), dict):
        print("venueMeta.json が読めない。処理中止（既存を変更しない）。")
        return
    venues = meta["venues"]
    racer_map = load_racer_map()

    # --- 疎通確認（開催中の先頭1場・1R）。失敗なら全体中止して報告 ---
    jcds = sorted(venues.keys())
    if not jcds:
        print("開催中の場が無い。終了。")
        return
    first_jcd = jcds[0]
    first_hd = str(venues[first_jcd].get("開催日", ""))
    ok, status, n = probe(first_jcd, first_hd)
    print("疎通確認: jcd={} hd={} 1R … {} / 艇数{}".format(first_jcd, first_hd, status, n))
    if not ok:
        print("疎通失敗。boatrace.jp本体に到達できないか構造不一致。全体を中止（既存を変更しない）。")
        return

    # --- 既存履歴の読み込みと重複キー ---
    hist = load_json(OUT)
    if not hist or not isinstance(hist.get("records"), list):
        hist = {
            "updated": "",
            "source": "boatrace.jp公式 直前情報",
            "note": "各レース各艇の部品交換等（実データのみ・解釈なし）。モーター整備履歴のカルテ化用。",
            "records": [],
        }
    seen = set()
    for r in hist["records"]:
        seen.add((str(r.get("jcd", "")).zfill(2), str(r.get("開催日", "")),
                  str(r.get("rno", "")), str(r.get("枠", ""))))

    added = 0
    fetched_races = 0
    for jcd in jcds:
        hd = str(venues[jcd].get("開催日", ""))
        vname = str(venues[jcd].get("場名", ""))
        for rno in range(1, 13):
            url = BASE.format(rno=rno, jcd=jcd, hd=hd)
            html = fetch(url)
            time.sleep(SLEEP)
            if not html:
                continue
            rows = parse_beforeinfo(html)
            if not rows:
                continue
            fetched_races += 1
            for row in rows:
                key = (jcd, hd, str(rno), str(row["枠"]))
                if key in seen:
                    continue  # 二重積み防止
                info = racer_map.get((jcd, row["登番"]), {})
                rec = {
                    "jcd": jcd,
                    "場名": vname,
                    "開催日": hd,
                    "rno": rno,
                    "枠": row["枠"],
                    "登番": row["登番"],
                    "氏名": info.get("氏名", ""),
                    "モーターNo": info.get("モーターNo", ""),
                    "部品交換": row["部品交換"],
                    "展示タイム": row["展示タイム"],
                    "チルト": row["チルト"],
                    "プロペラ変更": row["プロペラ変更"],
                    "出典URL": url,
                    "取得日時": datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
                }
                hist["records"].append(rec)
                seen.add(key)
                added += 1

    if added == 0 and not os.path.exists(OUT):
        print("積む実データが無く既存も無い。motorParts.json は未生成のまま。")
        return

    hist["updated"] = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)
    print("保存: {} … 取得{}レース / 追加{}行 / 累計{}行".format(
        OUT, fetched_races, added, len(hist["records"])))


if __name__ == "__main__":
    main()
