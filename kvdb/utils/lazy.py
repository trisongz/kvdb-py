from __future__ import annotations

# Lazy Initialization
import os
from .helpers import lazy_import
from typing import Dict, Any, Optional, Type, Union, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from kvdb.configs.base import KVDBSettings

_kvdb_settings: Optional['KVDBSettings'] = None

def get_settings() -> 'KVDBSettings':
    """
    Gets the settings object
    """
    global _kvdb_settings
    if _kvdb_settings is None:
        from kvdb.configs.base import KVDBSettings
        _kvdb_settings = KVDBSettings()
    return _kvdb_settings

