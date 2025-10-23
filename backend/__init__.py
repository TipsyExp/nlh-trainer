"""Backend package for the NLH trainer.

This module initialises the backend as a Python package.  It does not
automatically import submodules to avoid expensive side effects at
import time.  Consumers should import subpackages directly (e.g.,
``from backend.api import session``) to access API routers and
helpers.
"""

__all__: list[str] = []
