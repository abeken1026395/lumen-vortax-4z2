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
    # 気象ブロック抽出（weather1 系のdivを想定。無ければ天候/風速の周辺を出す）
    m=re.search(r'(<div class="weather1[\s\S]{0,2500}?</div>\s*</div>)', html)
    has_kisho = ('風' in html and ('m' in html or '波' in html))
    print(f"\n==== jcd{jcd} rno1 hd{HD} HTTP{code} len{len(html)} 気象語={has_kisho} ====")
    if m:
        block=re.sub(r'\s+',' ', m.group(1))
        print("weather1ブロック:", block[:1800])
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
