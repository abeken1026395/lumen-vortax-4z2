# -*- coding: utf-8 -*-
"""
24場「優勝戦の出目ランキング」集計。

優勝戦の特定は公式番組データ（BoatraceOpenAPI programs, race_subtitle=="優勝戦"）で行う。
※ boatrace.jp 本体は egress ポリシーで遮断されるため、到達可能な公式ミラー(programs)を使う。
※ 優勝戦は必ずしも12Rではない（例: 大村は11R優勝戦の節がある）。番組の race_number をそのまま採用。

3連単の出目（着順）は既存の docs/payouts/*Payouts.csv（combo列）から (hd, rno) で引く。
場ごとに優勝戦の出目を集計し、出現回数の多い順に並べて docs/payouts/champRace.json に出力する。

方針（CLAUDE.md 準拠）:
  - 「過去の優勝戦で実際に出た出目の回数」の可視化であり、買い目・確率・予想ではない。
  - 推奨表現（狙い目/来やすい等）・確率提示はしない。note に誤読対策の一文を持たせる。

環境変数 START/END で対象期間を指定（既定 20250715〜20260716）。
"""
import os
import csv
import glob
import json
import time
import datetime
import urllib.request
import urllib.error

PAYDIR = os.path.join("docs", "payouts")
OUT = os.path.join(PAYDIR, "champRace.json")
PROG = "https://raw.githubusercontent.com/BoatraceOpenAPI/programs/gh-pages/docs/v2/{y}/{ymd}.json"
UA = "Mozilla/5.0 boatrace-data-collector"
TIMEOUT = 30

SLUG2VENUE = {
    "kiryu": (1, "桐生"), "toda": (2, "戸田"), "edogawa": (3, "江戸川"),
    "heiwajima": (4, "平和島"), "tamagawa": (5, "多摩川"), "hamanako": (6, "浜名湖"),
    "gamagori": (7, "蒲郡"), "tokoname": (8, "常滑"), "tsu": (9, "津"),
    "mikuni": (10, "三国"), "biwako": (11, "びわこ"), "suminoe": (12, "住之江"),
    "amagasaki": (13, "尼崎"), "naruto": (14, "鳴門"), "marugame": (15, "丸亀"),
    "kojima": (16, "児島"), "miyajima": (17, "宮島"), "tokuyama": (18, "徳山"),
    "shimonoseki": (19, "下関"), "wakamatsu": (20, "若松"), "ashiya": (21, "芦屋"),
    "fukuoka": (22, "福岡"), "karatsu": (23, "唐津"), "omura": (24, "大村"),
}
JCD2VENUE = {jcd: (slug, name) for slug, (jcd, name) in SLUG2VENUE.items()}


def load_combo_map():
    """(jcd, hd, rno) -> combo を全24場CSVから構築。"""
    m = {}
    for path in glob.glob(os.path.join(PAYDIR, "*Payouts.csv")):
        slug = os.path.basename(path)[:-len("Payouts.csv")]
        meta = SLUG2VENUE.get(slug)
        if not meta:
            continue
        jcd = meta[0]
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                hd = (row.get("hd") or "").strip()
                rno = (row.get("rno") or "").strip()
                combo = (row.get("combo") or "").strip()
                if hd and rno and combo:
                    m[(jcd, hd, int(rno))] = combo
    return m


def fetch_programs(ymd):
    url = PROG.format(y=ymd[:4], ymd=ymd)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def fmt(ymd):
    return ymd[0:4] + "/" + ymd[4:6] + "/" + ymd[6:8]


def main():
    start_s = os.environ.get("START", "").strip() or "20250715"
    end_s = os.environ.get("END", "").strip() or "20260716"
    start = datetime.date(int(start_s[:4]), int(start_s[4:6]), int(start_s[6:8]))
    end = datetime.date(int(end_s[:4]), int(end_s[4:6]), int(end_s[6:8]))

    combo_map = load_combo_map()

    # jcd -> list of {date,rno,combo,title}
    champs = {j: [] for j in range(1, 25)}
    missing_combo = 0
    days_seen = set()

    d = start
    while d <= end:
        ymd = d.strftime("%Y%m%d")
        d += datetime.timedelta(days=1)
        doc = fetch_programs(ymd)
        if not doc:
            continue
        for p in doc.get("programs", []):
            sub = (p.get("race_subtitle") or "").strip()
            # 「準優勝戦」は部分一致で拾ってしまうため完全一致で優勝戦だけを対象にする
            if sub != "優勝戦":
                continue
            jcd = p.get("race_stadium_number")
            rno = p.get("race_number")
            if jcd not in champs or not rno:
                continue
            combo = combo_map.get((jcd, ymd, int(rno)))
            days_seen.add(ymd)
            if not combo:
                missing_combo += 1
                continue
            champs[jcd].append({
                "date": fmt(ymd), "rno": rno, "combo": combo,
                "title": (p.get("race_title") or "").strip(),
            })
        time.sleep(0.03)

    venues = {}
    for jcd in range(1, 25):
        lst = champs[jcd]
        if not lst:
            continue
        slug, name = JCD2VENUE[jcd]
        cnt = {}
        for r in lst:
            cnt[r["combo"]] = cnt.get(r["combo"], 0) + 1
        total = len(lst)
        ranking = [
            {"combo": c, "count": n, "share": round(n / total * 100, 1)}
            for c, n in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        dates = sorted(r["date"] for r in lst)
        venues["%02d" % jcd] = {
            "stadium": name, "jcd": jcd, "slug": slug,
            "total": total,
            "period": {"from": dates[0], "to": dates[-1]},
            "ranking": ranking,
            "races": sorted(lst, key=lambda r: r["date"], reverse=True),
        }

    out = {
        "title": "優勝戦の出目ランキング（過去実績）",
        "source": "公式競走成績・番組（BoatraceOpenAPI 経由）",
        "note": "過去の優勝戦で実際に出た出目の回数であり、次のレースの予想ではありません。",
        "venueCount": len(venues),
        "venues": venues,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=2))
    print("venues:", len(venues), " combo未取得:", missing_combo, " 優勝戦のあった日:", len(days_seen))
    for code in sorted(venues):
        v = venues[code]
        top = v["ranking"][0] if v["ranking"] else {}
        print(code, v["stadium"], "優勝戦%d戦 最多 %s×%d" % (v["total"], top.get("combo"), top.get("count", 0)))


if __name__ == "__main__":
    main()
