# Requires PowerShell 7. Starts only this demo's isolated, loopback PostgreSQL.
# Stop: & "$PostgresBin\pg_ctl.exe" -D $DataDir -m fast -w stop
[CmdletBinding()]
param(
    [string]$PostgresBin = 'E:\831py\.codex\cloud-tools\pgsql\bin',
    [int]$Port = 55432,
    [string]$DataDir = (Join-Path (Split-Path $PSScriptRoot -Parent) '..\scoop-runtime\postgres')
)
$ErrorActionPreference = 'Stop'
$DataDir = [System.IO.Path]::GetFullPath($DataDir)
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Choose an unprivileged PostgreSQL port.' }
foreach ($binary in @('initdb.exe', 'pg_ctl.exe', 'psql.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $PostgresBin $binary))) { throw "Missing PostgreSQL binary: $binary" }
}
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
function Invoke-Pg([string]$Binary, [string[]]$Arguments) {
    & (Join-Path $PostgresBin $Binary) @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Binary failed with exit code $LASTEXITCODE" }
}
if (-not (Test-Path -LiteralPath (Join-Path $DataDir 'PG_VERSION'))) {
    # Trust authentication is confined to this local demo; PostgreSQL binds 127.0.0.1.
    Invoke-Pg 'initdb.exe' @('-D', $DataDir, '-U', 'postgres', '-A', 'trust', '--encoding=UTF8', '--locale=C')
}
& (Join-Path $PostgresBin 'pg_ctl.exe') -D $DataDir status | Out-Null
if ($LASTEXITCODE -ne 0) {
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $start.FileName = Join-Path $PostgresBin 'pg_ctl.exe'
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    foreach ($argument in @('-D', $DataDir, '-l', (Join-Path $DataDir 'server.log'), '-o', "-p $Port -h 127.0.0.1", '-w', 'start')) {
        $start.ArgumentList.Add($argument)
    }
    $process = [System.Diagnostics.Process]::Start($start)
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "PostgreSQL startup failed. Inspect $(Join-Path $DataDir 'server.log')" }
}
$psql = Join-Path $PostgresBin 'psql.exe'
$connection = @('-h', '127.0.0.1', '-p', "$Port", '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1')
$actualDirectory = & $psql @connection -At -c 'SHOW data_directory'
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL verification failed.' }
if ([System.IO.Path]::GetFullPath($actualDirectory.Trim()) -ne $DataDir) { throw 'Port points to another PostgreSQL cluster; refusing to modify it.' }
$exists = & $psql @connection -At -c "SELECT 1 FROM pg_database WHERE datname = 'scoop'"
if ($LASTEXITCODE -ne 0) { throw 'Database existence check failed.' }
if ($exists -ne '1') { Invoke-Pg 'psql.exe' ($connection + @('-c', 'CREATE DATABASE scoop')) }
Write-Host "Scoop PostgreSQL ready at 127.0.0.1:$Port; data: $DataDir"
