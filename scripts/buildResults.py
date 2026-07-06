# -*- coding: utf-8 -*-
# buildResults.py
# BoatraceOpenAPI(GitHub Pages配信)から全24場・全レースの
# 着順(組番)・決まり手・全式別払戻を抽出し results/YYYYMMDD.json に出力。
# 見立て検証(verifyPredictions.py)の結果側データ、および結果表ページ(docs/results/)の元データ。
#
# 取得元: https://raw.githubusercontent.com/BoatraceOpenAPI/results/HEAD/docs/v2/YYYY/YYYYMMDD.json
#   ・GitHub配信のためGitHub ActionsのIPからも通る(mbraceのIPブロック問題を回避)。
#   ・当日結果はレース確定後に反映。未確定/非開催日は404。
#   ・OpenAPIには決まり手(race_technique_number)と全式別払戻(trifecta/trio/exacta/
#     quinella/quinella_place/win/place)が含まれるため mbrace LZH は不要。
#
# 本番: 環境変数なしで当日(JST)分を取得。
# 複数日: 環境変数 HD にカンマ区切りで日付(YYYYMMDD)を渡すと全日ぶん取得(過去分の穴埋め用)。
import io
import os
import json
import time
import datetime
import urllib.request

BASE = "https://raw.githubusercontent.com/BoatraceOpenAPI/results/HEAD/docs/v2/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) boatrace-data-collector"

# 決まり手コード(race_technique_number) → 表記
TECHNIQUE = {
    1: "逃げ", 2: "差し", 3: "まくり",
    4: "まくり差し", 5: "抜き", 6: "恵まれ",
}


def _payouts(payouts):
    """OpenAPIのpayoutsを、式別ごとの[{組番,配当}...]に整形して返す。
    単勝/複勝/2連単/2連複/拡連複/3連複/3連単の順。配当欠損は0/Noneを除外。"""
    # OpenAPIキー → 日本語式別名
    mapping = [
        ("win", "単勝"),
        ("place", "複勝"),
        ("exacta", "2連単"),
        ("quinella", "2連複"),
        ("quinella_place", "拡連複"),
        ("trio", "3連複"),
        ("trifecta", "3連単"),
    ]
    out = {}
    for key, label in mapping:
        rows = []
        for e in payouts.get(key, []) or []:
            combo = e.get("combination")
            pay = e.get("payout")
            if not combo or pay in (None, 0):
                continue
            try:
                rows.append({"組番": combo, "配当": int(pay)})
            except Exception:
                continue
        out[label] = rows
    return out


def fetch_json(hd):
    """指定日(YYYYMMDD)の結果JSONを取得してdictで返す。404/失敗はNone。"""
    y = hd[:4]
    url = "{0}{1}/{2}.json".format(BASE, y, hd)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
    except Exception:
        return None
    if not raw or len(raw) < 20:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def to_races(data):
    """OpenAPIのresults配列を、既存results形式のレース配列に変換。"""
    races = []
    for r in data.get("results", []):
        tri = r.get("payouts", {}).get("trifecta", [])
        if not tri:
            continue
        combo = tri[0].get("combination")
        pay = tri[0].get("payout")
        if not combo or pay in (None, 0):
            continue
        top3 = combo.split("-")
        if len(top3) != 3:
            continue
        try:
            boats = []
            for b in r.get("boats", []):
                boats.append({
                    "枠": b.get("racer_boat_number"),
                    "登番": b.get("racer_number"),
                    "氏名": b.get("racer_name"),
                    "コース": b.get("racer_course_number"),
                    "ST": b.get("racer_start_timing"),
                    "着": b.get("racer_place_number"),
                })
            tech_no = r.get("race_technique_number")
            try:
                tech_no = int(tech_no) if tech_no is not None else None
            except Exception:
                tech_no = None
            races.append({
                "場コード": "%02d" % int(r["race_stadium_number"]),
                "レース": "%dR" % int(r["race_number"]),
                "着順": combo,
                "1着": int(top3[0]), "2着": int(top3[1]), "3着": int(top3[2]),
                "三連単配当": int(pay),
                "決まり手": TECHNIQUE.get(tech_no),
                "払戻": _payouts(r.get("payouts", {})),
                "艇": boats,
            })
        except Exception:
            continue
    return races


def write_results(data, hd):
    races = to_races(data)
    venues = len(set(x["場コード"] for x in races))
    os.makedirs("results", exist_ok=True)
    outpath = os.path.join("results", "%s.json" % hd)
    obj = {"開催日": hd,
           "取得時刻": datetime.datetime.now().isoformat(timespec="seconds"),
           "レース数": len(races), "結果": races}
    with io.open(outpath, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    print("wrote", outpath, "races", len(races), "venues", venues)
    return len(races)


def main():
    hd_env = os.environ.get("HD", "").strip()
    if hd_env:
        days = [x.strip() for x in hd_env.replace("\u3001", ",").split(",") if x.strip()]
    else:
        today = datetime.datetime.utcnow() + datetime.timedelta(hours=9)
        days = [today.date().strftime("%Y%m%d")]

    for hd in days:
        data = fetch_json(hd)
        if not data:
            print("no data for", hd)
            continue
        write_results(data, hd)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
