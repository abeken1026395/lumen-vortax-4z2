# -*- coding: utf-8 -*-
"""
万舟のツボ 総合（全24場横断）集計。
到達可能な非公式ミラー BoatraceOpenAPI(v2) から全24場の3連単払戻を集計し、
docs/payouts/summary.json を生成する。

出力スキーマ:
  period: {from,to,days}          … 対象期間（実データのある日）
  totalRaces, manTotal            … 全24場合計
  topPayouts: [10]                … 全場横断の高配当TOP10（stadium/jcd/slug/date/rno/combo/payout）
  arareRanking: [24]              … 場別 万舟率ランキング（降順）
  maxRanking: [24]                … 場別 最高配当ランキング（降順）
  venues: {jcd: slug|null}        … R別ページのある場のslug対応

環境変数 START/END で期間指定（既定 20250715〜昨日JST）。
"""
import os
import json
import time
import datetime
import urllib.request
import urllib.error

MAN = 10000
RAW = "https://raw.githubusercontent.com/BoatraceOpenAPI/results/gh-pages/docs/v2/{y}/{ymd}.json"
OUT = os.path.join("docs", "payouts", "summary.json")
UA = "Mozilla/5.0 boatrace-data-collector"
TIMEOUT = 30

NAMES = {1:"桐生",2:"戸田",3:"江戸川",4:"平和島",5:"多摩川",6:"浜名湖",7:"蒲郡",8:"常滑",
9:"津",10:"三国",11:"びわこ",12:"住之江",13:"尼崎",14:"鳴門",15:"丸亀",16:"児島",
17:"宮島",18:"徳山",19:"下関",20:"若松",21:"芦屋",22:"福岡",23:"唐津",24:"大村"}

# R別ページを持つ場（jcd→slug）
SLUG = {18:"tokuyama",1:"kiryu",23:"karatsu",2:"toda",16:"kojima",
        20:"wakamatsu",24:"omura",11:"biwako",8:"tokoname",6:"hamanako"}


def fetch_day(d):
    ymd = d.strftime("%Y%m%d")
    url = RAW.format(y=d.strftime("%Y"), ymd=ymd)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def main():
    start_s = os.environ.get("START", "").strip() or "20250715"
    start = datetime.date(int(start_s[0:4]), int(start_s[4:6]), int(start_s[6:8]))
    end_s = os.environ.get("END", "").strip()
    end = (datetime.date(int(end_s[0:4]), int(end_s[4:6]), int(end_s[6:8]))
           if end_s else datetime.date.today() - datetime.timedelta(days=1))

    stat = {j: [0, 0, 0, None] for j in range(1, 25)}  # total, man, maxPayout, (ymd,rno,combo)
    days = {j: set() for j in range(1, 25)}
    all_alldays = set()

    d = start
    while d <= end:
        ymd = d.strftime("%Y%m%d")
        d += datetime.timedelta(days=1)
        doc = fetch_day(datetime.datetime.strptime(ymd, "%Y%m%d").date())
        if not doc:
            continue
        for r in doc.get("results", []):
            j = r.get("race_stadium_number")
            rno = r.get("race_number")
            tri = (r.get("payouts") or {}).get("trifecta") or []
            if not j or j not in stat or not rno or not tri:
                continue
            p = tri[0].get("payout")
            combo = tri[0].get("combination")
            if p is None or not combo:
                continue
            s = stat[j]
            s[0] += 1
            if p > MAN:
                s[1] += 1
            if p > s[2]:
                s[2] = p
                s[3] = (ymd, rno, combo)
            days[j].add(ymd)
            all_alldays.add(ymd)
        time.sleep(0.05)

    arare = []
    mx = []
    total_races = 0
    man_total = 0
    for j in range(1, 25):
        t, m, mp, info = stat[j]
        if t == 0:
            continue
        total_races += t
        man_total += m
        arare.append({
            "stadium": NAMES[j], "jcd": j, "slug": SLUG.get(j),
            "races": t, "manCount": m,
            "manRate": round(m / t * 100, 1),
        })
        if info:
            ymd, rno, combo = info
            mx.append({
                "stadium": NAMES[j], "jcd": j, "slug": SLUG.get(j),
                "date": ymd[0:4] + "/" + ymd[4:6] + "/" + ymd[6:8],
                "rno": rno, "combo": combo, "payout": mp,
            })
    arare.sort(key=lambda x: -x["manRate"])
    mx.sort(key=lambda x: -x["payout"])

    top_payouts = mx[:10]

    hds = sorted(all_alldays)
    def fmt(h):
        return h[0:4] + "/" + h[4:6] + "/" + h[6:8]
    period = {"from": fmt(hds[0]), "to": fmt(hds[-1]), "days": len(hds)} if hds else None

    out = {
        "title": "万舟のツボ 総合",
        "source": "BoatraceOpenAPI(v2) / 公式競走成績",
        "threshold": MAN,
        "period": period,
        "venueCount": len(arare),
        "totalRaces": total_races,
        "manTotal": man_total,
        "topPayouts": top_payouts,
        "arareRanking": arare,
        "maxRanking": mx,
        "venues": {str(j): SLUG.get(j) for j in range(1, 25)},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=2))
    print("venues:", len(arare), "totalRaces:", total_races, "manTotal:", man_total)


if __name__ == "__main__":
    main()
