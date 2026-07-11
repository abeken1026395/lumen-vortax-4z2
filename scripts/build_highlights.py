#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_highlights.py
出走表CSV＋モーターCSVを読み、本日の見どころ・展開文を計算して highlights.json に出力する。
ロジックは tenkai_logic.json の方針に準拠（買い目・確率・勝者断定・内心推測は出さない）。
使い方:
  python build_highlights.py [racers_csv] [motors_csv] [out_json]
  省略時: docs/racers/racers_today.csv  docs/motor/motors_all.csv  docs/highlights/highlights.json
"""
import csv, json, sys, os, datetime
from collections import defaultdict

RACERS = sys.argv[1] if len(sys.argv) > 1 else "docs/racers/racers_today.csv"
MOTORS = sys.argv[2] if len(sys.argv) > 2 else "docs/motor/motors_all.csv"
OUT    = sys.argv[3] if len(sys.argv) > 3 else "docs/highlights/highlights.json"
KIM    = sys.argv[4] if len(sys.argv) > 4 else "docs/players/racerKimarite.csv"
WEATHER = sys.argv[5] if len(sys.argv) > 5 else "docs/data/weather.json"

# --- 翌日プレビュー・モード（HL_MODE=next）---
# 前夜に「明日」タブ用の highlights_next.json を生成する専用モード。
# 当日モード(HL_MODE未設定)の挙動・出力先・predictions書き込みには一切干渉しない。
# 出力先は OUT と同ディレクトリの highlights_next.json 固定（当日 highlights.json は触らない）。
NEXT = os.environ.get('HL_MODE') == 'next'
NEXT_OUT = os.path.join(os.path.dirname(OUT) or '.', 'highlights_next.json')
FULL_RACES = 12  # 通常番組=12R。これ未満は「一部レースのみ（深夜に追加）」の暫定表示にする。

INTOP = {'大村':63,'徳山':62,'芦屋':64,'尼崎':62,'下関':60,'常滑':58,'住之江':55,'丸亀':56,
         '児島':55,'唐津':56,'若松':55,'宮島':54,'浜名湖':54,'三国':53,'蒲郡':54,'福岡':52,
         '鳴門':52,'びわこ':51,'多摩川':54,'平和島':50,'戸田':49,'津':54,'桐生':53,'江戸川':48}
CONFIRMED = {'尼崎','徳山','芦屋','下関','大村','常滑'}
MAKURI = {'戸田','江戸川','びわこ','平和島'}
K = '①②③④⑤⑥'

# --- 場特性の1行目（24場・断定しない範囲で水面の傾向のみ）---
# in天国(it>=58)/狭水面まくり場(MAKURI)/差し場を軸に、記者の1行目を作る。
NARROW = {'戸田','平和島','江戸川'}          # 狭い・インが残りにくい
SASHI  = {'常滑','蒲郡','児島','鳴門','丸亀'}  # うねり・差しが効きやすい傾向
def ba_line(ba, it):
    if ba in NARROW:
        return f"{ba}はインが残りにくい狭水面で、まくりの土壌がある。"
    if it >= 60:
        return f"{ba}はイン有利の水面。外が崩すには相応の材料がいる。"
    if it >= 57:
        return f"{ba}はインがしっかり残りやすい水面。"
    if ba in SASHI:
        return f"{ba}はうねりで差しが効きやすく、内の一角にも目が向く。"
    if it <= 50:
        return f"{ba}はインが盤石とは言えず、外の仕掛けが通りやすい。"
    return f"{ba}は極端に偏らない水面で、スタートの流れがものを言う。"

# --- 検証用 引き算スコア（標準化＋等重み・仮置き）---
# 重み・閾値は検証ログのスコア相関を見てから調整する。
LV = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
TH_KATA = 0.04    # スコア >= +0.04 → 堅め（5.3万件グリッド探索の最適値・場別上書きあり）
TH_HARAN = -0.09  # スコア <= -0.09 → 波乱（間は混戦）

# 場別チューニング（5.3万件で場別グリッド探索・下限ガードTK>=+0.02/TH<=-0.03）
# 出典：verify_log.csv 20250715-20260705 の全期間実測（2026-07-06反映）
BA_TH = {
    "桐生": (+0.03, -0.03),
    "戸田": (+0.08, -0.03),
    "江戸川": (+0.03, -0.03),
    "平和島": (+0.14, -0.07),
    "多摩川": (+0.02, -0.05),
    "浜名湖": (+0.11, -0.03),
    "蒲郡": (+0.03, -0.04),
    "常滑": (+0.04, -0.03),
    "津": (+0.05, -0.04),
    "三国": (+0.13, -0.03),
    "びわこ": (+0.11, -0.03),
    "住之江": (+0.17, -0.03),
    "尼崎": (+0.05, -0.03),
    "鳴門": (+0.04, -0.03),
    "丸亀": (+0.05, -0.03),
    "児島": (+0.11, -0.06),
    "宮島": (+0.08, -0.04),
    "徳山": (+0.04, -0.03),
    "下関": (+0.04, -0.05),
    "若松": (+0.08, -0.03),
    "芦屋": (+0.04, -0.04),
    "福岡": (+0.10, -0.05),
    "唐津": (+0.09, -0.03),
    "大村": (+0.07, -0.03),
}
def th_of(ba):
    return BA_TH.get(ba, (TH_KATA, TH_HARAN))

def f(x):
    try: return float(x)
    except: return 0.0

def nm(s): return s.replace('\u3000', '')

def load_csv(path):
    with open(path, encoding='utf-8-sig') as fp:
        return list(csv.DictReader(fp))

def main():
    rac = load_csv(RACERS)

    # --- 2日混載CSV対策（案①）: 当日(JST)の開催日の行だけを処理対象にする ---
    # 夜間に翌日分がracers_today.csvへ追記されると (場名,レース) キーが両日で衝突し、
    # 両日に出る場のレースが12艇化して脱落 → 見どころが片日限定の少数場へ縮退する事故を防ぐ。
    _today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%Y%m%d')
    _days = sorted(set((r.get('開催日') or '').strip() for r in rac if (r.get('開催日') or '').strip()))

    if NEXT:
        # --- 翌日モード: 対象日 = 当日highlights.jsonの開催日より後で最小のCSV開催日 ---
        # 壁時計today+1でなくCSV基準にすることで0時跨ぎでも当日を確実に除外し翌開催日を指す。
        base_day = ''
        try:
            with open(OUT, encoding='utf-8') as _bf:
                base_day = (json.load(_bf).get('開催日') or '').strip()
        except Exception:
            base_day = ''
        if not base_day:
            base_day = _today  # フォールバック: 当日highlightsが読めなければ壁時計今日を基準
        _future = [d for d in _days if d > base_day]
        if not _future:
            print("SKIP(翌日): 当日開催日{}より後のCSV開催日が無い（翌日未到着）。既存 highlights_next を保持（上書きせず）"
                  .format(base_day))
            return
        _target = _future[0]
        rac = [r for r in rac if (r.get('開催日') or '').strip() == _target]
        print("翌日モード: 基準日{} → 対象開催日{}（{}行）".format(base_day, _target, len(rac)))
    else:
        if len(_days) > 1:
            print("NOTE: CSVに複数開催日が混在: {} → 当日{}の行のみ処理".format(_days, _today))
        _rac_today = [r for r in rac if (r.get('開催日') or '').strip() == _today]
        if not _rac_today:
            # (a) 当日分が0行なら既存highlights・predictionsを上書きせずスキップ（朝の正生成を夜の空振りで壊さない）
            print("SKIP: 当日{}の出走表行が0（CSV開催日={}）。既存highlights・predictionsを保持（上書きせず）"
                  .format(_today, _days))
            return
        rac = _rac_today

    try:
        mot = load_csv(MOTORS)
    except Exception:
        mot = []
    mkey = {(m['場コード'], m['登録番号']): f(m['モーター2連対率']) for m in mot}

    # --- 検証スコア用 正規化（当日全出走者でmin-max・等重み）---
    def loc_or_nat(r):
        l = f(r['当地勝率']); return l if l > 0 else f(r['全国勝率'])
    _lv = [LV.get(r['級別'], 1) for r in rac]
    _loc = [loc_or_nat(r) for r in rac]
    _st = [f(r['平均ST']) for r in rac]
    _mtp = [v for v in (mkey.get((r['場コード'], r['登録番号']), 0.0) for r in rac) if v > 0]
    lv_lo, lv_hi = (min(_lv), max(_lv)) if _lv else (1, 4)
    loc_lo, loc_hi = (min(_loc), max(_loc)) if _loc else (0.0, 1.0)
    st_lo, st_hi = (min(_st), max(_st)) if _st else (0.1, 0.3)
    mt_lo, mt_hi = (min(_mtp), max(_mtp)) if _mtp else (0.0, 1.0)
    def _nz(v, lo, hi): return (v - lo) / (hi - lo) if hi > lo else 0.5
    def total_power(r):
        parts = [_nz(LV.get(r['級別'], 1), lv_lo, lv_hi),
                 _nz(loc_or_nat(r), loc_lo, loc_hi),
                 1 - _nz(f(r['平均ST']), st_lo, st_hi)]  # STは速い(小)ほど良い→反転
        mv = mkey.get((r['場コード'], r['登録番号']), 0.0)
        if mv > 0: parts.append(_nz(mv, mt_lo, mt_hi))
        return sum(parts) / len(parts)

    # 図鑑の決まり手CSVから やられ系（さされ・まくられ・まくりさされ）を読む。
    # 旧フォーマット（列が無い）やファイル欠損でも落ちないようにする。
    def fr(x):
        try:
            return float(x)
        except Exception:
            return None
    yarare = {}
    try:
        for k in load_csv(KIM):
            in1 = k.get('イン進入数', '')
            try:
                in1 = int(in1)
            except Exception:
                in1 = 0
            yarare[k['登録番号']] = {
                'さされ率': fr(k.get('さされ率', '')),
                'まくられ率': fr(k.get('まくられ率', '')),
                'まくりさされ率': fr(k.get('まくりさされ率', '')),
                'イン数': in1,
                'まくり率': fr(k.get('まくり率', '')),
                '差し率': fr(k.get('差し率', '')),
            }
    except Exception:
        yarare = {}
    # 場ごと0%率でモーター使用可否
    zero = defaultdict(lambda: [0, 0])
    for m in mot:
        zero[m['場名']][1] += 1
        if f(m['モーター2連対率']) == 0: zero[m['場名']][0] += 1
    motok = {k: (z/t < 0.4) for k, (z, t) in zero.items()}

    for r in rac:
        r['_mtr'] = mkey.get((r['場コード'], r['登録番号']), 0.0)

    # 決まり手タイプ（まくり型/差し型/標準）。データ欠損はNone。
    def kim_type(toban):
        y = yarare.get(toban, {})
        mk = y.get('まくり率'); sa = y.get('差し率')
        if mk is None and sa is None: return None
        mk = mk or 0.0; sa = sa or 0.0
        if mk >= 25 and mk >= sa + 8: return 'makuri'
        if sa >= 30 and sa >= mk + 8: return 'sashi'
        return None

    # 天候（表示だけ：締切時刻に最も近い時刻の風をweather.jsonから引く。結論は書かない）
    wjson = {}
    try:
        with open(WEATHER, encoding='utf-8') as wf:
            wjson = json.load(wf).get('stadiums', {})
    except Exception:
        wjson = {}

    def wind_line(jcd, hhmm):
        """締切HH:MMに最も近い時刻の風の事実を1行返す。取れなければ空文字。"""
        st = wjson.get(str(jcd).zfill(2))
        if not st or not hhmm or ':' not in hhmm:
            return ''
        try:
            target = int(hhmm.split(':')[0]) * 60 + int(hhmm.split(':')[1])
        except Exception:
            return ''
        best = None; bd = 1e9
        for h in st.get('hourly', []):
            t = h.get('time', '')
            if 'T' not in t:
                continue
            hm = t.split('T')[1][:5]
            try:
                cur = int(hm.split(':')[0]) * 60 + int(hm.split(':')[1])
            except Exception:
                continue
            dd = abs(cur - target)
            if dd < bd:
                bd = dd; best = h
        if not best:
            return ''
        wind = best.get('wind'); d = best.get('dir', ''); wx = best.get('wx', '')
        if wind is None:
            return ''
        # 事実の描写のみ。有利不利の結論には踏み込まない。
        wxs = f"{wx}天で" if wx and wx not in ('晴',) else ''
        if wind < 3:
            return f"当日は{wxs}{d}の風{wind:.0f}m前後と穏やかで、水面は落ち着いた条件。"
        elif wind < 5:
            return f"当日は{wxs}{d}の風{wind:.0f}m。スタート隊形に影響しうる風速。"
        elif wind < 7:
            return f"当日は{wxs}{d}の風{wind:.0f}mとやや強く、水面は波立ちやすい。"
        else:
            return f"当日は{wxs}{d}の風{wind:.0f}mの強風で、水面は落ち着かない。"

    races = defaultdict(list)
    for r in rac:
        races[(r['場名'], r['レース'])].append(r)

    out_races = []
    pred_list = []
    # 部分成功許容：1レース(場)分の生成を関数に切り出し、呼び出し側で例外を握る。
    # 一部の場/レースが壊れても「取れた分だけ」出力し、失敗はログする（全滅時のみ点1の自己検査で非ゼロ）。
    def _one(ba, rc, bo):
        if len(bo) != 6: return None
        bo.sort(key=lambda b: int(b['枠']))
        # --- 検証ログ：①総合力 − ④総合力（標準化・等重み）---
        diff = round(total_power(bo[0]) - total_power(bo[3]), 3)
        tk_ba, th_ba = th_of(ba)
        if diff >= tk_ba:
            verdict, hero = '堅め', 1
        elif diff <= th_ba:
            verdict, hero = '波乱', 4
        else:
            verdict, hero = '混戦', None  # 混戦の主役は下で機力→実力→決まり手で判断
        it = INTOP.get(ba, 53)
        use_m = motok.get(ba, True)
        mt = [b['_mtr'] for b in bo]
        valid = [v for v in mt if v > 0]
        mavg = sum(valid)/len(valid) if valid else None
        hi = lambda v: use_m and mavg and v > 0 and v > mavg+5
        lo = lambda v: use_m and mavg and v > 0 and v < mavg-5

        in1 = bo[0]; il = f(in1['当地勝率']); ina = f(in1['全国勝率'])
        inA = in1['級別'] in ('A1', 'A2')
        in_lo = lo(mt[0])
        in_strong = inA and il > ina and il > 0 and not in_lo
        inB = in1['級別'] in ('B1', 'B2')
        # ①不安の判定（全場共通）：
        #  ・B級インは不安。
        #  ・A級インは当地見劣り単独では不安にしない（格が担保）。機力下位のときだけ不安。
        #  ・イン天国(it>=60)ではB級のみ不安（機力下位でも水面が残す）。
        if it >= 60:
            in_weak = inB
        elif inA:
            in_weak = in_lo
        else:
            in_weak = inB or (il > 0 and il < ina) or in_lo

        seeds = 0
        if in_weak: seeds += 1
        threats = []; out_hi = False
        LVRANK = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
        for i, b in enumerate(bo):
            w = int(b['枠']); lv = b['級別']; loc = f(b['当地勝率']); nat = f(b['全国勝率']); st = f(b['平均ST'])
            n2 = f(b['全国2連率'])
            a_out = w >= 4 and lv in ('A1', 'A2')
            local_out = w >= 3 and loc > 0 and loc > nat
            if a_out or local_out:
                seeds += 1
                threats.append({'w': w, 'lv': lv, 'st': st, 'a_out': a_out,
                                'local_out': local_out, 'mhi': hi(mt[i]), 'nm': nm(b['氏名']),
                                'lvr': LVRANK.get(lv, 0), 'loc': loc,
                                'mlo': lo(mt[i]), 'n2': n2})
            if w >= 4 and hi(mt[i]): out_hi = True
        if in_lo and out_hi: seeds += 1

        # 混戦の主役を①と④で判断（機力差→実力(当地)差→決まり手）
        if hero is None:
            # 混戦の主役は①固定。逆算実測(20250715-20260705)：混戦で④に主役を振った
            # 条件(機力+8/当地+1.0/まくり型狭水面)でも④の1着率は9.6%・3着内45.8%に留まり、
            # 同レースの①は1着53.9%・3着内81.0%。④選定は誤りのため①へ据える。
            # （④の脅威は見出し/展開/波及で別途言及するので物語は損なわない）
            hero = 1
        if it >= 60: seeds = max(0, seeds-1)
        elif it <= 50: seeds += 1
        if ba in MAKURI: seeds += 1

        # --- 見立て見出し（scoreトーン×主役、断定しない） ---
        # score(diff)で①中心/難解/外主役のトーンを決め、その上に主役艇名を乗せる。
        o4 = sorted([t for t in threats if t['w'] >= 4], key=lambda x: x['w'])
        inn = sorted([t for t in threats if t['w'] < 4], key=lambda x: x['w'])
        head_w = None
        def _kt_of(w):
            return kim_type(bo[w-1]['登録番号'])
        # 語調は実測連動：スコアが深いほど強く言い切る（+0.40帯の波乱率18%実測）。
        # 波乱側はスコア深度と波乱率が相関しない実測のため、断定を強めない。
        if in_strong and diff >= tk_ba:
            if diff >= 0.30:
                headline = f"①{nm(in1['氏名'])}の信頼厚し。相手探しの一戦"; hid = 'K1'
            elif it >= 60:
                headline = f"①{nm(in1['氏名'])}中心。水面も後押しし、崩れは考えにくい"; hid = 'K2'
            else:
                headline = f"①{nm(in1['氏名'])}中心。外の一発をどこまで測るか"; hid = 'K3'
        elif in_weak and diff <= th_ba and o4:
            w0 = o4[0]; kt0 = _kt_of(w0['w'])
            if kt0 == 'makuri' and ba in NARROW:
                headline = f"①に不安。{K[w0['w']-1]}{w0['nm']}のまくりが狭水面で一考"; hid = 'H1'
            elif kt0 == 'sashi':
                headline = f"①に不安。{K[w0['w']-1]}{w0['nm']}のまくり差しを警戒"; hid = 'H2'
            else:
                headline = f"①に不安。{K[w0['w']-1]}{w0['nm']}の一撃を警戒したい"; hid = 'H3'
            head_w = w0['w']
        elif in_strong and verdict == '波乱' and o4:
            # in_strong水面でも④優勢で波乱判定＝外主役が実態に整合（旧K4矛盾の解消）
            w0 = o4[0]; kt0 = _kt_of(w0['w'])
            if kt0 == 'makuri' and ba in NARROW:
                headline = f"①に不安。{K[w0['w']-1]}{w0['nm']}のまくりが狭水面で一考"; hid = 'H1'
            elif kt0 == 'sashi':
                headline = f"①に不安。{K[w0['w']-1]}{w0['nm']}のまくり差しを警戒"; hid = 'H2'
            else:
                headline = f"①に不安。{K[w0['w']-1]}{w0['nm']}の一撃を警戒したい"; hid = 'H3'
            head_w = w0['w']
        elif in_strong:
            headline = f"①{nm(in1['氏名'])}の逃げが軸。外の一発をどこまで測るか"; hid = 'K4'
        elif in_weak and o4:
            w0 = o4[0]; kt0 = _kt_of(w0['w'])
            if kt0 == 'sashi':
                headline = f"①に不安、{K[w0['w']-1]}{w0['nm']}のまくり差しが主役候補"; hid = 'M1'
            elif kt0 == 'makuri':
                headline = f"①に不安、{K[w0['w']-1]}{w0['nm']}のまくりが主役候補"; hid = 'M2'
            else:
                headline = f"①に不安、{K[w0['w']-1]}{w0['nm']}のダッシュ一撃を測る一戦"; hid = 'M3'
            head_w = w0['w']
        elif in_weak and inn:
            headline = f"①に不安、{K[inn[0]['w']-1]}{inn[0]['nm']}の差しが突け入る一戦"; hid = 'M4'
            head_w = inn[0]['w']
        elif in_weak:
            headline = "①に不安、外の仕掛け待ちで波乱含み"; hid = 'M5'
        elif o4:
            headline = f"①の出方ひとつ、{K[o4[0]['w']-1]}{o4[0]['nm']}のまくりと連動"; hid = 'M6'
            head_w = o4[0]['w']
        else:
            headline = "軸を絞りにくい難解戦。展示のSで傾きを見たい"; hid = 'M7'

        # --- 展開の筋（記者文型：場特性→①〜したい〜だが→主役決まり手×場特性→死角）---
        tenkai = []
        # 〔場〕1行目に場特性（実装テーブルA①）
        tenkai.append(ba_line(ba, it))
        # 〔天候〕締切時刻の風の事実を1行（表示だけ・結論は書かない）
        wl_line = wind_line(bo[0]['場コード'], bo[0].get('締切時刻', ''))
        if wl_line:
            tenkai.append(wl_line)

        # 〔軸＋死角〕①を「〜したい〜だが」で（実装テーブルA②：級別×機力×当地で分岐）
        m1 = '機力は場上位' if hi(mt[0]) else '機力は場下位' if lo(mt[0]) else ('機力は場平均並み' if use_m and mt[0] > 0 else '')
        in_f = int(in1['F数']) >= 1
        in_kt = kim_type(in1['登録番号'])
        if in_strong:
            extra = ""
            if ba in NARROW or (it >= 60):
                extra = "水面もイン向きで、"
            if diff >= 0.30:
                tenkai.append(f"①{nm(in1['氏名'])}はA級・当地巧者{('で'+m1) if m1 else ''}。{extra}比較で抜けており、Sさえ五分なら主導権は譲るまい。")
            else:
                tenkai.append(f"逃げたい①{nm(in1['氏名'])}はA級・当地巧者{('で'+m1) if m1 else ''}。{extra}②③が壁を作れば主導権は譲りにくい。")
        elif in_weak:
            why = []
            if not inA: why.append('格')
            if il > 0 and il < ina: why.append('当地')
            if in_lo: why.append('機力')
            reason = '・'.join(why) if why else '総合力'
            fnote = '（F持ちで踏み込みにくく）' if in_f else ''
            tenkai.append(f"逃げたい①{nm(in1['氏名'])}だが{reason}で見劣り{fnote}、押し切りには不安。先マイを許さなければ外に主導権が渡る。")
        else:
            tenkai.append(f"逃げたい①{nm(in1['氏名'])}は標準評価{('（'+m1+'）') if m1 else ''}。Sが決まれば逃げ、遅れれば外に付け入る隙が生まれる。")

        # 〔主役〕見出しの主役艇を先頭に、次点はST順（見出しと展開のズレを防ぐ）
        th_sorted = sorted(threats, key=lambda t: (t['st'] if t['st'] > 0 else 9, t['w']))
        if head_w is not None:
            head_t = [t for t in threats if t['w'] == head_w]
            rest = [t for t in th_sorted if t['w'] != head_w]
            th2 = (head_t + rest)[:2]
        else:
            th2 = th_sorted[:2]
        toban_by_w = {int(b['枠']): b['登録番号'] for b in bo}
        # 全艇の格・当地の最上位を把握（格上艇が主役でない理由づけに使う）
        LVRANK2 = {'A1': 4, 'A2': 3, 'B1': 2, 'B2': 1}
        boat_meta = {int(b['枠']): {'lvr': LVRANK2.get(b['級別'], 0), 'lv': b['級別'],
                                    'loc': f(b['当地勝率']), 'nm': nm(b['氏名'])} for b in bo}
        used_shuyaku = False  # 「主役になりうる」を1レース1回に制限
        head_w0 = th2[0]['w'] if th2 else None
        for idx, t in enumerate(th2):
            role = '外枠のダッシュ勢' if t['w'] >= 4 else '内寄りの一角'
            ex = []
            if t['local_out']: ex.append('当地巧者')
            if t['a_out']: ex.append('A級')
            if t['mhi']: ex.append('機力上位')
            if t['st'] > 0 and t['st'] <= 0.15: ex.append('鋭ST')
            exs = ('（'+'・'.join(ex)+'）') if ex else ''
            kt = kim_type(toban_by_w.get(t['w'], ''))
            fit = ''
            if t['w'] >= 4:
                base_kim = 'まくり差し' if kt == 'sashi' else 'まくり'
                if kt == 'makuri':
                    if ba in NARROW: fit = 'まくり型で狭水面と噛み合い、'
                    elif it >= 58:   fit = 'まくり型だが差しの利く水面で割り引きたく、'
                    else:            fit = 'まくり型の持ち味を出しやすく、'
                elif kt == 'sashi':
                    fit = '差し型で、内が動いた隙を突く形なら、'
            else:
                base_kim = '差し・まくり差し'
                if kt == 'sashi':
                    fit = '差し型が水を得やすく、'
                elif kt == 'makuri':
                    fit = 'まくり型で一発の破壊力があり、'
            if idx == 0:
                # 主役：主役述語（1回だけ）
                tenkai.append(f"主役は{K[t['w']-1]}{t['nm']}{exs}。{fit}Sが決まれば{base_kim}の主役になりうる。")
                used_shuyaku = True
                # 三島型の機力注記：実力(全国2連率上位)に対し今節機が下位なら、決まり手に接続して一言
                if t.get('mlo') and t.get('n2', 0) >= 35 and use_m:
                    if t['w'] >= 4:
                        kimt = 'まくり一発の型は作りにくく、伸びが戻るかが鍵。'
                    else:
                        kimt = '差し場に持ち込む足がまだ物足りず、機の上向きを待ちたい。'
                    tenkai.append(f"ただ{K[t['w']-1]}は実力上位ながら今節機が伸び劣り、{kimt}")
            else:
                # 二番手以下：述語を変える（「主役になりうる」は使わない）
                pred2 = 'まくり差しから連に食い込む' if t['w'] >= 4 else '差し込みで連に絡む'
                tenkai.append(f"これに次ぐのが{K[t['w']-1]}{t['nm']}{exs}。{fit}二の矢、{pred2}形。")

        # 修正1：主役より格上・当地上位の艇がいれば、主役でない理由を一言添える
        mentioned_w = {t['w'] for t in th2}
        if head_w0 is not None:
            main_meta = boat_meta.get(head_w0, {})
            # 明確な格上のみ：級が1段以上上、または同格で当地が1.0以上上（僅差では言わない）
            # ※展開で既に言及した艇（二番手含む）は除外＝同一艇の二重言及バグ修正
            supers = [w for w, mm in boat_meta.items() if w not in mentioned_w and w != 1 and (
                mm['lvr'] > main_meta.get('lvr', 0) or
                (mm['lvr'] == main_meta.get('lvr', 0) and mm['loc'] > main_meta.get('loc', 0) + 1.0))]
            # 主役より級が下または同格なら「地力最上位」とは言わない
            supers = [w for w in supers if boat_meta[w]['lvr'] >= main_meta.get('lvr', 0)]
            if supers:
                sw = sorted(supers, key=lambda w: (-boat_meta[w]['lvr'], -boat_meta[w]['loc']))[0]
                sm = boat_meta[sw]
                # A級のみ「地力最上位/上位」と表現。非A級は控えめに
                if sm['lv'] in ('A1', 'A2'):
                    if sw <= 3:
                        tenkai.append(f"{K[sw-1]}{sm['nm']}は{sm['lv']}で地力最上位だが、内寄りで一撃の形を作りにくく、Sの決まった主役に主導権を譲る形。")
                    else:
                        tenkai.append(f"{K[sw-1]}{sm['nm']}は{sm['lv']}で地力上位だが、進入位置で分があるのは主役側。")

        # 〔混戦の痩せ対策〕言及すべき対抗が拾えなかったレースでも、主役側の一文を必ず置く
        if not th2:
            if hero == 4:
                tenkai.append(f"対するカド④{nm(bo[3]['氏名'])}。目立つ材料は薄いが、Sひとつで景色の変わる位置ではある。")
            else:
                tenkai.append("相手は横一線。②の差し、④のダッシュと、二番手争いは展示の気配次第。")

        # 〔死角〕必ず1つ（実装テーブルA④：F・級・機力から。同文を避け条件で散らす）
        saten = None; skw = None; sid = None
        # f_out：カド勢(w>=4)のF持ち。A級を優先、カドF単独(5のみ/6のみ)は死角として弱く除外
        _fout_all = [t for t in threats if t['w'] >= 4 and int(bo[t['w']-1]['F数']) >= 1]
        # A級F艇を最内優先、次に非A級F艇を最内優先
        _fA = sorted([t for t in _fout_all if bo[t['w']-1]['級別'] in ('A1','A2')], key=lambda x: x['w'])
        _fB = sorted([t for t in _fout_all if bo[t['w']-1]['級別'] not in ('A1','A2')], key=lambda x: x['w'])
        # カドF単独（F艇がカドで5のみ/6のみ＝他にF艇なし）は除外＝f_outを空にしてD3等へ流す
        # 実測(programs全期間)：5号艇F単独34.6%/6号艇F単独23.1%と4号艇F42%台より明確に低い弱層
        if len(_fout_all) == 1 and _fout_all[0]['w'] in (5, 6):
            f_out = []
        else:
            f_out = _fA + _fB
        f_in  = [b for b in bo if int(b['枠']) in (2,3) and int(b['F数']) >= 1]
        o4top = o4[0] if o4 else None
        o4kt = kim_type(toban_by_w.get(o4top['w'], '')) if o4top else None
        if f_out:
            t = f_out[0]
            saten = f"死角は{K[t['w']-1]}のF。慎重Sならまくり不発で①が残る目も出てくる。"
            skw = t['w']; sid = 'D1'
        elif f_in:
            fw = int(f_in[0]['枠'])
            saten = f"死角は{K[fw-1]}のF。慎重Sは外を後押しもするが、手堅く回れば①が立つ余地も残る。"
            skw = fw; sid = 'D2'
        elif in_strong:
            saten = "①がSを決め先マイすれば、地力で押し切る本線も濃い。"
            skw = 1; sid = 'D3'
        elif any(t['mhi'] for t in threats if t['w'] < 4):
            mb = next(t for t in threats if t['w'] < 4 and t['mhi'])
            saten = f"警戒は{K[mb['w']-1]}。機力上位で差し・まくり差しに動け、外の隙に連へ食い込む。"
            skw = mb['w']; sid = 'D4'
        elif in_weak:
            # ①不安時の死角を、弱点理由×外主役の決まり手で分岐（同文回避）
            wl = []
            if not inA: wl.append('格')
            if il > 0 and il < ina: wl.append('当地')
            if in_lo: wl.append('機力')
            if o4top and o4kt == 'makuri' and ba in NARROW:
                # 死角艇は実際にまくる外脅威(o4top)に付け替え＝旧⑥ハードコード(絡み30%)は過剰。
                # 実測：D5該当レースで6号艇3着内30.1%に対しo4top(多くは4号)は48.3%。文言も弱化。
                saten = f"死角は{K[o4top['w']-1]}のまくり。狭水面で決まれば内の隊形は乱れ、着順が入れ替わる目もある。"
                skw = o4top['w']; sid = 'D5'
            elif o4top and o4kt == 'makuri':
                saten = f"死角は{K[o4top['w']-1]}の握り込み。まくりが決まりきれば内の粘りごと連れ去る一撃もある。"
                skw = o4top['w']; sid = 'D6'
            elif o4top and o4kt == 'sashi':
                saten = f"死角は{K[o4top['w']-1]}の差し損じ。踏み込みが甘ければ①が粘り込む展開に振れる。"
                skw = 1; sid = 'D7'
            elif in_lo:
                saten = "死角は①の船足。伸びが戻れば見立てほど脆くはなく、逃げ残りも一考。"
                skw = 1; sid = 'D8'
            elif '格' in wl and '当地' not in wl:
                saten = "死角は①の地元利。格は下でもSさえ五分なら、押し切って波乱を消す目も残る。"
                skw = 1; sid = 'D9'
            elif '当地' in wl:
                saten = "死角は①の当地慣れ。水面相性が出れば数字以上に粘り、連の一角に残る目も。"
                skw = 1; sid = 'D10'
            else:
                saten = "死角は①の粘り。Sが五分なら外の攻めが不発になり、①残しもある。"
                skw = 1; sid = 'D11'
        elif any(t['w'] >= 4 for t in threats):
            # 外の仕掛けを担う筆頭＝threatsのw>=4で最内の艇（実測：D12死角艇は内ほど絡む
            # 4号57.8%>5号42.9%>6号29.3%。最外選択は6号偏重で弱いため最内優先に変更）
            out_thr = sorted([t for t in threats if t['w'] >= 4], key=lambda x: x['w'])
            saten = "外の仕掛けは一考。Sが決まれば隊形は乱れるが、そのまま連まで届くかは別問題。"
            skw = out_thr[0]['w']; sid = 'D12'
        else:
            # 内が壁を作る＝主役の①が残る想定。死角艇は①
            saten = "内が壁を作れば波及は内で収まり、荒れの芽は限られる。"
            skw = 1; sid = 'D13'
        tenkai.append(saten)

        # --- 波及の連鎖（主役の決まり手型×場×イン強弱で分岐。同文を散らす）---
        out4 = any(t['w'] >= 4 for t in threats)
        kt_h = _kt_of(head_w) if (head_w and head_w >= 4) else None
        n1 = nm(in1['氏名']); n2b = nm(bo[1]['氏名'])
        if in_strong and it >= 60:
            suji = f"①{n1}が先マイなら②③が続く本線。外が崩す材料は乏しく、波及は内で収まりやすい。"; fid = 'S1'
        elif in_strong or (not in_weak and not out4):
            suji = f"①{n1}が先マイを決めれば②③が続く筋。壁が崩れない限り波及は内で収まる。"; fid = 'S2'
        elif out4 and kt_h == 'makuri' and ba in NARROW:
            suji = f"{K[head_w-1]}{boat_meta[head_w]['nm']}が握って回れば内は総崩れ、空いた最内を⑤⑥が拾う目まで。外決着なら内の連は薄れる。"; fid = 'S3'
        elif out4 and kt_h == 'sashi':
            suji = f"{K[head_w-1]}{boat_meta[head_w]['nm']}がまくり差しに構えれば①②の間が割れ、差された内は着を落とす連鎖。"; fid = 'S4'
        elif out4 and head_w and head_w >= 4:
            suji = f"{K[head_w-1]}{boat_meta[head_w]['nm']}が仕掛ければ②③は外に張られ、空いた内を逃げ残りの①{n1}や⑤が拾う波及。"; fid = 'S5'
        elif out4:
            ow = o4[0]['w'] if o4 else 4
            suji = f"{K[ow-1]}{boat_meta[ow]['nm']}が仕掛ければ②③は外に張られ、空いた内を⑤や逃げ残りの①{n1}が拾う波及。外決着なら内の連は薄れる。"; fid = 'S6'
        else:
            suji = f"②{n2b}が差し込めば①{n1}は先頭を譲っても2着に残りやすく、③が続く形。"; fid = 'S7'

        # --- 締めの1行（実装テーブルA⑤：判定×語調実測連動でパターンを散らす）---
        if verdict == '堅め':
            if diff >= 0.30 and in_strong:
                shime = "①の信頼は厚い。展示は相手選びの材料に。"; cid = 'C1'
            elif in_strong:
                shime = "①軸は動かしにくい。崩れるとすれば外のS一枚。"; cid = 'C2'
            else:
                # 数字は①寄りだが文面は主役を絞れていない：矛盾しない締めに落とす
                shime = "比較の数字は①寄り。あとは体勢ひとつ、展示で確かめたい。"; cid = 'C6'
        elif verdict == '波乱':
            tgt = K[head_w-1] if head_w else '外'
            if in_weak:
                shime = f"「①残り」か「{tgt}の一撃」か。断は展示のSまで預けたい。"; cid = 'C3'
            else:
                shime = "比較の数字は外寄りに振れる。仕掛けの有無を展示で。"; cid = 'C7'
        else:
            if hero == 4:
                shime = "内外どちらにも振れる。進入と展示気配を見てから。"; cid = 'C4'
            else:
                shime = "軸を絞りにくい一戦。展示のSで傾きを確かめたい。"; cid = 'C5'
        tenkai.append(shime)

        # --- 検証ログ（拡張）：対抗・死角・文パターンIDまで保存し、書き方自体を検証可能に ---
        pred_entry = {'場名': ba, '場コード': bo[0]['場コード'], 'レース': rc,
                          '判定': verdict, '主役艇': hero, 'スコア': diff,
                          '対抗艇': (th2[1]['w'] if len(th2) > 1 else None),
                          '死角艇': skw,
                          '見出しID': hid, '死角ID': sid, '波及ID': fid, '締めID': cid}

        boats = []
        for b in bo:
            w = int(b['枠']); loc = f(b['当地勝率']); nat = f(b['全国勝率']); st = f(b['平均ST']); mv = b['_mtr']
            mev = 'na'
            if use_m and mv > 0:
                mev = 'hi' if hi(mv) else 'lo' if lo(mv) else 'mid'
            y = yarare.get(b['登録番号'], {})
            boats.append({
                '枠': w, '登録番号': b['登録番号'], '支部': b.get('支部',''), '級別': b['級別'], '氏名': nm(b['氏名']),
                '全国勝率': round(nat, 2), '当地勝率': round(loc, 2),
                '機力': round(mv, 1) if (use_m and mv > 0) else None, '機力評価': mev,
                'F': int(b['F数']) >= 1, '鋭ST': st > 0 and st <= 0.15,
                '当地優位': loc > 0 and loc > nat,
                'さされ率': y.get('さされ率'), 'まくられ率': y.get('まくられ率'),
                'まくりさされ率': y.get('まくりさされ率'), 'イン数': y.get('イン数')
            })

        out_entry = {
            '場名': ba, '場コード': bo[0]['場コード'], 'レース': rc,
            '締切時刻': bo[0].get('締切時刻', ''),
            '節名': bo[0].get('節名', ''), '企画名': bo[0].get('企画名', ''),
            '日目': bo[0].get('日目', ''),
            '波乱': seeds, 'イン堅': in_strong, 'モーター使用': use_m, 'イン1着率': it,
            '艇': boats, '見立て': headline, '展開': tenkai, '波及': suji
        }
        return out_entry, pred_entry

    # 呼び出し：場×レース単位に例外を握って「取れた分だけ」蓄積。失敗はログ。
    failed = []
    for (ba, rc), bo in races.items():
        try:
            _res = _one(ba, rc, bo)
        except Exception as e:
            failed.append((ba, rc, repr(e)))
            continue
        if _res is None:
            continue
        _out, _pred = _res
        out_races.append(_out)
        pred_list.append(_pred)
    if failed:
        vs = sorted(set(ba for ba, _rc, _e in failed))
        print("部分成功: {}レースをスキップ（例外を握って継続）／該当場: {}".format(len(failed), '・'.join(vs)))
        for ba, rc, err in failed[:50]:
            print("  SKIP {} {} : {}".format(ba, rc, err))

    kaisai = rac[0]['開催日'] if rac else ''
    doc = {
        '生成時刻': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(timespec='seconds'),
        '開催日': kaisai,
        '確定イン率場': sorted(CONFIRMED),
        'レース数': len(out_races),
        'レース': out_races
    }
    # ---- 自己検査(生成前) ----
    # 出走表が空 / 0レース＝生成失敗。既存 highlights・predictions を壊さず非ゼロ終了する
    # （上書きゼロ・鉄則厳守）。夜間の翌日分プレビュー(kaisai!=today)は下の日付ガードで正当スキップ。
    n_races = len(out_races)
    n_venues = len(set(r.get('場コード') for r in out_races))
    if not rac or n_races == 0:
        print("SELFCHECK NG: 出走表{}行 / 生成{}レース ＝ 生成失敗。"
              "既存 highlights・predictions は保持（上書きせず）".format(len(rac), n_races))
        sys.exit(3)

    # --- 翌日モード: highlights_next.json へ場単位マージ（当日 highlights.json・predictions/ は触らない）---
    if NEXT:
        now_iso = doc['生成時刻']
        now_hm = now_iso[11:16]
        by_jcd = defaultdict(list)
        for r in out_races:
            by_jcd[r.get('場コード')].append(r)
        run_meta = {}
        for jcd, rs in by_jcd.items():
            nR = len(rs)
            run_meta[jcd] = {'場名': rs[0].get('場名', ''), 'generatedAt': now_hm,
                             'partial': nR < FULL_RACES, 'レース数': nR}
        # 既存 next を読み、同一対象日ならマージ（このrunに無い＝未到着の場は据え置き）。別日なら破棄。
        merged_races, merged_meta = [], {}
        try:
            with open(NEXT_OUT, encoding='utf-8') as nf:
                oldn = json.load(nf)
            if (oldn.get('開催日') or '') == kaisai:
                keep = set(by_jcd.keys())
                merged_races = [r for r in (oldn.get('レース') or []) if r.get('場コード') not in keep]
                merged_meta = {k: v for k, v in (oldn.get('場別') or {}).items() if k not in keep}
        except Exception:
            pass
        merged_races.extend(out_races)   # このrunの場は最新で上書き（載せてから更新）
        merged_meta.update(run_meta)
        next_doc = {
            '生成時刻': now_iso, '開催日': kaisai, 'プレビュー': True,
            '確定イン率場': sorted(CONFIRMED),
            'レース数': len(merged_races), 'レース': merged_races,
            '場別': merged_meta,
        }
        os.makedirs(os.path.dirname(NEXT_OUT) or '.', exist_ok=True)
        with open(NEXT_OUT, 'w', encoding='utf-8') as nf:
            json.dump(next_doc, nf, ensure_ascii=False, separators=(',', ':'))
        part = sum(1 for m in merged_meta.values() if m.get('partial'))
        print("OK(翌日): 対象{} 今回{}場/{}レース → next計{}場/{}レース(一部公開{}場) → {}".format(
            kaisai, len(by_jcd), len(out_races), len(merged_meta), len(merged_races), part, NEXT_OUT))
        # 鉄則: predictions/ には一切書かない。prevローテーションもしない。当日 highlights.json も不変。
        return

    # 壁時計（JST）が今日になっている開催日のときだけ当日を書き換える。
    # 出走表が夜に翌日分へ更新されても、当日タブを前倒しで繰り上げない。
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%Y%m%d')
    if kaisai != today:
        print(f"SKIP: 開催日{kaisai} != 本日{today}（当日を保持）")
        return
    out_dir = os.path.dirname(OUT)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    prev_path = os.path.join(out_dir, 'highlights_prev.json') if out_dir else 'highlights_prev.json'
    prev2_path = os.path.join(out_dir, 'highlights_prev2.json') if out_dir else 'highlights_prev2.json'
    try:
        with open(OUT, 'r', encoding='utf-8') as pf:
            old_doc = json.load(pf)
        if old_doc.get('開催日') and old_doc.get('開催日') != kaisai:
            if os.path.exists(prev_path):
                os.replace(prev_path, prev2_path)
            with open(prev_path, 'w', encoding='utf-8') as pf:
                json.dump(old_doc, pf, ensure_ascii=False, separators=(',', ':'))
    except FileNotFoundError:
        pass
    except Exception:
        pass
    with open(OUT, 'w', encoding='utf-8') as fp:
        json.dump(doc, fp, ensure_ascii=False, separators=(',', ':'))
    print(f"OK: {n_races}レース/{n_venues}場 → {OUT}")

    # --- 検証ログ：予測を確定保存（結果を見る前・一度書いたら動かさない）---
    # 公開highlights.jsonには判定/主役艇を入れず、非公開predictions/にだけ残す。
    pred_written = None
    if pred_list:
        os.makedirs('predictions', exist_ok=True)
        pred_path = os.path.join('predictions', f'{kaisai}.json')
        if os.path.exists(pred_path):
            print(f"PRED skip: {pred_path} 既存（予測は動かさない）")
        else:
            pred_doc = {'開催日': kaisai, '生成時刻': doc['生成時刻'],
                        '閾値': {'堅め': TH_KATA, '波乱': TH_HARAN},
                        '予測': pred_list}
            with open(pred_path, 'w', encoding='utf-8') as pf:
                json.dump(pred_doc, pf, ensure_ascii=False, separators=(',', ':'))
            pred_written = pred_path
            print(f"PRED: {len(pred_list)}レース → {pred_path}")

    # ---- 自己検査(生成後) ----
    # 書いたファイルを読み直し、JSONとして開けて中身が空でないことを確認。
    # 破損/空なら非ゼロ終了して以降(コミット等)を止める。既存predictionsは検査対象外(不変)。
    try:
        with open(OUT, encoding='utf-8') as _cf:
            _c = json.load(_cf)
        if not (_c.get('レース数', 0) > 0 and _c.get('レース')):
            raise ValueError("highlights.json のレースが空")
    except Exception as e:
        print(f"SELFCHECK NG(生成後): highlights.json 再読込検査に失敗: {e}")
        sys.exit(4)
    if pred_written:
        try:
            with open(pred_written, encoding='utf-8') as _pf:
                _p = json.load(_pf)
            if not _p.get('予測'):
                raise ValueError("predictions の予測が空")
        except Exception as e:
            print(f"SELFCHECK NG(生成後): {pred_written} 再読込検査に失敗: {e}")
            sys.exit(4)
    print("SELFCHECK OK: highlights {}レース/{}場, predictions {}".format(
        n_races, n_venues,
        f"{len(pred_list)}レース(新規)" if pred_written else "既存保持/対象なし"))

if __name__ == '__main__':
    main()
