# -*- coding: utf-8 -*-
# buildBeforeinfoProbe.py
# beforeinfo収集（fetchPartsExchange.py → docs/data/motorParts.json）の「現在地」を
# 1枚のHTMLに可視化し、収集が空である原因（A:時刻が早すぎ／B:パーサ列ズレ）を
# 現物HTMLで切り分けて記録する調査用ページを生成する。
#
# 重要方針:
#   - fetchPartsExchange.py / motorParts.json のスキーマは一切変更しない（読むだけ）。
#   - 数値はすべて motorParts.json・リポジトリ現物・取得HTMLから機械的に算出する。
#   - 読めない項目は「不明」と表示し、推測で埋めない。
#   - 出力は docs/probe/beforeinfoProbe.html のみ。生HTMLはコミットしない（tmpに置く）。
#   - このページはけん専用。noindex,nofollow を付け、どのページからもリンクしない。
#
# 実行: python scripts/buildBeforeinfoProbe.py
import io
import os
import re
import csv
import sys
import json
import html
import datetime
import tempfile
import urllib.request

# fetchPartsExchange.parse_beforeinfo を「書き換えず」import して現物実証に使う。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import fetchPartsExchange as fpe
    from fetchPartsExchange import parse_beforeinfo
    from bs4 import BeautifulSoup
    HAVE_PARSER = True
    PARSER_IMPORT_ERR = ""
except Exception as e:  # bs4未導入など
    HAVE_PARSER = False
    PARSER_IMPORT_ERR = repr(e)

JST = datetime.timezone(datetime.timedelta(hours=9))

FPE_PATH = os.path.join("scripts", "fetchPartsExchange.py")
PARTS_JSON = os.path.join("docs", "data", "motorParts.json")
RACERS_CSV = os.path.join("docs", "racers", "racers_today.csv")
VENUE_META = os.path.join("docs", "data", "venueMeta.json")
WF_DIR = os.path.join(".github", "workflows")
OUT = os.path.join("docs", "probe", "beforeinfoProbe.html")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 現物検証で「展示タイムらしい値」を拾う正規表現（6.xx 等の展示タイム表記）。判定の裏取り用。
TENJI_RE = re.compile(r"^\d\.\d{2}$")
UNKNOWN = "不明"


def esc(x):
    return html.escape("" if x is None else str(x))


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 1. 何を集めているか（fetchPartsExchange.py から機械抽出）
# ---------------------------------------------------------------------------
def extract_source_facts():
    src = read_text(FPE_PATH)
    base = UNKNOWN
    m = re.search(r'BASE\s*=\s*"([^"]+)"', src)
    if m:
        base = m.group(1)
    return {"base": base, "found": bool(src)}


# ---------------------------------------------------------------------------
# 2. 何をしているか（.github/workflows を fetchPartsExchange で grep）
# ---------------------------------------------------------------------------
def find_workflow():
    """fetchPartsExchange を呼ぶ workflow を特定。cron全行とfetchPartsを起動するif条件を抽出。"""
    hit = None
    if os.path.isdir(WF_DIR):
        for fn in sorted(os.listdir(WF_DIR)):
            p = os.path.join(WF_DIR, fn)
            txt = read_text(p)
            if "fetchPartsExchange" in txt:
                hit = {"file": fn, "text": txt}
                break
    if not hit:
        return None
    txt = hit["text"]
    name_m = re.search(r'(?m)^name:\s*(.+)$', txt)
    hit["name"] = name_m.group(1).strip() if name_m else UNKNOWN
    # schedule の cron 全行
    crons = re.findall(r"(?m)^\s*-\s*cron:\s*['\"]([^'\"]+)['\"]", txt)
    hit["crons"] = crons
    # fetchPartsExchange を起動するステップの if 条件（起動cronの特定）
    gate = None
    for block in re.split(r'(?m)^\s*-\s*name:', txt):
        if "fetchPartsExchange" in block:
            gm = re.search(r'(?m)^\s*if:\s*(.+)$', block)
            if gm:
                gate = gm.group(1).strip()
            break
    hit["gate"] = gate
    return hit


def cron_to_jst(cron):
    """5フィールドcron(UTC)を JST(UTC+9) の時:分文字列へ機械換算。曜日/日/月は原文注記。"""
    parts = cron.split()
    if len(parts) < 2:
        return UNKNOWN
    mn, hr = parts[0], parts[1]
    try:
        mi = int(mn)
        h = int(hr)
    except ValueError:
        return UNKNOWN + "（UTC {} {}）".format(mn, hr)
    jh = (h + 9) % 24
    nextday = (h + 9) >= 24
    label = "JST {:02d}:{:02d}".format(jh, mi)
    if nextday:
        label += "（翌日）"
    return label


# ---------------------------------------------------------------------------
# 3/4. motorParts.json の集計
# ---------------------------------------------------------------------------
FIELD_KEYS = ["展示タイム", "チルト", "部品交換", "プロペラ変更", "モーターNo", "節名"]


def analyze_parts():
    d = load_json(PARTS_JSON)
    if not d or not isinstance(d.get("records"), list):
        return None
    recs = d["records"]
    total = len(recs)
    keys = list(recs[0].keys()) if recs else []

    def nonempty(k):
        if k == "プロペラ変更":
            return sum(1 for r in recs if r.get(k) is True)
        return sum(1 for r in recs if str(r.get(k, "")).strip() != "")

    fill = {k: nonempty(k) for k in FIELD_KEYS}

    # 開催日ごとの件数と取得日時レンジ
    by_date = {}
    for r in recs:
        hd = str(r.get("開催日", ""))
        b = by_date.setdefault(hd, {"count": 0, "times": set()})
        b["count"] += 1
        t = str(r.get("取得日時", "")).strip()
        if t:
            b["times"].add(t)

    # 欠測日（最小〜最大の範囲で1件も無い日）
    dates = sorted([hd for hd in by_date if re.fullmatch(r"\d{8}", hd)])
    missing = []
    if len(dates) >= 2:
        d0 = datetime.datetime.strptime(dates[0], "%Y%m%d").date()
        d1 = datetime.datetime.strptime(dates[-1], "%Y%m%d").date()
        cur = d0
        present = set(dates)
        while cur <= d1:
            s = cur.strftime("%Y%m%d")
            if s not in present:
                missing.append(s)
            cur += datetime.timedelta(days=1)

    zero_fields = [k for k in FIELD_KEYS if fill[k] == 0]

    return {
        "updated": d.get("updated", UNKNOWN) or UNKNOWN,
        "source": d.get("source", UNKNOWN) or UNKNOWN,
        "total": total,
        "keys": keys,
        "fill": fill,
        "by_date": by_date,
        "dates": dates,
        "missing": missing,
        "zero_fields": zero_fields,
        "sample_url": str(recs[0].get("出典URL", "")) if recs else "",
    }


# ---------------------------------------------------------------------------
# 蓄積データの時刻検証（原因A: 取得が全レースの発走前か）
# racers_today.csv と同一開催日について、最早締切より取得が前なら「発走前取得」＝A成立。
# ---------------------------------------------------------------------------
def load_deadlines():
    """racers_today.csv → {(jcd,rno):締切時刻}, その開催日, 最早締切(HH:MM)。"""
    dmap = {}
    hd = ""
    earliest = None
    if not os.path.exists(RACERS_CSV):
        return dmap, hd, earliest
    with open(RACERS_CSV, "r", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            hd = str(r.get("開催日", "")).strip() or hd
            jcd = str(r.get("場コード", "")).zfill(2)
            race = str(r.get("レース", "")).strip()
            rm = re.match(r"(\d+)", race)
            rno = rm.group(1) if rm else ""
            t = str(r.get("締切時刻", "")).strip()
            if jcd and rno and t:
                dmap[(jcd, rno)] = t
                if earliest is None or t < earliest:
                    earliest = t
    return dmap, hd, earliest


def timing_check(parts, deadlines_hd, earliest_deadline):
    """同一開催日について、全レコードの取得時刻が最早締切より前か判定。
    return (判定可能か, A成立か, 説明文)"""
    if not parts or not earliest_deadline or not deadlines_hd:
        return False, False, "racers_today.csv の締切時刻が読めず、蓄積側の時刻検証は" + UNKNOWN
    b = parts["by_date"].get(deadlines_hd)
    if not b or not b["times"]:
        return False, False, "開催日 {} の取得日時が無く時刻検証は{}".format(deadlines_hd, UNKNOWN)
    # 取得日時は "YYYY-MM-DD HH:MM"。時刻部だけ取り出して比較。
    max_t = max(t.split(" ")[-1] for t in b["times"])
    before = max_t < earliest_deadline
    txt = ("開催日 {} の最終取得時刻 {} が最早締切 {} より{}。"
           .format(deadlines_hd, max_t, earliest_deadline,
                   "前＝全レース発走前（直前情報未公開の時刻に取得）" if before
                   else "後（発走後の取得を含む）"))
    return True, before, txt


# ---------------------------------------------------------------------------
# 現物検証：本日開催中の1レースを選び beforeinfo を取得 → parse_beforeinfo で実証
# ---------------------------------------------------------------------------
def pick_target():
    """venueMeta と racers_today から「発走済み(直前情報公開済み)」の1レースを選ぶ。
    現在JST時刻で締切<=now の最も遅いレース。無ければ最早レース。"""
    meta = load_json(VENUE_META) or {}
    venues = meta.get("venues", {}) if isinstance(meta, dict) else {}
    deadlines, hd, _ = load_deadlines()
    now = datetime.datetime.now(JST)
    nowhm = now.strftime("%H:%M")
    cands = []
    for (jcd, rno), t in deadlines.items():
        if jcd in venues:
            cands.append((t, jcd, rno))
    if not cands:
        # フォールバック：venueMetaの先頭場・1R
        if venues:
            jcd = sorted(venues.keys())[0]
            hd = str(venues[jcd].get("開催日", "")) or hd
            return {"jcd": jcd, "vname": str(venues[jcd].get("場名", "")),
                    "rno": "1", "hd": hd, "deadline": UNKNOWN, "now": nowhm}
        return None
    past = [c for c in cands if c[0] <= nowhm]
    chosen = max(past) if past else min(cands)
    t, jcd, rno = chosen
    vname = str(venues.get(jcd, {}).get("場名", ""))
    hd = str(venues.get(jcd, {}).get("開催日", "")) or hd
    return {"jcd": jcd, "vname": vname, "rno": rno, "hd": hd,
            "deadline": t, "now": nowhm}


def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.getcode(), r.read().decode("utf-8", errors="replace"), ""
    except Exception as e:
        return None, "", repr(e)


def inspect_tbodies(html_text):
    """選手行と判定される各tbodyについて、先頭trのtdを index:text で全列挙。
    parse_beforeinfo と同じ検出ロジック（登番リンクを含むtd）をこちら側で再現（本体は改変しない）。"""
    soup = BeautifulSoup(html_text, "html.parser")
    toban_re = re.compile(r"toban=(\d{4})")
    result = []
    for tbody in soup.find_all("tbody"):
        tr = tbody.find("tr")
        if not tr:
            continue
        tds = tr.find_all("td", recursive=False)
        name_idx = None
        toban = ""
        for i, td in enumerate(tds):
            a = td.find("a", href=toban_re)
            if a:
                mm = toban_re.search(a.get("href", ""))
                if mm:
                    toban = mm.group(1)
                    name_idx = i
                    break
        if name_idx is None:
            continue
        cells = []
        for i, td in enumerate(tds):
            txt = re.sub(r"\s+", " ", td.get_text(" ", strip=True)).strip()
            cells.append((i, txt))
        # +2〜+5 が実際に指すセル
        rel = {}
        for k in (2, 3, 4, 5):
            idx = name_idx + k
            rel[k] = (idx, cells[idx][1] if 0 <= idx < len(cells) else "(範囲外)")
        result.append({"toban": toban, "name_idx": name_idx,
                       "cells": cells, "rel": rel})
    return result


def run_probe():
    """現物取得を試みる。到達不可なら unreachable=True で URL を返す（生HTMLはtmpのみ）。"""
    base = extract_source_facts()["base"]
    tgt = pick_target()
    if not tgt:
        return {"ok": False, "unreachable": True, "err": "venueMeta/racers から対象レースを選べず",
                "url": UNKNOWN, "target": None}
    url = base.replace("{rno}", str(tgt["rno"])).replace("{jcd}", tgt["jcd"]).replace("{hd}", tgt["hd"])
    res = {"url": url, "target": tgt, "now": tgt["now"]}
    if not HAVE_PARSER:
        res.update({"ok": False, "unreachable": True,
                    "err": "parse_beforeinfo を import 不可: " + PARSER_IMPORT_ERR})
        return res
    code, htmltext, err = fetch_html(url)
    if code != 200 or not htmltext:
        res.update({"ok": False, "unreachable": True, "err": err or ("HTTP " + str(code))})
        return res
    # 生HTMLは一時ディレクトリに退避（リポジトリにはコミットしない）
    try:
        tmpdir = tempfile.mkdtemp(prefix="beforeinfoProbe_")
        with open(os.path.join(tmpdir, "raw.html"), "w", encoding="utf-8") as f:
            f.write(htmltext)
        res["tmp"] = tmpdir
    except Exception:
        res["tmp"] = UNKNOWN
    rows = parse_beforeinfo(htmltext)
    tb = inspect_tbodies(htmltext)
    res.update({"ok": True, "unreachable": False, "err": "",
                "http": code, "rows": rows, "tbodies": tb})
    # 判定：発走後取得で 展示/チルト が取れれば A、取れず td列に展示値が別indexにあれば B
    got_field = any((str(r.get("展示タイム", "")).strip() or str(r.get("チルト", "")).strip())
                    for r in rows)
    misaligned = False
    for t in tb:
        for i, txt in t["cells"]:
            if TENJI_RE.match(txt) and i != t["name_idx"] + 2:
                misaligned = True
    res["got_field"] = got_field
    res["misaligned"] = misaligned
    if got_field:
        res["verdict"] = "A"
    elif misaligned:
        res["verdict"] = "B"
    else:
        res["verdict"] = UNKNOWN
    return res


# ---------------------------------------------------------------------------
# HTML生成
# ---------------------------------------------------------------------------
def build_html():
    now = datetime.datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    srcf = extract_source_facts()
    wf = find_workflow()
    parts = analyze_parts()
    deadlines, dhd, earliest = load_deadlines()
    tc_ok, tc_a, tc_txt = timing_check(parts, dhd, earliest)
    probe = run_probe()

    P = []
    A = P.append
    A("<!-- 自動生成: scripts/buildBeforeinfoProbe.py。手編集しない。 -->")
    A('<meta charset="utf-8">')
    A('<meta name="viewport" content="width=device-width, initial-scale=1">')
    A('<meta name="robots" content="noindex, nofollow">')
    A("<title>beforeinfo収集 現在地プローブ</title>")
    A("<style>")
    A("body{font-family:-apple-system,system-ui,sans-serif;margin:0;padding:12px;"
      "background:#f7f7f8;color:#1a1a1a;line-height:1.6;font-size:15px}")
    A("h1{font-size:19px;margin:8px 0}h2{font-size:16px;margin:22px 0 8px;"
      "border-left:5px solid #2b6cb0;padding-left:8px}")
    A("h3{font-size:14px;margin:16px 0 6px;color:#2b6cb0}")
    A(".card{background:#fff;border:1px solid #e2e2e5;border-radius:8px;padding:12px;margin:10px 0}")
    A("table{border-collapse:collapse;width:100%;font-size:13px;overflow-x:auto;display:block}")
    A("th,td{border:1px solid #ddd;padding:4px 6px;text-align:left;white-space:nowrap}")
    A("th{background:#eef2f7}")
    A(".ok{color:#1a7f37;font-weight:bold}.ng{color:#c1121f;font-weight:bold}")
    A(".muted{color:#666;font-size:12px}code{background:#eee;padding:1px 4px;border-radius:3px;"
      "font-size:12px;word-break:break-all}")
    A(".empty{color:#c1121f}.bignum{font-size:22px;font-weight:bold}")
    A("</style>")

    A("<h1>beforeinfo収集 現在地プローブ</h1>")
    A('<p class="muted">生成: {} JST ／ このページはけん専用（noindex）。どのページからもリンクしない。</p>'.format(esc(now)))

    # ---- 1. 何を集めているか ----
    A("<h2>1. 何を集めているか</h2>")
    A('<div class="card">')
    A("<p><b>データ源:</b> {}</p>".format(esc(parts["source"] if parts else UNKNOWN)))
    A("<p><b>ベースURL:</b> <code>{}</code></p>".format(esc(srcf["base"])))
    if parts:
        A("<p><b>収集項目（motorParts.json 実レコードのキー）:</b></p>")
        A("<p>" + " / ".join("<code>{}</code>".format(esc(k)) for k in parts["keys"]) + "</p>")
        A("<p><b>出典URLの実例:</b><br><code>{}</code></p>".format(esc(parts["sample_url"] or UNKNOWN)))
    else:
        A("<p class='ng'>motorParts.json が読めず、収集項目は{}。</p>".format(UNKNOWN))
    A("</div>")

    # ---- 2. 何をしているか ----
    A("<h2>2. 何をしているか</h2>")
    A('<div class="card">')
    if wf:
        A("<p><b>実行元ワークフロー:</b> {} <span class='muted'>({})</span></p>".format(
            esc(wf["name"]), esc(wf["file"])))
        if wf["gate"]:
            A("<p><b>fetchPartsExchange 起動条件(if):</b> <code>{}</code></p>".format(esc(wf["gate"])))
        if wf["crons"]:
            A("<p><b>schedule の cron 全行 → JST換算:</b></p><table><tr><th>cron(UTC)</th><th>JST</th></tr>")
            for c in wf["crons"]:
                A("<tr><td><code>{}</code></td><td>{}</td></tr>".format(esc(c), esc(cron_to_jst(c))))
            A("</table>")
            A("<p class='muted'>※上記は実行元WFの全schedule。実際に fetchPartsExchange を叩くのは"
              " if 条件に一致する回のみ。</p>")
        else:
            A("<p class='muted'>schedule cron 行なし。</p>")
    else:
        A("<p class='ng'>実行元WFなし（.github/workflows を fetchPartsExchange で grep して不検出）。"
          "＝手動実行のみ。</p>")
    A("<h3>処理の流れ</h3>")
    A("<p class='muted'>① beforeinfo(公式直前情報)を各場×12R取得 → ② parse_beforeinfo で"
      "枠/登番/展示/チルト/プロペラ/部品交換を抽出<br>"
      "③ racers_today.csv の登番→モーターNo/氏名を紐付け → ④ motorParts.json へ重複除いてappend蓄積</p>")
    A("</div>")

    # ---- 3. 何が完了しているか ----
    A("<h2>3. 何が完了しているか</h2>")
    A('<div class="card">')
    if parts:
        A("<p><b>総レコード数:</b> <span class='bignum'>{}</span></p>".format(parts["total"]))
        A("<p><b>最終更新(updated):</b> {}</p>".format(esc(parts["updated"])))
        A("<h3>各項目の充填率（非空件数／総数）</h3>")
        A("<table><tr><th>項目</th><th>非空</th><th>総数</th><th>充填率</th></tr>")
        tot = parts["total"] or 1
        for k in FIELD_KEYS:
            n = parts["fill"][k]
            pct = 100.0 * n / tot
            cls = "ng" if n == 0 else "ok"
            note = "（Trueの件数）" if k == "プロペラ変更" else ""
            A("<tr><td>{}{}</td><td class='{}'>{}</td><td>{}</td><td class='{}'>{:.1f}%</td></tr>".format(
                esc(k), note, cls, n, parts["total"], cls, pct))
        A("</table>")
        A("<h3>収集済み開催日と各日の件数</h3>")
        A("<table><tr><th>開催日</th><th>件数</th><th>取得時刻レンジ</th></tr>")
        for hd in parts["dates"]:
            b = parts["by_date"][hd]
            times = sorted(t.split(" ")[-1] for t in b["times"]) if b["times"] else []
            rng = "{}〜{}".format(times[0], times[-1]) if times else UNKNOWN
            A("<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(esc(hd), b["count"], esc(rng)))
        A("</table>")
    else:
        A("<p class='ng'>motorParts.json が読めず、完了状況は{}。</p>".format(UNKNOWN))
    A("</div>")

    # ---- 4. 何が未完了・未確定か ----
    A("<h2>4. 何が未完了・未確定か</h2>")
    A('<div class="card">')
    if parts:
        A("<h3>充填率0%の項目</h3>")
        if parts["zero_fields"]:
            A("<p class='ng'>" + " / ".join(esc(k) for k in parts["zero_fields"]) + "</p>")
        else:
            A("<p class='ok'>0%の項目なし。</p>")
        A("<h3>欠測日（収集済み最小〜最大の範囲で0件の日）</h3>")
        if parts["missing"]:
            A("<p class='ng'>" + " / ".join(esc(m) for m in parts["missing"]) + "</p>")
        else:
            A("<p class='ok'>範囲内の欠測日なし。</p>")
        A("<h3>蓄積データの時刻検証（原因A: 取得が全発走前か）</h3>")
        A("<p>{}</p>".format(esc(tc_txt)))
        A("<h3>原因判定</h3>")
        verdict_line = decide_verdict(probe, tc_ok, tc_a, dhd)
        A("<p class='bignum'>{}</p>".format(esc(verdict_line)))
    else:
        A("<p class='ng'>motorParts.json が読めず、未完了判定は{}。</p>".format(UNKNOWN))
    A("</div>")

    # ---- 現物検証 ----
    A("<h2>現物検証（beforeinfo 1枚を parse_beforeinfo に通す）</h2>")
    A('<div class="card">')
    tgt = probe.get("target")
    if tgt:
        A("<table>")
        A("<tr><th>jcd</th><td>{}</td><th>場名</th><td>{}</td></tr>".format(
            esc(tgt["jcd"]), esc(tgt["vname"])))
        A("<tr><th>rno</th><td>{}R</td><th>hd</th><td>{}</td></tr>".format(
            esc(tgt["rno"]), esc(tgt["hd"])))
        A("<tr><th>取得時刻(JST)</th><td>{}</td><th>締切/発走時刻</th><td>{}</td></tr>".format(
            esc(probe.get("now", UNKNOWN)), esc(tgt.get("deadline", UNKNOWN))))
        A("</table>")
    A("<p><b>対象URL:</b><br><code>{}</code></p>".format(esc(probe.get("url", UNKNOWN))))

    if probe.get("unreachable"):
        A("<p class='ng'>この実行環境から boatrace.jp に到達できず、現物取得は未実施。</p>")
        A("<p class='muted'>理由: <code>{}</code></p>".format(esc(probe.get("err", UNKNOWN))))
        A("<p>けんが iPhone/PC で上記URLを開いて保存し、ローカル（boatrace.jp到達可）で"
          " <code>python scripts/buildBeforeinfoProbe.py</code> を再実行すると、"
          "下記の6艇分の実値・td全列挙・A/B判定が自動で埋まる。</p>")
    elif probe.get("ok"):
        rows = probe.get("rows", [])
        A("<p class='ok'>取得成功（HTTP {}）／ parse_beforeinfo 返り {} 艇。</p>".format(
            esc(probe.get("http")), len(rows)))
        A("<h3>parse_beforeinfo の返り値（6艇分そのまま）</h3>")
        A("<table><tr><th>枠</th><th>登番</th><th>展示タイム</th><th>チルト</th>"
          "<th>プロペラ変更</th><th>部品交換</th></tr>")
        for r in rows:
            def cell(v):
                s = str(v).strip()
                return "<span class='empty'>(空)</span>" if s == "" else esc(s)
            A("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                esc(r.get("枠", "")), esc(r.get("登番", "")),
                cell(r.get("展示タイム", "")), cell(r.get("チルト", "")),
                esc(r.get("プロペラ変更")), cell(r.get("部品交換", ""))))
        A("</table>")
        A("<h3>選手tbody の td 全列挙（index : セルのテキスト）＝原因B特定の核</h3>")
        for t in probe.get("tbodies", []):
            A("<p class='muted'>登番 {} ／ name_idx = {} ／ "
              "+2={} +3={} +4={} +5={}</p>".format(
                esc(t["toban"]), t["name_idx"],
                esc("idx{}:{}".format(*t["rel"][2])), esc("idx{}:{}".format(*t["rel"][3])),
                esc("idx{}:{}".format(*t["rel"][4])), esc("idx{}:{}".format(*t["rel"][5]))))
            A("<table><tr><th>index</th><th>セルのテキスト</th></tr>")
            for i, txt in t["cells"]:
                disp = "<span class='empty'>(空)</span>" if txt == "" else esc(txt)
                A("<tr><td>{}</td><td>{}</td></tr>".format(i, disp))
            A("</table>")
        A("<h3>展示タイム/チルトの生表現</h3>")
        A("<p class='muted'>上のtd全列挙の生テキストで、空セル・記号・セル欠落のいずれかを確認できる"
          "（「空欄＝交換なし」と「未公開」の裁定材料）。</p>")
    else:
        A("<p class='ng'>現物検証：{}</p>".format(esc(probe.get("err", UNKNOWN))))

    A("<h3>7/14・7/15 の状況（GitHub Actions 実行履歴）</h3>")
    A("<p class='muted'>本スクリプトは Actions実行履歴API に到達しないため、ここでは{}。"
      "けんが GitHub Actions の「{}」実行履歴で 7/14・7/15 の発火有無/成否を確認のこと。</p>".format(
        UNKNOWN, esc(wf["name"]) if wf else "実行元WF"))
    A("</div>")

    return "\n".join(P)


def decide_verdict(probe, tc_ok, tc_a, dhd):
    """現物 → 蓄積時刻 の順で原因を一行に。断定不可なら不明。"""
    v = probe.get("verdict")
    if probe.get("ok") and v == "A":
        return "原因A（時刻）：発走後の現物取得で展示/チルトが取得できた＝収集ロジックは正常、過去の空は取得時刻が早すぎたため。"
    if probe.get("ok") and v == "B":
        return "原因B（パーサ）：現物td列で展示タイム値が name_idx+2 以外に存在＝相対列がズレている。"
    # 現物未取得 → 蓄積データの時刻検証で裏取り
    if tc_ok and tc_a:
        return ("原因A（時刻）が蓄積データから成立：全レコードの取得時刻が当該開催日の最早締切より前"
                "＝発走前で直前情報未公開。※Bの併存有無は正しい時刻での現物取得（上記現物検証）で要確認。")
    if tc_ok and not tc_a:
        return "不明：取得は発走後を含むのに空。原因B（パーサ）の可能性が高いが、現物td列の確認が必要。"
    return "不明：現物未取得かつ蓄積側の時刻検証も未確定。"


def main():
    html_out = build_html()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html_out)
    print("生成:", OUT, "(", len(html_out), "bytes )")


if __name__ == "__main__":
    main()
