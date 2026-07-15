# -*- coding: utf-8 -*-
# fetchPartsExchange.py
# boatrace.jp公式「直前情報(beforeinfo)」から各レース各艇の部品交換・展示タイム・チルト・
# プロペラ変更・体重を収集し、docs/data/motorParts.json に時系列 append 蓄積する
# （モーター整備履歴のカルテ化・前節1位機/motorHistoryと同思想）。
#
# 取得元（本体ドメイン。各場サブドメインと異なりActionsから到達可能な想定）:
#   https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={1-12}&jcd={01-24}&hd={YYYYMMDD}
#
# 対象日は「JST現在日−1日」に固定する（当日は発走前で全項目空、2日以上前は
# 別日へのサイレントリダイレクトが起きるため。workflow_dispatch時のみ HD_OVERRIDE で上書き可）。
# 対象の場・レースは venueMeta.json（当日開催場）ではなく results/{対象日}.json の
# 「結果」配列（場コード・レース）から取る。
#
# hd一致検証（今回の核）:
#   公式beforeinfoは2日以上前のhdを要求すると、エラーではなく別日のページを
#   同一URLでサイレントに返す。取得HTML内のレースリンク(beforeinfo?rno=...&jcd=...&hd=...)
#   から実際のjcd/hdを逆算し、要求値と一致しないレースは1行も保存せず破棄する。
#   検証に使う値がHTMLから取れない場合も安全側に倒して破棄する。
#
# 展示タイム＝公開済みフラグ:
#   展示タイムが空の行（未公開/欠場）は保存しない。展示タイムが入っている行は
#   部品交換欄が空でも保存する（＝この空は「交換なし」と確定できる）。
#
# ハルシネーション防止（絶対）:
#   beforeinfo から読めた実データのみ。部品交換欄が空なら空文字（＝交換なし）として記録し、
#   部品名を創作しない。出典URL・取得日時を必ず保持する。
#
# ※HTML構造（table.is-w748／各艇=1<tbody>／先頭<tr>に9td）は公式beforeinfoの実構造に基づく。
#   セレクタ table.is-w748 とtd位置は推定を含むため、名前セル(登番リンク)を基準に相対で拾う堅牢版。
import os
import re
import json
import time
import datetime
import urllib.request

from bs4 import BeautifulSoup

JST = datetime.timezone(datetime.timedelta(hours=9))

RACERS_CSV = os.path.join("docs", "racers", "racers_today.csv")
RESULTS_DIR = "results"
OUT = os.path.join("docs", "data", "motorParts.json")

BASE = "https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={rno}&jcd={jcd}&hd={hd}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
SLEEP = float(os.environ.get("PARTS_SLEEP", "0.8"))
TIMEOUT = int(os.environ.get("PARTS_TIMEOUT", "12"))

# 24場名（公式固定・他スクリプトと同一の対応表。推測ではなく既定値）
JCD_NAME = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}

# 部品凡例（公式固定）。参考メタとして保持（解釈は加えない）。
PARTS_LEGEND = ["ピストン", "リング", "電気", "キャブ", "シリンダ", "シャフト", "ギヤ", "キャリボ", "ペラ"]

TOBAN_RE = re.compile(r"toban=(\d{4})")
# ページ内のレースナビ(自レース含む)から実際に配信されたjcd/hdを逆算する
NAV_RE = re.compile(r"beforeinfo\?rno=\d+&jcd=(\d+)&hd=(\d+)")


def _cell_text(td):
    return re.sub(r"\s+", " ", td.get_text(" ", strip=True)).strip() if td else ""


def parse_beforeinfo(html):
    """beforeinfo のHTMLから各艇の情報を返す。
    返り値: [{枠, 登番, 体重, 展示タイム, チルト, プロペラ変更(bool), 部品交換(str)}]
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
        weight = rel(1)     # 体重
        tenji = rel(2)      # 展示タイム
        tilt = rel(3)       # チルト
        propeller = rel(4)  # プロペラ列（変更時「新」）
        parts = rel(5)      # 部品交換（空欄＝交換なし）
        out.append({
            "枠": waku,
            "登番": toban,
            "体重": weight,
            "展示タイム": tenji,
            "チルト": tilt,
            "プロペラ変更": ("新" in propeller),
            "部品交換": parts,
        })
    return out


def verify_hd_jcd(html, want_jcd, want_hd):
    """HTML内のレースナビからjcd/hdを逆算し、要求値と一致するか検証する。
    取れない/複数種混在/不一致なら安全側に倒して False。"""
    matches = NAV_RE.findall(html)
    if not matches:
        return False, "ナビからjcd/hdを抽出できず"
    jcds = set(j.zfill(2) for j, h in matches)
    hds = set(h for j, h in matches)
    if len(jcds) != 1 or len(hds) != 1:
        return False, "ナビ内でjcd/hdが混在（複数種）"
    got_jcd = next(iter(jcds))
    got_hd = next(iter(hds))
    if got_jcd != want_jcd or got_hd != want_hd:
        return False, "jcd/hd不一致（要求jcd={} hd={} / 実際jcd={} hd={}）".format(
            want_jcd, want_hd, got_jcd, got_hd)
    return True, ""


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
    """racers_today.csv から (jcd, 登番)→(モーターNo, 氏名) を作る（当日データのため best-effort）。"""
    m = {}
    if not os.path.exists(RACERS_CSV):
        return m
    import csv
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


def load_name_map_from_results(results_doc):
    """results/{hd}.json の「艇」配列から (jcd, 登番)→氏名 を作る（対象日そのものの実データ）。"""
    m = {}
    for rec in results_doc.get("結果", []):
        jcd = str(rec.get("場コード", "")).zfill(2)
        for boat in rec.get("艇", []):
            toban = str(boat.get("登番", "")).strip()
            name = str(boat.get("氏名", "")).strip()
            if jcd and toban and name:
                m[(jcd, toban)] = name
    return m


def target_hd():
    """対象hdを決める。workflow_dispatchのHD_OVERRIDEが妥当ならそれを優先、既定はJST現在日−1日。"""
    override = os.environ.get("HD_OVERRIDE", "").strip()
    if override:
        if re.fullmatch(r"\d{8}", override):
            return override
        print("HD_OVERRIDE不正（{}）。既定（前日）を使用。".format(override))
    return (datetime.datetime.now(JST) - datetime.timedelta(days=1)).strftime("%Y%m%d")


def load_target_races(hd):
    """results/{hd}.json の「結果」配列から (jcd, rno) の一覧を作る。ファイル無し/不正ならNone。"""
    path = os.path.join(RESULTS_DIR, "{}.json".format(hd))
    d = load_json(path)
    if not d or not isinstance(d.get("結果"), list):
        return None, None
    races = []
    for r in d["結果"]:
        jcd = str(r.get("場コード", "")).zfill(2)
        race = str(r.get("レース", "")).strip()
        m = re.match(r"(\d+)", race)
        if not jcd or not m:
            continue
        races.append((jcd, int(m.group(1))))
    return races, d


def main():
    hd = target_hd()
    races, results_doc = load_target_races(hd)
    if races is None:
        print("results/{}.json が無い/不正。処理中止（既存を変更しない）。hd={}".format(hd, hd))
        return
    if not races:
        print("results/{}.json にレースが無い。処理中止（既存を変更しない）。".format(hd))
        return

    jcds = sorted(set(j for j, _ in races))
    print("対象hd={} 対象場数={} 対象レース数={}".format(hd, len(jcds), len(races)))

    racer_map = load_racer_map()
    name_map = load_name_map_from_results(results_doc)

    # --- 疎通確認：先頭レースの取得可否のみ見る（ネットワーク到達不可なら全体中止・既存維持） ---
    first_jcd, first_rno = races[0]
    first_url = BASE.format(rno=first_rno, jcd=first_jcd, hd=hd)
    first_html = fetch(first_url)
    if not first_html:
        print("疎通失敗。boatrace.jp本体に到達できず。全体を中止（既存を変更しない）。")
        return
    time.sleep(SLEEP)

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
    mismatch_races = []
    skipped_empty_tenji = 0
    pending = list(races)

    for idx, (jcd, rno) in enumerate(pending):
        if idx == 0:
            html = first_html  # 疎通確認で取得済みの1件目を再利用（二重取得しない）
        else:
            url = BASE.format(rno=rno, jcd=jcd, hd=hd)
            html = fetch(url)
            time.sleep(SLEEP)
        if not html:
            continue
        url = BASE.format(rno=rno, jcd=jcd, hd=hd)

        ok, why = verify_hd_jcd(html, jcd, hd)
        if not ok:
            mismatch_races.append((jcd, rno, why))
            continue

        rows = parse_beforeinfo(html)
        if not rows:
            continue
        fetched_races += 1
        vname = JCD_NAME.get(jcd, "")
        for row in rows:
            if not str(row["展示タイム"]).strip():
                skipped_empty_tenji += 1
                continue  # 展示タイム空＝未公開/欠場のため保存しない
            key = (jcd, hd, str(rno), str(row["枠"]))
            if key in seen:
                continue  # 二重積み防止
            info = racer_map.get((jcd, row["登番"]), {})
            name = name_map.get((jcd, row["登番"])) or info.get("氏名", "")
            rec = {
                "jcd": jcd,
                "場名": vname,
                "開催日": hd,
                "rno": rno,
                "枠": row["枠"],
                "登番": row["登番"],
                "氏名": name,
                "モーターNo": info.get("モーターNo", ""),
                "節名": "",
                "部品交換": row["部品交換"],
                "展示タイム": row["展示タイム"],
                "チルト": row["チルト"],
                "プロペラ変更": row["プロペラ変更"],
                "体重": row["体重"],
                "出典URL": url,
                "取得日時": datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
            }
            hist["records"].append(rec)
            seen.add(key)
            added += 1

    hist["updated"] = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)

    print("保存: {} … 対象{}レース中 取得{}レース / 追加{}行 / 累計{}行".format(
        OUT, len(races), fetched_races, added, len(hist["records"])))
    print("hd/jcd不一致で破棄: {}件".format(len(mismatch_races)))
    for jcd, rno, why in mismatch_races:
        print("  破棄: jcd={} rno={} 理由={}".format(jcd, rno, why))
    print("展示タイム空でskip: {}行".format(skipped_empty_tenji))


if __name__ == "__main__":
    main()
