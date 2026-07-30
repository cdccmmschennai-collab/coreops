<#
.SYNOPSIS
    Builds a clean ZIP of the Phase 1 probe for the administrator PC.

.DESCRIPTION
    Copies an explicit WHITELIST of files into a staging directory and zips
    that. Nothing is excluded by pattern matching, because a whitelist cannot
    accidentally let a secret through: if a file is not named below it does not
    reach the archive.

    Never included: .env, .venv\, logs\, probe-output\, *.db, __pycache__\,
    .pytest_cache\, tests\, or any git metadata.

    The build FAILS if .env.example carries a non-empty password, token or
    secret, so a filled-in example file can never be shipped.

.EXAMPLE
    .\package_probe.ps1
#>
[CmdletBinding()]
param(
    # Destination .zip. Defaults to .\dist\CoreOps-EasyTime-Probe.zip
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'

$Root       = $PSScriptRoot
$EnvExample = Join-Path $Root '.env.example'

if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $Root 'dist\CoreOps-EasyTime-Probe.zip'
}

# The complete contents of the archive. Nothing else is copied.
$Whitelist = @(
    'config.py'
    'client.py'
    'schemas.py'
    'exceptions.py'
    'probe.py'
    'requirements.txt'
    'README.md'
    '.env.example'
    'setup_probe.ps1'
    'run_probe.ps1'
)

# Names that must never appear in the archive, checked again after zipping.
$ForbiddenEntryPatterns = @(
    '(^|/)\.env$'
    '(^|/)\.venv/'
    '(^|/)logs/'
    '(^|/)probe-output/'
    '(^|/)dist/'
    '(^|/)__pycache__/'
    '(^|/)\.pytest_cache/'
    '(^|/)\.git'
    '\.db$'
)

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

# -- 1. every whitelisted file must exist ------------------------------------
Write-Step '1. Source files'
$missing = @()
foreach ($name in $Whitelist) {
    $path = Join-Path $Root $name
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        Write-Host ("  [PASS] {0}" -f $name)
    } else {
        Write-Host ("  [FAIL] {0} - missing" -f $name) -ForegroundColor Red
        $missing += $name
    }
}
if ($missing.Count -gt 0) {
    Fail ("Cannot package: missing file(s): " + ($missing -join ', '))
}

# -- 2. .env.example must carry no real secret -------------------------------
Write-Step '2. Secret scan of .env.example'
$violations = @()
$lineNumber = 0
foreach ($line in (Get-Content -LiteralPath $EnvExample)) {
    $lineNumber++
    $trimmed = $line.Trim()
    if ($trimmed -eq '' -or $trimmed.StartsWith('#')) { continue }
    if ($trimmed -notmatch '^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { continue }

    $key   = $Matches[1]
    $value = $Matches[2].Trim().Trim('"').Trim("'")

    if ($key -match '(?i)(PASSWORD|PASSWD|TOKEN|SECRET|API_?KEY)' -and $value -ne '') {
        $violations += "line ${lineNumber}: $key has a non-empty value"
    }
}
if ($violations.Count -gt 0) {
    Write-Host "  A filled-in .env.example must never be shipped:" -ForegroundColor Red
    $violations | ForEach-Object { Write-Host "    - $_" -ForegroundColor Red }
    Fail "Blank the value(s) above in .env.example, or copy your real values into .env instead."
}
Write-Host "  [PASS] no password, token or secret carries a value"

# A real .env sitting next to the script is fine - it is simply not whitelisted -
# but say so out loud so nobody assumes it was packaged.
if (Test-Path -LiteralPath (Join-Path $Root '.env')) {
    Write-Host "  [note] a local .env exists and is NOT included in the archive"
}

# -- 3. stage and compress ---------------------------------------------------
Write-Step '3. Building the archive'
$staging = Join-Path ([System.IO.Path]::GetTempPath()) ("coreops-easytime-probe-" + [System.Guid]::NewGuid().ToString('N'))
$outputDir = Split-Path -Parent $OutputPath

try {
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    foreach ($name in $Whitelist) {
        Copy-Item -LiteralPath (Join-Path $Root $name) -Destination (Join-Path $staging $name) -Force
    }

    if (-not (Test-Path -LiteralPath $outputDir)) {
        New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    }
    if (Test-Path -LiteralPath $OutputPath) {
        Remove-Item -LiteralPath $OutputPath -Force
    }

    # Pass explicit paths (not a wildcard) so the leading-dot .env.example is
    # never skipped by wildcard expansion.
    $stagedFiles = Get-ChildItem -LiteralPath $staging -Force -File | ForEach-Object { $_.FullName }
    Compress-Archive -LiteralPath $stagedFiles -DestinationPath $OutputPath -CompressionLevel Optimal
    Write-Host "  [PASS] archive written"
} finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# -- 4. verify what actually landed in the zip -------------------------------
Write-Step '4. Archive verification'
Add-Type -AssemblyName System.IO.Compression.FileSystem | Out-Null
$zip = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $OutputPath).Path)
try {
    $entries = @($zip.Entries | ForEach-Object { $_.FullName })
} finally {
    $zip.Dispose()
}

$bad = @()
foreach ($entry in $entries) {
    $normalized = $entry -replace '\\', '/'
    foreach ($pattern in $ForbiddenEntryPatterns) {
        if ($normalized -match $pattern) { $bad += $entry; break }
    }
}
if ($bad.Count -gt 0) {
    Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
    Fail ("Archive deleted - it contained excluded entries: " + (($bad | Select-Object -Unique) -join ', '))
}

$unexpected = $entries | Where-Object { $Whitelist -notcontains $_ }
if ($unexpected) {
    Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
    Fail ("Archive deleted - unexpected entries: " + ($unexpected -join ', '))
}
$absent = $Whitelist | Where-Object { $entries -notcontains $_ }
if ($absent) {
    Remove-Item -LiteralPath $OutputPath -Force -ErrorAction SilentlyContinue
    Fail ("Archive deleted - expected entries are missing: " + ($absent -join ', '))
}

foreach ($entry in ($entries | Sort-Object)) {
    Write-Host "  [PASS] $entry"
}

# -- 5. report ---------------------------------------------------------------
$item = Get-Item -LiteralPath $OutputPath
$hash = Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256

Write-Step 'Package'
Write-Host "  Path    : $($item.FullName)"
Write-Host "  Size    : $([math]::Round($item.Length / 1KB, 1)) KB"
Write-Host "  Files   : $($entries.Count)"
Write-Host "  SHA-256 : $($hash.Hash)"
Write-Host ""
Write-Host "  Send this ZIP to the administrator PC. It contains NO credentials:" -ForegroundColor Green
Write-Host "  the admin copies .env.example to .env and types them in there." -ForegroundColor Green
Write-Host ""
exit 0
