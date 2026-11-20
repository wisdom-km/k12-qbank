# scripts/probe_mixed_soak.ps1
# One round is a full scripts/check.ps1, then the service-probe unit tests,
# then a snapshot of port 8765 and python processes.
# check.ps1 is invoked with no extra switches, so its service timeout stays
# at the value in scripts/check.conf.
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/probe_mixed_soak.ps1 -Rounds 20 -Fresh
# Summary: var/probe-mixed-soak-YYYYMMDD.log
# A failing round also writes:
#   var/probe-mixed-<round>.log
#   var/probe-mixed-<round>.stdout
#   var/probe-mixed-<round>.stderr
# This script does not edit the probe and does not kill a leftover process.
param(
  [int]$Rounds = 20,
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
  $LogPath = Join-Path $logDir ("probe-mixed-soak-{0}.log" -f (Get-Date -Format 'yyyyMMdd'))
}
if ($Fresh) {
  if (Test-Path -LiteralPath $LogPath) { Remove-Item -LiteralPath $LogPath -Force }
  Get-ChildItem -LiteralPath $logDir -File -Filter 'probe-mixed-*' -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notlike 'probe-mixed-soak-*' } |
    Remove-Item -Force
}

function Add-Log([string]$text) {
  [System.IO.File]::AppendAllText($LogPath, ($text.TrimEnd("`r", "`n") + "`n"), $Utf8)
}

function Invoke-Captured([string]$file, [string]$arguments) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $file
  $psi.Arguments = $arguments
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
    Stdout = [string]$outTask.Result
    Stderr = [string]$errTask.Result
  }
}

function Get-Netstat8765 {
  $lines = @(netstat -ano | Select-String -Pattern ':8765(\s|$)')
  if ($lines.Count -eq 0) { return '(none)' }
  return (($lines | ForEach-Object { $_.Line.Trim() }) -join "`n")
}

function Get-PythonPids {
  $procs = @(Get-Process -Name python -ErrorAction SilentlyContinue)
  if ($procs.Count -eq 0) { return '(none)' }
  return (($procs | ForEach-Object { $_.Id }) -join ',')
}

function Save-Failure([int]$round, [datetime]$start, [datetime]$end, [string]$step, $checkResult, $unitResult, [string]$netstat, [string]$pythonPids) {
  $base = Join-Path $logDir ("probe-mixed-{0}" -f $round)
  $stdoutPath = "$base.stdout"
  $stderrPath = "$base.stderr"
  $logFile = "$base.log"
  $stdout = "===== check.ps1 stdout =====`n"
  $stderr = "===== check.ps1 stderr =====`n"
  if ($null -ne $checkResult) {
    $stdout += [string]$checkResult.Stdout
    $stderr += [string]$checkResult.Stderr
  }
  $stdout += "`n===== unittest stdout =====`n"
  $stderr += "`n===== unittest stderr =====`n"
  if ($null -ne $unitResult) {
    $stdout += [string]$unitResult.Stdout
    $stderr += [string]$unitResult.Stderr
  }
  [System.IO.File]::WriteAllText($stdoutPath, $stdout, $Utf8)
  [System.IO.File]::WriteAllText($stderrPath, $stderr, $Utf8)
  $checkExit = if ($null -ne $checkResult) { $checkResult.ExitCode } else { 'not-run' }
  $unitExit = if ($null -ne $unitResult) { $unitResult.ExitCode } else { 'not-run' }
  $body = @(
    "round: $round",
    "failed_step: $step",
    ("start: {0}" -f $start.ToString('o')),
    ("end: {0}" -f $end.ToString('o')),
    "check_exit: $checkExit",
    "unit_exit: $unitExit",
    "stdout_file: $stdoutPath",
    "stderr_file: $stderrPath",
    '--- netstat 8765 ---',
    $netstat,
    "python_pids: $pythonPids",
    ''
  ) -join "`n"
  [System.IO.File]::WriteAllText($logFile, $body, $Utf8)
  return $logFile
}

$headShort = ''
try { $headShort = (& git rev-parse --short HEAD 2>$null) } catch { $headShort = '' }
if (-not $headShort) { $headShort = 'unknown' }
$clearedText = if ($cleared.Count) { $cleared -join ',' } else { '(none)' }
$pwsh = (Get-Process -Id $PID).Path
$checkScript = Join-Path $Root 'scripts\check.ps1'

Add-Log '# probe_mixed_soak session'
Add-Log ("started: {0}" -f (Get-Date).ToString('o'))
Add-Log "rounds: $Rounds"
Add-Log "head: $headShort"
Add-Log "python: $CondaPython"
Add-Log "cleared_env: $clearedText"
Add-Log "step1: $pwsh -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts/check.ps1"
Add-Log "step2: $CondaPython -m unittest tests.test_service_probe -v"
Add-Log 'step3: netstat 8765, python pids, elapsed'
Add-Log ''

$pass = 0
$fail = 0
for ($i = 1; $i -le $Rounds; $i++) {
  $start = Get-Date
  $checkResult = Invoke-Captured $pwsh "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$checkScript`""
  $unitResult = $null
  $failedStep = ''
  if ($checkResult.ExitCode -ne 0) {
    $failedStep = 'check.ps1'
  } else {
    $unitResult = Invoke-Captured $CondaPython '-m unittest tests.test_service_probe -v'
    if ($unitResult.ExitCode -ne 0) { $failedStep = 'unittest' }
  }
  $end = Get-Date
  $netstat = Get-Netstat8765
  $pythonPids = Get-PythonPids
  $seconds = [math]::Round(($end - $start).TotalSeconds, 2)
  $unitExitText = if ($null -ne $unitResult) { [string]$unitResult.ExitCode } else { 'not-run' }

  Add-Log ("===== round {0}/{1} =====" -f $i, $Rounds)
  Add-Log ("start: {0}" -f $start.ToString('o'))
  Add-Log ("end: {0}" -f $end.ToString('o'))
  Add-Log ("check_exit: {0}" -f $checkResult.ExitCode)
  Add-Log "unit_exit: $unitExitText"
  Add-Log "elapsed_s: $seconds"
  Add-Log 'netstat_8765:'
  Add-Log $netstat
  Add-Log "python_pids: $pythonPids"
  if ($failedStep) {
    $fail++
    $failLog = Save-Failure $i $start $end $failedStep $checkResult $unitResult $netstat $pythonPids
    Add-Log 'result: FAIL'
    Add-Log "failed_step: $failedStep"
    Add-Log "fail_log: $failLog"
    Add-Log ("stdout_file: {0}" -f ($failLog -replace '\.log$', '.stdout'))
    Add-Log ("stderr_file: {0}" -f ($failLog -replace '\.log$', '.stderr'))
    Add-Log 'stopped: first failing round; later rounds were not started'
  } else {
    $pass++
    Add-Log 'result: PASS'
  }
  Add-Log ''
  Write-Output ("round {0}/{1} check={2} unit={3} {4}s" -f $i, $Rounds, $checkResult.ExitCode, $unitExitText, $seconds)
  if ($failedStep) { break }
}

Add-Log ("summary rounds={0} pass={1} fail={2}" -f $Rounds, $pass, $fail)
Add-Log ("finished: {0}" -f (Get-Date).ToString('o'))
Write-Output ("summary rounds={0} pass={1} fail={2}" -f $Rounds, $pass, $fail)
Write-Output "log: $LogPath"
if ($fail -gt 0) { exit 1 }
exit 0
