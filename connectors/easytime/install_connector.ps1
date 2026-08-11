<#
.SYNOPSIS
    Installs the EasyTime connector application onto a Windows administrator PC.

.DESCRIPTION
    Copies an explicit WHITELIST of application files from the extracted package
    into Program Files, and creates the mutable ProgramData layout next to it:

      C:\Program Files\CoreOps\EasyTimeConnector\        application (read-only)
      C:\ProgramData\CoreOps\EasyTimeConnector\
          config\   connector.env          the one configuration file
          data\     state.db, sync.lock    the cursor
          logs\     sync-YYYYMMDD.log      the connector's own logs

    ProgramData, not Program Files, for everything mutable: the connector runs
    as an account that must be able to write its state, and Program Files is
    read-only for exactly that reason.

    What this script deliberately does NOT do:

      * It does NOT write credentials. It installs connector.env.example and
        stops there. A script that writes a password to disk is a script that
        has a password to write.
      * It does NOT overwrite or delete an existing connector.env, state.db or
        log file. Re-running it upgrades the application only.
      * It does NOT touch C:\CoreOps-EasyTime-Probe. The Phase 1 diagnostic
        probe is a separate, independent installation and is refused as a
        destination.
      * It does NOT create the Windows scheduled tasks unless
        -CreateScheduledTask is passed explicitly. A connector that starts
        syncing because someone ran an installer is a connector nobody decided
        to switch on.
      * It does NOT install Python packages. setup_connector.ps1 owns the
        virtual environment, and it installs into .venv only, never globally.

.PARAMETER SourceRoot
    The extracted package directory to install FROM. Defaults to the folder this
    script is sitting in.

.PARAMETER InstallRoot
    Where the application files are copied TO.

.PARAMETER DataRoot
    Where config\, data\ and logs\ are created.

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
    [string]$SourceRoot  = '',
    [string]$InstallRoot = 'C:\Program Files\CoreOps\EasyTimeConnector',
    [string]$DataRoot    = 'C:\ProgramData\CoreOps\EasyTimeConnector',

    # Explicitly opt in to registering the Windows scheduled tasks. Phase 3
    # ships them documented but NOT activated.
    [switch]$CreateScheduledTask
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($SourceRoot)) { $SourceRoot = $PSScriptRoot }

# The complete set of application files. A whitelist, not an exclusion list: a
# file that is not named here cannot reach Program Files, so no .env, no
# state.db, no log, no .venv, no test and no git metadata can be carried across
# by accident.
$AppFiles = @(
    # shared
    'config.py'
    'exceptions.py'
    'schemas.py'
    'client.py'
    'redaction.py'
    'requirements.txt'
    'README.md'
    '.env.example'
    # Phase 1 probe - still the first thing to run on a new site
    'probe.py'
    'run_probe.ps1'
    'setup_probe.ps1'
    # Phase 3 sync
    'sync.py'
    'sync_service.py'
    'coreops_client.py'
    'mapper.py'
    'state.py'
    'runlock.py'
    'logging_setup.py'
    'exit_codes.py'
    'run_sync.ps1'
    'setup_connector.ps1'
    'install_connector.ps1'
)

# The Phase 1 diagnostic probe. Separate installation, separate .env, separate
# lifecycle. Never an installation destination, never removed, never read.
$ProbeRoot = 'C:\CoreOps-EasyTime-Probe'

$ConfigFileName    = 'connector.env'
$ExampleFileName   = 'connector.env.example'

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
    try {
        New-Item -ItemType Directory -Path $Path -Force -ErrorAction Stop | Out-Null
    } catch {
        Fail @"
Cannot create $Path.

Program Files and ProgramData require an elevated prompt. Close this window,
right-click PowerShell, choose 'Run as administrator', and run this script
again.
"@
    }
    Write-Host "  [PASS] $Path"
}

# Compare two paths as paths, not as strings: 'C:\x' and 'C:\x\' and 'C:/x' are
# the same directory and a case difference is not a difference on Windows.
function Get-ComparablePath([string]$Path) {
    try {
        $full = [System.IO.Path]::GetFullPath($Path)
    } catch {
        $full = $Path
    }
    return $full.TrimEnd('\', '/').ToLowerInvariant()
}

function Test-IsUnder([string]$Child, [string]$Parent) {
    $c = Get-ComparablePath $Child
    $p = Get-ComparablePath $Parent
    return ($c -eq $p) -or $c.StartsWith($p + '\')
}

# -- 1. destinations ---------------------------------------------------------
# Validated FIRST, before privileges: "you pointed this at the probe directory"
# is a more useful answer than "C:\ is not writable", and a wrong destination is
# wrong whether or not the prompt is elevated.
Write-Step '1. Destinations'
$ConfigDir   = Join-Path $DataRoot 'config'
$DataDir     = Join-Path $DataRoot 'data'
$LogDir      = Join-Path $DataRoot 'logs'
$ConfigFile  = Join-Path $ConfigDir $ConfigFileName
$ExampleFile = Join-Path $ConfigDir $ExampleFileName

# The probe is a separate installation with its own .env. Installing over it, or
# under it, would give one folder two identities and two config files.
foreach ($pair in @(
    @{ Name = 'InstallRoot'; Path = $InstallRoot },
    @{ Name = 'DataRoot';    Path = $DataRoot }
)) {
    if (Test-IsUnder $pair.Path $ProbeRoot) {
        Fail @"
-$($pair.Name) '$($pair.Path)' is inside the Phase 1 probe directory
$ProbeRoot.

The probe is a separate diagnostic installation with its own .env and its own
lifecycle. This installer never writes there, never removes it, and never reads
it. Choose a different destination.
"@
    }
}
Write-Host "  [PASS] probe directory $ProbeRoot is not a destination (untouched)"

if (Test-IsUnder $SourceRoot $InstallRoot) {
    Fail @"
-SourceRoot '$SourceRoot' is the installation destination itself.

Run this script from the EXTRACTED PACKAGE folder (for example
C:\Users\<you>\Downloads\CoreOps-EasyTime-Connector\), not from
$InstallRoot. Copying a directory onto itself is not an upgrade.
"@
}
Write-Host "  [PASS] source and destination are different directories"
Write-Host "         source      : $SourceRoot"
Write-Host "         destination : $InstallRoot"

# -- 2. privileges -----------------------------------------------------------
Write-Step '2. Privileges'
$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin   = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if ($isAdmin) {
    Write-Host "  [PASS] running elevated as $($identity.Name)"
} else {
    Write-Host "  [WARN] not running as Administrator ($($identity.Name))." -ForegroundColor Yellow
    Write-Host "         Program Files and ProgramData are not writable without it." -ForegroundColor Yellow
    # Not fatal on its own: a custom -InstallRoot under the user's own profile
    # is a legitimate, unprivileged installation. What must not happen is a
    # HALF-DONE install, so prove writability before copying anything.
    foreach ($target in @($InstallRoot, $DataRoot)) {
        $existing = $target
        while ($existing -and -not (Test-Path -LiteralPath $existing)) {
            $existing = Split-Path -Parent $existing
        }
        if (-not $existing) {
            Fail "Cannot resolve an existing parent directory for $target."
        }
        $writeProbe = Join-Path $existing ".coreops-install-test-$([System.Guid]::NewGuid().ToString('N')).tmp"
        try {
            Set-Content -LiteralPath $writeProbe -Value 'ok' -Encoding utf8 -ErrorAction Stop
            Remove-Item -LiteralPath $writeProbe -Force -ErrorAction SilentlyContinue
        } catch {
            Fail @"
$existing is not writable by $($identity.Name), so installing to
$target would fail part-way through and leave a half-installed connector.

Re-run this script from an elevated PowerShell prompt:
    right-click PowerShell -> Run as administrator
"@
        }
    }
    Write-Host "  [PASS] the chosen roots are writable without elevation"
}

# -- 3. source files ---------------------------------------------------------
Write-Step '3. Source files'
$missing = @()
foreach ($name in $AppFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot $name) -PathType Leaf)) {
        $missing += $name
    }
}
if ($missing.Count -gt 0) {
    Fail @"
The package at $SourceRoot is incomplete. Missing:
    $($missing -join ', ')

Extract CoreOps-EasyTime-Connector.zip again and run this script from the folder
it produced.
"@
}
Write-Host "  [PASS] all $($AppFiles.Count) application files present"

# A .env carried into the package would shadow the installed connector.env
# (config.py prefers a .env sitting next to the scripts, which is what keeps the
# probe folder and source checkouts working). Refuse rather than delete: the
# file may hold the only copy of a credential.
$StraySource = Join-Path $SourceRoot '.env'
if (Test-Path -LiteralPath $StraySource -PathType Leaf) {
    Fail @"
$StraySource exists.

A .env next to the scripts takes precedence over the installed
$ConfigFile, so installing this package would produce a connector that
reads a file you did not expect. It is NOT deleted automatically - it may hold
the only copy of a credential.

Move it somewhere safe, then re-run this script.
"@
}

# -- 4. directory layout -----------------------------------------------------
Write-Step '4. Directory layout'
New-DirectoryIfMissing $InstallRoot
New-DirectoryIfMissing $DataRoot
New-DirectoryIfMissing $ConfigDir
New-DirectoryIfMissing $DataDir
New-DirectoryIfMissing $LogDir

# -- 5. write access to the mutable directories ------------------------------
Write-Step '5. Write access to the mutable directories'
$notWritable = @()
foreach ($dir in @($ConfigDir, $DataDir, $LogDir)) {
    $writeProbe = Join-Path $dir ".write-test-$([System.Guid]::NewGuid().ToString('N')).tmp"
    try {
        Set-Content -LiteralPath $writeProbe -Value 'ok' -Encoding utf8 -ErrorAction Stop
        Remove-Item -LiteralPath $writeProbe -Force -ErrorAction SilentlyContinue
        Write-Host "  [PASS] writable: $dir"
    } catch {
        Write-Host "  [FAIL] NOT writable: $dir" -ForegroundColor Red
        $notWritable += $dir
    }
}
if ($notWritable.Count -gt 0) {
    Fail @"
The connector cannot keep its cursor or its logs in:
    $($notWritable -join "`r`n    ")

Grant the account that will run the connector Modify permission on
$DataRoot, then re-run this script.
"@
}

# -- 6. install the application ----------------------------------------------
Write-Step '6. Installing application files'
# A stray .env already sitting in the install root would shadow connector.env
# for every future run. Same rule as the source check: refuse, never delete.
$StrayInstalled = Join-Path $InstallRoot '.env'
if (Test-Path -LiteralPath $StrayInstalled -PathType Leaf) {
    Fail @"
$StrayInstalled exists and would take precedence over
$ConfigFile.

This installer never creates that file. Move it somewhere safe (it may hold the
only copy of a credential), then re-run this script.
"@
}

$copied = 0
foreach ($name in $AppFiles) {
    $from = Join-Path $SourceRoot $name
    $to   = Join-Path $InstallRoot $name
    $verb = if (Test-Path -LiteralPath $to -PathType Leaf) { 'updated' } else { 'installed' }
    try {
        Copy-Item -LiteralPath $from -Destination $to -Force -ErrorAction Stop
    } catch {
        Fail "Could not copy $name to $InstallRoot. $($_.Exception.Message)"
    }
    Write-Host ("  [PASS] {0,-9} {1}" -f $verb, $name)
    $copied++
}
Write-Host "  [PASS] $copied application file(s) in $InstallRoot"

# Anything already in the install root that is not ours is reported, never
# removed. An upgrade that deletes a file somebody put there on purpose is an
# upgrade that loses data.
$foreign = @(Get-ChildItem -LiteralPath $InstallRoot -Force -File -ErrorAction SilentlyContinue |
    Where-Object { $AppFiles -notcontains $_.Name } |
    ForEach-Object { $_.Name })
if ($foreign.Count -gt 0) {
    Write-Host "  [note] not part of this package and left alone: $($foreign -join ', ')"
}
if (Test-Path -LiteralPath (Join-Path $InstallRoot '.venv')) {
    Write-Host "  [note] existing .venv left in place (run setup_connector.ps1 to refresh it)"
}

# -- 7. configuration: an example only ---------------------------------------
Write-Step '7. Configuration'
# The example is safe to overwrite on every run - it is documentation, and a
# newer build may document a new setting. The REAL file is never written.
Copy-Item -LiteralPath (Join-Path $SourceRoot '.env.example') -Destination $ExampleFile -Force
Write-Host "  [PASS] example installed: $ExampleFile"

if (Test-Path -LiteralPath $ConfigFile) {
    Write-Host "  [keep] $ConfigFile already exists - left exactly as it was."
    Write-Host "         This script does not read it, print it or copy it anywhere."
} else {
    Write-Host "  [TODO] $ConfigFile does not exist yet." -ForegroundColor Yellow
    Write-Host "         Create it yourself and type the credentials in:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "         copy `"$ExampleFile`" `"$ConfigFile`"" -ForegroundColor Yellow
    Write-Host "         notepad `"$ConfigFile`"" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "         Fill in EASYTIME_PASSWORD and COREOPS_CONNECTOR_TOKEN by hand." -ForegroundColor Yellow
    Write-Host "         No installer writes a credential for you, on purpose." -ForegroundColor Yellow
    Write-Host "         Save as UTF-8 without BOM, or ANSI - a BOM makes the first" -ForegroundColor Yellow
    Write-Host "         setting in the file silently unreadable." -ForegroundColor Yellow
}

if (Test-Path -LiteralPath (Join-Path $DataDir 'state.db')) {
    Write-Host "  [keep] $DataDir\state.db already exists - the cursor is preserved."
}

# -- 8. virtual environment --------------------------------------------------
Write-Step '8. Virtual environment'
$VenvPython = Join-Path $InstallRoot '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $VenvPython) {
    Write-Host "  [PASS] present at $VenvPython"
} else {
    Write-Host "  [TODO] not created yet. Run, from $InstallRoot :" -ForegroundColor Yellow
    Write-Host "           .\setup_connector.ps1" -ForegroundColor Yellow
}

# -- 9. scheduled tasks (opt-in only) ----------------------------------------
Write-Step '9. Scheduled tasks'
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
    if (-not (Test-Path -LiteralPath $ConfigFile)) {
        Fail "Refusing to schedule a connector that has no $ConfigFile. Fill it in and re-run."
    }

    $runSync = Join-Path $InstallRoot 'run_sync.ps1'
    if (-not (Test-Path -LiteralPath $runSync)) {
        Fail "run_sync.ps1 was not installed to $InstallRoot."
    }

    # Every 5 minutes, indefinitely. The connector's own run lock is what
    # actually prevents overlap; the task setting below is the second layer.
    $incrementalAction = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runSync`" -Mode Incremental" `
        -WorkingDirectory $InstallRoot
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
        -WorkingDirectory $InstallRoot
    $reconcileTrigger = New-ScheduledTaskTrigger -Daily -At '02:30'

    Register-ScheduledTask -TaskName 'CoreOps EasyTime Reconcile' `
        -Action $reconcileAction -Trigger $reconcileTrigger -Settings $settings `
        -Description 'Daily 7-day reconciliation pass; recovers late EasyTime uploads.' `
        -Force | Out-Null
    Write-Host "  [PASS] 'CoreOps EasyTime Reconcile' registered (daily 02:30)"
}

# -- 10. summary -------------------------------------------------------------
Write-Step 'Installed layout'
Write-Host "  Application   : $InstallRoot"
Write-Host "  Virtualenv    : $InstallRoot\.venv"
Write-Host "  Python        : $VenvPython"
Write-Host "  Config file   : $ConfigFile"
Write-Host "  Config example: $ExampleFile"
Write-Host "  State         : $DataDir\state.db"
Write-Host "  Lock          : $DataDir\sync.lock"
Write-Host "  Connector logs: $LogDir"
Write-Host "  Wrapper logs  : $LogDir"
Write-Host "  Probe (Phase 1, separate and untouched): $ProbeRoot"
Write-Host ""
Write-Host "  Next, from $InstallRoot :" -ForegroundColor Green
Write-Host "    .\setup_connector.ps1                     (once, creates .venv)"
Write-Host "    copy `"$ExampleFile`" `"$ConfigFile`""
Write-Host "    notepad `"$ConfigFile`"                   (type the credentials yourself)"
Write-Host "    .\run_sync.ps1 -Mode CheckConfig          (no network call)"
Write-Host "    .\run_sync.ps1 -Mode Backfill -FromDate <YYYY-MM-DD> -ToDate <YYYY-MM-DD>"
Write-Host ""
Write-Host "  To remove: delete $InstallRoot." -ForegroundColor Green
Write-Host "  $DataRoot holds the config, the cursor and the logs -"
Write-Host "  delete it only if you mean to lose them."
Write-Host ""
exit 0
