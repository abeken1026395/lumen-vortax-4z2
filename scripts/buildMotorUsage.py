# -*- coding: utf-8 -*-
# buildMotorUsage.py
# 人力で置かれた競走成績(Kファイル)群を自前集計し、各場のモーター機の
# 「初卸(推定)からの走行数・勝・2連・3連」を docs/data/motorUsage.json に出力する。
#
# 収集はこのスクリプトの対象外（mbraceはActions/Code/本環境すべて403のため、
# Kファイルは人力(iPhone/PC)で取得し data/kfiles/ に置かれる前提）。本スクリプトは
# 「置かれたKファイル群を処理する部分」だけを担う。
#
# 入力：KFILES_DIR（既定 data/kfiles/）内の kYYMMDD.lzh（SHIFT_JIS・lhafile解凍）。
#       ローカル検証用に解凍済み .txt(SHIFT_JIS) も読める。
# 出力：docs/data/motorUsage.json
#
# ハルシネーション防止（絶対）:
#   Kファイルから読めた明細のみカウント。欠けた期間は補完・推測しない。
#   「初卸」はKファイル初出日での推定（公式交換日は非公開）。coverageFrom を必ず出す。
import os
import re
import glob
import json
import datetime

JST = datetime.timezone(datetime.timedelta(hours=9))

KFILES_DIR = os.environ.get("KFILES_DIR", os.path.join("data", "kfiles"))
OUT = os.path.join("docs", "data", "motorUsage.json")

# 24場コード（scrape_motors.py の VENUES と同一）
VENUES = {
    "01": "桐生", "02": "戸田", "03": "江戸川", "04": "平和島",
    "05": "多摩川", "06": "浜名湖", "07": "蒲郡", "08": "常滑",
    "09": "津", "10": "三国", "11": "びわこ", "12": "住之江",
    "13": "尼崎", "14": "鳴門", "15": "丸亀", "16": "児島",
    "17": "宮島", "18": "徳山", "19": "下関", "20": "若松",
    "21": "芦屋", "22": "福岡", "23": "唐津", "24": "大村",
}
# 場名（全角/半角スペース除去）→ jcd。長い名前優先で照合（「津」と「唐津」の誤判定を防ぐ）。
NAME2JCD = sorted(((v, k) for k, v in VENUES.items()), key=lambda x: -len(x[0]))

SEISEKI = "［成績］"  # ［成績］
# 明細行（司令塔検証済み）：着順 艇 登番 氏名 モーターNo ボートNo レースタイム…
DETAIL_RE = re.compile(r"\s*(\d{1,2})\s+(\d)\s+(\d{4})\s+(.+?)\s+(\d{1,3})\s+(\d{1,3})\s+\d+\.\d+")
# 開催日「2026/ 7/ 8」形式
DATE_RE = re.compile(r"(\d{4})/\s*(\d{1,2})/\s*(\d{1,2})")


def decode_kfile(path):
    """Kファイルを SHIFT_JIS テキストで返す。.lzh は lhafile で解凍、.txt はそのまま。"""
    if path.lower().endswith(".lzh"):
        import lhafile
        arc = lhafile.Lhafile(path)
        names = arc.namelist()
        if not names:
            return ""
        raw = arc.read(names[0])
    else:
        with open(path, "rb") as f:
            raw = f.read()
    return raw.decode("shift_jis", errors="replace")


def file_date(text, path):
    """ファイルの開催日(YYYYMMDD)。本文の日付行を優先、無ければ kYYMMDD のファイル名から。"""
    m = DATE_RE.search(text)
    if m:
        return "{:04d}{:02d}{:02d}".format(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    mm = re.search(r"[kK](\d{2})(\d{2})(\d{2})", os.path.basename(path))
    if mm:
        return "20{}{}{}".format(mm.group(1), mm.group(2), mm.group(3))
    return ""


def parse_text(text):
    """SHIFT_JIS本文から明細を返す：[(jcd, 着順, 艇, 登番, 氏名, モーターNo, ボートNo)]。
    場ブロック見出し「○○［成績］」で現在の場を切り替える。"""
    out = []
    cur_jcd = None
    for ln in text.split("\n"):
        if SEISEKI in ln:
            head = ln.split(SEISEKI)[0].replace("　", "").replace(" ", "").strip()
            cur_jcd = None
            for name, jcd in NAME2JCD:  # 長い名前優先
                if head.endswith(name):
                    cur_jcd = jcd
                    break
            continue
        if cur_jcd is None:
            continue
        m = DETAIL_RE.match(ln)
        if not m:
            continue
        out.append((cur_jcd, int(m.group(1)), int(m.group(2)),
                    m.group(3), m.group(4).strip(), m.group(5), m.group(6)))
    return out


def main():
    files = sorted(glob.glob(os.path.join(KFILES_DIR, "*.lzh")) +
                   glob.glob(os.path.join(KFILES_DIR, "*.txt")))
    if not files:
        print("Kファイルが {} に無い。処理中止（既存を変更しない）。".format(KFILES_DIR))
        return

    motors = {}
    dates = []
    n_detail = 0
    for path in files:
        try:
            text = decode_kfile(path)
        except Exception as e:
            print("  [warn] 解凍/読込失敗 {}: {}".format(path, e))
            continue
        hd = file_date(text, path)
        if not hd:
            print("  [warn] 開催日不明のためスキップ: {}".format(path))
            continue
        dates.append(hd)
        details = parse_text(text)
        n_detail += len(details)
        for (jcd, chaku, tei, toban, name, mno, bno) in details:
            key = "{}_{}".format(jcd, mno)
            d = motors.get(key)
            if d is None:
                d = {"jcd": jcd, "モーターNo": mno, "走": 0, "勝": 0, "2連": 0, "3連": 0,
                     "初出日": hd, "最新日": hd}
                motors[key] = d
            d["走"] += 1
            if chaku == 1:
                d["勝"] += 1
            if chaku <= 2:
                d["2連"] += 1
            if chaku <= 3:
                d["3連"] += 1
            if hd < d["初出日"]:
                d["初出日"] = hd
            if hd > d["最新日"]:
                d["最新日"] = hd
        print("  [ok] {} ({}) … 明細{}件".format(os.path.basename(path), hd, len(details)))

    for d in motors.values():
        w = d["走"]
        d["2連率"] = round(d["2連"] / w * 100, 1) if w else "-"
        d["3連率"] = round(d["3連"] / w * 100, 1) if w else "-"

    out = {
        "updated": datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "source": "mbrace競走成績(K)由来・自前集計",
        "note": "初卸=Kファイル初出日で推定（公式交換日は非公開）。走行数・着順は実測カウントのみ。欠損期間は補完しない。",
        "coverageFrom": min(dates) if dates else "",
        "coverageTo": max(dates) if dates else "",
        "motors": motors,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("保存: {} … {}ファイル / 明細{}件 / {}機 / 期間{}〜{}".format(
        OUT, len(files), n_detail, len(motors), out["coverageFrom"], out["coverageTo"]))


if __name__ == "__main__":
    main()
