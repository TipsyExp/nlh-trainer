
# OMPEval Python Binding (native)

This directory contains the native build for the **OMPEval** backend used by the equity service. The binding exposes a minimal Python module named `ompeval` (via **pybind11**) that provides fast multiway equity (MC + exact) and hand evaluation using the upstream C++ library.

> Target: Linux/macOS/WSL. On Windows, WSL is recommended. A pure-MSVC build is possible but more manual.

---

## What this is

- A thin C++ wrapper (`pybind_ompeval.cpp`) compiled into a Python extension called `ompeval`.
- Build is driven by `pyproject.toml` + a companion `setup.py` (in this folder).
- At runtime, higher-level Python code (`backend/services/equity/backends/ompeval_backend.py`) calls into this module.

OMPEval basics:
- Up to **6 players**.
- **Monte Carlo** and **full enumeration**.
- **EquiLab-like** range syntax.
- Multithreaded.

---

## Prerequisites

- **Python 3.9+**
- **C++17** toolchain (gcc/clang, or MSVC if you insist).
- **pybind11** headers (installed automatically via build requirements).
- **OMPEval** sources/headers & library available to the compiler/linker.

You can use the upstream repo: <https://github.com/zekyll/OMPEval>
- Build the static library (`libompeval.a`) or make headers available.
- Alternatively, point the build to the OMPEval source directory so the binding compiles it as part of the build (see `setup.py`).

---

## Environment variables (include & lib discovery)

Before building you may set one of:

- `OMPEVAL_ROOT` — path to an OMPEval checkout (containing `omp/` headers and sources).
- or fine-grained:
  - `OMPEVAL_INCLUDEDIR` — directory containing `omp/*.h`.
  - `OMPEVAL_LIBRARYDIR` — directory containing `libompeval.a` (or `.so`/`.dylib`).

If none are set, the build will **attempt** to:
- Compile OMPEval sources vendored via `OMPEVAL_ROOT`, or
- Use system include/lib paths.

---

## Build (Linux/macOS/WSL)

From the project root (or from this folder):

```bash
# (optional) point to a local OMPEval checkout
export OMPEVAL_ROOT=/path/to/OMPEval

# build the wheel (pyproject uses setuptools backend)
python -m pip install --upgrade pip build
python -m build backend/native/ompeval

# OR in-place editable build during development:
pip install -e backend/native/ompeval

If you prefer direct setup.py:
cd backend/native/ompeval
python setup.py build_ext –inplace

Build (Windows)
Recommended: use WSL and follow Linux steps.
If you need native Windows:
•	Use "x64 Native Tools Command Prompt for VS".
•	Ensure C++17 toolset is installed.
•	Set OMPEVAL_ROOT/OMPEVAL_INCLUDEDIR/OMPEVAL_LIBRARYDIR as above.
•	Then:
cd backend\native\ompeval
py -m pip install -U pip build
py -m build .

Note: If linking fails, prefer static linking (libompeval.lib) or switch to WSL.
________________________________________
Verifying the build
python -c "import ompeval; print('ompeval ok:', hasattr(ompeval, '__doc__'))"

In the app:
•	Set EQUITY_BACKEND_POLICY=ompeval to prefer this backend.
•	Fallbacks (like eval7) will be used automatically if ompeval import fails.
________________________________________
Range syntax
OMPEval expects EquiLab-like ranges. Our Python layer accepts common PokerStove-ish strings and normalizes them before calling into ompeval. See backend/services/equity/range_syntax.py.
________________________________________
Troubleshooting
•	Cannot find OMPEval headers
Set OMPEVAL_INCLUDEDIR or OMPEVAL_ROOT.
•	Linker cannot find OMPEval library
Set OMPEVAL_LIBRARYDIR or build static and let setup.py compile sources.
•	C++ standard errors
Ensure your compiler supports C++17 and that build flags include -std=c++17 (or MSVC equivalent). Our setup.py sets this.
•	macOS arm64
You may need export ARCHFLAGS="-arch arm64" and use a recent clang.
•	Windows MSVC
If you hit CRT/linking pain, switch to WSL; otherwise ensure you are in the correct Developer Prompt.
________________________________________
Directory layout
backend/native/ompeval/
  ├─ pybind_ompeval.cpp     # pybind11 binding
  ├─ setup.py               # builds the extension (defines include/lib paths)
  ├─ pyproject.toml         # PEP 517 metadata/back-end
  ├─ README.md              # this file
  └─ LICENSE.txt            # copy of OMPEval license (ISC)

Some projects vendor OMPEval sources directly into this folder. We instead prefer pointing to a local OMPEval checkout via OMPEVAL_ROOT.
________________________________________
License
•	OMPEval is licensed under ISC (see LICENSE.txt).
•	This binding follows the project’s license and is intended solely as a thin bridge to OMPEval.

