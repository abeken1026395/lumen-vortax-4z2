# registerDailyMotorUsage.ps1
# dailyMotorUsage.ps1 を「毎日 JST 6:00」に走らせるタスクを登録する。再実行すれば設定を上書き更新する。
#
# ログオン種別について（重要）:
#   push は Git Credential Manager が Windows資格情報マネージャーに持つ資格情報を使う。
#   これはユーザーのDPAPIで保護されているため、"ユーザーがログオンしていなくても実行する" にすると
#   資格情報を復号できず push が失敗しうる。そのため -RunLevel Limited かつ対話ログオン
#   （= ログオン時のみ実行）で登録する。スリープからの起復は WakeToRun で担保する。

$ErrorActionPreference = 'Stop'

$TaskName = 'boatrace-dailyMotorUsage'
$Script   = 'C:\Users\USER\boatrace\scripts\dailyMotorUsage.ps1'
$PwshExe  = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

$action = New-ScheduledTaskAction -Execute $PwshExe `
    -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}"' -f $Script)

$trigger = New-ScheduledTaskTrigger -Daily -At '06:00'

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
    -Description 'mbrace Kファイル差分収集 → motorUsage.json 再生成 → 変更があればcommit&push' `
    -Force | Out-Null

"登録しました: $TaskName"
Get-ScheduledTask -TaskName $TaskName |
    Select-Object TaskName, State, @{n='Trigger';e={ $_.Triggers[0].StartBoundary }}
