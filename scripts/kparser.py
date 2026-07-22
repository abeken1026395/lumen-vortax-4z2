# -*- coding: utf-8 -*-
"""Defensive full-field parser for mbrace K files.
parse_day(text, hd) -> dict(races, entries, payouts, anomalies).
Never drops unexpected tokens: stores them raw in the cell AND logs an anomaly.
Wraps each race in try/except so one bad race can't stop the file.
"""
import re

HEAD_RE = re.compile(
    r'^\s+(\d+)R[\s　]+(.+?)[\s　]+H(\d+)m'
    r'[\s　]+([^\s　]+)[\s　]+風[\s　]+([^\s　]+)[\s　]+(\d+)m'
    r'[\s　]+波[\s　]+(\d+)cm')
HEAD_LOOSE = re.compile(r'^\s+(\d+)R[\s　]+(.*)$')
DIST_RE = re.compile(r'H(\d+)m')
W_WEATHER = re.compile(r'H\d+m[\s　]+([^\s　]+)')
W_WIND = re.compile(r'風[\s　]+([^\s　]+)[\s　]+(\d+)m')
W_WAVE = re.compile(r'波[\s　]+(\d+)cm')

ENTRY_RE = re.compile(
    r'^\s*(\S+)[\s　]+(\d)[\s　]+(\d{4})[\s　]+(.+?)'
    r'[\s　]+(\d+)[\s　]+(\d+)[\s　]+(\d+\.\d{2})'
    r'[\s　]+(\d)[\s　]+(\S+)[\s　]+(.+?)[\s　]*$')
ENTRY_RE2 = re.compile(
    r'^\s*(\S+)[\s　]+(\d)[\s　]+(\d{4})[\s　]+(.+?)'
    r'[\s　]+(\d+)[\s　]+(\d+)[\s　]+(.*)$')

SHIKI = ['単勝', '複勝', '２連単', '２連複', '拡連複', '３連単', '３連複']
SHIKI_NO_NINKI = ('単勝', '複勝')
NORMAL_CHAKU = re.compile(r'^0?[1-6]$')
COMBO_HEAD = re.compile(r'^\d+-\d+')
NUM_RE = re.compile(r'^\d+$')
ENTRY_LEAD = re.compile(r'^\s*(\d|S|F|L|K|欠|失|妨|転|落|沈|不|エ)')


def _toks(s):
    return re.split(r'[\s　]+', s.strip())


def parse_day(text, hd):
    races = []
    entries = []
    payouts = []
    anom = []

    def A(jcd, rno, typ, raw):
        anom.append({'hd': hd, 'jcd': jcd, 'rno': rno, '種別': typ, '生行': raw})

    lines = text.split('\n')
    n = len(lines)
    i = 0
    while i < n:
        m = re.match(r'^(\d{2})KBGN', lines[i])
        if not m:
            i += 1
            continue
        jcd = m.group(1)
        i += 1
        block = []
        while i < n and not re.match(r'^(\d{2})KEND', lines[i]):
            block.append(lines[i])
            i += 1
        # locate column-header rows (one per race); heading = preceding non-blank line
        hdr_idxs = [idx for idx, l in enumerate(block) if '登番' in l and '選' in l]
        head_idxs = []
        for h in hdr_idxs:
            j = h - 1
            while j >= 0 and not block[j].strip():
                j -= 1
            head_idxs.append(j if j >= 0 else h)
        for k in range(len(head_idxs)):
            s = head_idxs[k]
            e = head_idxs[k + 1] if k + 1 < len(head_idxs) else len(block)
            section = block[s:e]
            try:
                _parse_race(section, jcd, hd, races, entries, payouts, A)
            except Exception as ex:
                head = section[0] if section else ''
                A(jcd, '', '例外', repr(ex) + ' :: ' + head)
        # advance past KEND
        i += 1

    return {'races': races, 'entries': entries, 'payouts': payouts, 'anomalies': anom}


def _parse_race(section, jcd, hd, races, entries, payouts, A):
    head = section[0]
    hm = HEAD_RE.match(head)
    if hm:
        rno = int(hm.group(1))
        raceName = hm.group(2).strip()
        distance = 'H' + hm.group(3) + 'm'
        weather = hm.group(4)
        windDir = hm.group(5)
        windMps = hm.group(6) + 'm'
        waveCm = hm.group(7) + 'cm'
    else:
        loose = HEAD_LOOSE.match(head)
        rno = int(loose.group(1)) if loose else ''
        d = DIST_RE.search(head)
        distance = ('H' + d.group(1) + 'm') if d else ''
        # raceName = text between rno and distance if present, else the loose rest
        nm = re.match(r'^\s+\d+R[\s　]+(.+?)[\s　]+H\d+m', head)
        raceName = nm.group(1).strip() if nm else (loose.group(2).strip() if loose else '')
        w = W_WEATHER.search(head)
        weather = w.group(1) if w else ''
        wd = W_WIND.search(head)
        windDir = wd.group(1) if wd else ''
        windMps = (wd.group(2) + 'm') if wd else ''
        wv = W_WAVE.search(head)
        waveCm = (wv.group(1) + 'cm') if wv else ''
        if not (distance and weather and windDir and windMps and waveCm):
            A(jcd, rno, '気象トークン欠落', head)
    if raceName == '':
        A(jcd, rno, 'raceName空', head)

    # kimarite = last token of the 登番 column header line
    kimarite = ''
    for l in section:
        if '登番' in l and '選' in l:
            kimarite = _toks(l)[-1]
            break

    races.append({
        'hd': hd, 'jcd': jcd, 'rno': rno,
        'raceName': raceName, 'distance': distance, 'weather': weather,
        'windDir': windDir, 'windMps': windMps, 'waveCm': waveCm,
        'kimarite': kimarite,
    })

    cur_shiki = None
    for l in section[1:]:
        if not l.strip():
            continue
        if '登番' in l and '選' in l:
            continue
        if '---' in l:
            continue

        t = _toks(l)

        # payout header line
        if t and t[0] in SHIKI:
            cur_shiki = t[0]
            rest = t[1:]
            _emit_payout(hd, jcd, rno, cur_shiki, rest, l, payouts, A)
            continue
        # payout continuation (label-less indented combo line) for ANY shiki.
        # covers 拡連複 multi-rows AND 同着(dead-heat) 2つ目当り目 for
        # ２連単/２連複/３連単/３連複. Inherits the preceding shiki, same format.
        if cur_shiki and t and COMBO_HEAD.match(t[0]):
            _emit_payout(hd, jcd, rno, cur_shiki, t, l, payouts, A)
            continue

        # entry line (strict)
        em = ENTRY_RE.match(l)
        if em:
            rt = em.group(10).strip()
            if not re.search(r'\d', rt):
                rt = ''
            _emit_entry(hd, jcd, rno, em.group(1), em.group(2), em.group(3),
                        em.group(4).strip(), em.group(5), em.group(6),
                        em.group(7), em.group(8), em.group(9), rt, l,
                        entries, A)
            continue
        # entry line (lenient, e.g. 欠場K0 with 'K .' cells)
        em2 = ENTRY_RE2.match(l)
        if em2 and ENTRY_LEAD.match(l):
            _emit_entry(hd, jcd, rno, em2.group(1), em2.group(2), em2.group(3),
                        em2.group(4).strip(), em2.group(5), em2.group(6),
                        '', '', '', '', l, entries, A)
            continue

        # anything else that looks like data but didn't parse
        if ENTRY_LEAD.match(l):
            A(jcd, rno, '想定外行', l)


def _emit_entry(hd, jcd, rno, chaku, waku, toban, name, motorNo, boatNo,
                tenjiT, shinnyu, st, raceTime, raw, entries, A):
    entries.append({
        'hd': hd, 'jcd': jcd, 'rno': rno, 'chaku': chaku, 'waku': waku,
        'toban': toban, 'name': name, 'motorNo': motorNo, 'boatNo': boatNo,
        'tenjiT': tenjiT, 'shinnyu': shinnyu, 'st': st, 'raceTime': raceTime,
    })
    if NORMAL_CHAKU.match(chaku):
        return
    if chaku == 'K0':
        A(jcd, rno, '欠場K0', raw.rstrip())
    elif re.match(r'^S[0-9]$', chaku):
        A(jcd, rno, '失格系S0S1', raw.rstrip())
    else:
        A(jcd, rno, '想定外chaku記号', raw.rstrip())


def _emit_payout(hd, jcd, rno, shiki, rest, raw, payouts, A):
    if shiki in SHIKI_NO_NINKI:
        # pairs of (combo, payout), no ninki
        if len(rest) % 2 != 0 or not rest:
            A(jcd, rno, '払戻行パース不能', raw.rstrip())
        for idx in range(0, len(rest) - 1, 2):
            combo = rest[idx]
            payout = rest[idx + 1]
            payouts.append({'hd': hd, 'jcd': jcd, 'rno': rno, 'shiki': shiki,
                            'combo': combo, 'payout': payout, 'ninki': ''})
            if not NUM_RE.match(payout):
                A(jcd, rno, '払戻行パース不能', raw.rstrip())
    else:
        combo = rest[0] if rest else ''
        payout = rest[1] if len(rest) > 1 else ''
        ninki = ''
        if '人気' in rest:
            kk = rest.index('人気')
            if kk + 1 < len(rest):
                ninki = rest[kk + 1]
        payouts.append({'hd': hd, 'jcd': jcd, 'rno': rno, 'shiki': shiki,
                        'combo': combo, 'payout': payout, 'ninki': ninki})
        if not NUM_RE.match(payout):
            A(jcd, rno, '払戻行パース不能', raw.rstrip())
