<#
.SYNOPSIS
    One-time setup of the EasyTime probe on the administrator PC.

.DESCRIPTION
    Creates a LOCAL virtual environment in .\.venv and installs
    requirements.txt into it. Nothing is ever installed globally: every pip
    call goes through .venv\Scripts\python.exe -m pip.

    This script deliberately does NOT create or populate .env. Credentials are
    typed in by the administrator, never generated, defaulted or echoed by a
    script. If .env already exists it is left untouched and its contents are
    never read or printed.

.EXAMPLE
    .\setup_probe.ps1
#>
[CmdletBinding()]
param(
    # Delete and rebuild .venv from scratch.
    [switch]$Recreate
)

$ErrorActionPreference = 'Stop'

$Root         = $PSScriptRoot
$VenvDir      = Join-Path $Root '.venv'
$VenvPython   = Join-Path $VenvDir 'Scripts\python.exe'
$Requirements = Join-Path $Root 'requirements.txt'
$EnvExample   = Join-Path $Root '.env.example'
$EnvFile      = Join-Path $Root '.env'

$MinMajor = 3
$MinMinor = 11

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host $Text -ForegroundColor Cyan
    Write-Host ('-' * $Text.Length) -ForegroundColor Cyan
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    exit 1
}

# -- 1. locate a base interpreter -------------------------------------------
# Prefer the "py" launcher (the normal Windows install) and fall back to
# "python" on PATH. We only ever use this interpreter to CREATE the venv.
function Resolve-BaseInterpreter {
    $candidates = @(
        @{ Exe = 'py';     Prefix = @('-3') },
        @{ Exe = 'python'; Prefix = @() }
    )
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Exe -ErrorAction SilentlyContinue
        if ($null -eq $command) { continue }

        # No quotes in the -c snippet: Windows PowerShell strips double quotes
        # when handing arguments to a native executable.
        $probeArgs = @($candidate.Prefix) + @('-c', 'import sys; print(sys.version_info[0], sys.version_info[1], sys.version_info[2])')
        $raw = & $candidate.Exe @probeArgs
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) { continue }

        $parts = ($raw | Select-Object -First 1).Trim() -split '\s+'
        if ($parts.Count -lt 2) { continue }
        $version = $parts -join '.'
        $major = [int]$parts[0]
        $minor = [int]$parts[1]
        if ($major -lt $MinMajor -or ($major -eq $MinMajor -and $minor -lt $MinMinor)) {
            Write-Host "  skipping $($candidate.Exe) - Python $version is older than $MinMajor.$MinMinor" -ForegroundColor Yellow
            continue
        }
        return @{ Exe = $candidate.Exe; Prefix = $candidate.Prefix; Version = $version; Path = $command.Source }
    }
    return $null
}

Write-Step '1. Locating Python'
$base = Resolve-BaseInterpreter
if ($null -eq $base) {
    Fail @"
No usable Python $MinMajor.$MinMinor+ interpreter was found.

Neither 'py' nor 'python' answered with a supported version. Install Python
$MinMajor.$MinMinor or newer from https://www.python.org/downloads/windows/ and
tick "Add python.exe to PATH", then re-run this script.
"@
}
Write-Host "  [PASS] $($base.Exe) -> Python $($base.Version)"
Write-Host "         $($base.Path)"

if (-not (Test-Path -LiteralPath $Requirements)) {
    Fail "requirements.txt not found next to this script ($Requirements)."
}

# -- 2. create the local virtual environment --------------------------------
Write-Step '2. Virtual environment'
if ($Recreate -and (Test-Path -LiteralPath $VenvDir)) {
    Write-Host "  removing existing $VenvDir"
    Remove-Item -LiteralPath $VenvDir -Recurse -Force
}

if (Test-Path -LiteralPath $VenvPython) {
    Write-Host "  [PASS] reusing existing .venv (pass -Recreate to rebuild)"
} else {
    Write-Host "  creating $VenvDir"
    $venvArgs = @($base.Prefix) + @('-m', 'venv', $VenvDir)
    & $base.Exe @venvArgs
    if ($LASTEXITCODE -ne 0) { Fail "Failed to create the virtual environment (exit $LASTEXITCODE)." }
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Fail "The virtual environment was created but $VenvPython is missing."
    }
    Write-Host "  [PASS] .venv created"
}

# -- 3. install dependencies INTO THE VENV ONLY -----------------------------
Write-Step '3. Installing dependencies (local venv only)'
Write-Host "  using $VenvPython"

& $VenvPython -m pip install --upgrade pip --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Fail "pip self-upgrade failed (exit $LASTEXITCODE)." }

& $VenvPython -m pip install -r $Requirements --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Fail "Dependency installation failed (exit $LASTEXITCODE)." }
Write-Host "  [PASS] requirements.txt installed into .venv"

# -- 4. smoke-test the imports ----------------------------------------------
Write-Step '4. Import check'
& $VenvPython -c "import httpx, dotenv; print('  [PASS] httpx', httpx.__version__, '/ python-dotenv ok')"
if ($LASTEXITCODE -ne 0) { Fail "The installed packages could not be imported." }

# -- 5. tell the admin what to do next --------------------------------------
Write-Step 'Next steps'
if (Test-Path -LiteralPath $EnvFile) {
    Write-Host "  .env already exists - left untouched. This script never reads or"
    Write-Host "  prints its contents, and never writes credentials into it."
    Write-Host ""
    Write-Host "  Run the safe, offline check first:" -ForegroundColor Green
    Write-Host "    .\run_probe.ps1 -Mode CheckConfig" -ForegroundColor Green
} else {
    if (-not (Test-Path -LiteralPath $EnvExample)) {
        Write-Host "  [WARN] .env.example is missing; ask for the full probe package again." -ForegroundColor Yellow
    }
    Write-Host "  No .env was created. Create it yourself and type the credentials in:"
    Write-Host ""
    Write-Host "    copy .env.example .env" -ForegroundColor Green
    Write-Host "    notepad .env" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Fill in EASYTIME_BASE_URL, EASYTIME_USERNAME and EASYTIME_PASSWORD"
    Write-Host "  (use a dedicated read-only integration account, not a person's login),"
    Write-Host "  then run the safe, offline check:"
    Write-Host ""
    Write-Host "    .\run_probe.ps1 -Mode CheckConfig" -ForegroundColor Green
}
Write-Host ""
exit 0
