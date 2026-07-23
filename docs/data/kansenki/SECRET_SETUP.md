# ANTHROPIC_API_KEY 登録手順（けん作業・1枚）

観戦記の headless 執筆（`.github/workflows/writeKansenki.yml`）は、**Anthropic Console の APIキー**
（`sk-ant-api…`）で動きます。**APIキーは失効しない**ため、旧OAuthトークン（`sk-ant-oat…`）のように
定期的な再発行・貼り直しが要りません（OAuthは定期失効し、CIを止める原因になっていました）。
手元で1回キーを発行し、リポジトリの Secret に入れるだけです。**キーはコードやログに出しません。**

## 1. APIキーを発行（Anthropic Console で1回）
1. https://console.anthropic.com/ にログイン
2. **Settings → API keys → Create Key**
3. 観戦記専用のキーとして作成（名前例：`kansenki-ci`）
4. 表示された `sk-ant-api...` をコピー（この画面でしか全体は見られない）
5. **推奨（安全対策）**：**Settings → Limits** で月次の **Spend limit（使用上限）** を設定しておく
   （万一キーが漏れても被害が上限で止まる）

## 2. リポジトリに Secret 登録
1. GitHub のリポジトリを開く（**`abeken1026395/lumen-vortax-4z2`**）
   ※旧ドキュメントの `boatrace` は誤り。実リポ名は `lumen-vortax-4z2`。
2. **Settings** → **Secrets and variables** → **Actions**
3. 既存の場合は `ANTHROPIC_API_KEY` の **鉛筆(Update)**、無ければ **New repository secret**
4. **Name**：`ANTHROPIC_API_KEY`（この名前で固定・変更しない）
5. **Secret**：1でコピーしたキーを貼り付け（**前後の空白・改行を含めない**）
6. **Add secret / Update secret**

## 3. 隔離検証（貼る前に手元で1回・任意だが推奨）
ローカルの認証情報を混ぜないため、一時HOMEで APIキー単体の有効性を確認する。

Windows（PowerShell）:
```
$env:HOME="$env:TEMP\claudetest"; $env:USERPROFILE=$env:HOME
New-Item -ItemType Directory -Force $env:HOME | Out-Null
$env:ANTHROPIC_API_KEY="<発行したキー>"
claude -p "1と答えて" --model claude-sonnet-5 --output-format json
```
判定：`rc=0` かつ `total_cost_usd` に数値 → CIで有効。`rc≠0` → 貼らずにエラーを確認。

## 4. 確認（試験1回）
- Actions →「観戦記 執筆起動」を **Run workflow**（手動）で起動
- ただし当日分が執筆済みだと `run=0` の no-op になる。実証は**記事ゼロ状態での自然発火**で行う
  （成功すれば lint 全場PASS の記事が main へ自動追記＝公開される）
- 認証エラー時はジョブが**赤く失敗**する（キーの綴り／貼り付け欠け／無効化を確認）

## 失効・障害時の挙動と復旧
- APIキーは通常失効しないが、無効化・上限到達・障害時は headless 実行が非ゼロ終了 →
  **writeKansenki のジョブが失敗（赤いrun）** で即わかる。
- さらに翌朝 JST07:37 の **執筆漏れ警報**（kansenkiMissingAlarm）が「掲載日なのに記事0本」を検知し、
  ラベル `kansenki-missing` の **Issue を自動起票**する（二重に検知される）。
- 復旧：Console で新しいキーを発行 → 手順2で **Update**（Nameは `ANTHROPIC_API_KEY` のまま）。
- ローテーション：数か月ごとに新キーへ差し替え（旧キーは Console で失効）。

## 補足（実行モード・許可ツール）
- WFは `--bare` を付けずに実行する。認証は env の `ANTHROPIC_API_KEY` を使う
  （fresh CI HOME に OAuth は無いので claude はAPIキーで動く）。
- リポジトリ直下の `CLAUDE.md` が自動読込されるが、執筆の規範は
  **kansenkiRules.md**（システムプロンプトに注入）と **runbook.md** が正で、CLAUDE.md は補助情報。
- 許可ツールは Read/Write/Edit と assign/lint のみに制限しているため、git/push/network は実行されない
  （公開はWFが lint 全場PASS を確認してから main へ直接コミットして行う）。
