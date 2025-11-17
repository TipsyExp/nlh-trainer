<#
.SYNOPSIS
  Helper to build/install the OMPEval native extension via scikit-build-core on Windows/PowerShell.
  Works in regular Windows PowerShell or PowerShell 7. For Windows without a C++ toolchain,
  prefer WSL or fall back to the pure-Python eval7 backend.

.DESCRIPTION
  You can:
    - Install the extension into the current virtual environment
    - Build a wheel (no install), writing it to ./dist or a custom directory
    - Do editable installs for local dev
    - Clean prior build artifacts

.PARAMETER Wheel
  Build a wheel only (no install). Writes to ./dist by default, override with -Out.

.PARAMETER Editable
  Do an editable install (pip install -e).

.PARAMETER Clean
  Remove build artifacts before building.

.PARAMETER Out
  Output directory for wheels when -Wheel is specified (default: repo_root/dist).

.EXAMPLES
  # Install the extension into the current environment
  .\scripts\build_ompeval.ps1

  # Editable install for local dev
  .\scripts\build_ompeval.ps1 -Editable

  # Build a wheel (no install), write to .\out\
  .\scripts\build_ompeval.ps1 -Wheel -Out .\out

  # Clean then build/install
  .\scripts\build_ompeval.ps1 -Clean
#>

[CmdletBinding()]
param(
  [switch]$Wheel,
  [switch]$Editable,
  [switch]$Clean,
  [string]$Out
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Info($msg) { Write-Host "[ompeval] $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "[ompeval] $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "[ompeval] $msg" -ForegroundColor Red }

function Resolve-RepoRoot {
  param (
    [string]$ScriptDir
  )
  try {
    $gitTop = & git -C $ScriptDir rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -eq 0 -and $gitTop) {
      return (Resolve-Path $gitTop).Path
    }
  } catch { }
  return (Resolve-Path (Join-Path $ScriptDir '..')).Path
}

function Resolve-Python {
  # Prefer 'python' if present, else try 'py -3', else 'py'
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) { return $python.Source }

  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    # Try -3 first
    try {
      & $py.Source -3 -c "import sys; print(sys.version)" *> $null
      if ($LASTEXITCODE -eq 0) { return "$($py.Source) -3" }
    } catch { }
    return $py.Source
  }

  throw "Python not found in PATH. Install Python and ensure 'python' or 'py' is available."
}

function Exec([string]$exe, [string]$args) {
  Write-Info "$exe $args"
  & $exe $args
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code $LASTEXITCODE: $exe $args"
  }
}

# --- Resolve paths ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir   = Resolve-RepoRoot -ScriptDir $ScriptDir
$PkgDir    = Join-Path $RootDir 'backend/native/ompeval'

if (-not $Out) {
  $Out = Join-Path $RootDir 'dist'
}

# --- Sanity checks ---
$PyCmd = Resolve-Python
Write-Info "Using Python launcher: $PyCmd"

$PyProject = Join-Path $PkgDir 'pyproject.toml'
if (-not (Test-Path $PyProject)) {
  throw "pyproject.toml not found at $PyProject"
}

# cmake hint
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
  Write-Warn "CMake not found. scikit-build-core will attempt to use CMake; install it via winget/choco if build fails."
}

# --- Optional clean ---
if ($Clean) {
  Write-Info "Cleaning prior build artifacts…"
  foreach ($p in @('build', '_skbuild', 'dist')) {
    $target = Join-Path $PkgDir $p
    if (Test-Path $target) {
      Remove-Item -Recurse -Force $target -ErrorAction SilentlyContinue
    }
  }
  # egg-info globs
  Get-ChildItem -Path $PkgDir -Filter '*.egg-info' -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -Recurse -Force $_.FullName -ErrorAction SilentlyContinue
  }
}

# --- Install build tooling ---
Write-Info "Installing/Updating build tooling (pip, wheel, build, scikit-build-core, pybind11)…"
Exec $PyCmd "-m pip install -U pip wheel"
Exec $PyCmd "-m pip install -U build scikit-build-core pybind11"

# --- Build or Install ---
if ($Wheel) {
  Write-Info "Building wheel(s) from $PkgDir"
  Exec $PyCmd "-m build --wheel `"$PkgDir`""
  if (-not (Test-Path $Out)) { New-Item -ItemType Directory -Force -Path $Out | Out-Null }
  Get-ChildItem -Path (Join-Path $PkgDir 'dist') -Filter '*.whl' -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Info "Copying wheel $($_.Name) -> $Out"
    Copy-Item -Path $_.FullName -Destination $Out -Force
  }
  Write-Info "Done. Wheels are in: $Out"
} else {
  if ($Editable) {
    Write-Info "Editable install (pip -e): $PkgDir"
    Exec $PyCmd "-m pip install -e `"$PkgDir`""
  } else {
    Write-Info "Installing OMPEval extension from: $PkgDir"
    Exec $PyCmd "-m pip install `"$PkgDir`""
  }
  Write-Info "Verify import with:"
  Write-Host "  $PyCmd -c `"import ompeval; print(getattr(ompeval, '__version__', 'ok'))`""
}

Write-Info "Done."
