<#
.SYNOPSIS
    Runs one EasyTime -> CoreOps synchronization and keeps a sanitized log.

.DESCRIPTION
    Wrapper around sync.py, and the entry point a Windows scheduled task should
    call. It never takes a username, a password or a connector token on the
    command line - every secret lives in the configuration file, which this
    script never reads or prints. Console output is mirrored to a timestamped
    file under the log directory after a defensive redaction pass (sync.py is
    the primary redaction layer; this is the second net, exactly as
    run_probe.ps1 is for probe.py).

    **Location-independent.** Every path is derived from the location of this
    script or from a fixed absolute root - never from the caller's current
    directory - so it behaves identically when started from Program Files, from
    Task Scheduler, or from any other working directory:

        application  : the folder this script is in
        interpreter  : <application>\.venv\Scripts\python.exe
        configuration: -EnvFile, else $COREOPS_CONNECTOR_ENV_FILE, else
                       <application>\.env, else
                       C:\ProgramData\CoreOps\EasyTimeConnector\config\connector.env
        state + logs : C:\ProgramData\CoreOps\EasyTimeConnector\{data,logs}

    The resolved configuration path is exported as
    $COREOPS_CONNECTOR_ENV_FILE for the child process, so this script and
    sync.py can never disagree about which file is in force.

    It does not create, register or modify a scheduled task.

    The exit code of sync.py is propagated unchanged, so Task Scheduler sees
    the real result:

        0  success                     5  EasyTime transport/API failure
        2  invalid configuration       6  CoreOps authentication failure
        3  another run is active       7  CoreOps payload rejection
        4  EasyTime authentication     8  CoreOps transport/server failure
                                       9  local state failure

.PARAMETER Mode
    Incremental - the scheduled run: cursor minus the overlap, up to now.
    Reconcile   - re-send the last N days; recovers late uploads.
    Backfill    - an explicit -FromDate/-ToDate range. Requires both.
    Status      - print the local cursor and counters. No network call.
    CheckConfig - validate the configuration file. No network call.

.PARAMETER EnvFile
    Use a specific configuration file instead of the resolved default. A path is
    not a secret; the credentials still live only inside the file it names.

.PARAMETER DataRoot
    Override the ProgramData root that holds config\, data\ and logs\.

.EXAMPLE
    .\run_sync.ps1 -Mode CheckConfig

.EXAMPLE
    .\run_sync.ps1 -Mode Incremental

.EXAMPLE
    .\run_sync.ps1 -Mode Reconcile -ReconcileDays 7

.EXAMPLE
    .\run_sync.ps1 -Mode Backfill -FromDate 2026-07-29 -ToDate 2026-07-30
#>
# [CmdletBinding()] and the [Parameter()] attribute below make this an ADVANCED
# script, which means PowerShell adds the common parameters (-Verbose, -Debug,
# -ErrorAction, ...) automatically. Declaring a [switch]$Verbose of our own here
# is not a duplicate flag, it is a hard binding error - "A parameter with the
# name 'Verbose' was defined multiple times" - and the script then refuses to
# run at all, for every mode. -Verbose is therefore taken from the common
# parameter and read out of $PSBoundParameters further down.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Incremental', 'Reconcile', 'Backfill', 'Status', 'CheckConfig')]
    [string]$Mode,

    # Reconcile only: override SYNC_RECONCILIATION_DAYS.
    [ValidateRange(1, 90)]
    [int]$ReconcileDays,

    # Backfill only. Both are required, and there is no default on purpose.
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')]
    [string]$FromDate,

    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')]
    [string]$ToDate,

    # Backfill only: allow a range longer than SYNC_MAX_RANGE_DAYS.
    [switch]$Force,

    # An explicit configuration FILE PATH. Never a credential.
    [string]$EnvFile = '',

    [string]$DataRoot = 'C:\ProgramData\CoreOps\EasyTimeConnector'
)

$ErrorActionPreference = 'Stop'

# $PSScriptRoot, never $PWD: this script must resolve the same files whether it
# is launched by hand, by Task Scheduler, or from C:\Windows\System32.
$AppRoot    = $PSScriptRoot
$SyncFile   = Join-Path $AppRoot 'sync.py'
$Stamp      = Get-Date -Format 'yyyyMMdd-HHmmss'

$ConfigDir     = Join-Path $DataRoot 'config'
$InstalledEnv  = Join-Path $ConfigDir 'connector.env'
$ExampleEnv    = Join-Path $ConfigDir 'connector.env.example'
$LocalEnv      = Join-Path $AppRoot '.env'
$DataDir       = Join-Path $DataRoot 'data'
$ProgramDataLogDir = Join-Path $DataRoot 'logs'

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    exit 2
}

# -- locate the interpreter --------------------------------------------------
# A packaged installation ships a .venv next to the scripts. A frozen
# executable (should one ever be built) wins if it is present.
$PackagedExe = Join-Path $AppRoot 'coreops-easytime-sync.exe'
$VenvPython  = Join-Path $AppRoot '.venv\Scripts\python.exe'

if (Test-Path -LiteralPath $PackagedExe) {
    $Executable = $PackagedExe
    $BaseArgs   = @()
} elseif (Test-Path -LiteralPath $VenvPython) {
    if (-not (Test-Path -LiteralPath $SyncFile)) {
        Fail "sync.py not found next to this script ($SyncFile)."
    }
    $Executable = $VenvPython
    $BaseArgs   = @($SyncFile)
} else {
    Fail @"
Neither $VenvPython nor coreops-easytime-sync.exe was found.

Run the setup script once first, from $AppRoot :
    .\setup_connector.ps1
"@
}

# -- resolve the configuration file ------------------------------------------
# The same four rules, in the same order, as config.resolve_env_path. None of
# them looks at the current working directory.
if (-not [string]::IsNullOrWhiteSpace($EnvFile)) {
    $ResolvedEnv  = $EnvFile
    $EnvSource    = '-EnvFile'
} elseif (-not [string]::IsNullOrWhiteSpace($env:COREOPS_CONNECTOR_ENV_FILE)) {
    $ResolvedEnv  = $env:COREOPS_CONNECTOR_ENV_FILE
    $EnvSource    = '$COREOPS_CONNECTOR_ENV_FILE'
} elseif (Test-Path -LiteralPath $LocalEnv -PathType Leaf) {
    $ResolvedEnv  = $LocalEnv
    $EnvSource    = 'source checkout (.env next to the scripts)'
} else {
    $ResolvedEnv  = $InstalledEnv
    $EnvSource    = 'installed (ProgramData)'
}

if (-not (Test-Path -LiteralPath $ResolvedEnv -PathType Leaf)) {
    if ($Mode -ne 'Status') {
        Fail @"
Configuration file not found: $ResolvedEnv
  chosen by: $EnvSource

Create it from the installed example and type the credentials in yourself:
    copy "$ExampleEnv" "$InstalledEnv"
    notepad "$InstalledEnv"

If install_connector.ps1 has not been run on this PC yet, run it first - it is
what installs the example.
"@
    }
    Write-Host "[WARN] $ResolvedEnv does not exist; -Mode Status reads local state only." -ForegroundColor Yellow
} else {
    # A UTF-8 BOM makes python-dotenv read the first key as
    # "<BOM>EASYTIME_BASE_URL", so the first setting in the file silently goes
    # missing. Only the first three bytes are read here; the file's contents are
    # never touched, printed or logged.
    $firstBytes = Get-Content -LiteralPath $ResolvedEnv -Encoding Byte -TotalCount 3 -ErrorAction SilentlyContinue
    if ($firstBytes.Count -eq 3 -and $firstBytes[0] -eq 0xEF -and $firstBytes[1] -eq 0xBB -and $firstBytes[2] -eq 0xBF) {
        Write-Host "[WARN] the configuration file starts with a UTF-8 BOM. The FIRST setting" -ForegroundColor Yellow
        Write-Host "       in it will be ignored (it reads as a garbled key name). Re-save it" -ForegroundColor Yellow
        Write-Host "       as UTF-8 without BOM, or as plain ANSI, using Notepad." -ForegroundColor Yellow
    }
}

# Hand the child process the exact same answers, so there is no second
# resolution and no way for the two to disagree about which file is in force or
# where the cursor lives. Both are PATHS, not secrets.
$env:COREOPS_CONNECTOR_ENV_FILE = $ResolvedEnv
$env:COREOPS_CONNECTOR_DATA_ROOT = $DataRoot

# -- argument validation -----------------------------------------------------
if ($Mode -eq 'Backfill') {
    if ([string]::IsNullOrWhiteSpace($FromDate) -or [string]::IsNullOrWhiteSpace($ToDate)) {
        Fail "-Mode Backfill requires BOTH -FromDate and -ToDate (YYYY-MM-DD). There is no default range on purpose."
    }
} elseif ($FromDate -or $ToDate) {
    Fail "-FromDate/-ToDate only apply to -Mode Backfill."
}
if ($Mode -ne 'Reconcile' -and $PSBoundParameters.ContainsKey('ReconcileDays')) {
    Fail "-ReconcileDays only applies to -Mode Reconcile."
}
if ($Force -and $Mode -ne 'Backfill') {
    Write-Host "[WARN] -Force only affects Backfill; ignored for $Mode." -ForegroundColor Yellow
}

# -- build the sync.py argument list -----------------------------------------
# Note there is deliberately no username, password or token argument anywhere.
$SyncArgs = $BaseArgs
switch ($Mode) {
    'Incremental' { $SyncArgs += '--once' }
    'Reconcile'   {
        if ($PSBoundParameters.ContainsKey('ReconcileDays')) {
            $SyncArgs += @('--reconcile-days', "$ReconcileDays")
        } else {
            $SyncArgs += '--reconcile'
        }
    }
    'Backfill'    { $SyncArgs += @('--from-date', $FromDate, '--to-date', $ToDate) }
    'Status'      { $SyncArgs += '--status' }
    'CheckConfig' { $SyncArgs += '--check-config' }
}
if ($Force -and $Mode -eq 'Backfill') { $SyncArgs += '--force' }
# The COMMON -Verbose parameter, not one of ours. See the note above the param
# block for why this is not declared as a [switch].
if ($PSBoundParameters.ContainsKey('Verbose')) { $SyncArgs += '--verbose' }

# -- defensive redaction -----------------------------------------------------
# sync.py already refuses to print secrets. These patterns are a second layer
# applied to everything before it reaches the console or the wrapper log.
# [^\S\r\n] is horizontal whitespace only - plain \s would let a match run
# across a line break and swallow the following line.
$SensitivePatterns = @(
    '(?i)\b(password|passwd|pwd|token|secret|api[_-]?key|access_token|refresh_token|authorization)\b["'']?[^\S\r\n]*[:=][^\S\r\n]*["'']?[^\s"'',;}\]]+',
    '(?i)X-CoreOps-Connector-Token["'']?[^\S\r\n]*[:=][^\S\r\n]*["'']?[^\s"'',;}\]]+',
    '(?i)\b(JWT|Bearer|Token)[^\S\r\n]+[A-Za-z0-9\-\._~\+/]{16,}=*',
    '\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b'
)

function Protect-Text([string]$Text) {
    if ([string]::IsNullOrEmpty($Text)) { return $Text }
    foreach ($pattern in $SensitivePatterns) {
        $Text = [regex]::Replace($Text, $pattern, '<redacted>')
    }
    return $Text
}

# -- wrapper log -------------------------------------------------------------
# sync.py writes its own structured, dated log under SYNC_LOG_DIR. This wrapper
# log is separate and per-run: it captures whatever reached the console,
# including a Python traceback that never made it into the structured log.
#
# It must NOT land under Program Files - that directory is read-only for the
# account the scheduled task runs as, which is the whole reason ProgramData
# exists. Prefer the ProgramData log directory; fall back to the application
# folder only in a development checkout, and to TEMP if neither is writable.
function Resolve-LogDir {
    $candidates = @()
    if (Test-Path -LiteralPath $DataRoot -PathType Container) { $candidates += $ProgramDataLogDir }
    $candidates += (Join-Path $AppRoot 'logs')
    $candidates += (Join-Path ([System.IO.Path]::GetTempPath()) 'CoreOps-EasyTimeConnector-logs')

    foreach ($candidate in $candidates) {
        try {
            if (-not (Test-Path -LiteralPath $candidate -PathType Container)) {
                New-Item -ItemType Directory -Path $candidate -Force -ErrorAction Stop | Out-Null
            }
            $writeProbe = Join-Path $candidate ".write-test-$([System.Guid]::NewGuid().ToString('N')).tmp"
            Set-Content -LiteralPath $writeProbe -Value 'ok' -Encoding utf8 -ErrorAction Stop
            Remove-Item -LiteralPath $writeProbe -Force -ErrorAction SilentlyContinue
            return $candidate
        } catch {
            continue
        }
    }
    return $null
}

$LogDir = Resolve-LogDir
if ($null -eq $LogDir) {
    Fail "No writable directory for the wrapper log (tried $ProgramDataLogDir, $AppRoot\logs and TEMP)."
}
$LogFile = Join-Path $LogDir "sync-$($Mode.ToLower())-$Stamp.log"
$TmpOut  = Join-Path $LogDir "_stdout-$Stamp.tmp"
$TmpErr  = Join-Path $LogDir "_stderr-$Stamp.tmp"

$Header = @(
    "CoreOps EasyTime sync run"
    "  started   : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')"
    "  mode      : $Mode"
    "  application: $AppRoot"
    "  executable: $Executable"
    "  config    : $ResolvedEnv  ($EnvSource)"
    "  arguments : $($SyncArgs -join ' ')"
    "  note      : credentials are read from the configuration file by sync.py;"
    "              this script never reads, prints or logs its contents."
    ('=' * 72)
)
$Header | Out-File -FilePath $LogFile -Encoding utf8

Write-Host ""
Write-Host "Running sync: $Mode" -ForegroundColor Cyan
Write-Host "  application : $AppRoot"
Write-Host "  config      : $ResolvedEnv  ($EnvSource)"
Write-Host ('-' * 72)

# Start-Process with file redirection rather than "2>&1" - in Windows
# PowerShell, redirecting a native command's stderr inline turns each line into
# an ErrorRecord and corrupts the exit status. WorkingDirectory is pinned to the
# application folder so a relative path can never resolve against the caller's.
$startArgs = @{
    FilePath               = $Executable
    WorkingDirectory       = $AppRoot
    NoNewWindow            = $true
    Wait                   = $true
    PassThru               = $true
    RedirectStandardOutput = $TmpOut
    RedirectStandardError  = $TmpErr
}
if ($SyncArgs.Count -gt 0) { $startArgs['ArgumentList'] = $SyncArgs }

$process  = Start-Process @startArgs
$exitCode = $process.ExitCode

$stdout = if (Test-Path -LiteralPath $TmpOut) { Get-Content -LiteralPath $TmpOut -Raw } else { '' }
$stderr = if (Test-Path -LiteralPath $TmpErr) { Get-Content -LiteralPath $TmpErr -Raw } else { '' }
Remove-Item -LiteralPath $TmpOut, $TmpErr -Force -ErrorAction SilentlyContinue

$safeOut = Protect-Text $stdout
$safeErr = Protect-Text $stderr

if (-not [string]::IsNullOrWhiteSpace($safeOut)) {
    Write-Host $safeOut.TrimEnd()
    Add-Content -LiteralPath $LogFile -Value $safeOut -Encoding utf8
}
if (-not [string]::IsNullOrWhiteSpace($safeErr)) {
    Write-Host ""
    Write-Host "--- connector log (stderr) ---" -ForegroundColor DarkGray
    Write-Host $safeErr.TrimEnd() -ForegroundColor DarkGray
    Add-Content -LiteralPath $LogFile -Value "`r`n--- connector log (stderr) ---" -Encoding utf8
    Add-Content -LiteralPath $LogFile -Value $safeErr -Encoding utf8
}

Add-Content -LiteralPath $LogFile -Value ('=' * 72) -Encoding utf8
Add-Content -LiteralPath $LogFile -Value "exit code: $exitCode" -Encoding utf8

# -- report where everything landed ------------------------------------------
$ExitLabels = @{
    0 = 'success'
    2 = 'invalid configuration'
    3 = 'another run is active'
    4 = 'EasyTime authentication failure'
    5 = 'EasyTime transport/API failure'
    6 = 'CoreOps authentication failure'
    7 = 'CoreOps payload rejection'
    8 = 'CoreOps transport/server failure'
    9 = 'local state failure'
}
$labelText = if ($ExitLabels.ContainsKey($exitCode)) { $ExitLabels[$exitCode] } else { "unexpected failure" }

Write-Host ""
Write-Host ('-' * 72)
Write-Host "Wrapper log : $LogFile"

# The structured connector log and the state file live wherever the
# configuration points; sync.py prints the exact locations under --status. Show
# the defaults so the operator always has somewhere to look.
if (Test-Path -LiteralPath $DataRoot -PathType Container) {
    Write-Host "Sync logs   : $ProgramDataLogDir"
    Write-Host "State file  : $DataDir\state.db"
} else {
    Write-Host "Sync logs   : $(Join-Path $AppRoot 'logs')  (development layout)"
    Write-Host "State file  : $(Join-Path $AppRoot 'data\state.db')  (development layout)"
}
Write-Host "             (run '.\run_sync.ps1 -Mode Status' for the exact paths in use)"

if ($exitCode -eq 0) {
    Write-Host "Result      : $labelText (exit 0)" -ForegroundColor Green
} elseif ($exitCode -eq 3) {
    Write-Host "Result      : $labelText (exit 3)" -ForegroundColor Yellow
} else {
    Write-Host "Result      : $labelText (exit $exitCode)" -ForegroundColor Red
}
Write-Host ""

exit $exitCode
