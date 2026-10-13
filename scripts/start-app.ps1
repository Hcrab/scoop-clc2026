# PowerShell 7. Starts Scoop silently, preserving logs under the isolated runtime.
# Run from any directory: pwsh -NoProfile -File scripts/start-app.ps1
[CmdletBinding()]
param([int]$Port=8008)
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$runtime=[System.IO.Path]::GetFullPath((Join-Path $root '..\scoop-runtime'))
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
& (Join-Path $PSScriptRoot 'start-db.ps1')
$python=Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run scripts/setup-local.ps1 first.' }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "Port $Port is already in use; inspect the existing process before starting another server." }
$arguments=@('-m','uvicorn','scoop.main:app','--app-dir',('"'+(Join-Path $root 'backend')+'"'),'--host','127.0.0.1','--port',"$Port")
if (-not $env:OPENBLAS_NUM_THREADS) { $env:OPENBLAS_NUM_THREADS='1' }
if (-not $env:OMP_NUM_THREADS) { $env:OMP_NUM_THREADS='1' }
$process=Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtime 'api.stdout.log') -RedirectStandardError (Join-Path $runtime 'api.stderr.log')
Set-Content -LiteralPath (Join-Path $runtime 'api.pid') -Value $process.Id
for ($i=0;$i -lt 30;$i++) {
    if ($process.HasExited) { throw "Server exited; inspect $(Join-Path $runtime 'api.stderr.log')" }
    try { $response=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 1; if ($response.status -eq 'ok') { $listener=Get-NetTCPConnection -LocalPort $Port -State Listen; Set-Content -LiteralPath (Join-Path $runtime 'api.pid') -Value $listener[0].OwningProcess; Write-Host "Scoop ready: http://127.0.0.1:$Port (PID $($listener[0].OwningProcess))"; return } } catch { Start-Sleep -Milliseconds 300 }
}
throw 'Server startup timed out; inspect logs.'
