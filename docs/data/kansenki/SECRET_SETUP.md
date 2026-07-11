# CLAUDE_CODE_OAUTH_TOKEN 登録手順（けん作業・1枚）

観戦記の headless 執筆（`.github/workflows/writeKansenki.yml`）は、けんの **Claude Max サブスク**の
OAuth トークンで動きます（Anthropic API の従量課金は使いません）。手元で1回トークンを発行し、
リポジトリの Secret に入れるだけです。**トークンはコードやログに出しません。**

## 1. トークンを発行（手元のPCで1回）
1. Claude Code をインストール済みの端末で、ターミナルを開く
2. 次を実行：
   ```
   claude setup-token
   ```
3. ブラウザが開き、Claude（Max）アカウントで承認 → **1年有効のOAuthトークン**が発行される
4. 表示された `sk-ant-oat...`（OAuthトークン）をコピー
   ※ Claude Pro / Max / Team いずれかのサブスクが必要（Maxで可）

## 2. リポジトリに Secret 登録
1. GitHub のリポジトリを開く（abeken1026395/boatrace）
2. **Settings** → **Secrets and variables** → **Actions**
3. **New repository secret**
4. **Name**：`CLAUDE_CODE_OAUTH_TOKEN`（この名前で固定・変更しない）
5. **Secret**：1でコピーしたトークンを貼り付け
6. **Add secret**

## 3. 確認（試験1回）
- Actions → 「観戦記 執筆起動（headless・PRで停止）」を **Run workflow**（手動）で起動
- 成功すれば `kansenki/{掲載日}` ブランチと査読用PRが自動作成される（**マージはされない**）
- 認証エラー時はジョブが**赤く失敗**する（トークンの綴り／貼り付け欠け／失効を確認）

## トークン失効・期限切れ時の挙動
- トークンが失効すると headless 実行が非ゼロ終了 → **writeKansenki のジョブが失敗（赤いrun）** で即わかる。
- さらに翌朝 JST07:37 の **執筆漏れ警報**（kansenkiMissingAlarm）が「掲載日なのに記事0本」を検知し、
  ラベル `kansenki-missing` の **Issue を自動起票**する（二重に検知される）。
- 復旧：手順1で `claude setup-token` を再実行 → 手順2で **Update**（Nameは `CLAUDE_CODE_OAUTH_TOKEN` のまま）。

## 補足（--bare を外したことの影響）
- OAuthトークンは `--bare` モードでは読まれないため、WFは `--bare` を付けずに実行します。
- その結果リポジトリ直下の `CLAUDE.md`（プロジェクト方針メモ）が自動読込されますが、
  執筆の規範は **kansenkiRules.md**（システムプロンプトに注入）と **runbook.md** が正で、CLAUDE.md は補助情報です。
- 許可ツールは Read/Write/Edit と assign/lint のみに制限しているため、git/push/network は実行されません
  （公開は人がPRをマージして行う）。
