param(
  [string]$Topic = "repo.events",
  [int]$Partition = 0,
  [string]$Offset = "earliest",
  [int]$MaxMessages = 100,
  [string]$TargetTopic = "repo.events"
)

$ErrorActionPreference = 'Stop'

function Write-Step($msg) {
  Write-Host "`n==> $msg" -ForegroundColor Cyan
}

Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Step "Replaying from topic '$Topic' partition $Partition offset '$Offset' -> '$TargetTopic'"

$offsetArg = if ($Offset -eq 'earliest' -or $Offset -eq 'latest') { "--offset $Offset" } else { "--offset $([int64]$Offset)" }
$cmd = "kafka-console-consumer --bootstrap-server kafka:9092 --topic $Topic --partition $Partition $offsetArg --timeout-ms 5000 --max-messages $MaxMessages"
$raw = docker exec engbrain-kafka-1 bash -lc $cmd

$lines = $raw -split "`r?`n" | Where-Object { $_ -and $_.Trim() -ne "" }
if (-not $lines -or $lines.Count -eq 0) {
  Write-Host "No messages found for replay window." -ForegroundColor Yellow
  exit 0
}

Write-Step "Publishing $($lines.Count) message(s) to '$TargetTopic'"
$tmp = [System.IO.Path]::GetTempFileName()
$lines -join "`n" | Set-Content -Path $tmp
Get-Content $tmp | docker exec -i engbrain-kafka-1 kafka-console-producer --bootstrap-server kafka:9092 --topic $TargetTopic | Out-Null
Remove-Item $tmp -Force

Write-Host "✅ Replayed $($lines.Count) message(s)" -ForegroundColor Green
