from __future__ import annotations

"""
Configuration for Caching / Persistence
"""

from pydantic import Field, model_validator, validator
from kvdb.types.base import BaseModel, computed_field
from kvdb.types.common import CachePolicy
from .defaults import (
    get_default_cache_db_id,
    get_default_cache_serializer,
    get_default_cache_prefix,
)
from .base import SerializerConfig
from typing import Dict, Any, Optional, Type, Literal, Union, Callable, List, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from kvdb.components.session import KVDBSession

class KVDBCacheConfig(SerializerConfig, BaseModel):
    """
    The KVDB Cache Config
    """
    enabled: Optional[bool] = False
    ttl: Optional[int] = 60 * 10 # 10 minutes
    maxsize: Optional[int] = 1000
    typed: Optional[bool] = False
    eviction_policy: Optional[str] = 'LRU'
    cache_class: Optional[str] = None

    prefix: Optional[str] = Field('_kvc_', description = 'The prefix for the cache key')
    
    max_attempts: Optional[int] = 20

    db_id: Optional[int] = Field(default_factory = get_default_cache_db_id)


class KVDBCachifyConfig(SerializerConfig, BaseModel):
    """
    The KVDB Cachify Config
    """

    ttl: Optional[int] = 60 * 10 # 10 minutes
    ttl_kws: Optional[List[str]] = ['cache_ttl'] # The keyword arguments to use for the ttl

    keybuilder: Optional[Callable] = None
    name: Optional[Union[str, Callable]] = None
    typed: Optional[bool] = True
    exclude_keys: Optional[List[str]] = None
    exclude_null: Optional[bool] = True
    exclude_exceptions: Optional[Union[bool, List[Exception]]] = True
    prefix: Optional[str] = Field(default_factory = get_default_cache_prefix, description = 'The prefix for the cache key')

    exclude_null_values_in_hash: Optional[bool] = None
    exclude_default_values_in_hash: Optional[bool] = None

    disabled: Optional[Union[bool, Callable]] = None
    disabled_kws: Optional[List[str]] = ['cache_disable'] # If present and True, disable the cache
    
    invalidate_after: Optional[Union[int, Callable]] = None
    
    invalidate_if: Optional[Callable] = None
    invalidate_kws: Optional[List[str]] = ['cache_invalidate'] # If present and True, invalidate the cache

    overwrite_if: Optional[Callable] = None
    overwrite_kws: Optional[List[str]] = ['cache_overwrite'] # If present and True, overwrite the cache

    retry_enabled: Optional[bool] = False
    retry_max_attempts: Optional[int] = 3 # Will retry 3 times
    retry_giveup_callable: Optional[Callable[..., bool]] = None

    exclude_if: Optional[Callable] = None
    exclude_kws: Optional[List[str]] = ['cache_exclude'] # If present and True, does not cache the result

    timeout: Optional[float] = 5.0
    verbosity: Optional[int] = None

    raise_exceptions: Optional[bool] = True

    encoder: Optional[Union[str, Callable]] = None
    decoder: Optional[Union[str, Callable]] = None

    # Allow for custom hit setters and getters
    hit_setter: Optional[Callable] = None
    hit_getter: Optional[Callable] = None

    # Allow for max cache size
    cache_max_size: Optional[int] = None
    cache_max_size_policy: Optional[Union[str, CachePolicy]] = CachePolicy.LFU # 'LRU' | 'LFU' | 'FIFO' | 'LIFO'

    # Allow for post-init hooks
    post_init_hook: Optional[Union[str, Callable]] = None
    
    # Allow for post-call hooks
    post_call_hook: Optional[Union[str, Callable]] = None

    serializer: Optional[str] = Field(default_factory = get_default_cache_serializer)
    # 'json'

    # Private
    cache_field: Optional[str] = None
    is_class_method: Optional[bool] = None
    has_ran_post_init_hook: Optional[bool] = None
    is_async: Optional[bool] = None

    hset_enabled: Optional[bool] = True

    if TYPE_CHECKING:
        session: Optional['KVDBSession'] = None
    else:
        session: Optional[Any] = None