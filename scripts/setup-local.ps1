<#
Windows bootstrap (PowerShell 7):
  pwsh -NoProfile -File scripts/setup-local.ps1 -LoadData
Subsequent start without resetting data:
  pwsh -NoProfile -File scripts/start-db.ps1
  .\.venv\Scripts\python.exe -m uvicorn scoop.main:app --app-dir backend --host 127.0.0.1 --port 8008
-LoadData replaces synthetic demo tables in this script's isolated local database.
Linux users can continue using docker compose and backend/requirements.txt.
#>
[CmdletBinding()]
param(
    [string]$Python = 'C:\Users\ping\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe',
    [string]$PostgresBin = 'E:\831py\.codex\cloud-tools\pgsql\bin',
    [int]$Port = 55432,
    [switch]$LoadData
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
function Invoke-Python([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python failed with exit code $LASTEXITCODE" }
}
if (-not (Test-Path -LiteralPath $venvPython)) { Invoke-Python $Python @('-m', 'venv', (Join-Path $root '.venv')) }
Invoke-Python $venvPython @('-m', 'pip', 'install', '-r', (Join-Path $root 'backend\requirements-dev.txt'))
& (Join-Path $PSScriptRoot 'start-db.ps1') -PostgresBin $PostgresBin -Port $Port
$url = "postgresql+psycopg://postgres:postgres@127.0.0.1:$Port/scoop"
$envFile = Join-Path $root '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    [System.IO.File]::WriteAllText($envFile, "DATABASE_URL=$url`nSCOOP_LLM_PROVIDER=scripted`n", [System.Text.UTF8Encoding]::new($false))
} elseif ((Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^DATABASE_URL=' }) -ne "DATABASE_URL=$url") {
    throw "Existing .env uses a different database. Set DATABASE_URL=$url for this isolated runtime."
}
$oldPythonPath = $env:PYTHONPATH
$oldDatabaseUrl = $env:DATABASE_URL
try {
    $env:PYTHONPATH = Join-Path $root 'backend'
    $env:DATABASE_URL = $url
    Invoke-Python $venvPython @('-m', 'pip', 'check')
    Invoke-Python $venvPython @('-c', 'import fastapi, uvicorn, sqlalchemy, psycopg, pydantic, dotenv, numpy, pandas, scipy, lightgbm; from scoop.db import engine; from sqlalchemy import text; connection = engine.connect(); print("Connected:", connection.execute(text("SELECT current_database(), version()")).one()); connection.close()')
    if ($LoadData) {
        Invoke-Python $venvPython @('-m', 'scoop.synth.load')
        Invoke-Python $venvPython @('-m', 'scoop.prepare_demo')
    }
} finally {
    $env:PYTHONPATH = $oldPythonPath
    $env:DATABASE_URL = $oldDatabaseUrl
}
Write-Host 'Local Scoop runtime ready. See this script header for normal start commands.'
