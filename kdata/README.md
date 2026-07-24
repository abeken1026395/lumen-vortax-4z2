# kdata — mbrace Kファイル（競走成績）由来データの保全用コピー

過去約1年分の競走成績（Kファイル）を全項目パースして得た races / entries / payouts の保全用コピー。
公開目的ではなく **データ保全（バックアップ）目的**。docs/ 配下ではないため GitHub Pages では配信されない。

## 出典
- boatrace（mbrace）公式 競走成績（Kファイル）
- URL規則: `http://www1.mbrace.or.jp/od2/K/YYYYMM/kYYMMDD.lzh`
  （例: 2026-07-10 → `http://www1.mbrace.or.jp/od2/K/202607/k260710.lzh`）
- 本文は SHIFT_JIS。LZH は -lh5-。

## カバー期間・件数
- 期間: **hd 250722 〜 260721**（2025-07-22 〜 2026-07-21、YYMMDD）
- races: **54,696** レコード
- entries: **328,176** レコード
- payouts: **546,650** レコード

## ファイル構成
| ファイル | 内容 | 列数 | 行数 |
|---|---|---|---|
| `racesAll.csv` | races 全期間結合（月別の忠実な単純結合） | 10 | 54,696 |
| `entriesFull.csv` | **entries 完全版・全期間結合**（月別13列を hd,jcd,rno,waku 昇順で単純結合。entriesの本体） | 13 | 328,176 |
| `entriesLite2.csv` | entries 軽量版（entriesFull から5列を間引いた派生・アップロード用途。**完全版ではない**） | 8 | 328,176 |
| `entries202507.csv`〜`entries202607.csv`（13本） | entries 月別・全13列（完全版の元データ） | 13 | 計 328,176 |
| `payouts202507.csv`〜`payouts202607.csv`（13本） | payouts 月別（全結合ファイルは未作成のため月別で保全） | 7 | 計 546,650 |

補足（保全方針）:
- **entries の本体は `entriesFull.csv`（全13列）**。`entriesLite2.csv` は entriesFull から
  `chaku, name, shinnyu, st, raceTime` の**5列を間引いた8列の派生**（アップロード用途）であり、**完全版ではない**。
  「All＝完全版」と誤認して月別や `entriesFull.csv` を捨てないこと。月別entries（13列）も元データとして保全している。
- `racesAll.csv` は月別races（10列）の忠実な単純結合（行数=合計、ヘッダ一致）のため、月別racesは別途置いていない。

## 各CSVの列と1レコード実例

### racesAll.csv
```
hd,jcd,rno,raceName,distance,weather,windDir,windMps,waveCm,kimarite
250731,24,1,予選Ａ組男子,H1800m,晴,西,2m,1cm,逃げ
```

### entries202507.csv 〜（月別・完全13列）
```
hd,jcd,rno,chaku,waku,toban,name,motorNo,boatNo,tenjiT,shinnyu,st,raceTime
250731,24,1,01,1,4213,重　富　　伸　也,39,73,7.00,1,0.11,1.52.1
```

### entriesFull.csv（完全版・全13列・本体）
```
hd,jcd,rno,chaku,waku,toban,name,motorNo,boatNo,tenjiT,shinnyu,st,raceTime
250722,02,1,01,1,5182,宮　崎　　安　奈,15,41,6.70,1,0.09,1.50.8
```

### entriesLite2.csv（軽量8列・派生。本体は entriesFull.csv）
entriesFull から `chaku, name, shinnyu, st, raceTime` の5列を間引いた版。**完全版ではない。**
```
hd,jcd,rno,waku,toban,motorNo,boatNo,tenjiT
250731,24,1,1,4213,39,73,7.00
```

### payouts202507.csv 〜（月別）
```
hd,jcd,rno,shiki,combo,payout,ninki
250731,24,1,単勝,1,190,
```

## 生成スクリプト（scripts/ 配下）
- `scripts/kdataRunAll.py` — 全期間ハーベスト（DL → 解凍 → パース → 月別CSV出力）
- `scripts/kdataParse.py` — 単日パース＋CSV書き出し（検証用）
- `scripts/kdataReparse.py` — 保存済み生TXTから再パース（同着取り込み等の再生成用）
- `scripts/kdataMergeEntries.py` — 月別entries（13列）を hd,jcd,rno,waku 昇順で結合し `kdata/entriesFull.csv` を生成
- 依存ライブラリ: `scripts/kparser.py`（全項目パーサ parse_day）, `scripts/unpackLzh.py`（純Python lh5解凍）

注記: 上記 kdataRunAll.py / kdataParse.py / kdataReparse.py は、パース検証時の scratchpad 作業ディレクトリを
指すパス定数を含んだままコピーしている（保全目的のためコード無改変）。実行にはパス定数の調整が必要（動作確認は別タスク）。

## Kファイル本体（lzh）の保存先と再パース可能範囲
- 保存先: `data/kfiles/`（`.gitignore` 済み・非コミット）
- 現存: **k260401.lzh 〜 k260723.lzh（114本、260401〜260723）**
- したがってローカルの lzh から再パース可能なのは **260401 以降**のみ。
  CSVカバー期間のうち **250722〜260331 分の lzh は手元に無い**（再パースには mbrace からの再DLが必要）。
