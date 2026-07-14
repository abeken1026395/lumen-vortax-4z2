# -*- coding: utf-8 -*-
"""
mbrace公式の競走成績(Kファイル)を日付範囲で一括ダウンロードし data/kfiles/ に置く。
置いたあと scripts/buildMotorUsage.py を実行すると docs/data/motorUsage.json が出る。

出力: data/kfiles/kYYMMDD.lzh （SHIFT_JIS本文のLZH。解凍はしない＝配布物そのまま）

環境変数:
  START      … 開始日 YYYYMMDD（既定 20260401）
  END        … 終了日 YYYYMMDD（既定 20260708、両端含む）
  KFILES_DIR … 保存先（既定 data/kfiles）
  FORCE      … 1 で既存ファイルも再取得
"""
import os
import sys
import time
import datetime
import urllib.error
import urllib.request

BASE = "https://www1.mbrace.or.jp/od2/K/{ym}/k{ymd}.lzh"
KFILES_DIR = os.environ.get("KFILES_DIR", os.path.join("data", "kfiles"))

SLEEP = 1.0      # 公式サーバ負荷軽減（他スクレイプ系と同じ既定）
TIMEOUT = 40     # mbraceは応答が遅め(~20s)なので長めに
RETRY = 3        # 一時エラーのみ再試行
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) boatrace-data-collector"


def daterange(start, end):
    d = start
    while d <= end:
        yield d
        d += datetime.timedelta(days=1)


def parse_ymd(s, default):
    s = (s or "").strip()
    if not s:
        return default
    return datetime.date(int(s[0:4]), int(s[4:6]), int(s[6:8]))


def is_lzh(raw):
    """LZHの体裁か（ヘッダ3〜7バイト目が圧縮法 -lhN-）。HTMLエラーページ等を弾く。"""
    return len(raw) > 16 and raw[2:5] == b"-lh" and raw[6:7] == b"-"


def fetch(d):
    """1日分を取得。(bytes | None, 理由) を返す。Noneは当日分が存在しない(404)。"""
    url = BASE.format(ym=d.strftime("%Y%m"), ymd=d.strftime("%y%m%d"))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last = None
    for attempt in range(1, RETRY + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read(), "ok"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "404(開催なし)"
            last = "HTTP {}".format(e.code)
        except Exception as e:
            last = repr(e)
        if attempt < RETRY:
            time.sleep(SLEEP * attempt)
    raise RuntimeError(last)


def main():
    start = parse_ymd(os.environ.get("START"), datetime.date(2026, 4, 1))
    end = parse_ymd(os.environ.get("END"), datetime.date(2026, 7, 8))
    force = os.environ.get("FORCE", "") == "1"
    os.makedirs(KFILES_DIR, exist_ok=True)

    days = list(daterange(start, end))
    print("対象: {} 〜 {}（{}日） → {}".format(start, end, len(days), KFILES_DIR))

    got = skipped = absent = 0
    failed = []
    for d in days:
        name = "k{}.lzh".format(d.strftime("%y%m%d"))
        path = os.path.join(KFILES_DIR, name)
        if not force and os.path.exists(path) and os.path.getsize(path) > 0:
            skipped += 1
            continue
        try:
            raw, why = fetch(d)
        except Exception as e:
            print("  [fail] {} … {}".format(name, e))
            failed.append((name, str(e)))
            time.sleep(SLEEP)
            continue
        if raw is None:
            print("  [--] {} … {}".format(name, why))
            absent += 1
            time.sleep(SLEEP)
            continue
        if not is_lzh(raw):
            print("  [fail] {} … LZHでない応答({}B)".format(name, len(raw)))
            failed.append((name, "not lzh"))
            time.sleep(SLEEP)
            continue
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, path)  # 中断時に壊れたファイルを残さない
        got += 1
        print("  [ok] {} … {}B".format(name, len(raw)))
        time.sleep(SLEEP)

    print("完了: 取得{} / 既存スキップ{} / 開催なし{} / 失敗{}".format(
        got, skipped, absent, len(failed)))
    if failed:
        print("失敗一覧（欠けたまま＝補完しない）:")
        for name, why in failed:
            print("  {} … {}".format(name, why))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
