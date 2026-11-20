# scripts/probe_unit_soak.ps1
# Repeat the service-probe unit tests. This is the path that reported cleaned=False.
# It does not run the M-02 uvicorn probe from scripts/check.ps1.
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/probe_unit_soak.ps1 -Rounds 10 -Fresh
# Each round records the round number, start, end, and exit code in
# var/probe-unit-soak-YYYYMMDD.log.
# A failing round also writes:
#   var/probe-unit-fail-<round>.log
#   var/probe-unit-fail-<round>.stdout
#   var/probe-unit-fail-<round>.stderr
# This script does not edit the probe and does not kill a leftover process.
param(
  [int]$Rounds = 10,
  [string]$LogPath = '',
  [switch]$Fresh
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Utf8 = New-Object System.Text.UTF8Encoding $false

$CondaPython = 'G:\BaseWare\Anaconda\envs\k12-qbank\python.exe'
if (-not (Test-Path -LiteralPath $CondaPython)) {
  Write-Error "conda python missing: $CondaPython"
  exit 2
}
$CondaRoot = Split-Path -Parent $CondaPython
$env:PATH = "$CondaRoot;$CondaRoot\Scripts;" + $env:PATH

$cleared = @()
foreach ($name in @(
    'K12_PG_DSN', 'K12_ENV', 'K12_FILE_DIR', 'K12_ERROR_WEBHOOK_URL',
    'K12_OPENAPI', 'K12_SYNTH_SECRET', 'PHASE_SLICES'
  )) {
  if (Test-Path "Env:$name") {
    Remove-Item "Env:$name"
    $cleared += $name
  }
}

if ($Rounds -lt 1) {
  Write-Error 'Rounds must be at least 1'
  exit 2
}

$listeners = @(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
  $owners = ($listeners | ForEach-Object { $_.OwningProcess }) -join ','
  Write-Error "port 8765 is already listening (pid $owners). Soak not started."
  exit 3
}

$logDir = Join-Path $Root 'var'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
if (-not $LogPath) {
  $LogPath = Join-Path $logDir ("probe-unit-soak-{0}.log" -f (Get-Date -Format 'yyyyMMdd'))
}
if ($Fresh) {
  if (Test-Path -LiteralPath $LogPath) { Remove-Item -LiteralPath $LogPath -Force }
  Get-ChildItem -LiteralPath $logDir -File -Filter 'probe-unit-fail-*' -ErrorAction SilentlyContinue |
    Remove-Item -Force
}

function Add-Log([string]$text) {
  [System.IO.File]::AppendAllText($LogPath, ($text.TrimEnd("`r", "`n") + "`n"), $Utf8)
}

function Invoke-UnitSuite {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $CondaPython
  $psi.Arguments = '-m unittest tests.test_service_probe -v'
  $psi.WorkingDirectory = $Root
  $psi.UseShellExecute = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
  $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
  $psi.CreateNoWindow = $true
  $proc = New-Object System.Diagnostics.Process
  $proc.StartInfo = $psi
  [void]$proc.Start()
  $outTask = $proc.StandardOutput.ReadToEndAsync()
  $errTask = $proc.StandardError.ReadToEndAsync()
  [void]$proc.WaitForExit()
  return @{
    ExitCode = $proc.ExitCode
    Stdout = $outTask.Result
    Stderr = $errTask.Result
  }
}

function Save-Failure([int]$round, [datetime]$start, [datetime]$end, $result) {
  $base = Join-Path $logDir ("probe-unit-fail-{0}" -f $round)
  $stdoutPath = "$base.stdout"
  $stderrPath = "$base.stderr"
  $logFile = "$base.log"
  $stdout = [string]$result.Stdout
  $stderr = [string]$result.Stderr
  [System.IO.File]::WriteAllText($stdoutPath, $stdout, $Utf8)
  [System.IO.File]::WriteAllText($stderrPath, $stderr, $Utf8)
  $body = @(
    "round: $round",
    ("start: {0}" -f $start.ToString('o')),
    ("end: {0}" -f $end.ToString('o')),
    ("exit_code: {0}" -f $result.ExitCode),
    "stdout_file: $stdoutPath",
    "stderr_file: $stderrPath",
    '--- stdout ---',
    $stdout.TrimEnd(),
    '--- stderr ---',
    $stderr.TrimEnd(),
    ''
  ) -join "`n"
  [System.IO.File]::WriteAllText($logFile, $body, $Utf8)
  return $logFile
}

$headShort = ''
try { $headShort = (& git rev-parse --short HEAD 2>$null) } catch { $headShort = '' }
if (-not $headShort) { $headShort = 'unknown' }
$clearedText = if ($cleared.Count) { $cleared -join ',' } else { '(none)' }

Add-Log '# probe_unit_soak session'
Add-Log ("started: {0}" -f (Get-Date).ToString('o'))
Add-Log "rounds: $Rounds"
Add-Log "head: $headShort"
Add-Log "python: $CondaPython"
Add-Log "cleared_env: $clearedText"
Add-Log "argv: $CondaPython -m unittest tests.test_service_probe -v"
Add-Log ''

$pass = 0
$fail = 0
for ($i = 1; $i -le $Rounds; $i++) {
  $start = Get-Date
  $result = Invoke-UnitSuite
  $end = Get-Date
  $exitCode = $result.ExitCode
  Add-Log ("===== round {0}/{1} =====" -f $i, $Rounds)
  Add-Log ("start: {0}" -f $start.ToString('o'))
  Add-Log ("end: {0}" -f $end.ToString('o'))
  Add-Log "exit_code: $exitCode"
  $seconds = [math]::Round(($end - $start).TotalSeconds, 2)
  if ($exitCode -eq 0) {
    $pass++
    Add-Log 'result: PASS'
  } else {
    $fail++
    $failLog = Save-Failure $i $start $end $result
    Add-Log 'result: FAIL'
    Add-Log "fail_log: $failLog"
    Add-Log ("stdout_file: {0}" -f ($failLog -replace '\.log$', '.stdout'))
    Add-Log ("stderr_file: {0}" -f ($failLog -replace '\.log$', '.stderr'))
    Add-Log 'stopped: first failing round; later rounds were not started'
  }
  Add-Log ''
  Write-Output ("round {0}/{1} exit={2} {3}s" -f $i, $Rounds, $exitCode, $seconds)
  if ($exitCode -ne 0) { break }
}

$done = $pass + $fail
Add-Log ("summary requested={0} completed={1} pass={2} fail={3}" -f $Rounds, $done, $pass, $fail)
Add-Log ("finished: {0}" -f (Get-Date).ToString('o'))
Write-Output ("summary requested={0} completed={1} pass={2} fail={3}" -f $Rounds, $done, $pass, $fail)
Write-Output "log: $LogPath"
if ($fail -gt 0) { exit 1 }
exit 0
