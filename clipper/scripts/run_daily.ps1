# Daily clipper run (Windows). Called by Task Scheduler; safe to run by hand.
$ErrorActionPreference = "Continue"
$Repo = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Repo

# Pick up campaign changes pushed from Claude sessions; carry on offline if this fails.
git pull --ff-only 2>&1 | Out-Null

$Python = Join-Path $Repo ".venv\Scripts\python.exe"
& $Python -m clipper daily @args
exit $LASTEXITCODE
