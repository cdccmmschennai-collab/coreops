<#
.SYNOPSIS
    One-time setup of the CoreOps EasyTime connector's Python environment.

.DESCRIPTION
    The production setup entry point, run AFTER install_connector.ps1. It
    creates the virtual environment in the installed application directory -
    the same place run_sync.ps1 looks for it - and installs the pinned
    requirements.txt into it. Nothing is ever installed globally: every pip call
    goes through .venv\Scripts\python.exe -m pip.

        C:\Program Files\CoreOps\EasyTimeConnector\.venv\Scripts\python.exe

    This script deliberately does NOT create or populate the configuration file.
    Credentials are typed in by the administrator, never generated, defaulted or
    echoed by a script. It never reads or prints the contents of any .env or
    connector.env.

    setup_probe.ps1 is the Phase 1 equivalent and is unchanged; it remains the
    supported entry point for the standalone diagnostic probe in
    C:\CoreOps-EasyTime-Probe. This script supersedes it for the connector, and
    the two produce the same .venv when run from the same folder.

.PARAMETER AppRoot
    The installed application directory to create .venv inside. Defaults to the
    folder this script is sitting in, which is where install_connector.ps1 put
    it.

.PARAMETER DataRoot
    The ProgramData root the installed connector reads its configuration from.
    Only used to print the next step; nothing under it is created or read.

.PARAMETER Recreate
    Delete and rebuild .venv from scratch.

.EXAMPLE
    .\setup_connector.ps1

.EXAMPLE
    .\setup_connector.ps1 -Recreate
#>
[CmdletBinding()]
param(
    [string]$AppRoot = '',

    [string]$DataRoot = 'C:\ProgramData\CoreOps\EasyTimeConnector',

    [switch]$Recreate
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($AppRoot)) { $AppRoot = $PSScriptRoot }

$VenvDir      = Join-Path $AppRoot '.venv'
$VenvPython   = Join-Path $VenvDir 'Scripts\python.exe'
$Requirements = Join-Path $AppRoot 'requirements.txt'
$SyncFile     = Join-Path $AppRoot 'sync.py'

# Where the installed connector keeps its configuration. Printed as the next
# step; never created, never read, never written by this script.
$ConfigDir  = Join-Path $DataRoot 'config'
$ConfigFile = Join-Path $ConfigDir 'connector.env'
$ExampleFile = Join-Path $ConfigDir 'connector.env.example'

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

# -- 0. the application must be installed first ------------------------------
Write-Step '0. Application directory'
if (-not (Test-Path -LiteralPath $AppRoot -PathType Container)) {
    Fail "The application directory $AppRoot does not exist. Run install_connector.ps1 first."
}
if (-not (Test-Path -LiteralPath $SyncFile -PathType Leaf)) {
    Fail @"
sync.py is not in $AppRoot.

Run install_connector.ps1 from the extracted package first, then run this script
from the installed directory:
    C:\Program Files\CoreOps\EasyTimeConnector\setup_connector.ps1
"@
}
if (-not (Test-Path -LiteralPath $Requirements -PathType Leaf)) {
    Fail "requirements.txt is not in $AppRoot ($Requirements)."
}
Write-Host "  [PASS] $AppRoot"

# -- 1. locate a base interpreter --------------------------------------------
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
Write-Host "         base interpreter : $($base.Path)"

# -- 2. create the virtual environment IN THE INSTALLED LOCATION -------------
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
    if ($LASTEXITCODE -ne 0) {
        Fail @"
Failed to create the virtual environment at $VenvDir (exit $LASTEXITCODE).

Program Files needs an elevated prompt: right-click PowerShell, choose
'Run as administrator', and run this script again.
"@
    }
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Fail "The virtual environment was created but $VenvPython is missing."
    }
    Write-Host "  [PASS] .venv created"
}

# -- 3. install the PINNED dependencies, into the venv only ------------------
Write-Step '3. Installing pinned dependencies (local venv only)'
Write-Host "  using $VenvPython"
Write-Host "  from  $Requirements"

& $VenvPython -m pip install --upgrade pip --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Fail "pip self-upgrade failed (exit $LASTEXITCODE)." }

& $VenvPython -m pip install -r $Requirements --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Fail "Dependency installation failed (exit $LASTEXITCODE)." }
Write-Host "  [PASS] requirements.txt installed into .venv"

# -- 4. smoke-test the imports -----------------------------------------------
Write-Step '4. Import check'
& $VenvPython -c "import httpx, dotenv; print('  [PASS] httpx', httpx.__version__, '/ python-dotenv ok')"
if ($LASTEXITCODE -ne 0) { Fail "The installed packages could not be imported." }

# -- 5. paths, and what to do next -------------------------------------------
Write-Step 'Paths'
Write-Host "  Base Python   : $($base.Path)  (Python $($base.Version))"
Write-Host "  Application   : $AppRoot"
Write-Host "  Virtualenv    : $VenvDir"
Write-Host "  Venv Python   : $VenvPython"
Write-Host "  Config file   : $ConfigFile"
Write-Host "  Config example: $ExampleFile"

Write-Step 'Next steps'
if (Test-Path -LiteralPath $ConfigFile) {
    Write-Host "  $ConfigFile already exists - left untouched. This script never"
    Write-Host "  reads or prints its contents, and never writes credentials into it."
    Write-Host ""
    Write-Host "  Run the safe, offline check first:" -ForegroundColor Green
    Write-Host "    .\run_sync.ps1 -Mode CheckConfig" -ForegroundColor Green
} else {
    if (-not (Test-Path -LiteralPath $ExampleFile)) {
        Write-Host "  [WARN] $ExampleFile is missing. Run install_connector.ps1" -ForegroundColor Yellow
        Write-Host "         from the extracted package - it installs the example." -ForegroundColor Yellow
    }
    Write-Host "  No configuration file was created. Create it yourself and type the"
    Write-Host "  credentials in:"
    Write-Host ""
    Write-Host "    copy `"$ExampleFile`" `"$ConfigFile`"" -ForegroundColor Green
    Write-Host "    notepad `"$ConfigFile`"" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Fill in EASYTIME_BASE_URL, EASYTIME_USERNAME, EASYTIME_PASSWORD"
    Write-Host "  (use a dedicated read-only integration account, not a person's login)"
    Write-Host "  and COREOPS_CONNECTOR_TOKEN. Save as UTF-8 without BOM, or ANSI."
    Write-Host ""
    Write-Host "  Then run the safe, offline check:"
    Write-Host ""
    Write-Host "    .\run_sync.ps1 -Mode CheckConfig" -ForegroundColor Green
}
Write-Host ""
exit 0
