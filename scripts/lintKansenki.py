#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lintKansenki.py — 観戦記の事実照合・語彙・禁止表現・構造リント

記事(articles/YYYYMMDD-{jcd}.json)の全数値が同日 source(source/YYYYMMDD.json)の
対応venueに存在する（or 素材2値からの四則演算で到達可能）かを機械照合し、
ハルシネーションを人力査読から機械検査に移す。あわせて他競技語彙・禁止表現・構造を検査。

使い方:
  python scripts/lintKansenki.py                     # 全 articles/*.json を内容検査
  python scripts/lintKansenki.py docs/data/kansenki/articles/20260710-02.json
  python scripts/lintKansenki.py --coverage 20260711 # 網羅性: sourceの全場に記事があるか
  python scripts/lintKansenki.py --coverage          # 全source日付の網羅性を一括検査
1件でもFAILなら非ゼロ終了（執筆フロー最終段で必須実行し、合格までcommitしない）。
網羅性チェックは source(N場)と記事(M場)の乖離＝欠場を機械検知する（07-11のカード欠落の
再発防止。sourceはcronで場が増えて再生成されうるが記事は自動追随しないため）。

方針: 「数値と語彙の網」に徹する。小整数（レース番号/コース/着/日目/本数等の構造値）は
過剰検知を避けるため広めに許容。率(X.XX/XX.XX)・円・組番など捏造ベクトルを厳格照合。
"""

import io
import os
import re
import sys
import json
import glob

ART_DIR = "docs/data/kansenki/articles"
SRC_DIR = "docs/data/kansenki/source"

# --- 検査2: 他競技・他ギャンブル語彙（競艇語=舟券/万舟/節/水面）---
OTHER_SPORT = ["馬券", "万馬券", "車券", "レコード勝ち", "レコード", "単勝", "枠連", "馬連", "馬単"]
# ゴールは競艇でも使い得るため除外（誤検知回避）。

# --- 検査3: 禁止表現 ---
NAISHIN = ["勝ちたい", "負けられない", "譲れない", "気合", "意地", "焦り", "自信",
           "慎重になる", "慎重に行く", "狙いを定め", "悔し", "執念", "闘志"]
SHIME_KANYOKU = ["答えは水面の上に", "目が離せない", "注目したい", "期待がかか",
                 "どんなドラマ", "勝負の行方"]
BANNED_HIYU = ["目盛り", "物差し"]
AORI = ["激アツ", "大チャンス", "狙い目", "妙味"]


def load(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 素材からの許容数値集合
# ---------------------------------------------------------------------------
def _fmt(x):
    """floatを比較キー化（6.8と6.80を同一視）。"""
    return round(float(x), 3)


def collect_source_numbers(venue):
    """venue（dict）を再帰走査し、許容数値集合と組番集合を作る。"""
    floats = set()   # 比較用に丸めたfloat
    combos = set()   # 'X-X-X'
    ints = set()     # 整数（大きめの実数：配当・n・登番等）

    def walk(o):
        if isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            floats.add(_fmt(o))
            if float(o).is_integer():
                ints.add(int(o))
        elif isinstance(o, str):
            # 組番
            for m in re.findall(r"\d+-\d+-\d+", o):
                combos.add(m)
            # 文字列中の数値（localRacers summary の "6.80"/"49.33" 等）
            for m in re.findall(r"\d+\.\d+", o):
                floats.add(_fmt(m))
            for m in re.findall(r"\d+", o):
                ints.add(int(m))

    walk(venue)
    # 構造由来: レース数（results長）も許容
    try:
        ints.add(len(venue.get("results", []) or []))
    except Exception:
        pass
    return floats, ints, combos


def derive_pct(v, ints):
    """整数%が素材の整数2値の比率(a/b*100)で到達可能か。
    例: 1/11→9%。任意の積・商は許さない（偽陰性防止のため比率のみ）。"""
    for a in ints:
        for b in ints:
            if b > 0 and a <= b and round(100.0 * a / b) == v:
                return True
    return False


def derive_intsum(v, ints):
    """整数が素材整数2値の和・差で到達可能か（例: 8+4=12）。"""
    for a in ints:
        for b in ints:
            if a + b == v or a - b == v:
                return True
    return False


# ---------------------------------------------------------------------------
# 検査1: 数値照合
# ---------------------------------------------------------------------------
def check_numbers(body, venue):
    floats, ints, combos = collect_source_numbers(venue)
    fails = []

    # (1) 組番 X-X-X
    for m in re.findall(r"\d+-\d+-\d+", body):
        if m not in combos:
            fails.append(("組番", m))

    # (2) 円 配当（"13170円" / "4万円"）: 素材の配当(int)に直値一致。
    for m in re.findall(r"(\d+)\s*万円", body):
        val = int(m) * 10000
        # "4万円超" 等の概数は素材配当を万位で丸めた表現→[val, val+9999]に実配当があれば許容
        near = any(val <= p <= val + 9999 for p in ints)
        if val not in ints and not near:
            fails.append(("円(万)", m + "万円"))
    for m in re.findall(r"(?<!万)(\d{3,7})\s*円", body):
        val = int(m)
        if val not in ints:
            fails.append(("円", m + "円"))

    # (3) 小数（率/ST）: X.XX, XX.XX, .XX ── 素材の直値のみ許容（率/STは全て素材に直在するため
    #     任意の四則派生は認めない。これにより捏造率を確実に捕捉する）。
    for m in re.findall(r"(?<![\d-])(\d+\.\d+|\.\d+)", body):
        v = float(m if not m.startswith(".") else "0" + m)
        if _fmt(v) not in floats:
            fails.append(("小数", m))

    # (4) 整数%（"9%"等）: 素材直値 or 素材整数2値の比率(a/b*100)で許容。
    for m in re.findall(r"(?<![\d.])(\d+)\s*%", body):
        v = int(m)
        if _fmt(float(v)) in floats or v in ints or derive_pct(v, ints):
            continue
        fails.append(("整数%", m + "%"))

    # 大整数（>=100）: 素材直値 or 整数2値の和差。年間n(2171等)は ints に直在。
    for m in re.findall(r"(?<![\d.\-])(\d{3,})(?!\s*円)(?![\d.\-%])", body):
        v = int(m)
        if v in ints or derive_intsum(v, ints):
            continue
        fails.append(("大整数", m))

    return fails


def check_vocab(body):
    return [("他競技語", w) for w in OTHER_SPORT if w in body]


def check_banned(body):
    out = []
    out += [("内心語", w) for w in NAISHIN if w in body]
    out += [("締め常套句", w) for w in SHIME_KANYOKU if w in body]
    out += [("禁止比喩", w) for w in BANNED_HIYU if w in body]
    out += [("煽り", w) for w in AORI if w in body]
    return out


def check_structure(art, venue):
    fails = []
    # racersMentioned の toban が source に存在するか
    src_tobans = set()
    for f in venue.get("focusRacers", []) or []:
        if f.get("toban"):
            src_tobans.add(str(f["toban"]))
    for l in venue.get("localRacers", []) or []:
        if l.get("toban"):
            src_tobans.add(str(l["toban"]))
    sr = venue.get("scoreRank")
    if sr:
        for t in sr.get("top", []) or []:
            if t.get("toban"):
                src_tobans.add(str(t["toban"]))
    for rm in art.get("racersMentioned", []) or []:
        tb = str(rm.get("toban", ""))
        if tb and tb not in src_tobans:
            fails.append(("racer未在", "%s(%s)" % (rm.get("name"), tb)))

    # styleType が styleHistory直近3と重複していないか（初日=展望型は例外）
    st = art.get("styleType")
    hist = venue.get("styleHistory", []) or []
    day1 = (venue.get("dayNum") == 1)
    if st in hist[:3] and not (day1 and st == "展望型"):
        fails.append(("型連続", "%s ∈ styleHistory%s" % (st, hist[:3])))
    return fails


def lint_article(art_path):
    fn = os.path.basename(art_path)
    m = re.match(r"(\d{8})-(\d{2})\.json$", fn)
    if not m:
        return None
    ymd, jcd = m.group(1), m.group(2)
    art = load(art_path)
    src_path = os.path.join(SRC_DIR, ymd + ".json")
    if not os.path.exists(src_path):
        return (fn, [("素材欠", "source/%s.json なし" % ymd)])
    src = load(src_path)
    venue = next((v for v in src.get("venues", []) if v.get("jcd") == jcd), None)
    if venue is None:
        return (fn, [("素材欠", "source に jcd=%s なし" % jcd)])
    body = art.get("body", "")
    fails = []
    fails += check_numbers(body, venue)
    fails += check_vocab(body)
    fails += check_banned(body)
    fails += check_structure(art, venue)
    return (fn, fails)


def check_coverage(ymd):
    """網羅性チェック: source/YYYYMMDD.json の全venueに記事があるか。
    源泉(source)は cron で場が増えて再生成されうる（不完全CSV時点の暫定sourceが後で
    完全CSVに差し替わる）。記事は人が書く自動追随しない生成物なので、source(N場)と
    記事(M場)が乖離するとカードに穴が開く。それを機械検知する（欠場=FAIL）。"""
    src_path = os.path.join(SRC_DIR, ymd + ".json")
    if not os.path.exists(src_path):
        return [("素材欠", "source/%s.json なし" % ymd)]
    src = load(src_path)
    venues = src.get("venues", []) or []
    present, miss = [], []
    for v in venues:
        jcd = v.get("jcd")
        name = v.get("venue", "")
        if os.path.exists(os.path.join(ART_DIR, "%s-%s.json" % (ymd, jcd))):
            present.append(jcd)
        else:
            miss.append(("記事欠", "%s-%s(%s) の記事が無い" % (ymd, jcd, name)))
    # その日の記事が1本も無ければ「観戦記非運用日」としてスキップ（欠場検知の対象外）。
    # 「一部書いたのに一部欠けている」乖離だけを捕える設計。0本は執筆自体の未着手で別問題。
    if not present:
        return None
    return miss


def run_coverage(ymds):
    """指定日（複数可）の網羅性チェック。1日でも欠場があれば非ゼロ終了。
    記事0本の日はSKIP（非運用日）。日付省略時は全source日付を対象にする。"""
    if not ymds:
        ymds = sorted(re.match(r"(\d{8})\.json$", os.path.basename(p)).group(1)
                      for p in glob.glob(os.path.join(SRC_DIR, "*.json"))
                      if re.match(r"\d{8}\.json$", os.path.basename(p)))
    total_fail = checked = 0
    for ymd in ymds:
        res = check_coverage(ymd)
        if res is None:
            print("SKIP 網羅 %s（当日記事0本＝観戦記非運用日）" % ymd)
            continue
        checked += 1
        if res:
            total_fail += 1
            print("FAIL 網羅 %s" % ymd)
            for cat, tok in res:
                print("   [%s] %s" % (cat, tok))
        else:
            n = len(load(os.path.join(SRC_DIR, ymd + ".json")).get("venues", []) or [])
            print("PASS 網羅 %s（source全%d場に記事あり）" % (ymd, n))
    print("---")
    print("網羅結果: 検査%d日 / FAIL %d 日" % (checked, total_fail))
    sys.exit(1 if total_fail else 0)


def main():
    args = sys.argv[1:]
    if args and args[0] == "--coverage":
        run_coverage(args[1:])
        return
    if args:
        paths = args
    else:
        paths = sorted(glob.glob(os.path.join(ART_DIR, "*.json")))
    total_fail = 0
    for p in paths:
        r = lint_article(p)
        if r is None:
            continue
        fn, fails = r
        if fails:
            total_fail += 1
            print("FAIL %s" % fn)
            for cat, tok in fails:
                print("   [%s] %s" % (cat, tok))
        else:
            print("PASS %s" % fn)
    print("---")
    print("結果: %d/%d PASS / FAIL %d" % (len(paths) - total_fail, len(paths), total_fail))
    sys.exit(1 if total_fail else 0)


if __name__ == "__main__":
    main()
