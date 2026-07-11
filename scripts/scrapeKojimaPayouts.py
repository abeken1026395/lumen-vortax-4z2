# -*- coding: utf-8 -*-
"""
児島（jcd=16）3連単払戻データ収集スクレイパー
mbrace公式競走成績配布（LZH）方式。桐生・徳山と同設定。
出力: docs/payouts/kojimaPayouts.csv （列: hd, rno, combo, payout）

※ 児島の公式場コードは 16。標準順: … 16児島 17宮島 18徳山 …。

環境変数:
  YM     … 'YYYYMM' 指定でその月のみ収集（未指定なら今日から遡る）
  DAYS   … 遡る日数（未指定なら365）
  START  … 'YYYYMMDD' 明示開始日（CSV空のとき用）
  BSDTAR … bsdtar/tar 実行ファイルの明示パス（未指定なら自動探索）

注意: GitHub Actions のクラウド IP は mbrace に遮断されている。必ずローカルで実行する。
"""
import os
import re
import csv
import glob
import time
import shutil
import datetime
import tempfile
import subprocess
import urllib.request

# https直叩き（http://は301でhttpsへ飛ぶ。urllibはリダイレクト追従するがhttps固定で往復を省く）
BASE = "https://www1.mbrace.or.jp/od2/K/{ym}/k{ymd}.lzh"
OUT = "docs/payouts/kojimaPayouts.csv"

KOJIMA = "児　島［成績］"  # 児　島［成績］（2文字名は全角スペース有り）
SEISEKI = "［成績］"                    # ［成績］
PAY = "払戻金"                              # 払戻金
PAYLINE = re.compile(r"\s*(\d{1,2})R\s+(\d)-(\d)-(\d)\s+(\d+)")

SLEEP = 1.0
TIMEOUT = 40  # mbraceは応答が遅め(~20s)なので長めに
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) boatrace-data-collector"


def find_extractor():
    """LZH(lh5)を解凍できるコマンドを探す。bsdtar(libarchive)系を優先。"""
    env = os.environ.get("BSDTAR", "").strip()
    if env and os.path.exists(env):
        return env
    for name in ("bsdtar", "tar"):
        p = shutil.which(name)
        if p:
            return p
    # Windows同梱 tar.exe（bsdtar実体）
    win = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe")
    if os.path.exists(win):
        return win
    return None


EXTRACTOR = find_extractor()


def fetch_lzh(d):
    ym = d.strftime("%Y%m")
    ymd = d.strftime("%y%m%d")
    url = BASE.format(ym=ym, ymd=ymd)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def unlzh(raw):
    """LZHバイト列を解凍し、内側テキスト(K*.TXT)のバイト列を返す。失敗時None。"""
    with tempfile.TemporaryDirectory() as td:
        lzh = os.path.join(td, "k.lzh")
        with open(lzh, "wb") as f:
            f.write(raw)
        ok = False
        if EXTRACTOR:
            try:
                subprocess.run(
                    [EXTRACTOR, "-xf", lzh, "-C", td],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                ok = True
            except Exception:
                ok = False
        if not ok:
            # フォールバック: lhafile(pip) があれば使う
            try:
                import lhafile
                lf = lhafile.Lhafile(lzh)
                for name in lf.namelist():
                    with open(os.path.join(td, os.path.basename(name)), "wb") as f:
                        f.write(lf.read(name))
                ok = True
            except Exception:
                return None
        txts = glob.glob(os.path.join(td, "*.TXT")) + glob.glob(os.path.join(td, "*.txt"))
        if not txts:
            return None
        with open(txts[0], "rb") as f:
            return f.read()


def parse_kojima(raw):
    data = unlzh(raw)
    if not data:
        return []
    txt = data.decode("shift_jis", "ignore")
    out = []
    in_t = False
    in_p = False
    for ln in txt.split("\n"):
        if SEISEKI in ln:
            in_t = KOJIMA in ln
            in_p = False
            continue
        if not in_t:
            continue
        if PAY in ln:
            in_p = True
            continue
        if in_p:
            m = PAYLINE.match(ln)
            if m:
                rno = int(m.group(1))
                combo = m.group(2) + "-" + m.group(3) + "-" + m.group(4)
                payout = int(m.group(5))
                out.append((rno, combo, payout))
            elif out and not re.search(r"\d", ln):
                in_p = False
    return out


def load_done():
    done = set()
    rows = []
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            r = csv.reader(f)
            header = next(r, None)
            for row in r:
                if len(row) >= 4:
                    rows.append(row)
                    done.add((row[0], row[1]))
    return done, rows


def last_collected_date(rows):
    """CSVに記録済みの最終開催日(datetime.date)。無ければNone。"""
    last = None
    for row in rows:
        hd = row[0]
        if len(hd) == 8 and hd.isdigit() and (last is None or hd > last):
            last = hd
    if last is None:
        return None
    return datetime.date(int(last[0:4]), int(last[4:6]), int(last[6:8]))


def main():
    if EXTRACTOR is None:
        print("WARN: LZH解凍手段が見つかりません。bsdtar/tar を用意するか pip install lhafile。")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    done, rows = load_done()

    ym = os.environ.get("YM", "").strip()
    if ym:
        y = int(ym[:4]); mo = int(ym[4:6])
        start = datetime.date(y, mo, 1)
        if mo == 12:
            nxt = datetime.date(y + 1, 1, 1)
        else:
            nxt = datetime.date(y, mo + 1, 1)
        days = [start + datetime.timedelta(d) for d in range((nxt - start).days)]
    else:
        # daily差分: 前回取得日の翌日 〜 昨日（全期間の再取得はしない）
        kojimay = datetime.date.kojimay()
        yesterday = kojimay - datetime.timedelta(days=1)
        start_env = os.environ.get("START", "").strip()  # YYYYMMDD 明示指定（CSV空のとき用）
        last = last_collected_date(rows)
        if start_env:
            start = datetime.date(int(start_env[0:4]), int(start_env[4:6]), int(start_env[6:8]))
        elif last is not None:
            start = last + datetime.timedelta(days=1)
        else:
            start = yesterday - datetime.timedelta(days=int(os.environ.get("DAYS", "365")))
        days = []
        d = start
        while d <= yesterday:
            days.append(d)
            d += datetime.timedelta(days=1)

    got = 0
    for d in days:
        hd = d.strftime("%Y%m%d")
        if (hd, "1") in done:
            continue
        try:
            raw = fetch_lzh(d)
            recs = parse_kojima(raw)
        except Exception as e:
            print("skip", hd, repr(e))
            time.sleep(SLEEP)
            continue
        if recs:
            for rno, combo, payout in recs:
                rows.append([hd, str(rno), combo, str(payout)])
            got += len(recs)
            print("ok", hd, len(recs))
        time.sleep(SLEEP)

    rows.sort(key=lambda x: (x[0], int(x[1])))
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["hd", "rno", "combo", "payout"])
        w.writerows(rows)
    print("done. new records:", got, "total:", len(rows))


if __name__ == "__main__":
    main()
