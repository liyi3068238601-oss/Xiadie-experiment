param()
$ErrorActionPreference = "Stop"
$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$tempRoot = Join-Path $projectRoot (".cyr2d-crash-" + [Guid]::NewGuid().ToString("N"))
$backendPython = Join-Path $projectRoot "backend\.venv\Scripts\python.exe"
$token = [Guid]::NewGuid().ToString("N") + [Guid]::NewGuid().ToString("N")
$headers = @{ "X-Xiadie-Token" = $token }
$started = @()

function Stop-Tree([System.Diagnostics.Process]$Process) {
  if (-not $Process) { return }
  $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($Process.Id)" -ErrorAction SilentlyContinue
  foreach ($child in $children) { try { Stop-Tree ([System.Diagnostics.Process]::GetProcessById($child.ProcessId)) } catch {} }
  try { Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue } catch {}
}

function Start-Backend {
  param([string]$DataDir)
  $env:XIADIE_API_TOKEN = $token
  $env:XIADIE_DATA_DIR = $DataDir
  $env:XIADIE_DEV_MODE = "1"
  $env:XIADIE_PARENT_PID = [string]$PID
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $backendPython
  $psi.Arguments = "run_frozen.py"
  $psi.WorkingDirectory = Join-Path $projectRoot "backend"
  $psi.UseShellExecute = $false
  $proc = New-Object System.Diagnostics.Process
  $proc.StartInfo = $psi
  $null = $proc.Start()
  $script:started += $proc
  for ($i = 0; $i -lt 60; $i++) {
    try {
      $h = Invoke-RestMethod "http://127.0.0.1:9756/api/health" -Headers $headers -TimeoutSec 1
      if ($h.status -eq "ok") { return $proc }
    } catch {}
    Start-Sleep -Milliseconds 500
  }
  throw "backend did not become healthy"
}

try {
  if (Get-NetTCPConnection -LocalPort 8756 -State Listen -ErrorAction SilentlyContinue) {
    throw "CYR.2D crash-recovery E2E requires free port 9756; existing process was not touched."
  }
  if (-not (Test-Path -LiteralPath $backendPython)) { throw "backend venv missing" }
  New-Item -ItemType Directory -Path $tempRoot | Out-Null
  New-Item -ItemType Directory -Path (Join-Path $tempRoot "data") | Out-Null

  $backend = Start-Backend (Join-Path $tempRoot "data")
  $task = Invoke-RestMethod "http://127.0.0.1:9756/api/tasks" -Method Post -Headers $headers `
    -ContentType "application/json" -Body '{"title":"崩溃恢复验收"}'
  $run = Invoke-RestMethod "http://127.0.0.1:9756/api/tasks/$($task.id)/runs" -Method Post -Headers $headers `
    -ContentType "application/json" -Body '{"goal_summary":"崩溃恢复验收"}'
  $planBody = @{ nodes = @(@{ client_id = "a"; title = "步骤A"; depends_on = @(); completion_criteria = "完成" }); requires_approval = $false; expected_revision = $run.revision } | ConvertTo-Json -Depth 6
  $planned = Invoke-RestMethod "http://127.0.0.1:9756/api/task-runs/$($run.id)/plan" -Method Put -Headers $headers `
    -ContentType "application/json" -Body $planBody
  $running = Invoke-RestMethod "http://127.0.0.1:9756/api/task-runs/$($run.id)/start" -Method Post -Headers $headers `
    -ContentType "application/json" -Body (@{ expected_revision = $planned.revision } | ConvertTo-Json)
  if ($running.status -ne "running") { throw "run did not enter running" }

  Stop-Tree $backend
  Start-Sleep -Seconds 1

  $backend2 = Start-Backend (Join-Path $tempRoot "data")
  $recovered = Invoke-RestMethod "http://127.0.0.1:9756/api/task-runs/$($run.id)" -Headers $headers
  if ($recovered.status -ne "recovery_required") { throw "expected recovery_required, got $($recovered.status)" }
  $runningNode = $recovered.nodes | Where-Object { $_.status -eq "running" }
  if ($runningNode) { throw "running node should be blocked after crash" }

  $cancelled = Invoke-RestMethod "http://127.0.0.1:9756/api/task-runs/$($run.id)/cancel" -Method Post -Headers $headers `
    -ContentType "application/json" -Body (@{ expected_revision = $recovered.revision } | ConvertTo-Json)
  if ($cancelled.status -ne "cancelled") { throw "cancel failed" }
  $cancelled2 = Invoke-RestMethod "http://127.0.0.1:9756/api/task-runs/$($run.id)/cancel" -Method Post -Headers $headers `
    -ContentType "application/json" -Body (@{ expected_revision = $cancelled.revision } | ConvertTo-Json)
  if ($cancelled2.status -ne "cancelled") { throw "cancel not idempotent" }

  Write-Output "CYR.2D crash-recovery E2E: PASS"
} finally {
  foreach ($p in $started) { Stop-Tree $p }
  Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
