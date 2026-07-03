# CLAUDE.md — boatrace プロジェクト引き継ぎメモ

## このプロジェクトでの応対方針
- **常に日本語のみで返答する。**
- **思考過程（reasoning / 内部検討）は表示しない。** 結論と必要な説明だけを簡潔に返す。
- **bash・ファイル編集・git 系コマンドは確認せず自動実行してよい**（承認画面を出さない運用）。

---

## 目的
競艇（ボートレース）の公開データを毎日自動収集し、GitHub Pages（`docs/`）で閲覧できる
データポータルとして公開するプロジェクト。あわせて、朝に出す「見立て（荒れ/堅め判定）」を
夜の結果と突き合わせて検証する仕組みを持つ。

**方針上の重要な制約:** 公開ページ・見どころ生成では
**買い目・確率・勝者の断定・選手の内心推測は出さない**（`docs/data/tenkai_logic.json` の方針に準拠）。
勝敗の主観的予想ではなく「水面傾向・展開の見どころ」と「荒れやすさの可視化」に留める。
判定や主役艇などの内部値は公開 `highlights.json` には入れず、非公開の `predictions/` にのみ残す。

---

## ⚠️ 既知の重大問題・運用上の注意（最初に読む）

### (1) mbrace のIP遮断問題（払戻・結果収集が停止中）
- GitHub Actions のランナーから `www1.mbrace.or.jp`（公式競走成績LZH配布）への
  アクセスが遮断されるようになった。
- 影響:
  - **徳山払戻の daily 収集が 2026/05/01 分で停止**（`docs/payouts/tokuyamaPayouts.csv` は
    末尾が `20260501`）。
  - **桐生払戻も Timeout で取得できず**（`docs/payouts/kiryuPayouts.csv` はヘッダのみで実データなし）。
  - 同じ mbrace LZH に依存する `buildResults.py` / `scrapeKimarite.py` も
    Actions 経由では失敗しうる。
- **復旧の本命:** この **Claude Code（ローカル環境）からの mbrace アクセスでDL** し、
  取得できた CSV/JSON をコミットして反映する運用に切り替える。
  （Actions のスケジュールは残すが、mbrace 依存ジョブは当面ローカル手動が前提。）

### (2) profile.json は自動更新の対象外（手動マージ管理）
- `docs/players/profile.json` は選手図鑑（`docs/players/index.html`「選手図鑑」）の
  手作りデータ。**どの自動更新 Action の対象にもなっていない。**
- 構造: 登録番号をキーに、`tagline` / `nickname` / `note` / `hobby` を持つ（現在 246 選手・
  一部フィールドのみ記入。全件は埋まっていない）。
- あだ名の一括追記は `scripts/batch_update_nicknames.py` を使う（コード内の辞書に追記して実行）。
- **編集は手動マージで管理**する。スクレイプで上書きされない前提で運用すること。

### (3) 残タスク: 検証サマリを Actions に組み込む
- `updateResults.yml` はステップとして `build_verify_summary.py` を呼ぶが、
  **`scripts/build_verify_summary.py` はリポジトリに未追跡**で、
  出力 `docs/data/verify_summary.json` も未コミット。
- 対応: `build_verify_summary.py` を追加し、`updateResults.yml` のコミット手順で
  `docs/data/verify_summary.json` を確実に `git add` すること
  （現状 workflow には add 行はあるが、生成スクリプト本体が無いため機能していない）。

### (4) 残タスク: 選手グレード（級別）の更新（2026後期）
- 選手図鑑・各ページは **2026前期**基準（`docs/players/index.html` タイトル「選手図鑑 2026前期」）。
- **2026年7月1日以降は後期（fan2607 = 2026年7月期のファイル）で級別を更新する必要がある。**
- 級別（A1/A2/B1/B2）は `build_highlights.py` / `build_arare.py` / `scrape_racers.py` /
  `scrape_motors.py` が判定に使うため、期替わりの反映漏れに注意。

---

## ディレクトリ構成
```
.github/workflows/   GitHub Actions（自動収集・検証のスケジュール定義、全9本）
scripts/             データ収集・集計・生成の Python（全13本）＋HTMLテンプレート2本
docs/                GitHub Pages で公開する静的サイト＋データ本体
  index.html         データポータルの入口
  data/              定数・ロジック・生成JSON（weather / arare / tenkai_logic ほか）
  players/           選手図鑑（index.html, profile.json[手動], racerKimarite.csv）
  racers/            出走表（racers_today.csv）とビューワー
  motor/             モーター成績（motors_all.csv）とビューワー
  highlights/        本日の見どころ（highlights.json＋prev/prev2 の履歴）
  payouts/           徳山 R別万舟率（tokuyamaPayouts.csv, tokuyamaManRate.json）
  kiryu-payouts/     桐生 R別万舟率ページ（データは docs/payouts/kiryu*）
  stadium/           24場 特性＆荒れサイン早見表（gourmet.json あり）
  announcers/        実況アナ図鑑（announcers.json）
  uranai/            選手占い（相性・勝負運）
  aisho-suminoe/     相性で選ぶ 住之江・女子戦
  shobuun-suminoe/   勝負運ランキング 住之江・女子戦
predictions/         朝の見立て（YYYYMMDD.json、非公開の検証用スナップショット）
results/             夜に生成する結果データ（未追跡＝生成物。ローカル/Actionsで生成）
verify_log.csv       見立て×結果の突合ログ（未追跡＝生成物）
```

---

## 公開ページ一覧（`docs/`, GitHub Pages）
| パス | タイトル | 内容 |
|---|---|---|
| `index.html` | BOATRACE データポータル | 入口。players/racers/motor/stadium カード |
| `players/` | 選手図鑑 2026前期 | 選手プロフィール（`profile.json` 手動）＋決まり手 |
| `racers/` | 出走表 | 当日/翌日の出走表ビューワー |
| `motor/` | モーター成績 | 場×登番のモーター2連対率 |
| `highlights/` | 本日の見どころ｜データ攻め | 展開文・見どころ（判定は非公開） |
| `stadium/` | 24場 特性＆荒れサイン早見表 | 場特性・荒れ傾向・グルメ |
| `payouts/` | 徳山 R別万舟率 | 徳山の万舟率・平均配当 |
| `kiryu-payouts/` | 桐生 R別万舟率 | 桐生の万舟率（※(1)により停止中） |
| `announcers/` | 実況アナ図鑑 | アナウンサー情報（`announcers.json`） |
| `uranai/` | 選手占い（相性・勝負運） | 占い系コンテンツ |
| `aisho-suminoe/` | 相性で選ぶ 住之江・女子戦 | 住之江女子戦の相性 |
| `shobuun-suminoe/` | 勝負運ランキング 住之江・女子戦 | 住之江女子戦の勝負運 |

---

## スクリプトの役割（`scripts/`、全13本）
| スクリプト | 役割 | 主な入力 → 出力 |
|---|---|---|
| `scrape_racers.py` | 出走表スクレイプ（boatrace.jp） | 公式 → `docs/racers/racers_today.csv`, `index.html` |
| `scrape_motors.py` | モーター成績スクレイプ（boatrace.jp） | 公式 → `docs/motor/motors_all.csv`, `index.html` |
| `fetch_weather.py` | 24場の風予報取得（Open-Meteo API） | API → `docs/data/weather.json` |
| `scrapeKimarite.py` | 選手別 決まり手率・前づけ傾向を直近183日集計（mbrace LZH※） | 公式K配布 → `docs/players/racerKimarite.csv` |
| `build_highlights.py` | 出走表＋モーター＋決まり手＋風から「見どころ/展開文」を生成 | 上記CSV/JSON → `docs/highlights/highlights.json`（＋非公開 `predictions/YYYYMMDD.json`） |
| `build_arare.py` | 荒れ指数（荒れ条件が何個揃うか）を可視化。標準ライブラリのみ | 出走表/モーター/風＋場定数 → `docs/data/arare.json` |
| `scrapeTokuyamaPayouts.py` | 徳山(18)の3連単払戻を収集（mbrace LZH※） | 公式K配布 → `docs/payouts/tokuyamaPayouts.csv` |
| `buildTokuyamaManRate.py` | 徳山 払戻CSV → R別万舟率JSON集計 | CSV → `docs/payouts/tokuyamaManRate.json` |
| `scrapeKiryuPayouts.py` | 桐生(01)の3連単払戻を収集（mbrace LZH※） | 公式K配布 → `docs/payouts/kiryuPayouts.csv` |
| `buildKiryuManRate.py` | 桐生 払戻CSV → R別万舟率JSON集計 | CSV → `docs/payouts/kiryuManRate.json` |
| `buildResults.py` | 当日全24場の着順(3連単)と配当を抽出（mbrace LZH※） | 公式K配布 → `results/YYYYMMDD.json` |
| `verifyPredictions.py` | 朝の見立てと夜の結果を場×レースで突合し追記 | `predictions/` + `results/` → `verify_log.csv` |
| `batch_update_nicknames.py` | 選手あだ名を手動一括更新（コード内辞書に追記して実行） | `docs/players/profile.json` を書き換え |

`template.html` / `template_racers.html` … スクレイプ結果を埋め込むビューワーHTMLの雛形。
`build_verify_summary.py` … `updateResults.yml` から呼ばれるが**未追跡**（→残タスク(3)）。

※mbrace LZH に依存するスクリプトは、現在 Actions 経由では IP 遮断で失敗しうる（→(1)）。
LZH 解凍は `lhasa`（`lha` コマンド）または `lhafile`(pip) を使う。

---

## GitHub Actions ワークフロー（`.github/workflows/`、全9本）
すべて `github-actions[bot]` が生成物をコミット＆プッシュ。時刻は UTC 指定（JST=UTC+9）。
各ジョブは専用 `concurrency` グループでプッシュ競合を回避。`workflow_dispatch` で手動実行可。

| ファイル | 名前 | トリガー | 実行内容 | 状態 |
|---|---|---|---|---|
| `update_racers.yml` | 出走表データ自動更新 | 朝（当日確定）＋夜（翌日分、遅延対策で複数本） | `scrape_racers.py` | 稼働 |
| `update_motors.yml` | モーターデータ自動更新 | 朝＋夜（翌日予習） | `scrape_motors.py` | 稼働 |
| `update_weather.yml` | 気象データ自動更新 | 3時間ごと | `fetch_weather.py` | 稼働 |
| `update_highlights.yml` | 見どころJSON自動生成 | 「出走表データ自動更新」完了を受けて（`workflow_run`） | `build_highlights.py` | 稼働 |
| `update arare.yml` | 荒れ指数 更新 | 毎日 JST 8:45（出走表更新の後） | `build_arare.py` | 稼働 |
| `updateKimarite.yml` | update kimarite | 月2回（1日/15日） | `scrapeKimarite.py`（183日窓） | mbrace依存(1) |
| `updateResults.yml` | 見立て結果照合（夜） | 毎日 JST 23:37（全場終了後） | `buildResults.py`→`verifyPredictions.py`→`build_verify_summary.py`※未追跡 | mbrace依存(1)/残(3) |
| `updateTokuyamaPayouts.yml` | update tokuyama payouts | 毎日（JST 翌9:20/10:20 相当） | `scrapeTokuyamaPayouts.py`→`buildTokuyamaManRate.py` | **2026/05/01で停止(1)** |
| `updateKiryuPayouts.yml` | update kiryu payouts | 毎日 JST 翌0:20（結果確定後） | `scrapeKiryuPayouts.py`→`buildKiryuManRate.py` | **Timeoutで停止(1)** |

払戻系ジョブは `YM`/`ym` 入力で対象月を指定できる。

---

## データの流れ
### 1) 日次の公開データ更新（朝〜日中）
```
公式(boatrace.jp) ─ scrape_racers.py ─→ docs/racers/racers_today.csv
公式(boatrace.jp) ─ scrape_motors.py ─→ docs/motor/motors_all.csv
Open-Meteo        ─ fetch_weather.py ─→ docs/data/weather.json
公式(mbrace LZH※) ─ scrapeKimarite.py ─→ docs/players/racerKimarite.csv（月2回）
        │
        ▼（出走表更新の完了をトリガに）
build_highlights.py
   ├─→ docs/highlights/highlights.json（公開・判定や主役艇は含めない）
   └─→ predictions/YYYYMMDD.json（非公開・検証用スナップショット）
build_arare.py ─→ docs/data/arare.json（荒れ指数の可視化）
```

### 2) 夜の結果照合（検証ループ）
```
公式(mbrace LZH※) ─ buildResults.py ─→ results/YYYYMMDD.json（当日全24場の着順＋配当）
predictions/YYYYMMDD.json ＋ results/YYYYMMDD.json
        │ verifyPredictions.py（場×レースで突合。predictionsは読むだけ・書き換えない）
        ▼
verify_log.csv（1レース1行で追記）
        │ build_verify_summary.py（※未追跡＝残タスク(3)）
        ▼
docs/data/verify_summary.json（検証の要約・未コミット）
```
朝に出した見立て（`predictions/`）を夜に確定した結果（`results/`）と突き合わせ、
的中/傾向を記録する ＝ **見立ての精度を後から検証できる**設計。

### 3) 場別 払戻分析（徳山・桐生）※現在 mbrace 遮断で停止中(1)
```
公式(mbrace LZH※) ─ scrape*Payouts.py ─→ docs/payouts/*Payouts.csv（hd, rno, combo, payout）
        │ build*ManRate.py
        ▼
docs/payouts/*ManRate.json（R別の万舟率・平均配当・最高配当TOP5 など）
```

---

## 開発メモ
- 24場コード（jcd）は各スクリプトにハードコード（01桐生 … 24大村）。
- タイムゾーンは JST（UTC+9）。Actions は UTC 実行なので JST 換算して対象日を決める
  （夜の実行は翌日分を予習対象にするロジックあり）。
- 級別は A1/A2/B1/B2。期替わり（前期/後期）で更新が必要（→残タスク(4)）。
- スクレイプ系は公式サーバ負荷軽減のため `SLEEP`（既定1.0秒）を挟む。
- 出力ファイルは基本 UTF-8。`build_highlights.py` の入力CSVは BOM 付き(`utf-8-sig`)を読む。
- `predictions/` は「結果を見る前の値」。検証で読むだけにし、決して上書きしない（鉄則）。
- mbrace 依存の収集は当面ローカル（この Claude Code）から実行してコミットする（→(1)）。
