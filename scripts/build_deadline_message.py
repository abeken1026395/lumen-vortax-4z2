#!/usr/bin/env python3
"""締切一覧メッセージ生成（総合レース部屋向け）。

docs/racers/racers_today.csv の「締切時刻」から、対象日の各場について
1R(最小)〜最終R(最大)の締切を集計し、時間帯別に整形したテキストを出力する。

方針:
- 標準ライブラリのみ。
- 推測で埋めない。CSVに実在する締切だけを使う。対象日のデータが無ければ「未取得」と報告。
- 時間帯（モーニング/デイ/ナイター/ミッドナイト）は 1R 締切時刻で判定する
  （時間帯は場ごとに固定ではなく開催区分に依存するため）。
- 曜日は対象日の暦から算出（外部の曜日指定は信用しない）。

対象日: 既定は翌日(JST)。環境変数 DEADLINE_DATE=YYYYMMDD で上書き可。
出力: docs/data/deadlines_tomorrow.txt ＋ 標準出力 ＋ GITHUB_STEP_SUMMARY（あれば）。
"""

import csv
import os
import datetime

JST = datetime.timezone(datetime.timedelta(hours=9))
WD = ["月", "火", "水", "木", "金", "土", "日"]

CSV_PATH = os.path.join("docs", "racers", "racers_today.csv")
OUT_PATH = os.path.join("docs", "data", "deadlines_tomorrow.txt")

SLOT_ORDER = ["モーニング", "デイ", "ナイター", "ミッドナイト"]
SLOT_LABEL = {s: "【{}】".format(s) for s in SLOT_ORDER}


def target_hd():
    v = os.environ.get("DEADLINE_DATE", "").strip()
    if v:
        return v
    return (datetime.datetime.now(JST).date() + datetime.timedelta(days=1)).strftime("%Y%m%d")


def to_min(hhmm):
    """'HH:MM' → 分。パース不可なら None。"""
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def slot_of(first_min):
    """1R 締切時刻(分)で時間帯を判定。"""
    if first_min < 10 * 60:   # 〜09:59
        return "モーニング"
    if first_min < 14 * 60:   # 10:00〜13:59
        return "デイ"
    if first_min < 17 * 60:   # 14:00〜16:59
        return "ナイター"
    return "ミッドナイト"      # 17:00〜


def fmt_time(x):
    return "{:02d}:{:02d}".format(x // 60, x % 60)


def collect(hd):
    """対象日の 場名 -> [締切分, ...] を集める。"""
    venues = {}
    if not os.path.exists(CSV_PATH):
        return venues
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("開催日") or "").strip() != hd:
                continue
            name = (row.get("場名") or "").strip()
            dl = to_min((row.get("締切時刻") or "").strip())
            if not name or dl is None:
                continue
            venues.setdefault(name, []).append(dl)
    return venues


def build_message(hd, venues):
    d = datetime.datetime.strptime(hd, "%Y%m%d").date()
    header = "🌅{}/{}({})総合レース部屋🌅".format(d.month, d.day, WD[d.weekday()])

    if not venues:
        return (header + "\n\n（{}/{} の出走表がまだ取得できていません。"
                "公開後に自動更新されます）".format(d.month, d.day))

    # 場ごとに 1R(min)〜最終R(max) と時間帯
    items = []  # (slot, first_min, last_min, name)
    for name, mins in venues.items():
        items.append((slot_of(min(mins)), min(mins), max(mins), name))

    width = max(len(name) for *_, name in items)  # 全角幅を文字数で近似

    lines = [header, ""]
    for slot in SLOT_ORDER:
        group = sorted((it for it in items if it[0] == slot), key=lambda t: t[1])
        if not group:
            continue
        lines.append(SLOT_LABEL[slot])
        for _slot, fmin, lmax, name in group:
            pad = "　" * (width - len(name))
            lines.append("{}{}　{}〜{}".format(name, pad, fmt_time(fmin), fmt_time(lmax)))
        lines.append("")
    lines.append("↓レース話はこちらのスレッドからお願いします！")
    return "\n".join(lines)


def write_outputs(msg):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(msg + "\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### 締切一覧メッセージ\n\n```\n" + msg + "\n```\n")


def main():
    hd = target_hd()
    venues = collect(hd)
    msg = build_message(hd, venues)
    write_outputs(msg)
    print(msg)


if __name__ == "__main__":
    main()
