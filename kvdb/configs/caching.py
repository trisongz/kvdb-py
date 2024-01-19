from __future__ import annotations

"""
Configuration for Caching / Persistence
"""

from pydantic import Field, model_validator, validator
from kvdb.types.base import BaseModel, computed_field
from typing import Dict, Any, Optional, Type, Literal, Union, Callable, List, Mapping, TYPE_CHECKING
from .base import SerializerConfig

class KVDBCacheConfig(SerializerConfig, BaseModel):
    """
    The KVDB Cache Config
    """
    enabled: Optional[bool] = False
    ttl: Optional[int] = 60
    maxsize: Optional[int] = 1000
    typed: Optional[bool] = False
    eviction_policy: Optional[str] = 'LRU'
    cache_class: Optional[str] = None

    prefix: Optional[str] = Field('_kvc_', description = 'The prefix for the cache key')
    
    max_attempts: Optional[int] = 20