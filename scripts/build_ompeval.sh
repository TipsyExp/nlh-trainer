#!/usr/bin/env bash
# Tiny helper to build/install the OMPEval native extension via scikit-build-core.
# Works on Linux/macOS and WSL. For Windows, prefer WSL or build from the
# package directory with `pip install .` after installing build deps.
#
# Usage examples:
#   ./scripts/build_ompeval.sh                 # install the extension into current env
#   ./scripts/build_ompeval.sh --wheel         # build a wheel (no install), outputs to ./dist/
#   ./scripts/build_ompeval.sh --editable      # editable install (pip -e)
#   ./scripts/build_ompeval.sh --clean         # clean prior build artifacts before building
#   ./scripts/build_ompeval.sh --wheel --out outdir/   # write wheel(s) to outdir/
#
# Environment hints:
#   CMAKE_BUILD_PARALLEL_LEVEL: control parallel build jobs (e.g., export CMAKE_BUILD_PARALLEL_LEVEL=8)
#   SKBUILD_CMAKE_ARGS: extra CMake args (e.g., "-DCMAKE_BUILD_TYPE=Release")
#   PIP_INDEX_URL / PIP_EXTRA_INDEX_URL: if you mirror PyPI, set these before running
#
# Prereqs on Debian/Ubuntu/WSL:
#   sudo apt-get update && sudo apt-get install -y build-essential cmake python3-dev
#
set -euo pipefail

# --- resolve repo root ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Try git (preferred), else fall back relative to script dir
if ROOT_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

PKG_DIR="$ROOT_DIR/backend/native/ompeval"

if [[ ! -f "$PKG_DIR/pyproject.toml" ]]; then
  echo "ERROR: pyproject.toml not found at $PKG_DIR" >&2
  exit 1
fi

# --- defaults & args ---
DO_WHEEL=0
DO_EDITABLE=0
DO_CLEAN=0
OUT_DIR="$ROOT_DIR/dist"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wheel)
      DO_WHEEL=1
      shift
      ;;
    --editable|-e)
      DO_EDITABLE=1
      shift
      ;;
    --clean)
      DO_CLEAN=1
      shift
      ;;
    --out)
      OUT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      sed -n '1,80p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

# --- sanity checks ---
command -v python >/dev/null 2>&1 || { echo "ERROR: python not found in PATH"; exit 1; }
command -v pip >/dev/null 2>&1 || { echo "ERROR: pip not found in PATH"; exit 1; }

# cmake is required by scikit-build-core; warn if missing
if ! command -v cmake >/dev/null 2>&1; then
  echo "WARNING: cmake not found. Installing build deps may fail. Install cmake via your package manager." >&2
fi

# --- optional clean ---
if [[ $DO_CLEAN -eq 1 ]]; then
  echo "Cleaning previous build artifacts…"
  rm -rf "$PKG_DIR/build" "$PKG_DIR/_skbuild" "$PKG_DIR/dist" "$PKG_DIR/*.egg-info" 2>/dev/null || true
fi

# --- install build deps ---
echo "Installing build tooling (pip, wheel, build, scikit-build-core, pybind11)…"
python -m pip install -U pip wheel
python -m pip install -U build scikit-build-core pybind11

# --- build/install ---
if [[ $DO_WHEEL -eq 1 ]]; then
  # Build wheel (no install)
  echo "Building wheel for ompeval at: $PKG_DIR"
  python -m build --wheel "$PKG_DIR"

  mkdir -p "$OUT_DIR"
  # Move produced wheels to OUT_DIR
  shopt -s nullglob
  for whl in "$PKG_DIR"/dist/*.whl; do
    echo "Copying wheel: $(basename "$whl") -> $OUT_DIR"
    cp -f "$whl" "$OUT_DIR/"
  done
  echo "Done. Wheels are in: $OUT_DIR"
else
  # Install (editable or regular)
  if [[ $DO_EDITABLE -eq 1 ]]; then
    echo "Editable install: pip install -e $PKG_DIR"
    python -m pip install -e "$PKG_DIR"
  else
    echo "Installing ompeval extension from: $PKG_DIR"
    python -m pip install "$PKG_DIR"
  fi
  echo "Installed. Verify with: python -c 'import ompeval; print(ompeval.__dict__.get(\"__version__\"))'"
fi
