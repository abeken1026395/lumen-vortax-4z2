# -*- coding: utf-8 -*-
"""
尼崎払戻CSV → R別万舟率JSON集計（桐生・徳山と同一スキーマ）
入力: docs/payouts/amagasakiPayouts.csv （hd, rno, combo, payout）
出力: docs/payouts/amagasakiManRate.json
  - period: データ期間(from/to/開催日数)
  - races: R別（rno/races/manCount/manRate/avgPayout/maxPayout）
  - calmRace / wildRace: 最も堅い/荒れるR
  - topPayouts: 高配当TOP5（date/rno/combo/payout）
  - laneShare: 万舟時の1着枠内訳（lane/count/share）
"""
import io
import os
import csv
import json

SRC = os.path.join("docs", "payouts", "amagasakiPayouts.csv")
OUT = os.path.join("docs", "payouts", "amagasakiManRate.json")
MAN = 10000  # 万舟の閾値（1万円“超”。徳山・桐生と統一）


def main():
    stats = {}
    total_races = 0
    all_rows = []
    win_lane = {}
    man_total = 0

    with io.open(SRC, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 4:
                continue
            hd = row[0]
            rno = int(row[1])
            combo = row[2]
            payout = int(row[3])
            all_rows.append((hd, rno, combo, payout))

            s = stats.setdefault(rno, [0, 0, 0, 0])  # total, man, sum, max
            s[0] += 1
            if payout > MAN:
                s[1] += 1
                man_total += 1
                lane = combo.split("-")[0]
                win_lane[lane] = win_lane.get(lane, 0) + 1
            s[2] += payout
            if payout > s[3]:
                s[3] = payout
            total_races += 1

    races = []
    for rno in range(1, 13):
        if rno not in stats:
            continue
        total, man, ssum, smax = stats[rno]
        races.append({
            "rno": rno,
            "races": total,
            "manCount": man,
            "manRate": round(man / total * 100, 1) if total else 0.0,
            "avgPayout": round(ssum / total) if total else 0,
            "maxPayout": smax,
        })

    top = sorted(all_rows, key=lambda x: x[3], reverse=True)[:10]
    top_payouts = []
    for hd, rno, combo, payout in top:
        ymd = hd[0:4] + "/" + hd[4:6] + "/" + hd[6:8]
        top_payouts.append({
            "date": ymd, "rno": rno, "combo": combo, "payout": payout,
        })

    lane_share = []
    for lane in ["1", "2", "3", "4", "5", "6"]:
        c = win_lane.get(lane, 0)
        lane_share.append({
            "lane": int(lane),
            "count": c,
            "share": round(c / man_total * 100, 1) if man_total else 0.0,
        })

    calm = wild = None
    if races:
        calm = min(races, key=lambda r: r["manRate"])
        wild = max(races, key=lambda r: r["manRate"])

    # データ期間（最古〜最新の開催日と開催日数）
    hds = sorted({r[0] for r in all_rows})
    def fmt(h):
        return h[0:4] + "/" + h[4:6] + "/" + h[6:8]
    period = {
        "from": fmt(hds[0]),
        "to": fmt(hds[-1]),
        "days": len(hds),
    } if hds else None

    out = {
        "stadium": "尼崎",
        "jcd": 13,
        "threshold": MAN,
        "period": period,
        "totalRaces": total_races,
        "manTotal": man_total,
        "races": races,
        "topPayouts": top_payouts,
        "laneShare": lane_share,
        "calmRace": {"rno": calm["rno"], "manRate": calm["manRate"],
                     "avgPayout": calm["avgPayout"]} if calm else None,
        "wildRace": {"rno": wild["rno"], "manRate": wild["manRate"],
                     "avgPayout": wild["avgPayout"]} if wild else None,
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False, indent=2))

    print("total races:", total_races, "man:", man_total)


if __name__ == "__main__":
    main()
