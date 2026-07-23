# writeKansenkiLocal.ps1
# 観戦記の自走をローカルPCで実行する（認証済み claude CLI＝Maxプラン枠・API課金なし）。
# GitHub Actions では OAuth/Secret 問題で自走が安定しなかったため、ローカルのタスクスケジューラで毎朝実行する。
# 登録: scripts/registerWriteKansenkiLocal.ps1（毎日 JST 5:30・Interactive＋WakeToRun）。
#
# 処理順（writeKansenki.yml のローカル移植）:
#   a. main へ同期（checkout main → pull）。作業ツリーが汚れていれば何もせず退避（ユーザー作業の巻き込み回避）。
#   b. kansenki_pubplan.py で掲載日の toWrite を得る。空なら「執筆対象なし」で正常終了。
#   c. 二重執筆防止: articles/<pubdate>-*.json が既に在れば skip（既存記事は不変）。
#   d. assign_styles.py（位置引数）でスタイル決定。
#   e. claude -p ... で未執筆場のみ執筆（runbook 全文＋kansenkiRules をシステムプロンプト）。claude は push しない。
#   f. lint（各記事＋--coverage）。FAIL の記事は削除して持ち越し。
#   g. lint PASS の記事だけ add → commit → pull --rebase → push。
#   h. 全工程を scripts/logs/writeKansenki_<pubdate>.log に追記。
#
# 不変条件: 既存 articles/predictions は上書きしない。lint FAIL は書かない（持ち越し）。
#           source に無い事実・買い目・確率は出さない（規範は kansenkiRules.md / runbook.md）。

$ErrorActionPreference = 'Stop'

$Repo    = 'C:\Users\USER\boatrace'
# 絶対パス固定: タスクスケジューラの PATH は対話シェルと異なり、py.exe/npm系エイリアスは非対話で不安定。
$Py      = 'C:\Users\USER\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$Git     = 'C:\Program Files\Git\cmd\git.exe'
$Claude  = 'C:\Users\USER\.local\bin\claude.exe'
$PyDir   = Split-Path $Py   # claude 内部の Bash が叩く `python scripts/...` を実体に解決させるため PATH 先頭へ

$Pubdate = (Get-Date).ToString('yyyyMMdd')   # 掲載日＝当日（JST）。source/articles もこの日付。
$LogDir  = Join-Path $Repo 'scripts\logs'    # .gitignore 済み（logは決してcommitしない）
$LogFile = Join-Path $LogDir ("writeKansenki_{0}.log" -f $Pubdate)
$LockFile = Join-Path $LogDir '.writeKansenki.lock'

$SourceRel   = "docs/data/kansenki/source/$Pubdate.json"
$ArticlesDir = Join-Path $Repo 'docs\data\kansenki\articles'
$RunbookPath = Join-Path $Repo 'docs\data\kansenki\runbook.md'
$RulesPath   = 'docs/data/kansenki/kansenkiRules.md'

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Add-Content -Path $LogFile -Value $line -Encoding utf8
}

# native の stderr を 2>&1 で拾うと PS5.1 では ErrorRecord 化し、Stop 下で exit0 でも失敗扱いになる。
# 捕捉中だけ Continue に落とし、成否は $LASTEXITCODE で判定する（gitleaks等のstderr対策）。
function Invoke-Native([scriptblock]$block) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { return (& $block 2>&1 | Out-String) }
    finally { $ErrorActionPreference = $prev }
}
function Invoke-Step($what, [scriptblock]$block) {
    $out = Invoke-Native $block
    if ($out.Trim()) { Log ("{0}:`n{1}" -f $what, $out.TrimEnd()) }
    if ($LASTEXITCODE -ne 0) { throw ("{0} が失敗 (exit {1})" -f $what, $LASTEXITCODE) }
    return $out
}

# --- 同時実行防止 --------------------------------------------------------
if (Test-Path $LockFile) {
    $old = Get-Content $LockFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
        Log ("先行プロセス(PID {0})が実行中のため中止" -f $old); exit 0
    }
    Log "残存ロックを検出（前回が異常終了）。奪取して続行"
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}
Set-Content -Path $LockFile -Value $PID -Encoding ascii

try {
    Set-Location $Repo
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PATH = $PyDir + ';' + $env:PATH   # claude の子プロセスで `python` を実体へ
    Log "=== 開始 pubdate=$Pubdate ==="

    # --- a) main へ同期（ユーザー作業に触らない） -----------------------
    $branch = (& $Git rev-parse --abbrev-ref HEAD).Trim()
    if ($branch -ne 'main') { Invoke-Step 'git checkout main' { & $Git checkout main } | Out-Null }
    $dirty = & $Git status --porcelain --untracked-files=no
    if ($dirty) {
        Log ("追跡ファイルに未コミット変更があるため何もせず終了:`n{0}" -f ($dirty | Out-String).TrimEnd())
        exit 0
    }
    Invoke-Step 'git pull origin main' { & $Git pull origin main } | Out-Null

    # --- b) 執筆計画（未執筆かつ書ける場） -------------------------------
    $planPath = Join-Path $env:TEMP 'plan.json'
    $planText = Invoke-Native { & $Py scripts\kansenki_pubplan.py --pubdate $Pubdate }
    Set-Content -Path $planPath -Value $planText -Encoding utf8
    if ($LASTEXITCODE -ne 0) { throw "kansenki_pubplan.py が失敗 (exit $LASTEXITCODE)" }
    $plan = $planText | ConvertFrom-Json
    $toWrite = @($plan.toWrite)
    Log ("pubplan: pubdate={0} toWrite=[{1}] (計{2}場)" -f $plan.pubdate, ($toWrite -join ' '), $toWrite.Count)
    if ($toWrite.Count -eq 0) {
        Log "執筆対象なし（toWrite空）＝全場執筆済/未確定。正常終了。"
        exit 0
    }

    # --- c) 二重執筆防止 ------------------------------------------------
    $existing = @(Get-ChildItem -Path (Join-Path $ArticlesDir ("{0}-*.json" -f $Pubdate)) -ErrorAction SilentlyContinue)
    if ($existing.Count -gt 0) {
        Log ("既存記事 {0} 本あり（既執筆）→ 二重執筆防止のためスキップ。正常終了。" -f $existing.Count)
        exit 0
    }

    # --- d) スタイル決定（位置引数フォーム） ----------------------------
    Invoke-Step 'assign_styles.py' { & $Py scripts\assign_styles.py $SourceRel } | Out-Null

    # --- e) 執筆（headless claude・未執筆場のみ・push しない） -----------
    $runbook = Get-Content $RunbookPath -Raw -Encoding utf8
    $toWriteStr = ($toWrite -join ' ')
    $header = "掲載日=$Pubdate。執筆対象の場コード(jcd)は次のみ: $toWriteStr。この対象場だけを執筆し、既存記事のある場は絶対に上書きしない。PR作成・push・mergeは行わない（公開はスクリプトが行う）。以下のランブックに厳密に従うこと。"
    $prompt = $header + "`r`n`r`n" + $runbook   # runbook はデータとして連結（再解釈させない）
    $claudeOut = Join-Path $env:TEMP ("claude_out_{0}.json" -f $Pubdate)
    Log "claude 実行開始（model=claude-sonnet-5, max-turns=60, acceptEdits）"
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    & $Claude -p $prompt `
        --append-system-prompt-file $RulesPath `
        --allowedTools "Read,Write,Edit,Bash(python scripts/assign_styles.py*),Bash(python scripts/lintKansenki.py*),Bash(python scripts/kansenki_pubplan.py*)" `
        --permission-mode acceptEdits `
        --max-turns 60 `
        --model claude-sonnet-5 `
        --output-format json 2>&1 | Out-File -FilePath $claudeOut -Encoding utf8
    $claudeRc = $LASTEXITCODE
    $ErrorActionPreference = $prev
    try {
        $cj = Get-Content $claudeOut -Raw -Encoding utf8 | ConvertFrom-Json
        Log ("claude 完了 rc={0} cost_usd={1} session={2}" -f $claudeRc, $cj.total_cost_usd, $cj.session_id)
    } catch {
        Log ("claude 完了 rc={0}（JSON解析不可・出力先 {1}）" -f $claudeRc, $claudeOut)
    }
    if ($claudeRc -ne 0) { throw "claude 実行が非ゼロ終了 (rc=$claudeRc)。認証失効/失敗の可能性。今回は書かず持ち越し。" }

    # --- f) 検査: 各記事 lint → FAIL は削除（持ち越し）。その後 coverage ---
    $written = @(Get-ChildItem -Path (Join-Path $ArticlesDir ("{0}-*.json" -f $Pubdate)) -ErrorAction SilentlyContinue)
    if ($written.Count -eq 0) { Log "生成物なし → 公開なし（持ち越し）。正常終了。"; exit 0 }
    $keep = @()
    foreach ($f in $written) {
        $rel = 'docs/data/kansenki/articles/' + $f.Name
        $lintOut = Invoke-Native { & $Py scripts\lintKansenki.py $rel }
        if ($LASTEXITCODE -eq 0) {
            $keep += $rel
        } else {
            Log ("lint FAIL → 除外(持ち越し): {0}`n{1}" -f $f.Name, $lintOut.TrimEnd())
            Remove-Item $f.FullName -Force
        }
    }
    Log ("lint 結果: PASS {0}場 / 生成 {1}場" -f $keep.Count, $written.Count)
    if ($keep.Count -eq 0) { Log "全対象 lint FAIL → 公開なし（持ち越し）。正常終了。"; exit 0 }
    Invoke-Step 'lint --coverage' { & $Py scripts\lintKansenki.py --coverage $Pubdate } | Out-Null

    # --- g) 公開: PASS 記事だけ add → commit → pull --rebase → push ------
    Invoke-Step 'git add' { & $Git add $keep } | Out-Null
    $staged = & $Git diff --staged --name-only
    if (-not $staged) { Log "差分なし（公開なし）。正常終了。"; exit 0 }
    $msg = "kansenki: $Pubdate 掲載分 観戦記 +$($keep.Count)場（local・場単位・lint全場PASS）"
    Invoke-Step 'git commit' { & $Git commit -m $msg } | Out-Null
    try {
        Invoke-Step 'git pull --rebase' { & $Git pull --rebase origin main } | Out-Null
    } catch {
        Invoke-Native { & $Git rebase --abort } | Out-Null
        throw "git pull --rebase が衝突。中止した（ローカルのコミットは残存。手動確認が必要）"
    }
    Invoke-Step 'git push' { & $Git push origin main } | Out-Null
    $head = (& $Git rev-parse --short HEAD).Trim()
    Log ("=== 完了: {0}場を push（{1}）===" -f $keep.Count, $head)
    exit 0
}
catch {
    Log ("ERROR: {0}" -f $_.Exception.Message)
    Log "※ 失敗のまま終了。次回実行で再試行される"
    exit 1
}
finally {
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    Get-ChildItem $LogDir -Filter 'writeKansenki_*.log' -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}
