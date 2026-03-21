param(
  [string]$DlqTopic = "repo.events.dlq",
  [string]$TargetTopic = "repo.events",
  [int]$MaxMessages = 100,
  [switch]$FromBeginning
)

$ErrorActionPreference = 'Stop'

function Write-Step($msg) {
  Write-Host "`n==> $msg" -ForegroundColor Cyan
}

Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Step "Reading up to $MaxMessages from DLQ topic '$DlqTopic'"
$fromBeginningFlag = if ($FromBeginning) { "--from-beginning" } else { "" }
$dlqRaw = docker exec engbrain-kafka-1 kafka-console-consumer --bootstrap-server kafka:9092 --topic $DlqTopic $fromBeginningFlag --timeout-ms 5000 --max-messages $MaxMessages
if (-not $dlqRaw) {
  Write-Host "No DLQ messages found." -ForegroundColor Yellow
  exit 0
}

$lines = $dlqRaw -split "`r?`n" | Where-Object { $_ -and $_.Trim() -ne "" }
$replayed = 0

foreach ($line in $lines) {
  try {
    $obj = $line | ConvertFrom-Json
    if ($null -eq $obj.payload_raw -or [string]::IsNullOrWhiteSpace([string]$obj.payload_raw)) {
      Write-Host "Skipping malformed DLQ record (no payload_raw)" -ForegroundColor Yellow
      continue
    }

    $obj.payload_raw | docker exec -i engbrain-kafka-1 kafka-console-producer --bootstrap-server kafka:9092 --topic $TargetTopic | Out-Null
    $replayed += 1
  } catch {
    Write-Host "Failed to replay one DLQ message: $($_.Exception.Message)" -ForegroundColor Red
  }
}

Write-Host "`nReplayed $replayed message(s) from $DlqTopic to $TargetTopic" -ForegroundColor Green
