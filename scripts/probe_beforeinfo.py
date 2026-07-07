#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 一時プローブ：boatrace.jp 直前情報(beforeinfo)ページの気象ブロック現物を取得・表示。
# 実況天候(実測値: 風速/風向/波高/天候/気温/水温)の在り処とHTML構造を確認する目的。
import sys, re, urllib.request, ssl
HEADERS={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
HD=sys.argv[1] if len(sys.argv)>1 else "20260705"
def fetch(jcd,rno,hd):
    url=f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={rno}&jcd={jcd}&hd={hd}"
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=20,context=ssl.create_default_context()) as r:
        return url, r.getcode(), r.read().decode("utf-8","replace")
for jcd in [f"{i:02d}" for i in range(1,25)]:
    try:
        url,code,html=fetch(jcd,1,HD)
    except Exception as e:
        print(f"jcd{jcd}: ERR {e}"); continue
    # 気象ブロック抽出（weather1 全体）
    m=re.search(r'<div class="weather1">([\s\S]*?)<!--/weather1-->', html) or re.search(r'<div class="weather1">([\s\S]{0,4000}?)</div>\s*</div>\s*</div>', html)
    print(f"\n==== jcd{jcd} rno1 hd{HD} HTTP{code} len{len(html)} ====")
    if m:
        block=m.group(1)
        tm=re.search(r'weather1_title">([^<]+)<', html)
        print("実況時刻ラベル:", tm.group(1) if tm else "?")
        # 各bodyUnit: Title/Data と 付随class(is-direction/is-weather)
        for u in re.findall(r'<div class="weather1_bodyUnit([^"]*)">([\s\S]*?)</div>\s*</div>', html):
            cls=u[0].strip(); body=u[1]
            title=re.search(r'LabelTitle">([^<]*)<',body); data=re.search(r'LabelData">([^<]*)<',body)
            img=re.search(r'weather1_bodyUnitImage ([\w-]+)',body)
            print(f"  unit[{cls}] title={title.group(1) if title else '-'} data={data.group(1) if data else '-'} img={img.group(1) if img else '-'}")
        break
    else:
        # class名の候補を洗い出す
        cls=set(re.findall(r'class="(weather[\w-]*|[\w-]*is-weather[\w-]*|[\w-]*Weather[\w-]*)"', html))
        idx=html.find('風速')
        print("weather1不検出。weather系class:", sorted(cls)[:12])
        if idx>0: print("『風速』周辺:", re.sub(r'\s+',' ',html[idx-400:idx+400]))
        # 天候/波/水温 のラベル存在
        for lab in ("天候","風速","風向","水温","波"):
            print(f"  label {lab}: {'あり' if lab in html else 'なし'}")
        break
print("\n--- probe done ---")
