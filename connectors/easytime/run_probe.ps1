<#
.SYNOPSIS
    Runs the read-only EasyTime probe and keeps a sanitized log of the run.

.DESCRIPTION
    Wrapper around probe.py. It never takes a username or a password on the
    command line - credentials live only in .env, which this script never reads
    or prints. Console output is mirrored to a timestamped file under .\logs\
    after a defensive redaction pass (probe.py is the primary redaction layer;
    this is a second net in case a future change leaks something).

    The exit code of probe.py is propagated, so a failure is a failure here too.

.PARAMETER Mode
    CheckConfig  - validate .env, no network call at all.
    Discover     - probe every candidate endpoint and report which ones exist.
    Transactions - fetch one day of transactions (requires -Date).

.EXAMPLE
    .\run_probe.ps1 -Mode CheckConfig

.EXAMPLE
    .\run_probe.ps1 -Mode Discover

.EXAMPLE
    .\run_probe.ps1 -Mode Transactions -Date 2026-07-29 -EmployeeCode EMP069 -SaveReport
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('CheckConfig', 'Discover', 'Transactions')]
    [string]$Mode,

    # Day to fetch, YYYY-MM-DD. Required for -Mode Transactions.
    [ValidatePattern('^\d{4}-\d{2}-\d{2}$')]
    [string]$Date,

    # Optional: limit the fetch to a single EasyTime employee code.
    [string]$EmployeeCode,

    # Optional: force a smaller page so pagination can be proven.
    [ValidateRange(1, 10000)]
    [int]$PageSize,

    # Write a sanitized JSON summary to .\probe-output\.
    [switch]$SaveReport,

    # Print FULL employee codes instead of masked ones. Only for the CoreOps
    # code-match check, and only on the admin PC. Off unless explicitly passed.
    [switch]$ShowCodes
)

$ErrorActionPreference = 'Stop'

$Root       = $PSScriptRoot
$VenvPython = Join-Path $Root '.venv\Scripts\python.exe'
$ProbeFile  = Join-Path $Root 'probe.py'
$LogDir     = Join-Path $Root 'logs'
$OutputDir  = Join-Path $Root 'probe-output'
$Stamp      = Get-Date -Format 'yyyyMMdd-HHmmss'

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    exit 1
}

# -- defensive redaction -----------------------------------------------------
# probe.py already refuses to print secrets. These patterns are a second layer
# applied to everything before it reaches the console or the log file.
# [^\S\r\n] is "horizontal whitespace only" - plain \s would let a match run
# across a line break and swallow the following line.
$SensitivePatterns = @(
    '(?i)\b(password|passwd|pwd|token|secret|api[_-]?key|access_token|refresh_token|authorization)\b["'']?[^\S\r\n]*[:=][^\S\r\n]*["'']?[^\s"'',;}\]]+',
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

function Hide-Code([string]$Code) {
    if ([string]::IsNullOrEmpty($Code)) { return $Code }
    if ($Code.Length -le 4) { return $Code.Substring(0, 1) + ('*' * ($Code.Length - 1)) }
    return $Code.Substring(0, 3) + ('*' * ($Code.Length - 4)) + $Code.Substring($Code.Length - 1, 1)
}

# -- preconditions -----------------------------------------------------------
if (-not (Test-Path -LiteralPath $ProbeFile)) {
    Fail "probe.py not found next to this script ($ProbeFile)."
}
if (-not (Test-Path -LiteralPath $VenvPython)) {
    Fail @"
.venv\Scripts\python.exe not found.

Run the setup script once first:
    .\setup_probe.ps1
"@
}
# A UTF-8 BOM makes python-dotenv read the first key as "<BOM>EASYTIME_BASE_URL",
# so the first setting in the file silently goes missing. Saving .env from
# PowerShell redirection or "Save as UTF-8 with BOM" is how this happens.
# Only the first three bytes are read here; the file's contents are not.
$EnvFile = Join-Path $Root '.env'
if (Test-Path -LiteralPath $EnvFile) {
    $firstBytes = Get-Content -LiteralPath $EnvFile -Encoding Byte -TotalCount 3 -ErrorAction SilentlyContinue
    if ($firstBytes.Count -eq 3 -and $firstBytes[0] -eq 0xEF -and $firstBytes[1] -eq 0xBB -and $firstBytes[2] -eq 0xBF) {
        Write-Host "[WARN] .env starts with a UTF-8 BOM. The FIRST setting in the file will be" -ForegroundColor Yellow
        Write-Host "       ignored (it reads as a garbled key name). Re-save .env as UTF-8" -ForegroundColor Yellow
        Write-Host "       without BOM, or as plain ANSI, using Notepad." -ForegroundColor Yellow
    }
}

if ($Mode -eq 'Transactions' -and [string]::IsNullOrWhiteSpace($Date)) {
    Fail "-Mode Transactions requires -Date YYYY-MM-DD (be explicit; the report has to name the day)."
}
if ($Mode -ne 'Transactions' -and -not [string]::IsNullOrWhiteSpace($EmployeeCode)) {
    Fail "-EmployeeCode only applies to -Mode Transactions."
}
if ($Mode -eq 'CheckConfig' -and $SaveReport) {
    Write-Host "[WARN] -SaveReport is ignored for CheckConfig: that mode exits before any report is built." -ForegroundColor Yellow
}

# -- build the probe.py argument list ---------------------------------------
# Note there is deliberately no username/password argument anywhere here.
$ProbeArgs = @($ProbeFile)
switch ($Mode) {
    'CheckConfig'  { $ProbeArgs += '--check-config' }
    'Discover'     { $ProbeArgs += '--discover' }
    'Transactions' { $ProbeArgs += @('--date', $Date) }
}
if ($Mode -eq 'Transactions' -and -not [string]::IsNullOrWhiteSpace($EmployeeCode)) {
    $ProbeArgs += @('--emp-code', $EmployeeCode)
}
if ($Mode -eq 'Transactions' -and $PSBoundParameters.ContainsKey('PageSize')) {
    $ProbeArgs += @('--page-size', "$PageSize")
}
if ($SaveReport) { $ProbeArgs += '--save-report' }
if ($ShowCodes)  { $ProbeArgs += '--show-codes' }

# -- logging -----------------------------------------------------------------
if (-not (Test-Path -LiteralPath $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}
$LogFile = Join-Path $LogDir "probe-$($Mode.ToLower())-$Stamp.log"
$TmpOut  = Join-Path $LogDir "_stdout-$Stamp.tmp"
$TmpErr  = Join-Path $LogDir "_stderr-$Stamp.tmp"

# The employee code is masked in the log header unless -ShowCodes was passed,
# so the log matches the privacy level of the probe output it accompanies.
$LoggedArgs = $ProbeArgs | ForEach-Object {
    if (-not $ShowCodes -and $_ -eq $EmployeeCode -and -not [string]::IsNullOrWhiteSpace($EmployeeCode)) {
        Hide-Code $_
    } else { $_ }
}

$Header = @(
    "CoreOps EasyTime probe run"
    "  started    : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')"
    "  mode       : $Mode"
    "  python     : $VenvPython"
    "  arguments  : $($LoggedArgs -join ' ')"
    "  show-codes : $($ShowCodes.IsPresent)"
    "  note       : credentials are read from .env by probe.py; this script"
    "               never reads, prints or logs the contents of .env."
    ('=' * 72)
)
$Header | Out-File -FilePath $LogFile -Encoding utf8

Write-Host ""
Write-Host "Running probe: $Mode" -ForegroundColor Cyan
Write-Host ('-' * 72)

# Start-Process with file redirection rather than "2>&1" - in Windows
# PowerShell, redirecting a native command's stderr inline turns each line into
# an ErrorRecord and corrupts the exit status.
$process = Start-Process -FilePath $VenvPython `
                         -ArgumentList $ProbeArgs `
                         -WorkingDirectory $Root `
                         -NoNewWindow `
                         -Wait `
                         -PassThru `
                         -RedirectStandardOutput $TmpOut `
                         -RedirectStandardError $TmpErr

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
    Write-Host "--- stderr ---" -ForegroundColor Yellow
    Write-Host $safeErr.TrimEnd() -ForegroundColor Yellow
    Add-Content -LiteralPath $LogFile -Value "`r`n--- stderr ---" -Encoding utf8
    Add-Content -LiteralPath $LogFile -Value $safeErr -Encoding utf8
}

Add-Content -LiteralPath $LogFile -Value ('=' * 72) -Encoding utf8
Add-Content -LiteralPath $LogFile -Value "exit code: $exitCode" -Encoding utf8

# -- report where everything landed ------------------------------------------
Write-Host ""
Write-Host ('-' * 72)
Write-Host "Log file : $LogFile"

$reportPath = $null
if ($safeOut -match 'Report written to (.+)') {
    $reportPath = $Matches[1].Trim()
}
if ($reportPath) {
    Write-Host "Report   : $reportPath"
} elseif ($SaveReport -and $Mode -ne 'CheckConfig') {
    Write-Host "Report   : none written (the probe exited before the report step)" -ForegroundColor Yellow
} else {
    Write-Host "Report   : not requested (pass -SaveReport to write one to $OutputDir)"
}

if ($exitCode -eq 0) {
    Write-Host "Result   : OK (exit 0)" -ForegroundColor Green
} else {
    Write-Host "Result   : FAILED (exit $exitCode)" -ForegroundColor Red
}
Write-Host ""

exit $exitCode
