# -*- coding: utf-8 -*-
# 徳山(jcd=18)の3連単払戻を収集する。
# 月間スケジュールで開催日を特定 -> 開催日だけ巡回。非開催日は一切叩かない。
# 環境変数 YM (例: 202604) を指定するとその月のみ処理。未指定なら直近 MONTHS_BACK ヶ月。
import io
import os
import re
import csv
import time
import datetime
import urllib.request

JCD = 18
RESULT = "https://www.boatrace.jp/owpc/pc/race/raceresult"
SCHED = "https://www.boatrace.jp/owpc/pc/race/monthlyschedule"
OUT = os.path.join("docs", "payouts", "tokuyamaPayouts.csv")
SLEEP = 0.4
MONTHS_BACK = 12

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception:
            if attempt == 0:
                time.sleep(0.5)
    return None


# スケジュールページから徳山(jcd=18)の開催初日(hd)を全部拾う
SCHED_HD = re.compile(r"jcd=18&hd=(\d{8})")


def kaisai_start_days(ym):
    url = "{0}?ym={1}".format(SCHED, ym)
    html = get(url)
    if not html:
        return []
    days = sorted(set(SCHED_HD.findall(html)))
    return days


def normalize(html):
    return html.replace("&yen;", "\uffe5").replace("&#165;", "\uffe5").replace("\uff13", "3")


COMBO = re.compile(r"3\u9023\u5358(.*?)(\d)-(\d)-(\d)(.*)", re.S)
MONEY = re.compile(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,})")


def parse_payout(html):
    if html is None:
        return None
    html = normalize(html)
    m = COMBO.search(html)
    if not m:
        return None
    combo = m.group(2) + "-" + m.group(3) + "-" + m.group(4)
    mm = MONEY.search(m.group(5))
    if not mm:
        return None
    yen = int(mm.group(1).replace(",", ""))
    if yen < 100 or yen > 9999999:
        return None
    return combo, yen


def fetch_result(hd, rno):
    url = "{0}?rno={1}&jcd={2}&hd={3}".format(RESULT, rno, JCD, hd)
    return get(url)


def load_done():
    done = set()
    if os.path.exists(OUT):
        with io.open(OUT, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if len(row) >= 2:
                    done.add((row[0], row[1]))
    return done


def months_to_process():
    ym = os.environ.get("YM", "").strip()
    if ym:
        return [ym]
    today = datetime.date.today()
    out = []
    y, m = today.year, today.month
    for _ in range(MONTHS_BACK + 1):
        out.append("%04d%02d" % (y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    done = load_done()
    new_file = not os.path.exists(OUT)
    out = io.open(OUT, "a", encoding="utf-8", newline="")
    writer = csv.writer(out)
    if new_file:
        writer.writerow(["hd", "rno", "combo", "payout"])

    today = datetime.date.today()
    collected = 0
    sample_dumped = False

    # 開催日を全部集める（各節は初日から最大7日連続とみなして展開し、結果有無で確認）
    target_days = set()
    for ym in months_to_process():
        starts = kaisai_start_days(ym)
        time.sleep(SLEEP)
        for s in starts:
            d0 = datetime.date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
            for off in range(0, 7):
                d = d0 + datetime.timedelta(days=off)
                if d <= today:
                    target_days.add(d.strftime("%Y%m%d"))

    for hd in sorted(target_days):
        day_hit = 0
        for rno in range(1, 13):
            if (hd, str(rno)) in done:
                day_hit += 1
                continue
            html = fetch_result(hd, rno)
            time.sleep(SLEEP)
            res = parse_payout(html)
            if res is None:
                if html and not sample_dumped and ("3\u9023\u5358" in html):
                    print("=== SAMPLE hd=%s rno=%d ===" % (hd, rno))
                    idx = html.find("3\u9023\u5358")
                    print(html[idx:idx + 300])
                    print("=== END SAMPLE ===")
                    sample_dumped = True
                # 節の最終日翌日など結果が無い日は2Rで見切る
                if rno == 2 and day_hit == 0:
                    break
                continue
            combo, yen = res
            writer.writerow([hd, rno, combo, yen])
            out.flush()
            collected += 1
            day_hit += 1

    out.close()
    print("collected:", collected, "target_days:", len(target_days))


if __name__ == "__main__":
    main()
