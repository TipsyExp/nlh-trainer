# Building the OMPEval Native Extension

OMPEval is a fast C++ evaluator / equity engine we use as the **primary** backend for
multiway range equity. This doc explains how to build and install our Python
extension (`ompeval`) so the backend can be used by the app, tests, and the
benchmark harness.

If OMPEval isn’t available on a machine, the system **automatically falls back**
to the pure-Python `eval7` backend (slower, but zero-compile). OMPEval is
strictly optional for local dev.

---

## What gets built

A Python extension module named `ompeval` located at:

backend/native/ompeval/


We use **scikit-build-core + CMake + pybind11** to compile and install a
platform-specific wheel into your current Python environment.

- Module name: `ompeval`
- Source entry: `backend/native/ompeval/pybind_ompeval.cpp`
- Build config: `backend/native/ompeval/pyproject.toml`

---

## Prerequisites

You need a C++ toolchain and CMake that match your Python environment.

### Common requirements

- **Python**: 3.9+ recommended (whatever your venv uses)
- **pip / wheel**: up to date
- **CMake**: 3.18+ (roughly; newer is better)
- **A C++ compiler**:
  - **Linux**: `build-essential` (gcc/g++), `cmake`
  - **macOS**: Xcode Command Line Tools (`xcode-select --install`)
  - **Windows** (native):
    - Visual Studio **Build Tools** (MSVC) **or**
    - use **WSL** (Ubuntu) which is usually the easiest route

> Tip: If native Windows C++ builds become a time sink, use WSL. The Python
> wheel installs into your Linux venv; the app/test suite runs the same.

---

## Quick start

We provide helper scripts that install build tooling, compile the extension,
and install it into your current venv.

### Linux / macOS

```bash
# From repo root
bash scripts/build_ompeval.sh

Editable install:
bash scripts/build_ompeval.sh -e

Build wheel only (writes to ./dist by default):
bash scripts/build_ompeval.sh -w -o ./out

Windows (PowerShell)
# From repo root
.\scripts\build_ompeval.ps1

Editable install:
.\scripts\build_ompeval.ps1 -Editable

Build wheel only:
.\scripts\build_ompeval.ps1 -Wheel -Out .\out

Clean build artifacts:
.\scripts\build_ompeval.ps1 -Clean

Manual install (no scripts)

From repo root (ensure your venv is active):
python -m pip install -U pip wheel build scikit-build-core pybind11
python -m pip install ./backend/native/ompeval

Build a wheel without installing:
python -m build --wheel ./backend/native/ompeval
ls ./backend/native/ompeval/dist/*.whl

Editable install:
python -m pip install -e ./backend/native/ompeval

Verifying the build

In the same environment you built/installed:
python -c "import ompeval; print(getattr(ompeval, '__version__', 'ok'))"

No error = the module is importable.

You can also run a tiny end-to-end check via our equity API tests (OMPEval
tests will skip if the module isn’t importable):
pytest -q backend/tests/test_equity_ompeval_multiway.py -q

Using OMPEval in the app

Default policy is auto, which will try ompeval first.

You can force the policy for debugging:
# Use OMPEval if available
export EQUITY_BACKEND_POLICY=ompeval    # (Linux/macOS)
$env:EQUITY_BACKEND_POLICY="ompeval"    # (PowerShell)

If ompeval fails to import, auto falls back to eval7 automatically.

CI notes (high level)

The default CI job does not compile OMPEval (falls back to eval7).

A future matrix job should:

Install build deps (cmake, toolchain).

pip install ./backend/native/ompeval

Run full tests and a tiny bench-equity scenario.

Keep iterations tiny for CI (the benchmark script already has safe defaults).

Troubleshooting

“CMake not found”
Install CMake (apt install cmake, brew install cmake, or VS Build Tools
with CMake component).

“No C++ compiler found” / MSVC errors

Windows: install Visual Studio Build Tools (C++), or use WSL.

macOS: xcode-select --install.

Linux: sudo apt-get install build-essential.

ABI / wheel mismatch
Rebuild in the same venv you will run the app/tests with. Wheels are
Python-ABI specific (e.g. cp311 vs cp312).

Module not importable after build
Ensure you installed into the active venv. Try:
python -m pip uninstall -y ompeval
python -m pip install ./backend/native/ompeval
python -c "import ompeval"

Range syntax differences
OMPEval expects Equilab-like syntax. Our service normalizes common PokerStove
forms internally; if you feed raw strings to the native layer, convert them
first using our range shim.

License

OMPEval is licensed under ISC (see upstream).

This repository includes a copy:
backend/native/ompeval/LICENSE.txt