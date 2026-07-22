# dailyMotorUsage.ps1
# Kファイル差分収集 →(A) motorUsage.json 再生成 / (B) motorParts.json モーターNo空欄の後追い補填
#   → 変更があればコミット＆push。fetchKfiles を共有し重複DLを避けた1本化。
# Windowsタスクスケジューラから毎日1回実行される想定（登録: scripts/registerDailyMotorUsage.ps1）。
#
# 方針:
#   - 失敗してもPCの他作業を止めない。全例外はログに残して非0で静かに終了する。
#   - ユーザーの作業を巻き込まない。main以外・作業ツリーが汚れている場合は何もせず退避。
#   - motorUsage.json の updated は毎回変わるため、updated を除いて比較し
#     実データが変わったときだけコミットする（タイムスタンプだけの空コミットを作らない）。
#   - motorParts.json の補填は空 "モーターNo" のみを埋め、updated/他フィールドは触らない。
#     ＝motorParts に素の差分が出れば「モーターNo補填が起きた」証拠。補填ゼロなら書かれず差分無し(no-op)。
#   - mbrace は GitHub Actions からIP遮断のため、K依存の収集・補填はこのローカル日次で回す。
#   - Kファイル本体(.lzh)は .gitignore 済み。add するのは motorUsage.json / motorParts.json だけ。

$ErrorActionPreference = 'Stop'

$Repo = 'C:\Users\USER\boatrace'
# 絶対パス固定: タスクスケジューラのPATHは対話シェルと異なる。
# py.exe は WindowsApps のアプリ実行エイリアスで非対話だと不安定なため実体を直に指す。
$Py  = 'C:\Users\USER\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$Git = 'C:\Program Files\Git\cmd\git.exe'

$LookbackDays = 7   # 取りこぼし吸収。既存ファイルはfetch側でスキップされるので実質差分だけ落ちる
$LogDir       = Join-Path $Repo 'scripts\logs'
$LogFile      = Join-Path $LogDir ("dailyMotorUsage_{0}.log" -f (Get-Date -Format 'yyyyMMdd'))
$LockFile     = Join-Path $LogDir '.dailyMotorUsage.lock'
$TargetUsage  = 'docs/data/motorUsage.json'
$TargetParts  = 'docs/data/motorParts.json'

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Add-Content -Path $LogFile -Value $line -Encoding utf8
}

# ネイティブコマンドの実行と出力捕捉。
# PS5.1 では native の stderr を 2>&1 すると各行が ErrorRecord に化け、
# ErrorActionPreference='Stop' 下では exit 0 でも終了エラーになる
# （gitleaks等のフックがstderrに出すと commit が誤って失敗扱いになる）。
# そのため捕捉中だけ Continue に落とし、成否は $LASTEXITCODE だけで判定する。
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
# タスク側でも MultipleInstances=IgnoreNew を設定済み。手動実行との二重起動もここで防ぐ。
if (Test-Path $LockFile) {
    $old = Get-Content $LockFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
        Log ("先行プロセス(PID {0})が実行中のため中止" -f $old)
        exit 0
    }
    Log "残存ロックを検出（前回が異常終了）。奪取して続行"
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}
Set-Content -Path $LockFile -Value $PID -Encoding ascii

try {
    Set-Location $Repo
    $env:PYTHONIOENCODING = 'utf-8'   # ログの文字化け(cp932)防止
    Log "=== 開始 ==="

    # --- 安全確認: ユーザーの作業に触らない -----------------------------
    $branch = & $Git rev-parse --abbrev-ref HEAD
    if ($branch -ne 'main') {
        Log ("main ではなく '{0}' に居るため何もせず終了（ユーザー作業の巻き込み回避）" -f $branch)
        exit 0
    }
    $dirty = & $Git status --porcelain --untracked-files=no
    if ($dirty) {
        Log ("追跡ファイルに未コミット変更があるため何もせず終了:`n{0}" -f ($dirty | Out-String).TrimEnd())
        exit 0
    }

    # --- 0.5) 最新originへ同期 -------------------------------------------
    # motorParts.json は Actions側 fetchPartsExchange が随時追記するため、最新状態に対して補填する。
    # クリーンツリー・0先行なので fast-forward 相当。衝突時は中止して手動確認に委ねる。
    try {
        Invoke-Step 'git pull --rebase (開始時同期)' { & $Git pull --rebase origin main } | Out-Null
    } catch {
        Invoke-Native { & $Git rebase --abort } | Out-Null
        throw "開始時 git pull --rebase が衝突。中止した（手動確認が必要）"
    }

    # --- 1) Kファイル差分収集（共有） -----------------------------------
    $env:START = (Get-Date).AddDays(-$LookbackDays).ToString('yyyyMMdd')
    $env:END   = (Get-Date).AddDays(-1).ToString('yyyyMMdd')   # 前日分まで（当日分は未確定）
    Log ("Kファイル収集: {0} 〜 {1}" -f $env:START, $env:END)
    # 取得失敗日があっても集計・補填は続ける（欠けた日は欠いたまま＝補完しない方針）
    $fetchOut = Invoke-Native { & $Py scripts\fetchKfiles.py }
    Log ("fetchKfiles.py:`n{0}" -f $fetchOut.TrimEnd())
    if ($LASTEXITCODE -ne 0) { Log "※ 取得できない日があった（欠損のまま継続）" }

    # --- 2) motorUsage 集計 ---------------------------------------------
    Invoke-Step 'buildMotorUsage.py' { & $Py scripts\buildMotorUsage.py } | Out-Null

    # --- 3) motorParts モーターNo空欄の後追い補填（空欄のみ・他フィールド不変・no-op安全） ---
    Invoke-Step 'backfillMotorPartsMotorNo.py' { & $Py scripts\backfillMotorPartsMotorNo.py } | Out-Null

    # --- 4) 変更判定 -----------------------------------------------------
    $toAdd = @()

    # (A) motorUsage: updated だけの差分は無視（実データが変わった時のみ対象）
    $verdict = (@'
import json, subprocess, sys
git, target = sys.argv[1], sys.argv[2]
def norm(t):
    d = json.loads(t)
    d.pop("updated", None)
    return json.dumps(d, sort_keys=True, ensure_ascii=False)
try:
    old = subprocess.run([git, "show", "HEAD:" + target], capture_output=True, check=True).stdout.decode("utf-8")
except Exception:
    print("CHANGED"); sys.exit(0)          # HEADに無い＝初回
with open(target, encoding="utf-8") as f:
    new = f.read()
print("SAME" if norm(old) == norm(new) else "CHANGED")
'@ | & $Py - $Git $TargetUsage) | Select-Object -Last 1

    if ($verdict -eq 'SAME') {
        & $Git checkout -- $TargetUsage   # updatedだけの差分を捨てる（空コミット防止）
        Log "motorUsage: 実データ変更なし（新規Kなし）→ 対象外に戻す"
    } else {
        Log "motorUsage: 実データ変更あり → コミット対象"
        $toAdd += $TargetUsage
    }

    # (B) motorParts: backfill は補填時のみ書く・updated等は触らない → 素の差分があれば補填が起きた
    $partsDirty = & $Git status --porcelain $TargetParts
    if ($partsDirty) {
        Log "motorParts: モーターNo補填あり → コミット対象"
        $toAdd += $TargetParts
    } else {
        Log "motorParts: 補填なし（空欄0 または該当K無し）"
    }

    if ($toAdd.Count -eq 0) {
        Log "変更なし（両者とも実データ不変）。コミットせず正常終了"
        exit 0
    }

    # --- 5) コミット -----------------------------------------------------
    Invoke-Step 'git add' { & $Git add $toAdd } | Out-Null
    $msg = 'auto: daily K更新 (' + ($toAdd -join ', ') + ')'
    Invoke-Step 'git commit' { & $Git commit -m $msg } | Out-Null

    # --- 6) 他の自動処理と衝突しないよう rebase してから push -----------
    try {
        Invoke-Step 'git pull --rebase' { & $Git pull --rebase origin main } | Out-Null
    } catch {
        # 衝突を放置するとリポジトリがrebase途中で固まりユーザー作業を壊す
        Invoke-Native { & $Git rebase --abort } | Out-Null
        throw "git pull --rebase が衝突。rebase を中止した（ローカルのコミットは残存。手動確認が必要）"
    }
    Invoke-Step 'git push' { & $Git push origin main } | Out-Null

    Log ("=== 完了: {0} を push（{1}）===" -f (& $Git rev-parse --short HEAD), ($toAdd -join ', '))
    exit 0
}
catch {
    Log ("ERROR: {0}" -f $_.Exception.Message)
    Log "※ 失敗のまま終了。次回実行で再試行される"
    exit 1
}
finally {
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    # ログは30日で剪定（無限に溜めない）
    Get-ChildItem $LogDir -Filter 'dailyMotorUsage_*.log' -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}
