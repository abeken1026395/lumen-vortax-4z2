# heartbeat 常設発火役：Windows PC タスクスケジューラ登録手順

GitHub schedule は不発火が多い（実績5%）。このPCから毎時 heartbeat を叩き、
heartbeat が時刻帯で nightlyPipeline / writeKansenki を内部起動する。
**このPCの `gh` 認証を使う。追加トークン発行・外部サービス登録は不要。**

前提：このPCに GitHub CLI (`gh`) が入っていて `gh auth status` が通ること。
（未ログインなら一度だけ `gh auth login` する。）

## 方法A：schtasks（コマンド1行・毎時0分・終日）
管理者PowerShell もしくは cmd で：

```
schtasks /Create /TN "boatrace-heartbeat" ^
  /TR "cmd /c gh api repos/abeken1026395/lumen-vortax-4z2/actions/workflows/heartbeat.yml/dispatches -f ref=main" ^
  /SC HOURLY /MO 1 /ST 00:00 /F
```

## 方法B：PowerShell（スリープ復帰後の取りこぼしも追い付く＝推奨）
`StartWhenAvailable`（予定を逃したら起動後すぐ実行）とバッテリー時も実行を有効化：

```powershell
$act = New-ScheduledTaskAction -Execute "gh.exe" `
  -Argument "api repos/abeken1026395/lumen-vortax-4z2/actions/workflows/heartbeat.yml/dispatches -f ref=main"
$trg = New-ScheduledTaskTrigger -Once -At 00:00 `
  -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([TimeSpan]::MaxValue)
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "boatrace-heartbeat" -Action $act -Trigger $trg -Settings $set -Force
```

## 登録後の確認
- 次の毎時0分を待つ、または即時実行：`schtasks /Run /TN "boatrace-heartbeat"`
- Actions 履歴で heartbeat が撃たれたか確認：
  https://github.com/abeken1026395/lumen-vortax-4z2/actions/workflows/heartbeat.yml
- heartbeat run が success で、時刻帯に応じ nightlyPipeline / writeKansenki が
  workflow_dispatch で起動していれば成立（本日 2026-07-15 に GITHUB_TOKEN 内部起動は実証済み）。

## 削除
```
schtasks /Delete /TN "boatrace-heartbeat" /F
```

## 補足
- PCオフ時間帯は GitHub schedule（毎時 UTC8-23）が保険。ただし発火率は低いので期待しない。
- cron-job.org 等の外部cronでも代替可（heartbeat を毎時 workflow_dispatch で叩くだけ）。その場合は
  fine-grained PAT（Actions: read/write）が1本必要。PC常設なら PAT 不要（PCの gh 認証を使うため）。
