param(
    [string]$Config = "config/job_watch.local.json"
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $RepositoryRoot

$UvExecutable = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $UvExecutable) {
    $UvExecutable = Join-Path $env:USERPROFILE ".local/bin/uv.exe"
}
if (-not (Test-Path -LiteralPath $UvExecutable)) {
    throw "uv executable was not found. Install uv or add it to PATH."
}

& $UvExecutable run --project backend python apps/worker/job_watch.py --config $Config
exit $LASTEXITCODE
