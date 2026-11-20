# scripts/probe_soak.ps1
# Run only the M-02 service probe from scripts/check.ps1, many times.
# Does not run the rest of check.ps1. Does not change probe behavior.
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/probe_soak.ps1 -Rounds 10 -Fresh
# Each round records start, end, exit code, cleaned, netstat for port 8765,
# and the python PID list, before and after the probe.
# A round with cleaned other than True also writes var/probe-soak-fail-<timestamp>.log,
# waits 30 seconds, and samples again. It does not kill any process.
param(
  [int]$Rounds = 10,
  [string]$LogPath = '',
  [switch]$Fresh
)

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Utf8 = New-Object System.Text.UTF8Encoding $false

$CondaRoot = 'G:\BaseWare\Anaconda\envs\k12-qbank'
$CondaPython = Join-Path $CondaRoot 'python.exe'
if (-not (Test-Path -LiteralPath $CondaPython)) {
  Write-Error "conda python missing: $CondaPython"
  exit 2
}
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

function Read-Text([string]$path) {
  [System.IO.File]::ReadAllText((Join-Path $Root $path), $Utf8)
}

$Conf = 'scripts/check.conf'
$ConfMap = @{}
foreach ($line in (Read-Text $Conf) -split "`r?`n") {
  if ($line -match '^\s*([A-Z_]+)\s*=(.*)$') {
    $v = $Matches[2].Trim()
    if ($v -match '^"(.*)"$' -or $v -match "^'(.*)'$") { $v = $Matches[1] }
    $ConfMap[$Matches[1]] = $v
  }
}
function Conf([string]$key, [string]$default) {
  if ($ConfMap.ContainsKey($key)) { $ConfMap[$key] } else { $default }
}

$ServiceCmd = Conf 'SERVICE_CMD' ''
$ServiceSmoke = Conf 'SERVICE_SMOKE_CMD' ''
$ServiceSmokeTimeout = Conf 'SERVICE_SMOKE_TIMEOUT' '5'
$ServiceTimeout = Conf 'SERVICE_READY_TIMEOUT' '5'
$ServiceReady = Conf 'SERVICE_READY_TOKEN' 'READY'
$ServiceHealth = Conf 'SERVICE_HEALTH_URL' ''
if (-not $ServiceCmd) {
  Write-Error 'SERVICE_CMD is empty in scripts/check.conf'
  exit 2
}
if ($Rounds -lt 1) {
  Write-Error 'Rounds must be at least 1'
  exit 2
}

$logDir = Join-Path $Root 'var'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
if (-not $LogPath) {
  $LogPath = Join-Path $logDir ("probe-soak-{0}.log" -f (Get-Date -Format 'yyyyMMdd'))
}
if ($Fresh -and (Test-Path -LiteralPath $LogPath)) {
  Remove-Item -LiteralPath $LogPath -Force
}

function Add-Log([string]$text) {
  [System.IO.File]::AppendAllText($LogPath, ($text.TrimEnd("`r", "`n") + "`n"), $Utf8)
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

function Get-PythonDetail {
  $blocks = New-Object System.Collections.Generic.List[string]
  try {
    $named = @(Get-Process -Name python -IncludeUserName -ErrorAction Stop)
    if ($named.Count -eq 0) {
      $blocks.Add('Get-Process python -IncludeUserName: (none)')
    } else {
      $rows = $named | ForEach-Object {
        'pid={0} user={1} start={2}' -f $_.Id, $_.UserName, $(if ($_.StartTime) { $_.StartTime.ToString('o') } else { '' })
      }
      $blocks.Add(("Get-Process python -IncludeUserName:`n" + ($rows -join "`n")))
    }
  } catch {
    $blocks.Add("Get-Process python -IncludeUserName failed: $($_.Exception.Message)")
    $plain = @(Get-Process -Name python -ErrorAction SilentlyContinue)
    if ($plain.Count -eq 0) {
      $blocks.Add('Get-Process python: (none)')
    } else {
      $rows = $plain | ForEach-Object {
        'pid={0} start={1}' -f $_.Id, $(if ($_.StartTime) { $_.StartTime.ToString('o') } else { '' })
      }
      $blocks.Add(("Get-Process python:`n" + ($rows -join "`n")))
    }
  }
  $cim = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" -ErrorAction SilentlyContinue)
  if ($cim.Count -eq 0) {
    $blocks.Add('Win32_Process python.exe: (none)')
  } else {
    $rows = $cim | ForEach-Object {
      $created = ''
      if ($_.CreationDate) { $created = $_.CreationDate.ToString('o') }
      'pid={0} ppid={1} start={2}' -f $_.ProcessId, $_.ParentProcessId, $created
    }
    $blocks.Add(("Win32_Process python.exe:`n" + ($rows -join "`n")))
  }
  $handle = Get-Command handle.exe -ErrorAction SilentlyContinue
  if ($handle) {
    $handleOut = & handle.exe -accepteula -p python 2>&1 | ForEach-Object { "$_" }
    $blocks.Add(("handle.exe:`n" + ($handleOut -join "`n")))
  } else {
    $blocks.Add('handle.exe: not found')
  }
  return ($blocks -join "`n")
}

function Write-FailEvidence([int]$round, [string]$reason, [string]$stdout) {
  $stamp = Get-Date -Format 'yyyyMMddTHHmmss'
  $failPath = Join-Path $logDir "probe-soak-fail-$stamp.log"
  $head = @(
    "round: $round",
    "reason: $reason",
    "captured_at: $((Get-Date).ToString('o'))",
    'note: no process was killed by this script',
    '--- probe stdout ---',
    $stdout,
    '--- immediate netstat 8765 ---',
    (Get-Netstat8765),
    '--- immediate processes ---',
    (Get-PythonDetail)
  ) -join "`n"
  [System.IO.File]::WriteAllText($failPath, ($head + "`n"), $Utf8)
  Start-Sleep -Seconds 30
  $later = @(
    "--- after 30s at $((Get-Date).ToString('o')) ---",
    '--- netstat 8765 ---',
    (Get-Netstat8765),
    '--- processes ---',
    (Get-PythonDetail),
    ''
  ) -join "`n"
  [System.IO.File]::AppendAllText($failPath, $later, $Utf8)
  return $failPath
}

$listeners = @(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
  $owners = ($listeners | ForEach-Object { $_.OwningProcess }) -join ','
  Write-Error "port 8765 is already listening (pid $owners). Soak not started."
  exit 3
}

$probeArgs = @(
  'scripts/service_probe.py',
  '--command', $ServiceCmd,
  '--timeout', $ServiceTimeout,
  '--ready-token', $ServiceReady,
  '--smoke', $ServiceSmoke,
  '--smoke-timeout', $ServiceSmokeTimeout
)
if ($ServiceHealth) { $probeArgs += @('--health-url', $ServiceHealth) }
$shown = ($probeArgs | ForEach-Object { if ($_ -match '\s') { '"{0}"' -f $_ } else { $_ } }) -join ' '
$headShort = ''
try { $headShort = (& git rev-parse --short HEAD 2>$null) } catch { $headShort = '' }
if (-not $headShort) { $headShort = 'unknown' }
$clearedText = if ($cleared.Count) { $cleared -join ',' } else { '(none)' }

Add-Log '# probe_soak session'
Add-Log ("started: {0}" -f (Get-Date).ToString('o'))
Add-Log "rounds: $Rounds"
Add-Log "head: $headShort"
Add-Log "python: $CondaPython"
Add-Log "cleared_env: $clearedText"
Add-Log "argv: python $shown"
Add-Log ''

$pass = 0
$badExit = 0
$cleanedFalse = 0
for ($i = 1; $i -le $Rounds; $i++) {
  $beforePort = Get-Netstat8765
  $beforePids = Get-PythonPids
  $start = Get-Date
  $probeOut = & python @probeArgs 2>&1
  $exitCode = $LASTEXITCODE
  $end = Get-Date
  $stdout = ''
  if ($null -ne $probeOut) {
    $stdout = (($probeOut | ForEach-Object { "$_" }) -join "`n").TrimEnd()
  }
  $cleaned = '(missing)'
  $found = [regex]::Matches($stdout, 'cleaned=(True|False)')
  if ($found.Count -gt 0) { $cleaned = $found[$found.Count - 1].Groups[1].Value }
  $afterPort = Get-Netstat8765
  $afterPids = Get-PythonPids

  Add-Log ("===== round {0}/{1} =====" -f $i, $Rounds)
  Add-Log ("start: {0}" -f $start.ToString('o'))
  Add-Log ("end: {0}" -f $end.ToString('o'))
  Add-Log "exit_code: $exitCode"
  Add-Log "cleaned: $cleaned"
  Add-Log 'netstat_8765_before:'
  Add-Log $beforePort
  Add-Log 'netstat_8765_after:'
  Add-Log $afterPort
  Add-Log "python_pids_before: $beforePids"
  Add-Log "python_pids_after: $afterPids"
  Add-Log 'probe_stdout:'
  Add-Log $(if ($stdout) { $stdout } else { '(empty)' })

  $failed = ($exitCode -ne 0) -or ($cleaned -ne 'True')
  if ($failed) {
    $badExit++
    if ($cleaned -eq 'False') { $cleanedFalse++ }
    $reason = "exit_code=$exitCode cleaned=$cleaned"
    $failPath = Write-FailEvidence $i $reason $stdout
    Add-Log "fail_log: $failPath"
  } else {
    $pass++
  }
  Add-Log ''
  $seconds = [math]::Round(($end - $start).TotalSeconds, 2)
  Write-Output ("round {0}/{1} exit={2} cleaned={3} {4}s" -f $i, $Rounds, $exitCode, $cleaned, $seconds)
}

Add-Log ("summary rounds={0} pass={1} bad_exit_or_cleaned={2} cleaned_false={3}" -f $Rounds, $pass, $badExit, $cleanedFalse)
Add-Log ("finished: {0}" -f (Get-Date).ToString('o'))
Write-Output ("summary rounds={0} pass={1} bad_exit_or_cleaned={2} cleaned_false={3}" -f $Rounds, $pass, $badExit, $cleanedFalse)
Write-Output "log: $LogPath"
if ($badExit -gt 0) { exit 1 }
exit 0
