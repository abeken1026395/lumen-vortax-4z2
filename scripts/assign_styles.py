#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assign_styles.py — 観戦記 執筆前の「型・主役」決定化（headless実行の品質担保）

source/YYYYMMDD.json を読み、各場の styleType（styleHistory直近3回避・初日=展望）と
主役候補（isLocalのfocus）、killer材料を機械決定する。文章はモデルが書くが、
型選択・styleHistory回避・主役分散という“ブレやすい構造判断”はここで規約準拠に固定する。

出力：stdout に JSON（--out でファイルにも書ける）。標準ライブラリのみ。
使い方:
  python scripts/assign_styles.py docs/data/kansenki/source/20260712.json
  python scripts/assign_styles.py docs/data/kansenki/source/20260712.json --out /tmp/assign.json
"""
import sys
import os
import io
import json
import re

CANDIDATES = ["人物型", "番狂わせ型", "データ型", "群像型", "水面型"]  # 展望型は初日専用で別扱い
NARROW = {"戸田", "平和島", "江戸川"}
SASHI = {"常滑", "蒲郡", "児島", "鳴門", "丸亀"}
# 群像に寄りやすい節キーワード（対抗戦・男女W・女子・全国大会）
GUNZO_KW = ["男女", "Ｗ優勝", "W優勝", "対抗", "甲子園", "マスターズ", "レジェンド",
            "ヴィーナス", "レディース", "クイーンズ"]

ARTICLES_DIR = "docs/data/kansenki/articles"


def load(path):
    with io.open(path, encoding="utf-8") as f:
        return json.load(f)


def prev_date8(ymd8):
    y, m, d = int(ymd8[:4]), int(ymd8[4:6]), int(ymd8[6:8])
    import datetime
    return (datetime.date(y, m, d) - datetime.timedelta(days=1)).strftime("%Y%m%d")


def prev_day_protagonists(date8):
    """前日記事の racersMentioned toban 集合（連日主役被り回避に使う）。"""
    out = set()
    pd = prev_date8(date8)
    if not os.path.isdir(ARTICLES_DIR):
        return out
    for fn in os.listdir(ARTICLES_DIR):
        m = re.match(r"^%s-(\d{2})\.json$" % pd, fn)
        if not m:
            continue
        try:
            a = load(os.path.join(ARTICLES_DIR, fn))
        except Exception:
            continue
        for rm in a.get("racersMentioned", []) or []:
            if rm.get("toban"):
                out.add(str(rm["toban"]))
    return out


def existing_article(jcd, date8):
    """同日の既執筆記事（前夜便で書いた場）を読む。styleType と主役toban を返す。無ければ None。
    ＝場単位執筆で「既に書いた場」を型分布に数え、再割当せず不変に保つための参照。"""
    if not date8 or not jcd:
        return None
    p = os.path.join(ARTICLES_DIR, "%s-%s.json" % (date8, jcd))
    if not os.path.exists(p):
        return None
    try:
        a = load(p)
    except Exception:
        return None
    rm = a.get("racersMentioned") or []
    prot = None
    if rm and rm[0].get("toban"):
        prot = {"toban": str(rm[0]["toban"]),
                "name": (rm[0].get("name") or "").replace("　", "")}
    return {"styleType": a.get("styleType"), "protagonist": prot}


def _daysback(ymd8, n):
    import datetime
    y, m, d = int(ymd8[:4]), int(ymd8[4:6]), int(ymd8[6:8])
    return (datetime.date(y, m, d) - datetime.timedelta(days=n)).strftime("%Y%m%d")


def venue_protag_history(jcd, date8, back=2):
    """同一場の過去 back 日ぶんの主役 toban（各記事の racersMentioned[0]）を新しい順で返す。"""
    out = []
    for k in range(1, back + 1):
        pd = _daysback(date8, k)
        p = os.path.join(ARTICLES_DIR, "%s-%s.json" % (pd, jcd))
        if not os.path.exists(p):
            out.append(None)
            continue
        try:
            a = load(p)
            rm = a.get("racersMentioned") or []
            out.append(str(rm[0]["toban"]) if rm and rm[0].get("toban") else None)
        except Exception:
            out.append(None)
    return out


def _max_manshu(v):
    races = (v.get("resultsSummary") or {}).get("manshuRaces") or []
    if not races:
        return None
    return max(races, key=lambda r: r.get("payout", 0))


def _trail_wins(focus):
    return [t for t in (focus.get("finishTrail") or []) if t.get("finish") == 1]


def _local_aclass(v):
    n = 0
    for l in v.get("localRacers", []) or []:
        s = l.get("summary") or ""
        if s.startswith("A1") or s.startswith("A2"):
            n += 1
    return n


def score_types(v):
    """許可された型ごとのスコア（材料の強さ）。styleHistory回避・初日=展望は呼び出し側で適用。"""
    ref = v.get("reference") or {}
    vy = ref.get("venueYearStats") or {}
    e30 = ref.get("e30") or {}
    sv = ref.get("setsuVsYear") or {}
    rs = v.get("resultsSummary") or {}
    manshu = rs.get("manshuCount") or 0
    top = _max_manshu(v)
    top_pay = (top or {}).get("payout", 0)
    series = v.get("series") or ""
    focus = (v.get("focusRacers") or [{}])[0]
    kt = focus.get("kimariteType") or {}

    sc = {}
    # 番狂わせ型
    s = 0
    if manshu > 0:
        s = 10 + manshu * 4
        if top_pay >= 20000:
            s += 25
        if top_pay >= 100000:
            s += 40
    sc["番狂わせ型"] = s
    # データ型
    s = 14
    if sv.get("setsuRaces"):
        s += 5
    m2 = focus.get("motor2renSetsu")
    m2a = focus.get("motor2renSetsuAvg")
    if m2 is not None and m2a is not None and abs(m2 - m2a) >= 15:
        s += 22  # 機力の乖離＝データの柱
    if (vy.get("manRate") or 0) >= 19 or (vy.get("katameRate") or 0) >= 57:
        s += 6
    if e30.get("applies"):
        s += 3
    sc["データ型"] = s
    # 人物型
    wins = len(_trail_wins(focus))
    sc["人物型"] = 8 + wins * 11 if focus else 0
    # 群像型
    s = _local_aclass(v) * 8
    if any(k in series for k in GUNZO_KW):
        s += 14
    sc["群像型"] = s
    # 水面型
    s = 12
    if v.get("venue") in NARROW or v.get("venue") in SASHI:
        s += 10
    kinds = {r.get("kimarite") for r in (v.get("results") or []) if r.get("kimarite")}
    if len(kinds) >= 4:
        s += 8
    sc["水面型"] = s
    return sc


def _protag_pool(v):
    """主役候補プール（新しい軸から）: isLocalのfocus → 他のfocus → localRacersのA級。"""
    pool = []
    seen = set()
    focus = v.get("focusRacers") or []
    for f in [x for x in focus if x.get("isLocal")] + [x for x in focus if not x.get("isLocal")]:
        tb = str(f.get("toban") or "")
        if tb and tb not in seen:
            seen.add(tb)
            g = f.get("grade")
            pool.append({"toban": tb, "name": (f.get("name") or "").replace("　", ""),
                         "grade": g, "branch": f.get("branch")})
    for l in v.get("localRacers") or []:
        tb = str(l.get("toban") or "")
        if not tb or tb in seen:
            continue
        s = l.get("summary") or ""
        g = s[:2] if s[:2] in ("A1", "A2", "B1", "B2") else None
        seen.add(tb)
        pool.append({"toban": tb, "name": (l.get("name") or "").replace("　", ""),
                     "grade": g, "branch": l.get("branch")})
    # A級を前に寄せる（弱い番組でも代替を出しやすく）
    pool.sort(key=lambda p: 0 if (p.get("grade") in ("A1", "A2")) else 1)
    return pool


def pick_protagonist(v, exclude=None):
    exclude = set(exclude or ())
    for p in _protag_pool(v):
        if p["toban"] not in exclude:
            return p
    return None


def killer_hints(v):
    ref = v.get("reference") or {}
    vy = ref.get("venueYearStats") or {}
    sv = ref.get("setsuVsYear") or {}
    e30 = ref.get("e30") or {}
    top = _max_manshu(v)
    focus = (v.get("focusRacers") or [{}])[0]
    return {
        "manshuCount": (v.get("resultsSummary") or {}).get("manshuCount"),
        "manshuTop": ({"rno": top["rno"], "combo": top["combo"], "payout": top["payout"]}
                      if top else None),
        "venueYear": {"manRate": vy.get("manRate"), "haranRate": vy.get("haranRate"),
                      "katameRate": vy.get("katameRate"), "n": vy.get("n")},
        "setsu": {"manshu": sv.get("setsuManshu"), "races": sv.get("setsuRaces")},
        "e30": {"applies": e30.get("applies"), "since": e30.get("since")},
        "machine": {"no": focus.get("motorNo"), "setsu": focus.get("motor2renSetsu"),
                    "setsuAvg": focus.get("motor2renSetsuAvg")},
        "protagonistWins": _trail_wins(focus),
    }


def assign(src):
    date8 = (src.get("date") or "").replace("-", "")
    prev_prot = prev_day_protagonists(date8) if date8 else set()
    venues = src.get("venues", [])
    # 0パス目: 既執筆場（前夜便で書いた場）をロック。型を分布に数え、再割当しない。
    result = [None] * len(venues)
    used = {}
    locked_idx = set()
    for i, v in enumerate(venues):
        ex = existing_article(v.get("jcd"), date8) if date8 else None
        if not ex:
            continue
        locked_idx.add(i)
        st = ex.get("styleType")
        if st:
            used[st] = used.get(st, 0) + 1  # 既執筆の型を分布に先行計上（回収便の偏り回避）
        result[i] = {
            "jcd": v.get("jcd"), "venue": v.get("venue"),
            "styleType": st, "dayNum": v.get("dayNum"), "dayLabel": v.get("dayLabel"),
            "protagonist": ex.get("protagonist"),
            "locked": True,  # 既に執筆済み＝この計画では書かない・変えない
            "hasTodayProgram": bool(v.get("todayProgram")),
        }
    # 1パス目: 未執筆場のみ 許可型とスコアを出す
    plan = []
    for i, v in enumerate(venues):
        if i in locked_idx:
            continue
        day1 = (v.get("dayNum") == 1)
        forbidden = set((v.get("styleHistory") or [])[:3])
        sc = score_types(v)
        if day1:
            allowed = ["展望型"]
            sc = {"展望型": 999}
        else:
            allowed = [t for t in CANDIDATES if t not in forbidden]
            if not allowed:  # 万一全滅なら規約の例外（killerに明記させる）
                allowed = CANDIDATES[:]
        plan.append({"i": i, "v": v, "allowed": allowed, "score": sc, "day1": day1})
    # 2パス目: 分散を加味した貪欲割当（スコア降順に確定、使用回数ペナルティ）
    # 確定順は「最高スコアと次点の差が大きい＝迷いが少ない場」から
    order = sorted(range(len(plan)),
                   key=lambda i: -(max(plan[i]["score"].get(t, 0) for t in plan[i]["allowed"])))
    for k in order:
        p = plan[k]
        best_t, best_val = None, -1e9
        for t in p["allowed"]:
            val = p["score"].get(t, 0) - used.get(t, 0) * 12  # 使用回数ペナルティで分散（実測で均等化）
            if val > best_val:
                best_val, best_t = val, t
        used[best_t] = used.get(best_t, 0) + 1
        v = p["v"]
        jcd = v.get("jcd")
        primary = pick_protagonist(v)
        # 追補: 同一場の連日主役は2日連続まで可・3日連続は不可。
        # 過去2日が同一tobanで、今回もそれが筆頭なら代替主役を確定出力（居なければ切り口変更フラグ）。
        hist = venue_protag_history(jcd, date8, 2) if date8 else [None, None]
        forced_alt = False
        must_change = False
        prot = primary
        if primary and len([h for h in hist if h]) >= 2 and hist[0] == hist[1] == primary["toban"]:
            alt = pick_protagonist(v, exclude={primary["toban"]})
            if alt:
                prot, forced_alt = alt, True
            else:
                must_change = True  # 代替不在（弱small番組等）＝被り継続を許すが切り口を変えさせる
        prot_repeat = bool(prot and hist and prot["toban"] == hist[0])
        result[p["i"]] = {
            "jcd": jcd, "venue": v.get("venue"),
            "styleType": best_t, "dayNum": v.get("dayNum"), "dayLabel": v.get("dayLabel"),
            "protagonist": prot,
            "protagonistRepeatsPrevDay": prot_repeat,
            "protagonistForcedAlternate": forced_alt,   # 3日連続回避で代替に差し替えた
            "mustChangeAngle": must_change,              # 代替不在＝被り継続だが切り口を変える
            "protagonistHistory": hist,                  # [前日, 前々日] の主役toban
            "styleHistoryTop3": (v.get("styleHistory") or [])[:3],
            "hasTodayProgram": bool(v.get("todayProgram")),
            "killerHints": killer_hints(v),
        }
    return {"date": src.get("date"), "assignments": result,
            "typeDistribution": used}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = None
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    if not args:
        print("usage: assign_styles.py source/YYYYMMDD.json [--out path]", file=sys.stderr)
        sys.exit(2)
    res = assign(load(args[0]))
    txt = json.dumps(res, ensure_ascii=False, indent=1)
    if out:
        with io.open(out, "w", encoding="utf-8") as f:
            f.write(txt)
    print(txt)


if __name__ == "__main__":
    main()
