# data/kfiles/ — 競走成績(Kファイル)置き場

`buildMotorUsage.py` が読む Kファイルをここに置く。

## 運用（手動収集・mbrace不要の処理部）
- mbrace.or.jp（Kファイル配布元）は GitHub Actions / Claude Code / 実行環境すべてから **403** で遮断される。
  そのため Kファイルの取得は **人力（iPhone/PC）** で行い、取得した `kYYMMDD.lzh` をこのフォルダに置く。
- 置いたあと `python scripts/buildMotorUsage.py` を実行すると、
  `docs/data/motorUsage.json`（各場モーターの初卸推定からの走行数集計）が生成される。

## 受け付ける形式
- `kYYMMDD.lzh`（SHIFT_JIS・lhafile で解凍）… 通常はこれ
- `kYYMMDD.txt`（SHIFT_JIS・解凍済み）… ローカル検証用にも読める

## 注意
- 「初卸」は Kファイル初出日での**推定**（公式交換日は非公開）。
- 走行数・着順は読めた明細の**実測カウントのみ**。欠けた期間は補完・推測しない。
- Kファイル自体はこのリポジトリにコミットしなくてよい（生成物 `motorUsage.json` のみ反映すれば足りる）。
