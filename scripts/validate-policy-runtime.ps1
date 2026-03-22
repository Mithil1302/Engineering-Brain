param(
  [string]$Repo = "Mithil1302/Pre-Delinquency-Intervention-Engine",
  [int]$PrNumber = 2
)

$ErrorActionPreference = "Stop"

Write-Host "==> Rebuilding worker-service"
docker compose up -d --build worker-service | Out-Null
Start-Sleep -Seconds 6

Write-Host "==> Checking worker policy health"
python -c "import sys, urllib.request, json; sys.path.append('scripts'); from auth_headers import build_claims_headers; req=urllib.request.Request('http://localhost:8003/policy/pipeline/health', headers=build_claims_headers(subject='runtime-validator', role='platform-admin', tenant_id='t1', repo_scope=['*'])); print(json.dumps(json.loads(urllib.request.urlopen(req).read().decode()), indent=2))"

Write-Host "==> Checking dashboard overview"
$overviewUrl = "http://localhost:8003/policy/dashboard/overview?repo=$Repo&pr_number=$PrNumber&window=5"
python -c "import sys, urllib.request, json; sys.path.append('scripts'); from auth_headers import build_claims_headers; req=urllib.request.Request('$overviewUrl', headers=build_claims_headers(subject='runtime-validator', role='developer', tenant_id='t1', repo_scope=['$Repo'])); print(json.dumps(json.loads(urllib.request.urlopen(req).read().decode()), indent=2))"

Write-Host "==> Checking health snapshots"
$snapUrl = "http://localhost:8003/policy/dashboard/health-snapshots?repo=$Repo&pr_number=$PrNumber&limit=3"
python -c "import sys, urllib.request, json; sys.path.append('scripts'); from auth_headers import build_claims_headers; req=urllib.request.Request('$snapUrl', headers=build_claims_headers(subject='runtime-validator', role='developer', tenant_id='t1', repo_scope=['$Repo'])); print(json.dumps(json.loads(urllib.request.urlopen(req).read().decode()), indent=2))"

Write-Host "==> Checking doc refresh jobs"
$docUrl = "http://localhost:8003/policy/dashboard/doc-refresh-jobs?repo=$Repo&pr_number=$PrNumber&limit=3"
python -c "import sys, urllib.request, json; sys.path.append('scripts'); from auth_headers import build_claims_headers; req=urllib.request.Request('$docUrl', headers=build_claims_headers(subject='runtime-validator', role='developer', tenant_id='t1', repo_scope=['$Repo'])); print(json.dumps(json.loads(urllib.request.urlopen(req).read().decode()), indent=2))"

Write-Host "✅ policy runtime validation completed"
