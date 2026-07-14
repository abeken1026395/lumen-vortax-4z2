# dailyMotorUsage.ps1
# Kファイル差分収集 → motorUsage.json 再生成 → 変更があればコミット＆push。
# Windowsタスクスケジューラから毎日1回実行される想定（登録: scripts/registerDailyMotorUsage.ps1）。
#
# 方針:
#   - 失敗してもPCの他作業を止めない。全例外はログに残して非0で静かに終了する。
#   - ユーザーの作業を巻き込まない。main以外・作業ツリーが汚れている場合は何もせず退避。
#   - motorUsage.json の updated は毎回変わるため、updated を除いて比較し
#     実データが変わったときだけコミットする（タイムスタンプだけの空コミットを作らない）。
#   - Kファイル本体(.lzh)は .gitignore 済み。add するのは motorUsage.json だけ。

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
$Target       = 'docs/data/motorUsage.json'

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

    # --- 1) Kファイル差分収集 -------------------------------------------
    $env:START = (Get-Date).AddDays(-$LookbackDays).ToString('yyyyMMdd')
    $env:END   = (Get-Date).AddDays(-1).ToString('yyyyMMdd')   # 前日分まで（当日分は未確定）
    Log ("Kファイル収集: {0} 〜 {1}" -f $env:START, $env:END)
    # 取得失敗日があっても集計は続ける（欠けた日は欠いたまま＝補完しない方針）
    $fetchOut = Invoke-Native { & $Py scripts\fetchKfiles.py }
    Log ("fetchKfiles.py:`n{0}" -f $fetchOut.TrimEnd())
    if ($LASTEXITCODE -ne 0) { Log "※ 取得できない日があった（欠損のまま集計を継続）" }

    # --- 2) 集計 ---------------------------------------------------------
    Invoke-Step 'buildMotorUsage.py' { & $Py scripts\buildMotorUsage.py } | Out-Null

    # --- 3) 実データが変わったかの判定（updated を無視して比較） ---------
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
'@ | & $Py - $Git $Target) | Select-Object -Last 1

    if ($verdict -eq 'SAME') {
        # updated だけの差分なので作業ツリーを元に戻して終了（空コミットを積まない）
        & $Git checkout -- $Target
        Log "変更なし（新規Kファイルなし＝実データ同一）。コミットせず正常終了"
        exit 0
    }
    Log "実データに変更あり。コミットへ"

    # --- 4) コミット -----------------------------------------------------
    Invoke-Step 'git add' { & $Git add $Target } | Out-Null
    Invoke-Step 'git commit' { & $Git commit -m 'auto: motorUsage daily update' } | Out-Null

    # --- 5) 他の自動処理と衝突しないよう rebase してから push ------------
    try {
        Invoke-Step 'git pull --rebase' { & $Git pull --rebase origin main } | Out-Null
    } catch {
        # 衝突を放置するとリポジトリがrebase途中で固まりユーザー作業を壊す
        Invoke-Native { & $Git rebase --abort } | Out-Null
        throw "git pull --rebase が衝突。rebase を中止した（ローカルのコミットは残存。手動確認が必要）"
    }
    Invoke-Step 'git push' { & $Git push origin main } | Out-Null

    Log ("=== 完了: {0} を push ===" -f (& $Git rev-parse --short HEAD))
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
