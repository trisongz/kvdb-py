from __future__ import annotations

"""
A KVDB-backed Dict-like object
"""

from kvdb.configs import settings as kvdb_settings
from kvdb.utils.logs import logger
from kvdb.types.base import supported_schemas
from lazyops.libs.persistence.backends.base import BaseStatefulBackend, SchemaType
from typing import Any, Dict, Optional, Union, Iterable, List, Type, TYPE_CHECKING


if TYPE_CHECKING:
    from .session import KVDBSession
    from lazyops.types.models import BaseSettings


class KVDBStatefulBackend(BaseStatefulBackend):
    """
    Implements Stateful Backend using KVDB
    """
    
    name: Optional[str] = "kvdb"

    # Default Global Level Settings that can then be tuned
    # at an instance level
    expiration: Optional[int] = None
    hset_disabled: Optional[bool] = False
    keyjoin: Optional[str] = ':'
    cache: Optional['KVDBSession'] = None

    def __init__(
        self,
        name: Optional[str] = None,
        expiration: Optional[int] = None,
        hset_disabled: Optional[bool] = False,
        keyjoin: Optional[str] = None,
        serializer: Optional[str] = None,
        serializer_kwargs: Optional[Dict[str, Any]] = None,
        base_key: Optional[str] = None,
        async_enabled: Optional[bool] = False,
        settings: Optional['BaseSettings'] = None,
        **kwargs,
    ):
        """
        Initializes the backend
        """
        _kvdb_kwargs = {}
        if kwargs:
            for key in kwargs:
                if key.startswith('redis_'):
                    _kvdb_kwargs[key.replace('redis_', '')] = kwargs.pop(key)
                elif key.startswith('keydb_'):
                    _kvdb_kwargs[key.replace('keydb_', '')] = kwargs.pop(key)
        
        if settings is None: settings = kvdb_settings
        self.base_key = base_key
        self.async_enabled = async_enabled
        self.settings = settings
        # Handle Serialization
        
        if name is not None: self.name = name
        if expiration is not None: self.expiration = expiration
        self.hset_enabled = (not hset_disabled and self.base_key is not None)
        if keyjoin is not None: self.keyjoin = keyjoin
        self._kwargs = kwargs



