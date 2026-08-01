<#
.SYNOPSIS
    Prepares the Windows directory layout for the EasyTime connector.

.DESCRIPTION
    Creates the folders the connector needs and reports what is still missing.
    It does exactly that, and deliberately nothing else:

      * It does NOT write credentials. The administrator copies .env.example to
        .env and types the values in. A script that writes a password to disk
        is a script that has a password to write.
      * It does NOT create the Windows scheduled task unless -CreateScheduledTask
        is passed explicitly. During development the task must not exist: a
        connector that starts syncing because someone ran an installer is a
        connector nobody decided to switch on.
      * It does NOT install Python packages. setup_probe.ps1 owns the
        virtualenv, and it installs into .\.venv only, never globally.

    Layout created:

      C:\Program Files\CoreOps\EasyTimeConnector\    program files (read-only)
      C:\ProgramData\CoreOps\EasyTimeConnector\
          config\                                    .env lives here
          data\                                      state.db, sync.lock
          logs\                                      dated connector logs

    ProgramData, not Program Files, for everything mutable: the connector runs
    as a service account that must be able to write its state, and Program Files
    is read-only for exactly that reason.

.PARAMETER CreateScheduledTask
    Also register the scheduled tasks. OFF by default and not part of Phase 3 -
    see docs/attendance/easytime-integration.md for the task definitions to
    review before anything is switched on.

.EXAMPLE
    .\install_connector.ps1

.EXAMPLE
    .\install_connector.ps1 -InstallRoot 'C:\CoreOps\EasyTimeConnector'
#>
[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\Program Files\CoreOps\EasyTimeConnector',
    [string]$DataRoot    = 'C:\ProgramData\CoreOps\EasyTimeConnector',

    # Explicitly opt in to registering the Windows scheduled tasks. Phase 3
    # ships them documented but NOT activated.
    [switch]$CreateScheduledTask
)

$ErrorActionPreference = 'Stop'

$Root = $PSScriptRoot

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

function New-DirectoryIfMissing([string]$Path) {
    if (Test-Path -LiteralPath $Path -PathType Container) {
        Write-Host "  [skip] $Path (already exists)"
        return
    }
    if (Test-Path -LiteralPath $Path) {
        Fail "$Path exists but is a file, not a directory."
    }
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
    Write-Host "  [PASS] $Path"
}

# -- 1. administrator check --------------------------------------------------
Write-Step '1. Privileges'
$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin   = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($isAdmin) {
    Write-Host "  [PASS] running elevated"
} else {
    Write-Host "  [WARN] not running as Administrator." -ForegroundColor Yellow
    Write-Host "         Creating folders under Program Files or ProgramData will fail." -ForegroundColor Yellow
    Write-Host "         Re-run from an elevated PowerShell prompt." -ForegroundColor Yellow
}

# -- 2. directory layout -----------------------------------------------------
Write-Step '2. Directory layout'
$ConfigDir = Join-Path $DataRoot 'config'
$DataDir   = Join-Path $DataRoot 'data'
$LogDir    = Join-Path $DataRoot 'logs'

New-DirectoryIfMissing $InstallRoot
New-DirectoryIfMissing $DataRoot
New-DirectoryIfMissing $ConfigDir
New-DirectoryIfMissing $DataDir
New-DirectoryIfMissing $LogDir

# -- 3. write permissions ----------------------------------------------------
Write-Step '3. Write access to the mutable directories'
foreach ($dir in @($ConfigDir, $DataDir, $LogDir)) {
    $probe = Join-Path $dir ".write-test-$([System.Guid]::NewGuid().ToString('N')).tmp"
    try {
        Set-Content -LiteralPath $probe -Value 'ok' -Encoding utf8 -ErrorAction Stop
        Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
        Write-Host "  [PASS] writable: $dir"
    } catch {
        Write-Host "  [FAIL] NOT writable: $dir" -ForegroundColor Red
        Write-Host "         The account that runs the scheduled task must be able to" -ForegroundColor Red
        Write-Host "         write here, or the connector cannot keep its cursor." -ForegroundColor Red
    }
}

# -- 4. credentials: reported, never written ---------------------------------
Write-Step '4. Configuration'
$EnvFile     = Join-Path $Root '.env'
$EnvExample  = Join-Path $Root '.env.example'

if (Test-Path -LiteralPath $EnvFile) {
    Write-Host "  [PASS] .env exists at $EnvFile"
    Write-Host "         This script does not read it, print it or copy it anywhere."
} else {
    Write-Host "  [TODO] .env not found." -ForegroundColor Yellow
    Write-Host "         copy `"$EnvExample`" `"$EnvFile`"" -ForegroundColor Yellow
    Write-Host "         notepad `"$EnvFile`"" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "         Fill in EASYTIME_PASSWORD and COREOPS_CONNECTOR_TOKEN by hand." -ForegroundColor Yellow
    Write-Host "         No installer writes a credential for you, on purpose." -ForegroundColor Yellow
}

$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $VenvPython) {
    Write-Host "  [PASS] virtualenv present at .venv"
} else {
    Write-Host "  [TODO] virtualenv not found. Run: .\setup_probe.ps1" -ForegroundColor Yellow
}

# -- 5. scheduled tasks (opt-in only) ----------------------------------------
Write-Step '5. Scheduled tasks'
if (-not $CreateScheduledTask) {
    Write-Host "  [skip] not created (pass -CreateScheduledTask to register them)."
    Write-Host ""
    Write-Host "         Phase 3 ships the tasks DOCUMENTED but NOT ACTIVATED. Review"
    Write-Host "         the definitions in docs/attendance/easytime-integration.md,"
    Write-Host "         run a few manual syncs first, then switch them on deliberately."
} else {
    if (-not $isAdmin) {
        Fail "Registering a scheduled task requires an elevated prompt."
    }
    if (-not (Test-Path -LiteralPath $EnvFile)) {
        Fail "Refusing to schedule a connector that has no .env. Fill it in and re-run."
    }

    $runSync = Join-Path $Root 'run_sync.ps1'
    if (-not (Test-Path -LiteralPath $runSync)) {
        Fail "run_sync.ps1 not found next to this script."
    }

    # Every 5 minutes, indefinitely. The connector's own run lock is what
    # actually prevents overlap; the task setting below is the second layer.
    $incrementalAction = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runSync`" -Mode Incremental" `
        -WorkingDirectory $Root
    $incrementalTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Minutes 5)
    $settings = New-ScheduledTaskSettingsSet `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 5) `
        -DontStopIfGoingOnBatteries `
        -AllowStartIfOnBatteries

    Register-ScheduledTask -TaskName 'CoreOps EasyTime Sync' `
        -Action $incrementalAction -Trigger $incrementalTrigger -Settings $settings `
        -Description 'Incremental EasyTime -> CoreOps punch synchronization (one shot per fire).' `
        -Force | Out-Null
    Write-Host "  [PASS] 'CoreOps EasyTime Sync' registered (every 5 minutes)"

    # Daily reconciliation: re-sends the last SYNC_RECONCILIATION_DAYS days and
    # is what actually recovers punches EasyTime uploaded the next morning.
    $reconcileAction = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runSync`" -Mode Reconcile" `
        -WorkingDirectory $Root
    $reconcileTrigger = New-ScheduledTaskTrigger -Daily -At '02:30'

    Register-ScheduledTask -TaskName 'CoreOps EasyTime Reconcile' `
        -Action $reconcileAction -Trigger $reconcileTrigger -Settings $settings `
        -Description 'Daily 7-day reconciliation pass; recovers late EasyTime uploads.' `
        -Force | Out-Null
    Write-Host "  [PASS] 'CoreOps EasyTime Reconcile' registered (daily 02:30)"
}

# -- 6. summary --------------------------------------------------------------
Write-Step 'Layout'
Write-Host "  Program files : $InstallRoot"
Write-Host "  Config        : $ConfigDir"
Write-Host "  State         : $DataDir\state.db"
Write-Host "  Lock          : $DataDir\sync.lock"
Write-Host "  Logs          : $LogDir"
Write-Host ""
Write-Host "  Next:" -ForegroundColor Green
Write-Host "    .\setup_probe.ps1                    (once, creates .venv)"
Write-Host "    copy .env.example .env; notepad .env (type the credentials yourself)"
Write-Host "    .\run_sync.ps1 -Mode CheckConfig     (no network call)"
Write-Host "    .\run_sync.ps1 -Mode Status          (no network call)"
Write-Host "    .\run_sync.ps1 -Mode Incremental     (the first real sync)"
Write-Host ""
exit 0
