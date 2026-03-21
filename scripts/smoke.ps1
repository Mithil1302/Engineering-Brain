param(
  [switch]$SkipBuild,
  [switch]$ResetVolumes
)

$ErrorActionPreference = 'Stop'

function Write-Step($msg) {
  Write-Host "`n==> $msg" -ForegroundColor Cyan
}

function Assert($condition, $message) {
  if (-not $condition) {
    throw "Smoke assertion failed: $message"
  }
}

Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Step "Starting stack"
if ($ResetVolumes) {
  Write-Step "Resetting containers/networks/volumes for deterministic smoke run"
  docker compose down -v --remove-orphans | Out-Null
}

if ($SkipBuild) {
  docker compose up -d
} else {
  docker compose up -d --build
}

if ($LASTEXITCODE -ne 0) {
  Write-Warning "docker compose up returned non-zero ($LASTEXITCODE). Continuing to readiness assertions..."
}

Write-Step "Waiting for api-gateway mesh readiness"
$mesh = $null
$attempts = 30
for ($i = 1; $i -le $attempts; $i++) {
  try {
    $mesh = Invoke-RestMethod -Uri "http://localhost:3000/mesh" -Method Get
    if ($mesh.ok) { break }
  } catch {
    # keep retrying
  }
  Start-Sleep -Seconds 3
}

Assert ($null -ne $mesh) "mesh endpoint did not return"
Assert ($mesh.ok -eq $true) "mesh readiness is false"

Write-Step "Checking health endpoints"
$healthUrls = @(
  "http://localhost:3000/healthz",
  "http://localhost:3001/healthz",
  "http://localhost:8001/healthz",
  "http://localhost:8002/healthz",
  "http://localhost:8003/healthz",
  "http://localhost:8002/github/bridge/health",
  "http://localhost:8003/policy/pipeline/health"
)

foreach ($url in $healthUrls) {
  $r = Invoke-RestMethod -Uri $url -Method Get
  if ($url -like "*/github/bridge/health" -or $url -like "*/policy/pipeline/health") {
    Assert ($null -ne $r.running) "pipeline health endpoint malformed for $url"
  } else {
    Assert ($r.status -eq 'ok') "health check failed for $url"
  }
}

Write-Step "Validating Kafka topics"
$topicsRaw = docker exec engbrain-kafka-1 kafka-topics --bootstrap-server kafka:9092 --list
$topics = $topicsRaw -split "`r?`n" | Where-Object { $_ -and $_.Trim() -ne "" }
$requiredTopics = @('repo.events','repo.events.dlq','graph.updates','analysis.jobs','pr.checks','pr.checks.dlq','agent.requests','ci.events')
foreach ($t in $requiredTopics) {
  Assert ($topics -contains $t) "missing Kafka topic: $t"
}

Write-Step "Validating Postgres bootstrap tables"
$sql = "SELECT tablename FROM pg_tables WHERE schemaname='meta' ORDER BY tablename;"
$tablesRaw = docker exec engbrain-postgres-1 psql -U brain -d brain -t -A -c $sql
$tables = $tablesRaw -split "`r?`n" | Where-Object { $_ -and $_.Trim() -ne "" }
$requiredTables = @('audit_logs','embedding_metadata','jobs','policies')
foreach ($tbl in $requiredTables) {
  Assert ($tables -contains $tbl) "missing Postgres table: meta.$tbl"
}

Write-Step "Readiness matrix"
$mesh | ConvertTo-Json -Depth 6

Write-Host "`n✅ Smoke test passed." -ForegroundColor Green
