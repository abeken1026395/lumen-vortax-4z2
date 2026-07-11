# ANTHROPIC_API_KEY 登録手順（けん作業・1枚）

観戦記の headless 執筆（`.github/workflows/writeKansenki.yml`）が Claude Code を動かすために、
リポジトリに APIキーを1つ登録します。**この鍵はコードやログに出しません（Secretに入れるだけ）。**

## 1. APIキーを発行
1. https://console.anthropic.com/ にログイン
2. 左メニュー **API Keys** → **Create Key**
3. 名前は任意（例：`boatrace-kansenki`）→ 作成
4. 表示された `sk-ant-...` の鍵をコピー（**この画面を離れると再表示できない**ので今コピー）

## 2. リポジトリに Secret 登録
1. GitHub のリポジトリを開く（abeken1026395/boatrace）
2. **Settings** → 左メニュー **Secrets and variables** → **Actions**
3. **New repository secret**
4. **Name**：`ANTHROPIC_API_KEY`（この名前で固定・変更しない）
5. **Secret**：1でコピーした `sk-ant-...` を貼り付け
6. **Add secret**

## 3. 確認
- Actions → 「観戦記 執筆起動（headless・PRで停止）」を **Run workflow**（手動）で1回起動。
- 成功すれば `kansenki/{掲載日}` ブランチと査読用PRが自動作成される（マージはされない）。
- 認証エラー時はジョブが失敗する（鍵名の綴り／貼り付け欠けを確認）。

## 補足
- 料金は Anthropic の従量課金（使った分だけ）。1回の実額は各runのログ `cost_usd=` に出ます。
- 鍵を差し替えたいときは同じ手順で **Update**（Nameは `ANTHROPIC_API_KEY` のまま）。
- 外部cron（cron-job.org 等）から起動する場合も、この Secret があれば追加設定は不要
  （cron は「起動を叩く」だけ・鍵は GitHub 側に保持）。
