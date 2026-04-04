#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Restarts one or more Docker Compose services and reloads .env variables.

.DESCRIPTION
    Unlike 'docker compose restart', this script uses --force-recreate so that
    any changes to your .env file (e.g. GEMINI_API_KEY) are picked up immediately.

.EXAMPLE
    .\restart-service.ps1 worker-service
    .\restart-service.ps1 worker-service agent-service
    .\restart-service.ps1          # restarts ALL services
#>

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Services
)

if ($Services.Count -eq 0) {
    Write-Host "Recreating ALL services (picks up latest .env)..." -ForegroundColor Cyan
    docker compose up -d --force-recreate
} else {
    $list = $Services -join ", "
    Write-Host "Recreating: $list (picks up latest .env)..." -ForegroundColor Cyan
    docker compose up -d --force-recreate @Services
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "Done! Services are up with fresh environment variables." -ForegroundColor Green

    # Short health wait
    Start-Sleep -Seconds 3
    foreach ($svc in $Services) {
        $status = docker compose ps --format "table {{.Service}}\t{{.Status}}" $svc 2>$null
        Write-Host $status
    }
} else {
    Write-Host "ERROR: docker compose failed (exit $LASTEXITCODE)" -ForegroundColor Red
}
