# registerWriteKansenkiLocal.ps1
# writeKansenkiLocal.ps1 を「毎日 JST 5:30」に走らせるタスクを登録する。再実行で上書き更新。
#
# ログオン種別について（registerDailyMotorUsage.ps1 と同じ理由・重要）:
#   git push は Git Credential Manager が Windows資格情報マネージャーに持つ資格情報（ユーザーDPAPI保護）を、
#   claude は Max プランの OAuth 認証情報（同じくユーザープロファイル配下）を使う。
#   "ユーザーがログオンしていなくても実行" にするとこれらを復号/参照できず push も claude も失敗しうる。
#   そのため -RunLevel Limited かつ対話ログオン（= ログオン時のみ実行）で登録する。
#   スリープからの起復は WakeToRun で担保する（完全シャットダウン/ログオフ中は動かない）。

$ErrorActionPreference = 'Stop'

$TaskName = 'boatrace-writeKansenkiLocal'
$Script   = 'C:\Users\USER\boatrace\scripts\writeKansenkiLocal.ps1'
$PwshExe  = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

$action = New-ScheduledTaskAction -Execute $PwshExe `
    -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $Script)

$trigger = New-ScheduledTaskTrigger -Daily -At '05:30'

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -WakeToRun `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description '観戦記の自走をローカルで実行: source確定後、pubplanで未執筆場を判定→claude(Max/課金なし)で執筆→lint全場PASSのみcommit&push' `
    -Force | Out-Null

"登録しました: $TaskName"
Get-ScheduledTask -TaskName $TaskName |
    Select-Object TaskName, State, @{n='Trigger';e={ $_.Triggers[0].StartBoundary }}
