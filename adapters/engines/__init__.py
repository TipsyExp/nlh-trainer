"""
Engine adapters subpackage.

This package contains thin wrappers for connecting to different poker
engines.  In M0 we support only PokerKit.  Each adapter must export
the functions described in the engine interface specification.
"""

__all__ = ["pokerkit_adapter"]