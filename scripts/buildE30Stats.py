#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
buildE30Stats.py
E30該当期間のレースに絞り、選手(登番)×進入コース別の「生の成績」を
出典・N数・集計期間つきで e30PlayerStats.json に出力する。

方針（サイト哲学準拠）:
  ・生データのみ。「E30で伸びる」等の推測・評価・確率・買い目は一切出さない。
  ・出典 / 集計期間 / N走 を必ず併記。母数が小さい選手が多数出る前提。

該当判定:
  e30Schedule.json（確定場のみ列挙）の startDate(YYYY-MM-DD)以降 × 該当場のみ。

データ源:
  当初想定は mbrace 競走成績 kYYMMDD.lzh（SHIFT_JIS・lhafile解凍）だが、
  mbrace は当環境(sandbox)からも GitHub Actions からも IP 遮断で取得不可
  （CLAUDE.md 既知問題(1)）。代替として buildResults.py と同じ
  BoatraceOpenAPI/results ミラー（GitHub配信）を使う。決まり手(race_technique_number)・
  進入コース(racer_course_number)・ST(racer_start_timing)・着(racer_place_number)・
  登番(racer_number) を全て含む。※ミラー配信は 2025-07-15 以降のみ
  （それ以前は404）。したがって 2025-07-15 より前に始まった場は
  集計期間がその日から切り詰められる（出力に実際の集計期間を明記）。

集計単位: 登番 × 進入コース別に
  出走数 / 1着数 / 2連対数 / 平均ST / 決まり手内訳。

出力: docs/data/e30PlayerStats.json（GitHub Pagesで配信＝閲覧ページから参照可能）
使い方: python scripts/buildE30Stats.py
  環境変数:
    E30_SCHEDULE  スケジュールJSON（既定 e30Schedule.json）
    E30_OUT       出力先（既定 docs/data/e30PlayerStats.json）
    E30_END       集計最終日 YYYYMMDD（既定=当日JST）
    E30_MIN_N     出力に載せる最低出走数（既定 1=全件。司令塔判定用に可変）
"""
import os, io, sys, json, time, datetime, urllib.request

BASE = "https://raw.githubusercontent.com/BoatraceOpenAPI/results/HEAD/docs/v2/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) boatrace-data-collector"}
MIRROR_FIRST = "20250715"   # ミラー配信の最古日（これ以前は404）

TECHNIQUE = {1: "逃げ", 2: "差し", 3: "まくり", 4: "まくり差し", 5: "抜き", 6: "恵まれ"}

SCHEDULE = os.environ.get("E30_SCHEDULE", "e30Schedule.json")
OUT      = os.environ.get("E30_OUT", "docs/data/e30PlayerStats.json")
MIN_N    = int(os.environ.get("E30_MIN_N", "1"))
CACHE    = os.environ.get("E30_CACHE", "")   # 任意: 日次JSONのキャッシュディレクトリ


def jst_today():
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).date()


def load_schedule():
    with io.open(SCHEDULE, encoding="utf-8") as f:
        sc = json.load(f)
    venues = {}
    for v in sc.get("venues", []):
        jcd = str(v["jcd"]).zfill(2)
        sd = v["startDate"].replace("-", "")     # YYYYMMDD
        venues[jcd] = {"name": v.get("name", ""), "start": sd}
    return venues


def fetch_json(hd):
    if CACHE:
        cp = os.path.join(CACHE, hd + ".json")
        if os.path.exists(cp):
            try:
                with io.open(cp, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    url = "{0}{1}/{2}.json".format(BASE, hd[:4], hd)
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15).read()
    except Exception:
        return None
    if not raw or len(raw) < 50:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if CACHE:
        try:
            os.makedirs(CACHE, exist_ok=True)
            with io.open(os.path.join(CACHE, hd + ".json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass
    return data


def daterange(start_ymd, end_ymd):
    d = datetime.datetime.strptime(start_ymd, "%Y%m%d").date()
    e = datetime.datetime.strptime(end_ymd, "%Y%m%d").date()
    while d <= e:
        yield d.strftime("%Y%m%d")
        d += datetime.timedelta(days=1)


def main():
    venues = load_schedule()
    if not venues:
        print("e30Schedule.json に対象場がありません"); return
    end = os.environ.get("E30_END", "").strip() or jst_today().strftime("%Y%m%d")
    # 収集開始日 = 対象場の最早startDate。ただしミラー最古日でクランプ。
    earliest = min(v["start"] for v in venues.values())
    span_start = max(earliest, MIRROR_FIRST)
    truncated = span_start != earliest

    # 集計: players[登番] = {name, courses{course:{r,w1,w2,st_sum,st_n,tech{}}}}
    players = {}
    first_seen = None; last_seen = None; race_cnt = 0; day_cnt = 0
    for hd in daterange(span_start, end):
        data = fetch_json(hd)
        time.sleep(0.15)
        if not data:
            continue
        day_used = False
        for r in data.get("results", []):
            try:
                jcd = "%02d" % int(r["race_stadium_number"])
            except Exception:
                continue
            v = venues.get(jcd)
            if not v or hd < v["start"]:
                continue                 # 対象場でない or startDate前
            tech = r.get("race_technique_number")
            try:
                tech = int(tech) if tech is not None else None
            except Exception:
                tech = None
            for b in r.get("boats", []):
                no = b.get("racer_number")
                course = b.get("racer_course_number")
                st = b.get("racer_start_timing")
                place = b.get("racer_place_number")
                if no is None or course is None:
                    continue
                if not isinstance(st, (int, float)):
                    continue             # ST無し=欠場等は出走に数えない
                p = players.setdefault(str(no), {"name": b.get("racer_name", ""), "courses": {}})
                if b.get("racer_name"):
                    p["name"] = b["racer_name"]
                c = p["courses"].setdefault(int(course),
                        {"出走数": 0, "1着数": 0, "2連対数": 0, "st_sum": 0.0, "st_n": 0, "決まり手": {}})
                c["出走数"] += 1
                if isinstance(place, int) and place == 1:
                    c["1着数"] += 1
                    if tech in TECHNIQUE:
                        c["決まり手"][TECHNIQUE[tech]] = c["決まり手"].get(TECHNIQUE[tech], 0) + 1
                if isinstance(place, int) and place in (1, 2):
                    c["2連対数"] += 1
                if st >= 0:              # F(負値)は平均STから除外（別途フライングは着コードで判別可）
                    c["st_sum"] += st; c["st_n"] += 1
                race_cnt += 1
                day_used = True
        if day_used:
            first_seen = first_seen or hd
            last_seen = hd
            day_cnt += 1

    # 整形出力
    out_players = {}
    total_kept = 0
    for no, p in players.items():
        courses = {}
        n_total = 0
        for course, c in sorted(p["courses"].items()):
            avg_st = round(c["st_sum"] / c["st_n"], 2) if c["st_n"] else None
            n_total += c["出走数"]
            courses[str(course)] = {
                "出走数": c["出走数"],
                "1着数": c["1着数"],
                "2連対数": c["2連対数"],
                "平均ST": avg_st,
                "決まり手": c["決まり手"],
            }
        if n_total < MIN_N:
            continue
        out_players[no] = {"氏名": p["name"], "総出走数": n_total, "コース別": courses}
        total_kept += 1

    doc = {
        "生成時刻JST": (datetime.datetime.utcnow() + datetime.timedelta(hours=9)).strftime("%Y-%m-%d %H:%M"),
        "出典": "BoatraceOpenAPI/results ミラー（mbrace由来・GitHub配信）",
        "集計期間": {"開始": first_seen, "終了": last_seen, "開催日数": day_cnt},
        "対象場": {j: {"場名": v["name"], "E30開始日": v["start"]} for j, v in sorted(venues.items())},
        "最低出走数フィルタ": MIN_N,
        "注記": ("生データのみ。推測・確率・評価・買い目は含まない。"
                 + ("　※ミラー配信開始(2025-07-15)より前に始まった場は集計期間が切り詰められている。" if truncated else "")),
        "選手数": total_kept,
        "延べ出走数": race_cnt,
        "選手成績": out_players,
    }
    if os.path.dirname(OUT):
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print("wrote", OUT)
    print("  対象場", list(venues.keys()), "集計期間", first_seen, "〜", last_seen,
          "開催日", day_cnt, "延べ出走", race_cnt, "選手", total_kept,
          ("(先頭切詰め)" if truncated else ""))


if __name__ == "__main__":
    main()
