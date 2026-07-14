# data/kfiles/ — 競走成績(Kファイル)置き場

`buildMotorUsage.py` が読む Kファイルをここに置く。

## 運用
- `py scripts/fetchKfiles.py` で mbrace から `kYYMMDD.lzh` をこのフォルダへ一括取得する。
  範囲は環境変数 `START` / `END`（`YYYYMMDD`、既定 20260401〜20260708）、`FORCE=1` で再取得。
- そのあと `py scripts/buildMotorUsage.py` を実行すると、
  `docs/data/motorUsage.json`（各場モーターの初卸推定からの走行数集計）が生成される。
- **ローカル環境からは mbrace に到達できる**（2026-07-14 実測）。一方 GitHub Actions のランナーからは
  遮断されるため、この収集は当面ローカル実行が前提（CLAUDE.md 既知問題(1)と同じ扱い）。
  取得できない日があっても**欠けたまま**にする（補完・推測はしない）。

## 受け付ける形式
- `kYYMMDD.lzh`（SHIFT_JIS）… 通常はこれ。解凍は `lhafile` があればそれ、無ければ
  Windows 同梱 bsdtar(`C:\Windows\System32\tar.exe`)。Python 3.14 では lhafile が
  ビルドできないため実質 bsdtar 経路。
- `kYYMMDD.txt`（SHIFT_JIS・解凍済み）… ローカル検証用にも読める
- 同じ日の `.lzh` と `.txt` を**両方置かない**（buildMotorUsage.py は両方読むため二重計上になる）。

## 注意
- 「初卸」は Kファイル初出日での**推定**（公式交換日は非公開）。
- 走行数・着順は読めた明細の**実測カウントのみ**。欠けた期間は補完・推測しない。
- Kファイル自体はこのリポジトリにコミットしなくてよい（生成物 `motorUsage.json` のみ反映すれば足りる）。
