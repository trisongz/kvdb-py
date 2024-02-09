"""
Helper Functions to Apply to the `cachify` Module
"""

from typing import Optional

def is_not_cachable(*args, cachable: Optional[bool] = None, **kwargs) -> bool:
    """
    Returns if the request is cachable
    """
    return not cachable

def is_disabled(*args, disabled: Optional[bool] = None, **kwargs) -> bool:
    """
    Returns if the caching is disabled
    """
    return disabled

def is_overwrite(*args, overwrite: Optional[bool] = None, **kwargs) -> bool:
    """
    Returns if the request is cachable
    """
    return overwrite is True


