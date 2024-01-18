from __future__ import annotations

# Lazy Initialization
import os
from .helpers import lazy_import
from typing import Dict, Any, Optional, Type, Union, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from kvdb.configs.base import KVDBSettings

_kvdb_settings: Optional['KVDBSettings'] = None
_concurrency_limit: Optional[int] = None

def get_settings() -> 'KVDBSettings':
    """
    Gets the settings object
    """
    global _kvdb_settings
    if _kvdb_settings is None:
        from kvdb.configs.base import KVDBSettings
        _kvdb_settings = KVDBSettings()
    return _kvdb_settings


def set_concurrency_limit(
    limit: Optional[int] = None
):
    """
    Set the concurrency limit
    """
    global _concurrency_limit
    if limit is None: limit = os.cpu_count() * 4
    _concurrency_limit = limit

def get_concurrency_limit() -> Optional[int]:
    """
    Get the concurrency limit
    """
    global _concurrency_limit
    if _concurrency_limit is None: set_concurrency_limit()
    return _concurrency_limit