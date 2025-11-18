"""
OMPEval bindings shim.

This module normalizes import paths for the native OMPEval extension.  It
attempts to import the canonical ``ompeval`` package first, then falls
back to the historical ``nlh_ompeval`` name if necessary.  If neither
package can be imported, an ImportError is raised.

Usage:

    from .ompeval_bindings import ompeval

After import, the ``ompeval`` symbol will reference whichever module was
successfully imported.
"""

from __future__ import annotations

try:
    import ompeval as _ompeval  # type: ignore
except Exception:
    try:
        import nlh_ompeval as _ompeval  # type: ignore
    except Exception as e:
        raise ImportError(
            "No OMPEval bindings found (tried 'ompeval' and 'nlh_ompeval')"
        ) from e

# Re-export the resolved module under a consistent name.
ompeval = _ompeval  # type: ignore

__all__ = ["ompeval"]
