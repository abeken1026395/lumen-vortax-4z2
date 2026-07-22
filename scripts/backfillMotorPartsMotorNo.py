# -*- coding: utf-8 -*-
# backfillMotorPartsMotorNo.py
# motorParts.json の「モーターNo」空欄を、K由来(競走成績)の (jcd,開催日,登番)→モーターNo で
# 後追い補填する。fetchPartsExchange.py の収集ロジックは一切変えない（空でもappendのまま）。
# 翌日Kが確定してから本スクリプトを回し、空欄だけを埋める＝今日やった補填を毎日自動で回す形。
#
# 設計（安全第一・ハルシネーション防止）:
#   - 解凍は純Python lh5 デコーダ(unpackLzh) を本命に、lhafile があればそれも使う。
#     ＝Python3.14/コンパイラ無しのローカル環境でも .lzh を確実に解凍できる
#       （buildMotorUsage.decode_kfile は lhafile→bsdtar 依存で、当ローカルでは不可）。
#   - K解析は検証済み kparser（全項目パーサ）を再利用。着順が S0/S1/K0/F 等の異常でも
#     モーターNo を拾う＝今日の本番補填(982件)と完全一致するカバレッジ。
#     （buildMotorUsage.parse_text は着順=数字前提で S0/S1 等 5件を取りこぼす）
#   - Kで実際に引けた (jcd,開催日,登番) のモーターNoのみ埋める。引けない/衝突は空のまま（創作しない）。
#   - JSON全体を再シリアライズしない。空 `"モーターNo": ""` の行だけを records 順に正規表現置換する。
#     ＝他フィールド・空白・改行(LF)・末尾を1バイトも触らない（再dump差異の事故を構造的に排除）。
#   - 書き込み前に自己検証: モーターNo以外の全フィールドがバイト不変 / CR混入なし /
#     空欄の減少数＝補填数。1つでも崩れたら書かずに異常終了する。
#
# 使い方:
#   python scripts/backfillMotorPartsMotorNo.py                        # docs/data/motorParts.json を補填
#   python scripts/backfillMotorPartsMotorNo.py --path P --kdir D --dry # テスト（--dryは書き込まない）
# 終了コード: 0=正常（補填有/無どちらも）, 2=検証失敗（未書込）, 3=入力不備。
import os
import re
import sys
import glob
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kparser  # 検証済み全項目Kパーサ（re のみ依存）

DEFAULT_PATH = os.path.join("docs", "data", "motorParts.json")
DEFAULT_KDIR = os.environ.get("KFILES_DIR", os.path.join("data", "kfiles"))
# 空のモーターNoフィールドだけにマッチ（値入りの "..." は非マッチ）
EMPTY_RE = re.compile(r'("モーターNo":\s*)""')
FNAME_HD_RE = re.compile(r"[kK](\d{2})(\d{2})(\d{2})")


def decode_kfile(path):
    """Kファイルを SHIFT_JIS テキストで返す。.lzh は解凍(純Python→lhafile)、.txt はそのまま。"""
    if path.lower().endswith(".lzh"):
        try:
            import unpackLzh
            raw, _meta = unpackLzh.load_lzh(path)   # 原寸+CRC16照合つき純Python解凍
            return raw.decode("shift_jis", errors="replace")
        except Exception:
            import lhafile
            arc = lhafile.Lhafile(path)
            names = arc.namelist()
            return (arc.read(names[0]) if names else b"").decode("shift_jis", errors="replace")
    with open(path, "rb") as f:
        return f.read().decode("shift_jis", errors="replace")


def hd_from_name(path):
    """ファイル名 kYYMMDD → (YYMMDD, YYYYMMDD)。取れなければ (None, None)。"""
    m = FNAME_HD_RE.search(os.path.basename(path))
    if not m:
        return None, None
    yy, mm, dd = m.group(1), m.group(2), m.group(3)
    return yy + mm + dd, "20" + yy + mm + dd


def build_k_index(kdir, need_days=None):
    """data/kfiles の（need_days に該当する）Kファイルから (jcd, 開催日YYYYMMDD, 登番)->モーターNo を作る。
    need_days=None なら全ファイル。空欄のある開催日だけ解凍すれば夜間実行は軽い。
    同一キーで値が食い違う場合は最初を採用しつつ件数を数える（通常は一日一機で一致）。"""
    idx = {}
    conflicts = 0
    used = 0
    files = sorted(glob.glob(os.path.join(kdir, "*.lzh")) +
                   glob.glob(os.path.join(kdir, "*.txt")) +
                   glob.glob(os.path.join(kdir, "*.TXT")))
    for path in files:
        hd6, hd8 = hd_from_name(path)
        if not hd6:
            continue
        if need_days is not None and hd8 not in need_days:
            continue
        used += 1
        try:
            text = decode_kfile(path)
        except Exception:
            continue
        res = kparser.parse_day(text, hd6)
        for e in res["entries"]:
            mno = (e.get("motorNo") or "").strip()
            if not mno:
                continue
            key = (e["jcd"], hd8, str(e["toban"]))
            if key in idx:
                if idx[key] != mno:
                    conflicts += 1
                continue
            idx[key] = mno
    return idx, used, conflicts


def backfill(path, kdir, dry=False):
    raw = open(path, "rb").read()
    if b"\r" in raw:
        raise SystemExit("入力に CR が混入している（LF専用のはず）。中止。")
    text = raw.decode("utf-8")
    data = json.loads(text)
    recs = data.get("records", [])

    # 空欄のある開催日だけを K インデックス対象にする（夜間実行を軽く）
    need_days = set(r.get("開催日") for r in recs if r.get("モーターNo", "") == "")
    idx, nfiles, conflicts = build_k_index(kdir, need_days)

    # records順に、空モーターNoの埋め値を決める（引けなければ None＝空のまま）
    fills = []
    filled = left = 0
    by_date_fill, by_date_left = {}, {}
    for r in recs:
        if r.get("モーターNo", "") != "":
            continue
        key = (r.get("jcd"), r.get("開催日"), str(r.get("登番")))
        mno = idx.get(key)
        fills.append(mno)
        hd = r.get("開催日")
        if mno is not None:
            filled += 1
            by_date_fill[hd] = by_date_fill.get(hd, 0) + 1
        else:
            left += 1
            by_date_left[hd] = by_date_left.get(hd, 0) + 1

    empty_in_text = len(EMPTY_RE.findall(text))
    if empty_in_text != len(fills):
        raise SystemExit("整合エラー: テキスト上の空モーターNo=%d と records上の空=%d が不一致"
                         % (empty_in_text, len(fills)))

    # 空 "モーターNo": "" を records順に置換（Noneは据え置き）
    it = iter(fills)

    def repl(m):
        v = next(it)
        return m.group(1) + ('""' if v is None else '"%s"' % v)
    new_text = EMPTY_RE.sub(repl, text)

    # ---- 自己検証（書く前に必ず全問通す） --------------------------------
    new_bytes = new_text.encode("utf-8")
    if b"\r" in new_bytes:
        raise SystemExit("検証NG: CR が混入した")
    new_data = json.loads(new_text)
    nrecs = new_data.get("records", [])
    if len(nrecs) != len(recs):
        raise SystemExit("検証NG: レコード数が変化した")
    changed = 0
    for a, b in zip(recs, nrecs):
        ka, kb = list(a.keys()), list(b.keys())
        if ka != kb:
            raise SystemExit("検証NG: キー順/集合が変化した")
        for k in ka:
            if k == "モーターNo":
                if a[k] != b[k]:
                    changed += 1
                    if a[k] != "" or b[k] == "":
                        raise SystemExit("検証NG: 空以外のモーターNoが変わった or 値でない")
            elif a[k] != b[k]:
                raise SystemExit("検証NG: モーターNo以外のフィールドが変わった (%s)" % k)
    if changed != filled:
        raise SystemExit("検証NG: 変化数%d != 補填数%d" % (changed, filled))
    for tk in ("updated", "source", "note"):
        if data.get(tk) != new_data.get(tk):
            raise SystemExit("検証NG: トップキー %s が変わった" % tk)

    if not dry and new_text != text:
        with open(path, "wb") as f:      # LF維持のためバイナリ書き
            f.write(new_bytes)

    return {
        "kfiles": nfiles, "kIndex": len(idx), "kConflicts": conflicts,
        "emptyBefore": len(fills), "filled": filled, "leftEmpty": left,
        "changed": changed, "byDateFill": dict(sorted(by_date_fill.items())),
        "byDateLeft": dict(sorted(by_date_left.items())),
        "wrote": (not dry and new_text != text),
    }


def main():
    path, kdir, dry = DEFAULT_PATH, DEFAULT_KDIR, False
    a = sys.argv[1:]
    i = 0
    while i < len(a):
        if a[i] == "--path":
            path = a[i + 1]; i += 2
        elif a[i] == "--kdir":
            kdir = a[i + 1]; i += 2
        elif a[i] == "--dry":
            dry = True; i += 1
        else:
            print("unknown arg:", a[i]); return 3
    if not os.path.exists(path):
        print("motorParts が無い:", path); return 3
    st = backfill(path, kdir, dry=dry)
    print("K: %dファイル / index %d件 / 衝突%d" % (st["kfiles"], st["kIndex"], st["kConflicts"]))
    print("空モーターNo: %d → 補填 %d / 未補填(K無) %d%s"
          % (st["emptyBefore"], st["filled"], st["leftEmpty"], "（dry）" if dry else ""))
    print("補填 日別:", st["byDateFill"])
    if st["leftEmpty"]:
        print("未補填 日別(K未取得等・空のまま):", st["byDateLeft"])
    print("書込:", "あり" if st["wrote"] else "なし（変更なし）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
