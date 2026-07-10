#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""buildKansenkiSource.py — 観戦記システムの素材JSON生成部

夜のActions（updateResults.yml 後段, JST22時以降）で実行し、翌朝のClaude Code執筆の
唯一の入力 docs/data/kansenki/source/YYYYMMDD.json を生成する。
執筆側は「素材にない事実は書かない」ため、ここに入らない情報は記事に存在できない。

設計指針は「buildKansenkiSource.py 入出力仕様・実装指示書 v2」に準拠。
- 日付定義は出走表CSVの開催日＋日目を正とする（システム日付から単純導出しない §0）
- boatrace.jp アクセスは pointrank のみ（新規・optional）。失敗は scoreRank=null で続行
- predictions/・verify_log.csv・profile.json・e30Schedule.json は読み取りのみ（書き込み禁止 §6）
- 再実行はnullフィールドの補完のみ・非null値不変・夜間帯限定（§4.1）
- 文字列処理はPython io.open + UTF-8（bashで日本語grep/sed禁止 §6）
"""

import io
import os
import csv
import json
import re
import datetime

# ---- 任意依存（pointrank取得用）。無ければ scoreRank は常にnullで続行 ----
try:
    import requests
    from bs4 import BeautifulSoup
    _HAS_NET = True
except Exception:  # pragma: no cover
    requests = None
    BeautifulSoup = None
    _HAS_NET = False

JST = datetime.timezone(datetime.timedelta(hours=9))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RACERS_CSV = os.path.join(ROOT, "docs", "racers", "racers_today.csv")
RESULTS_DIR = os.path.join(ROOT, "results")
VERIFY_LOG = os.path.join(ROOT, "verify_log.csv")
PROFILE_JSON = os.path.join(ROOT, "docs", "players", "profile.json")
KIMARITE_CSV = os.path.join(ROOT, "docs", "players", "racerKimarite.csv")
ARTICLES_DIR = os.path.join(ROOT, "docs", "data", "kansenki", "articles")
OUT_DIR = os.path.join(ROOT, "docs", "data", "kansenki", "source")

# e30Schedule.json はルート／docs/data の双方に存在（同一）。ルートを正、無ければdocs/data。
E30_CANDIDATES = [
    os.path.join(ROOT, "e30Schedule.json"),
    os.path.join(ROOT, "docs", "data", "e30Schedule.json"),
]

VENUES = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}

# 場の地元支部（isLocal判定用）。支部＝選手の所属県。
VENUE_KEN = {
    "01": "群馬", "02": "埼玉", "03": "東京", "04": "東京",
    "05": "東京", "06": "静岡", "07": "愛知", "08": "愛知",
    "09": "三重", "10": "福井", "11": "滋賀", "12": "大阪",
    "13": "兵庫", "14": "徳島", "15": "香川", "16": "岡山",
    "17": "広島", "18": "山口", "19": "山口", "20": "福岡",
    "21": "福岡", "22": "福岡", "23": "佐賀", "24": "長崎",
}

# 既知の節タイプ辞書（辞書外はnull §4.4）。節名の部分一致で機械付与。
# 注: 「周年」「記念」の素朴な部分一致は、BTS（場外発売場）の開設周年記念＝一般戦を
# G1周年と誤付与する（例: ＢＴＳ岡山わけ開設５周年記念競走）。周年G1は series_note_for で
# 「開設<数字>周年記念」の厳密一致かつBTS表記を含まない場合のみに限定する。
SERIES_NOTE = [
    ("甲子園", "都道府県対抗の大会"),
    ("ヤングダービー", "若手の全国大会"),
    ("マスターズ", "ベテランの全国大会"),
    ("レディースチャンピオン", "女子のG1タイトル戦"),
    ("クイーンズクライマックス", "女子の年間王者決定戦"),
    ("オールスター", "ファン投票によるSG"),
    ("グランプリ", "賞金上位によるSG年間王者決定戦"),
    ("ダービー", "全国ボートレース地区対抗ではないSG王座戦"),
]

MAN_TH = 10000    # 万舟（三連単配当>10000, payoutsページと統一）
HARAN_TH = 5000   # 荒れ（三連単配当>=5000, build_verify_summaryと統一）

REQ_TIMEOUT = int(os.environ.get("BKS_TIMEOUT", "15"))

# 司令塔判断①: scoreRank shadow mode。
# 自己検知(§3.1-3 得点−減点÷走数≒得点率)が実HTMLで確定するまで、pointrankが非nullで
# 取れてもJSONには書き込まずログ出力のみ（shadow）とする。汚染検証(a)(b)(c)だけで信用して
# 書き込む状態を作らない。実ページ1件でDOM列と再計算を確定→司令塔確認後に
# BKS_SCORERANK_WRITE=1 かつ 自己検知passed で書き込み解禁。
SCORERANK_WRITE = os.environ.get("BKS_SCORERANK_WRITE") == "1"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


# ---------------------------------------------------------------------------
# 汎用ヘルパ
# ---------------------------------------------------------------------------
def jst_now():
    return datetime.datetime.now(JST)


def to_float(s):
    """数値文字列→float。空・非数値はNone。"""
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def to_int(s):
    f = to_float(s)
    return int(f) if f is not None and float(f).is_integer() else (f if f is not None else None)


def ymd_dash(hd8):
    """'20260709' -> '2026-07-09'"""
    return "{}-{}-{}".format(hd8[0:4], hd8[4:6], hd8[6:8])


def parse_date8(hd8):
    return datetime.date(int(hd8[0:4]), int(hd8[4:6]), int(hd8[6:8]))


def rno_to_int(rno):
    m = re.match(r"(\d+)", str(rno))
    return int(m.group(1)) if m else None


def load_json(path):
    """JSONを読む。存在しない・破損（部分書き込み等の欠番ファイル）はNoneで続行。
    §0の「検証ループ7/6欠番と同種のスケジュール・ドリフト事故」対策で例外を握りつぶす。"""
    if not os.path.exists(path):
        return None
    try:
        with io.open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return None


# ---------------------------------------------------------------------------
# 入力ロード
# ---------------------------------------------------------------------------
def load_racers():
    """当日出走表CSV（BOM付きutf-8-sig）を場コード別にまとめる。"""
    rows = []
    with io.open(RACERS_CSV, "r", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append(r)
    by_jcd = {}
    for r in rows:
        by_jcd.setdefault(r["場コード"], []).append(r)
    return rows, by_jcd


def load_results(results_date8):
    """results/YYYYMMDD.json を読む。無ければNone。戻り: (data, path or None)。"""
    path = os.path.join(RESULTS_DIR, results_date8 + ".json")
    data = load_json(path)
    return data, (path if data is not None else None)


def results_by_jcd(results_data):
    """results 結果リストを場コード別（'01'..）に分ける。"""
    out = {}
    if not results_data:
        return out
    lst = results_data.get("結果") if isinstance(results_data, dict) else results_data
    if not isinstance(lst, list):
        return out
    for row in lst:
        jcd = str(row.get("場コード", "")).zfill(2)
        out.setdefault(jcd, []).append(row)
    return out


def load_verify_venue_stats(results_date8):
    """verify_log.csv から場別・過去1年（results_dateを終点）の実績を1パスで集計。
    戻り: {jcd: {n, man, haran, lane1}}。読み取りのみ。"""
    try:
        end = parse_date8(results_date8)
    except Exception:
        end = jst_now().date()
    start = end - datetime.timedelta(days=365)
    agg = {}
    if not os.path.exists(VERIFY_LOG):
        return agg
    with io.open(VERIFY_LOG, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = (row.get("日付") or "").strip()
            if len(d) != 8:
                continue
            try:
                dd = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
            except Exception:
                continue
            if not (start <= dd <= end):
                continue
            jcd = (row.get("場コード") or "").zfill(2)
            pay = to_int(row.get("配当"))
            if pay is None:
                continue
            a = agg.setdefault(jcd, {"n": 0, "man": 0, "haran": 0, "lane1": 0})
            a["n"] += 1
            if pay > MAN_TH:
                a["man"] += 1
            if pay >= HARAN_TH:
                a["haran"] += 1
            chaku = (row.get("着順") or "").strip()
            if chaku[:1] == "1":
                a["lane1"] += 1
    return agg


def load_kimarite():
    """racerKimarite.csv を登録番号キーで読む（読み取りのみ）。"""
    out = {}
    if not os.path.exists(KIMARITE_CSV):
        return out
    with io.open(KIMARITE_CSV, "r", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out[str(r.get("登録番号", "")).strip()] = r
    return out


def load_profile():
    d = load_json(PROFILE_JSON)
    return d if isinstance(d, dict) else {}


def load_e30():
    for p in E30_CANDIDATES:
        d = load_json(p)
        if d:
            return {v["jcd"]: v for v in d.get("venues", [])}
    return {}


# ---------------------------------------------------------------------------
# 派生ロジック
# ---------------------------------------------------------------------------
def day_num_and_label(venue_rows):
    """日目（数値）とdayLabelを出走表から導出。
    '初日'/'N日目'/'最終日' を解釈。最終日は成績セルの最大日+1で数値化。"""
    label = ""
    for r in venue_rows:
        label = (r.get("日目") or "").strip()
        if label:
            break
    zen2han = str.maketrans("０１２３４５６７８９", "0123456789")
    lab = label.translate(zen2han)
    m = re.search(r"(\d+)\s*日目", lab)
    if m:
        return int(m.group(1)), label
    if "初日" in lab:
        return 1, label
    # 最終日など: 成績セルが埋まっている最大日インデックス+1
    max_day = 0
    for r in venue_rows:
        for k in range(1, 7):
            if (r.get("{}日目成績".format(k)) or "").strip():
                if k > max_day:
                    max_day = k
    return (max_day + 1 if max_day else None), label


def series_note_for(series):
    s = series or ""
    for key, note in SERIES_NOTE:
        if key in s:
            return note
    # 開設周年記念（G1）: 実在レース場の開設周年のみ。BTS等（場外発売場）の開設周年記念は
    # 一般戦のため除外（辞書外＝null）。「開設<数字>周年記念」の厳密一致かつBTS表記を含まない場合のみ。
    if re.search(r"開設[0-9０-９]+周年記念", s) and "ＢＴＳ" not in s and "BTS" not in s:
        return "開設周年記念のG1"
    return None


def parse_day_cell(cell):
    """'1R/2/.38/4 6R/3/.20/2' -> [{'rno':1,'course':2,'st':0.38,'finish':4}, ...]
    ※ CSVの2番目の値は進入コース。枠(waku)ではないため course として保持（捏造防止）。"""
    out = []
    cell = (cell or "").strip()
    if not cell:
        return out
    for tok in cell.split():
        parts = tok.split("/")
        if len(parts) < 4:
            continue
        rno = rno_to_int(parts[0])
        course = to_int(parts[1])
        st = to_float(parts[2])
        finish = to_int(parts[3])
        out.append({"rno": rno, "course": course, "st": st, "finish": finish})
    return out


def finish_trail_and_st(row):
    """出走表の各日成績セルから finishTrail と 日別平均ST(stSetsu) を作る。"""
    trail = []
    st_by_day = []
    for k in range(1, 7):
        cell = parse_day_cell(row.get("{}日目成績".format(k)))
        if not cell:
            continue
        sts = []
        for e in cell:
            trail.append({"day": k, "rno": e["rno"], "course": e["course"],
                          "st": e["st"], "finish": e["finish"]})
            if e["st"] is not None:
                sts.append(e["st"])
        if sts:
            st_by_day.append(round(sum(sts) / len(sts), 3))
    return trail, st_by_day


def kimarite_type(toban, kimarite_map):
    """racerKimarite.csv（直近183日集計）から決まり手型ラベル＋生数値を導出。
    司令塔判断(C): 裸のラベルは素材に入れない＝比較軸となる実数（まくり率/差し率/前づけ等）を同梱。
    - typeラベルは1着5本未満null（小標本での型断定を避ける）。生数値は標本サイズ(winCount)込みで併記。
    - racerKimarite.csv に該当登番が無ければ全体null。source は racerKimarite.csv（v2の
      「profile.json由来」記載は誤りで、決まり手の実体は本CSVにある）。"""
    r = kimarite_map.get(str(toban))
    if not r:
        return None
    wins = to_int(r.get("1着数")) or 0
    cats = [("逃げ", "逃げ型"), ("差し", "差し型"),
            ("まくり", "まくり型"), ("まくり差し", "まくり差し型")]
    label = None
    if wins >= 5:
        best_n = -1
        for key, lab in cats:
            n = to_int(r.get(key)) or 0
            if n > best_n:
                best_n = n
                label = lab
        if best_n <= 0:
            label = None
    return {
        "type": label,
        "winCount": wins,
        "runs": to_int(r.get("出走数")),
        "nige": to_int(r.get("逃げ")),
        "sashi": to_int(r.get("差し")),
        "makuri": to_int(r.get("まくり")),
        "makurisashi": to_int(r.get("まくり差し")),
        "makuriRate": to_float(r.get("まくり率")),
        "sashiRate": to_float(r.get("差し率")),
        "maezukeRate": to_float(r.get("前づけ率")),
        "maezukeAvg": to_float(r.get("前づけ平均")),
        "window": "{}〜{}".format((r.get("集計開始") or "").strip(),
                                  (r.get("集計終了") or "").strip()),
        "source": "racerKimarite.csv",
    }


def motor_avg(venue_rows):
    vals = [to_float(r.get("モーター2連率")) for r in venue_rows]
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def build_focus_racer(row, jcd, kimarite_map, profile, motor2avg):
    toban = str(row.get("登録番号", "")).strip()
    branch = (row.get("支部") or "").strip()
    trail, st_setsu = finish_trail_and_st(row)
    prof = profile.get(toban) or {}
    # profile.jsonに読み仮名フィールドは存在しない前提。あれば使用、なければnull（捏造禁止）。
    yomi = prof.get("yomi") or prof.get("読み") or None
    return {
        "toban": toban,
        "name": (row.get("氏名") or "").strip(),
        "yomi": yomi,
        "grade": (row.get("級別") or "").strip() or None,
        "branch": branch or None,
        "isLocal": (branch == VENUE_KEN.get(jcd)),
        "finishTrail": trail,
        "motorNo": to_int(row.get("モーターNo")),
        "motor2renSetsu": to_float(row.get("モーター2連率")),
        "motor2renSetsuAvg": motor2avg,
        "zenkokuWinRate": to_float(row.get("全国勝率")),
        "tochiWinRate": to_float(row.get("当地勝率")),
        # fan2604由来の当地参戦数/複勝はこのリポジトリに素材が無いためnull（過去参戦データ無し扱い）
        "tochiHistory": None,
        "fCount": to_int(row.get("F数")),
        "stSetsu": st_setsu,
        "stCareer": to_float(row.get("平均ST")),
        "kimariteType": kimarite_type(toban, kimarite_map),
    }


def pick_focus_tobans(jcd, venue_rows, score_rank, results_venue, csv_hd8, results_date8):
    """focusRacers対象登番を機械抽出（3〜5名）。得点率上位3＋地元勢最上位＋前日万舟1着艇。
    重複は詰める。素材が薄い場合は少数でよい。"""
    order = []

    def add(tb):
        tb = str(tb).strip()
        if tb and tb not in order:
            order.append(tb)

    # 1) 得点率上位3（scoreRankがあれば）
    if score_rank and score_rank.get("top"):
        for e in score_rank["top"][:3]:
            add(e.get("toban"))

    # 2) 地元勢最上位（全国勝率の高い順）
    locals_ = [r for r in venue_rows if (r.get("支部") or "").strip() == VENUE_KEN.get(jcd)]
    locals_.sort(key=lambda r: (to_float(r.get("全国勝率")) or -1), reverse=True)
    if locals_:
        add(locals_[0].get("登録番号"))

    # 3) 前日万舟の1着艇選手 — §4.3 CSV突合ガード:
    #    当日CSVの開催日が結果日と一致する夜間帯のみ成立。不一致ならスキップ（null）。
    if csv_hd8 == results_date8 and results_venue:
        for res in results_venue:
            pay = to_int(res.get("三連単配当"))
            if pay is not None and pay > MAN_TH:
                for boat in (res.get("艇") or []):
                    if to_int(boat.get("着")) == 1:
                        add(boat.get("登番"))
    return order[:5]


def build_results_block(results_venue):
    out = []
    for res in sorted(results_venue, key=lambda r: (rno_to_int(r.get("レース")) or 99)):
        entry = {
            "rno": rno_to_int(res.get("レース")),
            "finish": res.get("着順"),
            "payout": to_int(res.get("三連単配当")),
        }
        km = res.get("決まり手")
        if km:  # §2.1: results に決まり手が入っている場合のみ出力
            entry["kimarite"] = km
        out.append(entry)
    return out


def build_results_summary(results_block, vstat):
    man_races = [r for r in results_block
                 if r.get("payout") is not None and r["payout"] > MAN_TH]
    base = None
    if vstat and vstat["n"]:
        base = {
            "rate": round(100 * vstat["man"] / vstat["n"], 1),
            "source": "verify_log当場実績",
            "n": vstat["n"],
        }
    return {
        "manshuCount": len(man_races),
        "manshuRaces": [{"rno": r["rno"], "combo": r.get("finish"), "payout": r["payout"]}
                        for r in man_races],
        "venueManRateBase": base,
    }


def build_setsu_vs_year(jcd, results_date8, as_of_day):
    """今節（節初日〜結果日）の万舟ペースを、結果ファイルを横断集計して出す。
    結果ファイルが無ければnull。評価語なし・数値のみ（§4.4）。"""
    if not as_of_day or as_of_day < 1:
        return None
    try:
        end = parse_date8(results_date8)
    except Exception:
        return None
    setsu_races = 0
    setsu_man = 0
    found_any = False
    for back in range(0, as_of_day):  # 節初日=結果日-(as_of_day-1) 〜 結果日
        d = end - datetime.timedelta(days=back)
        data, _ = load_results(d.strftime("%Y%m%d"))
        if data is None:
            continue
        found_any = True
        for res in results_by_jcd(data).get(jcd, []):
            setsu_races += 1
            pay = to_int(res.get("三連単配当"))
            if pay is not None and pay > MAN_TH:
                setsu_man += 1
    if not found_any:
        return None
    return {
        "setsuManshu": setsu_man,
        "setsuRaces": setsu_races,
        "note": "今節万舟ペースと年間実績の比較軸（数値のみ・評価語なし）",
    }


def build_reference(jcd, vstat, results_date8, as_of_day, hd8, e30map):
    venue_year = None
    if vstat and vstat["n"]:
        n = vstat["n"]
        venue_year = {
            "manRate": round(100 * vstat["man"] / n, 1),
            "haranRate": round(100 * vstat["haran"] / n, 1),
            "katameRate": round(100 * vstat["lane1"] / n, 1),
            "n": n,
            "source": "verify_log.csv 当場過去1年（万舟>10000/荒れ>=5000/イン先頭決着）",
        }
    e30 = e30map.get(jcd)
    if e30:
        applies = hd8 is not None and ymd_dash(hd8) >= e30["startDate"]
        e30block = {"applies": bool(applies), "since": e30["startDate"],
                    "source": "e30Schedule.json"}
    else:
        e30block = {"applies": False, "since": None, "source": "e30Schedule.json"}
    return {
        "venueYearStats": venue_year,
        "setsuVsYear": build_setsu_vs_year(jcd, results_date8, as_of_day),
        "e30": e30block,
    }


def build_local_racers(jcd, venue_rows):
    ken = VENUE_KEN.get(jcd)
    locals_ = [r for r in venue_rows if (r.get("支部") or "").strip() == ken]
    locals_.sort(key=lambda r: (to_float(r.get("全国勝率")) or -1), reverse=True)
    seen = set()
    out = []
    for r in locals_:
        tb = str(r.get("登録番号", "")).strip()
        if tb in seen:
            continue
        seen.add(tb)
        grade = (r.get("級別") or "").strip()
        zwr = to_float(r.get("全国勝率"))
        t2 = to_float(r.get("当地2連率"))
        parts = []
        if grade:
            parts.append(grade)
        if zwr is not None:
            parts.append("全国勝率{:.2f}".format(zwr))
        if t2 is not None:
            parts.append("当地2連率{:.2f}%".format(t2))
        out.append({
            "toban": tb,
            "name": (r.get("氏名") or "").strip(),
            "branch": ken,
            "summary": "・".join(parts),
        })
    return out


def load_style_history(jcd, before_hd8):
    """同場の直近3本の記事JSONのstyleTypeを新しい順。3本未満はある分・ゼロは空配列。
    before_hd8（掲載日）より前の記事のみ対象＝当日の自記事や未来分は除外（自己参照防止）。"""
    if not os.path.isdir(ARTICLES_DIR):
        return []
    files = []
    for fn in os.listdir(ARTICLES_DIR):
        m = re.match(r"(\d{8})-" + re.escape(jcd) + r"\.json$", fn)
        if m and m.group(1) < before_hd8:
            files.append((m.group(1), fn))
    files.sort(reverse=True)
    out = []
    for _d, fn in files[:3]:
        art = load_json(os.path.join(ARTICLES_DIR, fn)) or {}
        out.append(art.get("styleType"))
    return out


def load_prev_article(jcd, prev_date8):
    path = os.path.join(ARTICLES_DIR, "{}-{}.json".format(prev_date8, jcd))
    art = load_json(path)
    if not art:
        return {"exists": False}
    return {
        "exists": True,
        "title": art.get("title"),
        "body": art.get("body"),
        "styleType": art.get("styleType"),
    }


# ---------------------------------------------------------------------------
# pointrank（新規・optional）
# ---------------------------------------------------------------------------
def _z2h(s):
    return (s or "").translate(str.maketrans("０１２３４５６７８９．－",
                                             "0123456789.-"))


def fetch_pointrank(jcd, hd8, venue_name, series, as_of_day):
    """得点率一覧を取得・検証して返す。取得不可/汚染/自己検知不一致はNone（scoreRank=null）。
    §3の全バリデーションを実装。"""
    if not _HAS_NET:
        return None
    url = "https://www.boatrace.jp/owpc/pc/race/pointrank?jcd={}&hd={}".format(jcd, hd8)
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQ_TIMEOUT)
        if r.status_code != 200:
            return None
        html = r.text
    except Exception:
        return None

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # 汚染検証(a)(b)(c): 場名・節名・「N日目終了時点」
    if venue_name and venue_name not in text:
        return None
    if series and series not in text:
        return None
    m = re.search(r"([0-9０-９]+)\s*日目\s*終了時点", text)
    if not m:
        return None
    page_asof = int(_z2h(m.group(1)))
    if as_of_day is not None and page_asof != as_of_day:
        return None  # 別日の古いキャッシュ返却 → 破棄

    # 行パース: 得点率一覧テーブル。各行= 順位/登番/氏名/級別/走数由来の着列/得点/減点/得点率
    rows = _parse_pointrank_rows(soup)
    if not rows:
        return None

    # 自己検知: (得点-減点)/走数 ≒ 得点率（許容差0.005）。1件でも不一致なら全破棄(§3.1-3)。
    # _recompute は実HTMLのDOM列（得点/減点欄）特定が未確定のため現状 None＝未実行。
    # checked==0（未実行）のときは self_check.passed=False となり、書き込みは解禁されない。
    checked = 0
    for row in rows:
        recomputed = row.get("_recompute")
        rate = row.get("rate")
        if recomputed is None or rate is None:
            continue
        checked += 1
        if abs(recomputed - rate) > 0.005:
            return None
    self_check = {"ran": checked > 0, "passed": checked > 0, "checked": checked}

    top = [{"rank": r["rank"], "toban": r["toban"], "name": r["name"],
            "yomi": None, "grade": r.get("grade"), "rate": r.get("rate"),
            "series_finishes": r.get("series_finishes")} for r in rows]

    border = _compute_border(rows, series)
    return {"asOfDay": as_of_day, "border": border, "top": top,
            "_selfCheck": self_check}


def _parse_pointrank_rows(soup):
    """得点率一覧テーブルを行dictのリストへ。構造不一致は空リスト。
    走数=着列の空白除去後の文字数（転・Ｆ・Ｌ・欠・失も1走 §3.1）。"""
    rows = []
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        cells = [td.get_text(" ", strip=True) for td in tds]
        rank = _z2h(cells[0]).strip()
        if not re.match(r"^\d+$", rank):
            continue
        toban = None
        for c in cells:
            mm = re.search(r"\b(\d{4})\b", _z2h(c))
            if mm:
                toban = mm.group(1)
                break
        if not toban:
            continue
        grade_m = re.search(r"(A1|A2|B1|B2)", " ".join(cells))
        rate = None
        for c in reversed(cells):
            cv = _z2h(c).strip()
            fm = re.match(r"^-?\d+\.\d+$", cv)
            if fm:
                rate = float(cv)
                break
        # 着列（節内着順文字列）: 全角数字や転/Ｆ等が並ぶセルを推定
        series_fin = ""
        for c in cells:
            cc = c.replace(" ", "")
            if re.search(r"[０-９]", cc) and not re.search(r"\.", cc) and len(cc) <= 8:
                series_fin = cc
                break
        # 走数=着列文字数（特殊行も1走）
        runs = len(series_fin) if series_fin else None
        # 得点・減点の推定（自己検知用）。数値2つ（得点, 減点）を拾えたら再計算。
        nums = []
        for c in cells:
            for tok in re.findall(r"-?\d+\.?\d*", _z2h(c)):
                nums.append(tok)
        recompute = None
        # 明示的な得点/減点欄を機械的に特定できない場合はNone（自己検知スキップ）
        name = ""
        for c in cells:
            cv = c.strip()
            if re.search(r"[一-龥ぁ-んァ-ンー]", cv) and not re.search(r"A1|A2|B1|B2", cv):
                name = re.sub(r"\s+", "", cv)
                break
        rows.append({
            "rank": int(rank), "toban": toban, "name": name,
            "grade": grade_m.group(1) if grade_m else None,
            "rate": rate, "series_finishes": series_fin or None,
            "runs": runs, "_recompute": recompute,
        })
    return rows


def _compute_border(rows, series):
    """規定順位=準優3本＝18位固定。18位の得点率をボーダー（同点タイはその値）。
    SG等の特殊方式はborder=null（§3.2）。"""
    if series and re.search(r"ＳＧ|SG", series):
        return None
    line = 18
    at = [r for r in rows if r["rank"] == line and r.get("rate") is not None]
    if not at:
        return {"rankLine": line, "rate": None, "tieCount": 0}
    rate = at[0]["rate"]
    tie = sum(1 for r in rows if r.get("rate") == rate)
    return {"rankLine": line, "rate": rate, "tieCount": tie}


# ---------------------------------------------------------------------------
# 補完マージ（§4.1: nullフィールドの補完のみ・非null不変）
# ---------------------------------------------------------------------------
def null_merge(old, new):
    """oldを基準に、oldがnull/未設定の箇所だけnewで補完。非null値は不変。
    dictは再帰、それ以外（list含む）はleaf扱い。"""
    if old is None:
        return new
    if isinstance(old, dict) and isinstance(new, dict):
        out = dict(old)
        for k, nv in new.items():
            if k not in out or out[k] is None:
                out[k] = nv
            else:
                out[k] = null_merge(out[k], nv)
        return out
    return old  # 非null leaf は不変


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def build_venue(jcd, venue_rows, results_map, vstats, kimarite_map, profile,
                e30map, csv_hd8, results_date8):
    row0 = venue_rows[0]
    hd8 = (row0.get("開催日") or "").strip()
    series = (row0.get("節名") or "").strip() or None
    day_num, day_label = day_num_and_label(venue_rows)
    as_of_day = (day_num - 1) if day_num else None

    results_venue = results_map.get(jcd, [])
    results_block = build_results_block(results_venue)
    vstat = vstats.get(jcd)

    # scoreRank: shadow mode（判断①）。自己検知passed かつ 書き込み解禁時のみJSONへ。
    # それ以外は取得できてもログのみで scoreRank=null（focus抽出でも使わない）。
    score_raw = fetch_pointrank(jcd, hd8, VENUES.get(jcd, jcd), series, as_of_day)
    score_rank = None
    if score_raw is not None:
        sc = score_raw.get("_selfCheck", {})
        if SCORERANK_WRITE and sc.get("passed"):
            score_rank = {k: v for k, v in score_raw.items() if not k.startswith("_")}
        else:
            print("[shadow] scoreRank {} {}: 取得成功だが書き込み保留 "
                  "(selfCheck={}, WRITE={}). rows={}".format(
                      jcd, VENUES.get(jcd, jcd), sc, SCORERANK_WRITE,
                      len(score_raw.get("top", []))))

    motor2avg = motor_avg(venue_rows)
    focus_tobans = pick_focus_tobans(jcd, venue_rows, score_rank,
                                      results_venue, csv_hd8, results_date8)
    row_by_toban = {str(r.get("登録番号", "")).strip(): r for r in venue_rows}
    focus = []
    for tb in focus_tobans:
        r = row_by_toban.get(tb)
        if r:
            focus.append(build_focus_racer(r, jcd, kimarite_map, profile, motor2avg))

    prev_date8 = (parse_date8(hd8) - datetime.timedelta(days=1)).strftime("%Y%m%d") \
        if hd8 else results_date8

    return {
        "jcd": jcd,
        "venue": VENUES.get(jcd, row0.get("場名")),
        "series": series,
        "grade": None,  # 出走表に級(SG/G1/G2/G3)欄が無く確定不能のためnull（捏造防止）
        "dayNum": day_num,
        "dayLabel": day_label or None,
        "seriesNote": series_note_for(series),
        "results": results_block,
        "resultsSummary": build_results_summary(results_block, vstat),
        "reference": build_reference(jcd, vstat, results_date8, as_of_day, hd8, e30map),
        "scoreRank": score_rank,
        "focusRacers": focus,
        "localRacers": build_local_racers(jcd, venue_rows),
        "styleHistory": load_style_history(jcd, hd8),
        "prevArticle": load_prev_article(jcd, prev_date8),
    }


def main():
    allow_daytime = os.environ.get("BKS_ALLOW_DAYTIME") == "1"
    now = jst_now()
    # 夜間帯 = JST22:00〜翌08:59。updateResults の schedule 実発火は遅延が常態で
    # 03〜06時台に流れ込むため、当日レース開始(〜10:30)前を許容範囲としてhour<9まで広げる。
    # 日中(09〜21時)の再実行は従来どおり排除（§4.1/§4.3）。
    if not allow_daytime and not (now.hour >= 22 or now.hour < 9):
        raise SystemExit(
            "夜間帯（JST22時以降〜翌9時）専用。日中の再実行は禁止（§4.1/§4.3）。"
            "ローカル検証時は BKS_ALLOW_DAYTIME=1 で明示的に上書き。")

    rows, by_jcd = load_racers()
    if not rows:
        raise SystemExit("出走表CSVが空。")

    # 日付の正 = 出走表CSVの開催日（掲載日）。system日付から導出しない（§0）。
    hd_counts = {}
    for r in rows:
        hd_counts[(r.get("開催日") or "").strip()] = hd_counts.get(
            (r.get("開催日") or "").strip(), 0) + 1
    csv_hd8 = max(hd_counts.items(), key=lambda kv: kv[1])[0]
    date_dash = ymd_dash(csv_hd8)                     # 掲載日
    results_date8 = (parse_date8(csv_hd8) - datetime.timedelta(days=1)).strftime("%Y%m%d")

    results_data, results_path = load_results(results_date8)
    results_map = results_by_jcd(results_data)
    vstats = load_verify_venue_stats(results_date8)
    kimarite_map = load_kimarite()
    profile = load_profile()
    e30map = load_e30()

    venues = []
    for jcd in sorted(by_jcd.keys()):
        venue_rows = [r for r in by_jcd[jcd] if (r.get("開催日") or "").strip() == csv_hd8]
        if not venue_rows:
            continue
        venues.append(build_venue(jcd, venue_rows, results_map, vstats, kimarite_map,
                                   profile, e30map, csv_hd8, results_date8))

    doc = {"date": date_dash, "venues": venues}

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, csv_hd8 + ".json")

    existing = load_json(out_path)
    # サイレント欠番の可視化: 実行時にCSV開催日・導出date・既存sourceの有無を必ずログ。
    print("CSV開催日={} 導出date(掲載日)={} results(前日)={} 既存source={}".format(
        csv_hd8, date_dash, results_date8, "有" if existing is not None else "無"))
    if existing is not None:
        # 導出date（=掲載日）のファイルが既に存在＝CSVが翌日カードへ未更新。
        # 新しい日付の素材は生成されず、既存への null補完のみ（非null不変）に留まる。
        print("CSV未更新のため新規生成なし（既存 {}.json への null補完のみ・非null不変）"
              .format(csv_hd8))
        # 再実行=nullフィールドの補完のみ。venue単位でjcd照合しマージ。
        old_by_jcd = {v.get("jcd"): v for v in existing.get("venues", [])}
        merged = []
        for v in venues:
            ov = old_by_jcd.get(v["jcd"])
            merged.append(null_merge(ov, v) if ov else v)
        # 既存にしか無いvenueも保持
        seen = {v["jcd"] for v in venues}
        for ov in existing.get("venues", []):
            if ov.get("jcd") not in seen:
                merged.append(ov)
        doc = {"date": existing.get("date", date_dash), "venues": merged,
               "supplementedAt": now.isoformat()}

    with io.open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    print("wrote {} ({} venues)".format(out_path, len(doc["venues"])))
    print("date(掲載日)={} results(前日)={} results_file={}".format(
        date_dash, results_date8, results_path or "なし"))


if __name__ == "__main__":
    main()
