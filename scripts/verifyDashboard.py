#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verifyDashboard.py — 予想（引き算スコアの判定）の荒れ判別精度を可視化する診断ツール（第1層）。

賭けの損益ではなく「どの場で・いつ 荒れを当てられているか」の判定精度メーター。
verify_log.csv を読むだけの完全オフラインGUI（config・ネットワーク接続なし）。

読むデータ: リポ直下 verify_log.csv
  列: 日付, 場コード, レース, 判定, 主役艇, スコア, 着順, 配当, 波乱正誤, 主役正誤

集計定義（司令塔で実データ検証済み・厳守）:
  荒れ        = 配当 >= 5000（HARANTH 固定）
  有効行      = 配当を数値化できる行のみ（カンマ除去して float）
  母集団荒れ率 = 有効行のうち荒れの割合
  判別力(pt)  = 対象群の荒れ率 − 母集団荒れ率
  判定別      = 堅め/波乱/混戦 でgroupby
  場別        = 判定=波乱 の行を 場コード でgroupby → 判別力
  月次        = 日付[:6] でgroupby、判定=波乱 の判別力推移
  スコア帯    = スコアを0.05刻みでbin化し各帯の荒れ率（母集団線を重ねる）

不変条件: verify_log.csv は読み取り専用（書き換え・生成しない）。predictions/・公開docs/・HARANTH は触らない。

exe化（PyInstaller・リポにバイナリは入れない。dist/ build/ *.spec は .gitignore 済み）:
    pyinstaller --onefile --noconsole scripts/verifyDashboard.py

依存: matplotlib のみ（pandas不要・csvモジュールで足りる）。GUIは Python3標準の tkinter。
"""

import csv
import os
import sys

import logging
import matplotlib
logging.getLogger('matplotlib.font_manager').setLevel(logging.ERROR)  # 副次フォント不在の findfont 警告を抑制
matplotlib.rcParams['font.family'] = ['IPAGothic', 'Noto Sans CJK JP', 'sans-serif']
matplotlib.rcParams['axes.unicode_minus'] = False
from matplotlib.figure import Figure

HARANTH = 5000  # 3連単この額以上を「荒れ」とする固定閾値（司令塔検証済み・動かさない）

venueNames = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川',
    '06': '浜名湖', '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国',
    '11': 'びわこ', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀',
    '16': '児島', '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村',
}
judgeOrder = ['堅め', '波乱', '混戦']
posColor = '#2f7be2'   # 正の判別力＝青
negColor = '#e23b3b'   # 負の判別力＝赤


def defaultCsvPath():
    """リポ直下（このスクリプトの2つ上）の verify_log.csv を既定にする。無ければカレント。"""
    here = os.path.dirname(os.path.abspath(__file__))
    repoRoot = os.path.dirname(here)
    cand = os.path.join(repoRoot, 'verify_log.csv')
    return cand if os.path.exists(cand) else 'verify_log.csv'


def toFloat(text):
    """カンマ除去して float。数値化できなければ None。"""
    if text is None:
        return None
    try:
        return float(str(text).replace(',', '').strip())
    except (ValueError, AttributeError):
        return None


def loadRows(path):
    """verify_log.csv を読み取り専用で読む。行はそのままdictのリストで返す。"""
    with open(path, encoding='utf-8-sig', newline='') as fp:
        return list(csv.DictReader(fp))


def validRowsOf(rows):
    """有効行＝配当が数値化できる行のみ。荒れフラグを添えて返す。"""
    out = []
    for r in rows:
        pay = toFloat(r.get('配当'))
        if pay is None:
            continue
        out.append((r, pay >= HARANTH))
    return out


def rateOf(pairs):
    """(row, isHaran) のリストの荒れ率（0-100%）。空なら None。"""
    if not pairs:
        return None
    return 100.0 * sum(1 for _, h in pairs if h) / len(pairs)


def computeSummary(rows):
    """母集団荒れ率と、判定別（堅め/波乱/混戦）の判別力(pt)を返す。"""
    valid = validRowsOf(rows)
    base = rateOf(valid)
    result = {'baseRate': base, 'total': len(valid), 'byJudge': {}}
    if base is None:
        return result
    for judge in judgeOrder:
        sub = [(r, h) for (r, h) in valid if r.get('判定') == judge]
        rt = rateOf(sub)
        result['byJudge'][judge] = {
            'rate': rt, 'edge': (None if rt is None else rt - base), 'n': len(sub)}
    return result


def computeVenueRanking(rows, ascending=False):
    """判定=波乱 の行を場コードでgroupby → 判別力(pt)。件数併記。降順/昇順。"""
    valid = validRowsOf(rows)
    base = rateOf(valid)
    haran = [(r, h) for (r, h) in valid if r.get('判定') == '波乱']
    groups = {}
    for r, h in haran:
        code = (r.get('場コード') or '').strip().zfill(2)
        groups.setdefault(code, []).append((r, h))
    items = []
    for code, pairs in groups.items():
        rt = rateOf(pairs)
        items.append({
            'code': code,
            'name': venueNames.get(code, code),
            'edge': (None if rt is None or base is None else rt - base),
            'n': len(pairs)})
    items = [it for it in items if it['edge'] is not None]
    items.sort(key=lambda it: it['edge'], reverse=not ascending)
    return items, base


def computeMonthly(rows):
    """日付[:6]（YYYYMM）でgroupby、判定=波乱 の判別力(pt)推移。時系列昇順。"""
    valid = validRowsOf(rows)
    base = rateOf(valid)
    haran = [(r, h) for (r, h) in valid if r.get('判定') == '波乱']
    groups = {}
    for r, h in haran:
        ym = (r.get('日付') or '')[:6]
        if len(ym) != 6:
            continue
        groups.setdefault(ym, []).append((r, h))
    months = sorted(groups.keys())
    series = []
    for ym in months:
        rt = rateOf(groups[ym])
        series.append({'ym': ym, 'edge': (None if rt is None or base is None else rt - base),
                       'n': len(groups[ym])})
    return series, base


def computeScoreBins(rows, step=0.05):
    """スコアを step 刻みでbin化し、各帯の荒れ率(%)。母集団荒れ率も返す（水平線用）。"""
    valid = validRowsOf(rows)
    base = rateOf(valid)
    bins = {}
    for r, h in valid:
        sc = toFloat(r.get('スコア'))
        if sc is None:
            continue
        idx = int(_floorDiv(sc, step))
        bins.setdefault(idx, []).append((r, h))
    out = []
    for idx in sorted(bins.keys()):
        lo = idx * step
        out.append({'lo': lo, 'hi': lo + step, 'center': lo + step / 2.0,
                    'rate': rateOf(bins[idx]), 'n': len(bins[idx])})
    return out, base


def _floorDiv(value, step):
    """負値も含めて floor(value/step)。境界を安定させるため微小誤差を吸収。"""
    import math
    return math.floor(round(value / step, 9))


# --- 描画（Figureを受け取り軸を描く。GUI埋め込みとheadless保存の両方で使う）---
def plotVenueRanking(fig, rows, ascending=False):
    fig.clear()
    items, base = computeVenueRanking(rows, ascending=ascending)
    ax = fig.add_subplot(111)
    if not items:
        ax.text(0.5, 0.5, 'データなし', ha='center', va='center')
        return
    labels = [f"{it['name']} ({it['n']})" for it in items]
    values = [it['edge'] for it in items]
    colors = [posColor if v >= 0 else negColor for v in values]
    ypos = range(len(items))
    ax.barh(list(ypos), values, color=colors)
    ax.set_yticks(list(ypos))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()  # 上が最上位
    ax.axvline(0, color='#333', linewidth=1)  # 0基準線
    ax.set_xlabel('波乱判別力（pt＝群荒れ率 − 母集団荒れ率）')
    ttl = '場別 波乱判別力ランキング'
    if base is not None:
        ttl += f'（母集団荒れ率 {base:.1f}%・判定=波乱のみ）'
    ax.set_title(ttl, fontsize=11)
    for y, v in zip(ypos, values):
        ax.text(v + (0.3 if v >= 0 else -0.3), y, f'{v:+.1f}',
                va='center', ha='left' if v >= 0 else 'right', fontsize=8)
    fig.tight_layout()


def plotMonthly(fig, rows):
    fig.clear()
    series, base = computeMonthly(rows)
    ax = fig.add_subplot(111)
    pts = [s for s in series if s['edge'] is not None]
    if not pts:
        ax.text(0.5, 0.5, 'データなし', ha='center', va='center')
        return
    xs = [s['ym'][4:6] + '\n' + s['ym'][:4] for s in pts]
    ys = [s['edge'] for s in pts]
    ax.plot(range(len(pts)), ys, marker='o', color=posColor)
    ax.axhline(0, color='#e23b3b', linewidth=1, linestyle='--')  # 0基準線（劣化監視）
    ax.set_xticks(range(len(pts)))
    ax.set_xticklabels(xs, fontsize=7)
    ax.set_ylabel('pt')
    ax.set_title('月次 波乱判別力の推移', fontsize=11)
    fig.tight_layout()


def plotScoreBins(fig, rows):
    fig.clear()
    bins, base = computeScoreBins(rows)
    ax = fig.add_subplot(111)
    pts = [b for b in bins if b['rate'] is not None]
    if not pts:
        ax.text(0.5, 0.5, 'データなし', ha='center', va='center')
        return
    centers = [b['center'] for b in pts]
    rates = [b['rate'] for b in pts]
    ax.bar(centers, rates, width=0.045, color='#8fb8d6', edgecolor='#4a6a8a')
    if base is not None:
        ax.axhline(base, color='#e23b3b', linewidth=1.5,
                   label=f'母集団荒れ率 {base:.1f}%')
        ax.legend(fontsize=8)
    ax.set_xlabel('スコア帯（0.05刻み・①−④）')
    ax.set_ylabel('荒れ率 %')
    ax.set_title('スコア帯 × 荒れ率', fontsize=11)
    fig.tight_layout()


def summaryLines(rows):
    """サマリー①の数値カード用テキスト行を返す。"""
    s = computeSummary(rows)
    lines = []
    if s['baseRate'] is None:
        return ['有効データなし']
    lines.append(f"母集団荒れ率  {s['baseRate']:.1f}%   （有効 {s['total']:,} 行）")
    for judge in judgeOrder:
        d = s['byJudge'].get(judge)
        if not d or d['edge'] is None:
            continue
        lines.append(f"{judge}：判別力 {d['edge']:+.1f} pt   （荒れ率 {d['rate']:.1f}% / n={d['n']:,}）")
    return lines


# --- GUI（tkinterは遅延import：集計・描画関数を headless で使えるようにするため）---
def main():
    import tkinter as tk
    from tkinter import filedialog
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    state = {'path': defaultCsvPath(), 'rows': [], 'ascending': False}

    root = tk.Tk()
    root.title('verify ダッシュボード — 荒れ判別精度メーター（第1層）')
    root.geometry('1180x760')

    top = tk.Frame(root)
    top.pack(side=tk.TOP, fill=tk.X, padx=6, pady=4)
    pathVar = tk.StringVar(value=state['path'])
    tk.Label(top, text='CSV:').pack(side=tk.LEFT)
    tk.Label(top, textvariable=pathVar, fg='#245', anchor='w').pack(side=tk.LEFT, padx=4)
    orderVar = tk.StringVar(value='降順')

    body = tk.Frame(root)
    body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    left = tk.Frame(body)                 # 主役②
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    right = tk.Frame(body, width=430)     # ①③④
    right.pack(side=tk.RIGHT, fill=tk.BOTH)

    figRank = Figure(figsize=(6.6, 7.2), dpi=100)
    canvasRank = FigureCanvasTkAgg(figRank, master=left)
    canvasRank.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    cardFrame = tk.LabelFrame(right, text='① サマリー（判定精度）', padx=8, pady=6)
    cardFrame.pack(side=tk.TOP, fill=tk.X, padx=4, pady=4)
    cardVar = tk.StringVar(value='')
    tk.Label(cardFrame, textvariable=cardVar, justify=tk.LEFT, font=('TkDefaultFont', 11)).pack(anchor='w')

    figMonthly = Figure(figsize=(4.2, 2.6), dpi=100)
    canvasMonthly = FigureCanvasTkAgg(figMonthly, master=right)
    canvasMonthly.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)
    figScore = Figure(figsize=(4.2, 2.6), dpi=100)
    canvasScore = FigureCanvasTkAgg(figScore, master=right)
    canvasScore.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)

    def redraw():
        rows = state['rows']
        cardVar.set('\n'.join(summaryLines(rows)))
        plotVenueRanking(figRank, rows, ascending=state['ascending'])
        plotMonthly(figMonthly, rows)
        plotScoreBins(figScore, rows)
        canvasRank.draw()
        canvasMonthly.draw()
        canvasScore.draw()

    def reload():
        try:
            state['rows'] = loadRows(state['path'])
        except Exception as exc:  # 読めなくてもGUIは落とさない
            cardVar.set(f'CSV読込エラー: {exc}')
            state['rows'] = []
        pathVar.set(state['path'])
        redraw()

    def chooseCsv():
        picked = filedialog.askopenfilename(
            title='verify_log.csv を選択',
            filetypes=[('CSV', '*.csv'), ('すべて', '*.*')])
        if picked:
            state['path'] = picked
            reload()

    def toggleOrder():
        state['ascending'] = not state['ascending']
        orderVar.set('昇順' if state['ascending'] else '降順')
        plotVenueRanking(figRank, state['rows'], ascending=state['ascending'])
        canvasRank.draw()

    tk.Button(top, text='CSVを選択', command=chooseCsv).pack(side=tk.RIGHT, padx=3)
    tk.Button(top, textvariable=orderVar, command=toggleOrder, width=6).pack(side=tk.RIGHT, padx=3)
    tk.Label(top, text='並び:').pack(side=tk.RIGHT)

    reload()
    root.mainloop()


if __name__ == '__main__':
    main()
