# scripts/check.ps1 - Windows PowerShell / PowerShell 7 version of scripts/check.
# Same checks, same IDs (M-xx, R-x from project-essentials MANDATORY.md), same scripts/check.conf.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/check.ps1 [-Ci] [-Fast] [-IfChanged]
#        (--ci, --fast, --if-changed also work, as in scripts/check)
# Exit code: 0 = no MUST failed. 1 = at least one MUST failed (report "not met").
# Do not weaken this file to make it pass. Changing a gate needs the user's OK.
# This file is ASCII on purpose (Windows PowerShell 5.1 reads BOM-less files as ANSI);
# Chinese words are written as \uXXXX regex escapes.
param([switch]$Ci, [switch]$Fast, [switch]$IfChanged, [Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)
foreach ($a in $Rest) {
  switch ($a) { '--ci' { $Ci = $true } '--fast' { $Fast = $true } '--if-changed' { $IfChanged = $true } default { Write-Error "scripts/check.ps1: unknown option $a"; exit 1 } }
}

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Conf = 'scripts/check.conf'
$Utf8 = New-Object System.Text.UTF8Encoding($false)
if ($env:CI -eq 'true') { $Ci = $true }
$OnWindows = ($PSVersionTable.PSVersion.Major -lt 6) -or $IsWindows

function Read-Text($path) { [System.IO.File]::ReadAllText((Join-Path $Root $path), $Utf8) }

# ---------- settings ----------
$ConfMap = @{}
if (Test-Path $Conf) {
  foreach ($line in (Read-Text $Conf) -split "`r?`n") {
    if ($line -match '^\s*([A-Z_]+)\s*=(.*)$') {
      $v = $Matches[2].Trim()
      if ($v -match '^"(.*)"$' -or $v -match "^'(.*)'$") { $v = $Matches[1] }
      $ConfMap[$Matches[1]] = $v
    }
  }
}
function Conf($key, $default) { if ($ConfMap.ContainsKey($key)) { $ConfMap[$key] } else { $default } }

$Tier = Conf 'TIER' ''
$TierNote = ''
if ($Tier -notin @('demo', 'tracer', 'long')) { $TierNote = "tier not confirmed (TIER='$Tier'), using tracer"; $Tier = 'tracer' }
$RealData = Conf 'REAL_DATA' 'no'; $Public = Conf 'PUBLIC' 'no'
$RunCmd = Conf 'RUN_CMD' ''; $TestCmd = Conf 'TEST_CMD' ''; $InstallCmd = Conf 'INSTALL_CMD' ''
$AppDirs = (Conf 'APP_DIRS' '.') -split '\s+' | Where-Object { $_ }
$LintCmd = Conf 'LINT_CMD' ''; $LogCheckCmd = Conf 'LOG_CHECK_CMD' ''
$CoreDirs = (Conf 'CORE_DIRS' '') -split '\s+' | Where-Object { $_ }

$GitExe = (Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
function Invoke-Git { if ($GitExe) { & $GitExe @args 2>$null } else { $global:LASTEXITCODE = 127 } }
$InGit = ((Invoke-Git rev-parse --is-inside-work-tree) -eq 'true')
$HasHead = $false
if ($InGit) { Invoke-Git rev-parse --verify -q HEAD | Out-Null; $HasHead = ($LASTEXITCODE -eq 0) }

# ---------- fingerprint (for agent hooks) ----------
function Get-Fingerprint {
  $parts = @()
  $parts += (Invoke-Git rev-parse HEAD)
  $parts += ((Invoke-Git diff HEAD --binary) -join "`n")
  foreach ($f in (Invoke-Git ls-files -o --exclude-standard)) { if (Test-Path -LiteralPath $f -PathType Leaf) { $parts += "$f $(Invoke-Git hash-object -- $f)" } }
  if (Test-Path $Conf) { $parts += (Read-Text $Conf) }
  $bytes = $Utf8.GetBytes(($parts -join "`n"))
  $sha = [System.Security.Cryptography.SHA256]::Create()
  ([System.BitConverter]::ToString($sha.ComputeHash($bytes))) -replace '-', ''
}
$FpFile = $null
if ($InGit) { $FpFile = Join-Path (Invoke-Git rev-parse --git-dir) 'check-last-pass-ps1' }
if ($IfChanged -and $FpFile -and (Test-Path $FpFile)) {
  if ((Get-Fingerprint) -eq ((Get-Content $FpFile -Raw).Trim())) {
    Write-Output 'scripts/check: no change since the last full PASS; skipped.'; exit 0
  }
}

# ---------- reporting ----------
$Waived = @()
if (Test-Path 'docs/WAIVERS.md') {
  foreach ($line in (Read-Text 'docs/WAIVERS.md') -split "`r?`n") {
    if ($line -match '^\|\s*W-\d+' -and $line -match '\u6709\u6548|[Aa]ctive' -and $line -notmatch '\u5DF2\u5230\u671F|\u5DF2\u8865\u9F50|[Ee]xpired') {
      $Waived += ([regex]::Matches($line, 'M-\d{2}') | ForEach-Object { $_.Value })
    }
  }
}
$NotWaivable = 'M-03'  # red line R-1
$script:MustFailed = @(); $script:ShouldFailed = @()
function Report($id, $level, $status, $text) {
  if ($status -eq 'FAIL') {
    if ($level -eq 'SHOULD') { $status = 'WARN'; $script:ShouldFailed += $id }
    elseif ($level -eq 'MUST' -and $Waived -contains $id -and $id -ne $NotWaivable) { $status = 'WAIVED'; $text = "$text (waived in docs/WAIVERS.md)" }
    elseif ($level -eq 'MUST' -and $script:MustFailed -notcontains $id) { $script:MustFailed += $id }
  }
  Write-Output ('{0,-5} {1,-6} {2,-6} {3}' -f $id, $level, $status, $text)
}
function ByTier($demo, $tracer, $long) { switch ($Tier) { 'demo' { $demo } 'tracer' { $tracer } default { $long } } }
$script:LastOut = ''
function Invoke-Configured($cmd) {
  if ($OnWindows) { $out = & cmd.exe /d /c $cmd 2>&1 } else { $out = & /bin/sh -c $cmd 2>&1 }
  $rc = $LASTEXITCODE
  $script:LastOut = (($out | Select-Object -Last 15) -join ' | ')
  return ($rc -eq 0)
}
function List-Files {
  if ($InGit) { Invoke-Git ls-files -co --exclude-standard }
  else { Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch '[\\/](\.git|node_modules)[\\/]' } | ForEach-Object { Resolve-Path -Relative $_.FullName } }
}

$yn = @{ $true = 'yes'; $false = 'no' }
Write-Output "scripts/check.ps1  tier=$Tier  [D]=$RealData  [P]=$Public  ci=$($yn[[bool]$Ci])  fast=$($yn[[bool]$Fast])"
if ($TierNote) { Write-Output "NOTE: $TierNote" }
if (-not (Test-Path $Conf)) { Write-Output "NOTE: $Conf not found; using defaults." }
Write-Output 'ID    LEVEL  STATUS DETAIL'

# ---------- M-01 ----------
if (-not $InGit) { Report 'M-01' 'MUST' 'FAIL' 'not a git repository. Fix: git init, then commit each small working step.' }
elseif (-not $HasHead -and (Invoke-Git diff --cached --name-only)) { Report 'M-01' 'MUST' 'PASS' 'first commit in progress (files staged)' }
elseif (-not $HasHead) { Report 'M-01' 'MUST' 'FAIL' 'no commit yet. Fix: commit the first working step.' }
else {
  Report 'M-01' 'MUST' 'PASS' "git repo, HEAD $(Invoke-Git rev-parse --short HEAD)"
  if ($Tier -eq 'long') { Report 'M-01' 'MUST' 'MANUAL' 'main protected (PR only, required check): not checkable here. See recipes/mandatory-gates.md.' }
}

# ---------- M-02 ----------
if (-not (Test-Path 'README.md')) { Report 'M-02' 'MUST' 'FAIL' 'README.md missing. Fix: add it with what this is and the run command.' }
elseif (-not $RunCmd) { Report 'M-02' 'MUST' 'FAIL' "RUN_CMD is empty in $Conf. Fix: set the one command that starts the app." }
else {
  $readme = Read-Text 'README.md'
  $first = ($readme -split "`r?`n" | Where-Object { $_.Trim() } | Select-Object -First 1)
  $words = switch ($Tier) { 'demo' { '\u539F\u578B|prototype|demo' } 'tracer' { '\u66F3\u5149\u5F39|tracer' } default { '' } }
  if (-not $readme.Contains($RunCmd)) { Report 'M-02' 'MUST' 'FAIL' "README.md does not show the run command '$RunCmd'. Fix: add it." }
  elseif ($TestCmd -and -not $readme.Contains($TestCmd)) { Report 'M-02' 'MUST' 'FAIL' "README.md does not show the test command '$TestCmd'. Fix: add it." }
  elseif ($words -and ($first -notmatch "(?i)$words")) { Report 'M-02' 'MUST' 'FAIL' "README first line must name the tier ($Tier)." }
  else { Report 'M-02' 'MUST' 'PASS' "README.md shows '$RunCmd'" }
}

# ---------- M-03 / R-1 .env hygiene ----------
if ($InGit) {
  $trackedEnv = Invoke-Git ls-files | Where-Object { $_ -match '(^|/)\.env(\.[^/]*)?$' -and $_ -notmatch '\.env\.(example|sample|template|dist)$' }
  Invoke-Git check-ignore -q --no-index .env | Out-Null; $envIgnored = ($LASTEXITCODE -eq 0)
  if ($trackedEnv) { Report 'M-03' 'MUST' 'FAIL' "R-1: env file tracked: $($trackedEnv -join ' '). Fix: git rm --cached <file>, add to .gitignore, rotate every key in it." }
  elseif (-not $envIgnored) { Report 'M-03' 'MUST' 'FAIL' "R-1: .gitignore does not ignore .env. Fix: add a line '.env' to .gitignore." }
  elseif (-not (Test-Path '.env.example')) { Report 'M-03' 'MUST' 'FAIL' '.env.example missing. Fix: add it with placeholder values only.' }
  else { Report 'M-03' 'MUST' 'PASS' '.env ignored and not tracked; .env.example present' }
}

# ---------- M-03 / R-1 secret scan ----------
$patKeys = '-----BEGIN ([A-Z]+ )*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|sk-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}'
$patAssign = '(?i)(password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)["'']?\s*[:=]\s*["''][^"''\s<>${}]{12,}["'']'
$skip = '(?i)example|placeholder|changeme|your[_-]|xxxx|dummy|<[a-z_]+>'
$hits = @()
foreach ($f in (List-Files)) {
  if ($f -match '(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|uv\.lock|Cargo\.lock|go\.sum)$') { continue }
  if (-not (Test-Path -LiteralPath $f -PathType Leaf)) { continue }
  $bytes = [System.IO.File]::ReadAllBytes((Join-Path $Root $f))
  if ($bytes -contains 0) { continue }
  $n = 0
  foreach ($line in ($Utf8.GetString($bytes) -split "`n")) {
    $n++
    if (($line -match $patKeys -or $line -match $patAssign) -and $line -notmatch $skip) { $hits += "${f}:$n" }
  }
  if ($hits.Count -ge 10) { break }
}
if ($hits) { Report 'M-03' 'MUST' 'FAIL' "R-1: possible secret at $($hits -join ' '). Fix: move it to .env (ignored), read it from the environment, rotate the key." }
else { Report 'M-03' 'MUST' 'PASS' 'built-in secret patterns: no match' }
if ((Get-Command gitleaks -ErrorAction SilentlyContinue) -and $InGit) {
  $gl = @()
  $glArgs = @('--redact', '--no-banner', '--log-level', 'error')
  if ($HasHead) { & gitleaks git @glArgs . *> $null; if ($LASTEXITCODE -ne 0) { $gl += 'history' } }
  & gitleaks git --pre-commit @glArgs . *> $null; if ($LASTEXITCODE -ne 0) { $gl += 'working-tree' }
  & gitleaks git --pre-commit --staged @glArgs . *> $null; if ($LASTEXITCODE -ne 0) { $gl += 'staged' }
  $untracked = @(Invoke-Git ls-files -o --exclude-standard)
  if ($untracked.Count -gt 0) {
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
    foreach ($f in $untracked) {
      if (Test-Path -LiteralPath $f -PathType Leaf) {
        $dest = Join-Path $tmp $f; New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
        Copy-Item -LiteralPath $f -Destination $dest
      }
    }
    & gitleaks dir @glArgs $tmp *> $null; if ($LASTEXITCODE -ne 0) { $gl += 'untracked' }
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
  }
  if ($gl) { Report 'M-03' 'MUST' 'FAIL' "R-1: gitleaks found secrets in: $($gl -join ' '). See: gitleaks git -v --redact . Fix: remove and rotate the key." }
  else { Report 'M-03' 'MUST' 'PASS' 'gitleaks: history, staged, working tree, untracked clean' }
} else {
  Report 'M-03' (ByTier 'SHOULD' 'MUST' 'MUST') 'FAIL' 'gitleaks not installed. Fix: install it (https://github.com/gitleaks/gitleaks#installing) and rerun.'
}

# ---------- M-09 lockfiles ----------
$script:SawManifest = $false
function Test-Tracked($p) { if (-not $InGit) { return $false }; Invoke-Git ls-files --error-unmatch -- $p | Out-Null; $LASTEXITCODE -eq 0 }
function Check-Lock($dir, $manifest, [string[]]$locks) {
  if (-not (Test-Path (Join-Path $dir $manifest))) { return }
  $script:SawManifest = $true
  foreach ($lf in $locks) {
    $p = (Join-Path $dir $lf) -replace '\\', '/'
    if (Test-Path $p) {
      if (Test-Tracked $p) { Report 'M-09' 'MUST' 'PASS' "$dir/$manifest -> $p committed" }
      else { Report 'M-09' 'MUST' 'FAIL' "$p exists but is not committed. Fix: git add $p" }
      return
    }
  }
  Report 'M-09' 'MUST' 'FAIL' "$dir/$manifest has no lockfile ($($locks -join ' ')). Fix: run the install once, commit the lockfile."
}
foreach ($d in $AppDirs) {
  $d = $d.TrimEnd('/')
  Check-Lock $d 'package.json' @('package-lock.json', 'npm-shrinkwrap.json', 'pnpm-lock.yaml', 'yarn.lock', 'bun.lock', 'bun.lockb')
  Check-Lock $d 'pyproject.toml' @('uv.lock', 'poetry.lock', 'pdm.lock', 'Pipfile.lock', 'pylock.toml', 'requirements.txt')
  Check-Lock $d 'Pipfile' @('Pipfile.lock')
  Check-Lock $d 'Cargo.toml' @('Cargo.lock')
  Check-Lock $d 'Gemfile' @('Gemfile.lock')
  Check-Lock $d 'composer.json' @('composer.lock')
  Check-Lock $d 'pubspec.yaml' @('pubspec.lock')
  Check-Lock $d 'Package.swift' @('Package.resolved')
  Check-Lock $d 'Podfile' @('Podfile.lock')
  $gomod = Join-Path $d 'go.mod'
  if ((Test-Path $gomod) -and ((Read-Text $gomod) -match '(?m)^require')) { Check-Lock $d 'go.mod' @('go.sum') }
  $req = Join-Path $d 'requirements.txt'
  if ((Test-Path $req) -and -not (Test-Path (Join-Path $d 'pyproject.toml'))) {
    $script:SawManifest = $true
    $loose = (Read-Text $req) -split "`r?`n" | Where-Object { $_ -notmatch '^\s*(#|-|$)' -and $_ -notmatch '==|\s@\s' } | Select-Object -First 3
    if ($loose) { Report 'M-09' 'MUST' 'FAIL' "$req has unpinned lines: $($loose -join ' '). Fix: pin with ==." }
    elseif (Test-Tracked ($req -replace '\\', '/')) { Report 'M-09' 'MUST' 'PASS' "$req fully pinned and committed" }
    else { Report 'M-09' 'MUST' 'FAIL' "$req not committed. Fix: git add it." }
  }
  if ((Test-Path (Join-Path $d 'build.gradle')) -or (Test-Path (Join-Path $d 'build.gradle.kts'))) {
    $script:SawManifest = $true
    Report 'M-09' 'SHOULD' 'FAIL' "${d}: Gradle has no default lockfile. Pin exact versions; consider Gradle dependency locking."
  }
}
if (-not $script:SawManifest) { Report 'M-09' 'MUST' 'N/A' "no dependency manifest found in APP_DIRS ($($AppDirs -join ' '))" }
if ($script:SawManifest -and $Tier -ne 'demo') {
  if (-not $InstallCmd) { Report 'M-09' 'MUST' 'FAIL' "INSTALL_CMD empty. Fix: set a lockfile install command in $Conf (e.g. npm ci)." }
  elseif ($InstallCmd -match '(^|[;&|]\s*)npm (install|i)(\s|$)') { Report 'M-09' 'MUST' 'FAIL' "INSTALL_CMD uses 'npm install', which can change the lockfile. Fix: use 'npm ci'." }
  elseif ($InstallCmd -match '(^|\s)(yarn|pnpm)( install)?(\s|$)' -and $InstallCmd -notmatch '--frozen-lockfile|--immutable') { Report 'M-09' 'MUST' 'FAIL' 'INSTALL_CMD for yarn/pnpm must use --frozen-lockfile or --immutable.' }
  elseif ($InstallCmd -match 'uv sync' -and $InstallCmd -notmatch '--locked|--frozen') { Report 'M-09' 'MUST' 'FAIL' "INSTALL_CMD 'uv sync' must use --locked (or --frozen)." }
}
if ($Ci -and -not $Fast -and $InstallCmd) {
  if (Invoke-Configured $InstallCmd) { Report 'M-09' (ByTier 'SHOULD' 'MUST' 'MUST') 'PASS' "CI install from lockfile: '$InstallCmd' exit 0" }
  else { Report 'M-09' (ByTier 'SHOULD' 'MUST' 'MUST') 'FAIL' "'$InstallCmd' failed: $script:LastOut" }
}

# ---------- M-05 no swallowed errors ----------
$emptyPat = '(catch\s*(\([^()]*\))?\s*\{\s*\}|\.catch\(\s*\(\s*[^()]*\)\s*=>\s*\{\s*\}\s*\)|except\b[^:\n]*:[ \t]*(#[^\n]*)?\r?\n?[ \t]*pass\b|if\s+err\s*!=\s*nil\s*\{\s*\})'
$empties = @()
foreach ($f in (List-Files | Where-Object { $_ -match '\.(js|jsx|ts|tsx|mjs|cjs|vue|svelte|java|kt|kts|cs|dart|swift|php|py|go)$' })) {
  if (-not (Test-Path -LiteralPath $f -PathType Leaf)) { continue }
  $text = Read-Text $f
  foreach ($m in [regex]::Matches($text, $emptyPat)) {
    $line = ($text.Substring(0, $m.Index) -split "`n").Count
    $empties += "${f}:$line"
  }
  if ($empties.Count -ge 10) { break }
}
if ($empties) { Report 'M-05' 'MUST' 'FAIL' "swallowed error (empty catch / except: pass / empty err branch) at: $($empties -join ' '). Fix: log it once with context and rethrow or show the user a message." }
else { Report 'M-05' 'MUST' 'PASS' 'no empty catch / except-pass / empty err branch found' }

# ---------- M-04 logging rules ----------
if ($CoreDirs) {
  $bare = @()
  $printPat = '(^|[^.\w])(console\.(log|debug|info|warn|error)|print|println|System\.out\.print(ln)?|fmt\.Print(ln|f)?)\('
  foreach ($cdir in $CoreDirs) {
    if (-not (Test-Path $cdir -PathType Container)) { continue }
    foreach ($file in (Get-ChildItem -Recurse -File $cdir)) {
      $n = 0
      foreach ($line in ([System.IO.File]::ReadAllText($file.FullName, $Utf8) -split "`n")) { $n++; if ($line -match $printPat) { $bare += "$(Resolve-Path -Relative $file.FullName):$n" } }
    }
  }
  if ($bare) { Report 'M-04' 'MUST' 'FAIL' "bare print in core: $(($bare | Select-Object -First 5) -join ' '). Fix: use the injected logger with event and request_id." }
  else { Report 'M-04' 'MUST' 'PASS' "no bare print / console.log in CORE_DIRS ($($CoreDirs -join ' '))" }
}
if (-not $Fast) {
  if ($LogCheckCmd) {
    if (Invoke-Configured $LogCheckCmd) { Report 'M-04' 'MUST' 'PASS' "'$LogCheckCmd' exit 0" } else { Report 'M-04' 'MUST' 'FAIL' "'$LogCheckCmd' failed: $script:LastOut" }
  } elseif ($Tier -eq 'long') { Report 'M-04' 'MUST' 'FAIL' 'LOG_CHECK_CMD empty. Long tier: logging rules that a machine can check must run here (recipes/logging.md).' }
  if ($LintCmd) {
    if (Invoke-Configured $LintCmd) { Report 'LINT' 'MUST' 'PASS' "'$LintCmd' exit 0" } else { Report 'LINT' 'MUST' 'FAIL' "'$LintCmd' failed: $script:LastOut" }
  }
}

# ---------- M-06 tests ----------
if (-not $Fast) {
  $tl = ByTier 'SHOULD' 'MUST' 'MUST'
  if (-not $TestCmd) { Report 'M-06' $tl 'FAIL' 'TEST_CMD empty. Fix: add one repeatable smoke check and set TEST_CMD.' }
  elseif (Invoke-Configured $TestCmd) { Report 'M-06' $tl 'PASS' "'$TestCmd' exit 0" }
  # Every tier: a test that exists and fails blocks. Only "no tests at all" is SHOULD on demo.
  else { Report 'M-06' 'MUST' 'FAIL' "'$TestCmd' failed: $script:LastOut" }
}

# ---------- M-08 CI ----------
$ciLevel = ByTier 'SHOULD' 'MUST' 'MUST'
$ciHit = @()
foreach ($f in @(Get-ChildItem -File -Path '.github/workflows' -Include '*.yml', '*.yaml' -Recurse -ErrorAction SilentlyContinue) + @(Get-Item '.gitlab-ci.yml' -ErrorAction SilentlyContinue)) {
  if ($f -and ((Read-Text (Resolve-Path -Relative $f.FullName)) -match 'scripts/check')) { $ciHit += (Resolve-Path -Relative $f.FullName) }
}
if ($ciHit) { Report 'M-08' $ciLevel 'PASS' "CI config runs scripts/check: $($ciHit -join ' ')" }
else { Report 'M-08' $ciLevel 'FAIL' 'no CI workflow runs scripts/check. Fix: copy .github/workflows/ci.yml from the template.' }
if ($Tier -eq 'long') { Report 'M-08' 'MUST' 'MANUAL' 'CI must be a required status check on main: not checkable here (recipes/mandatory-gates.md).' }

Write-Output 'MANUAL: M-07 review, M-10 security (if [P]), M-11 data safety (if [D]), M-12 docs, M-13/M-14 release items -> gate table (MANDATORY.md section 6).'
if ($RealData -eq 'yes') { Write-Output 'MANUAL: [D]=yes -> R-2: no irreversible operation on real data without a backup.' }

if ($script:MustFailed) {
  $sf = if ($script:ShouldFailed) { "  SHOULD failed: $($script:ShouldFailed -join ' ')" } else { '' }
  Write-Output "RESULT: NOT MET (MUST failed: $($script:MustFailed -join ' '))$sf"
  Write-Output 'Do not say done, do not merge. Fix the FAIL lines, or ask the user; a waiver counts only if the user says it and it is in docs/WAIVERS.md (R-1/M-03 cannot be waived).'
  exit 1
}
$sf = if ($script:ShouldFailed) { "  SHOULD failed: $($script:ShouldFailed -join ' ')" } else { '' }
Write-Output "RESULT: PASS (all MUST items this script can check)$sf"
Write-Output 'MANUAL lines still need evidence in the gate table.'
if (-not $Fast -and $FpFile) { Set-Content -Path $FpFile -Value (Get-Fingerprint) -Encoding ascii }
exit 0
