from __future__ import annotations

"""
Cachify Component for KVDB

This component is used to cache the results of a function call
"""
import time
import anyio
import backoff
import inspect
import functools
import contextlib

from pydantic import Field, model_validator, validator, root_validator
from kvdb.types.base import BaseModel
from kvdb.types.common import CachePolicy
from kvdb.types.generic import ENOVAL
from kvdb.configs.caching import KVDBCachifyConfig
from kvdb.utils.logs import logger
from kvdb.utils.lazy import lazy_import
from kvdb.utils.helpers import create_cache_key_from_kwargs, is_coro_func, ensure_coro, full_name, timeout, is_classmethod
from lazyops.utils import timed_cache
from lazyops.utils.lazy import get_function_name
from lazyops.libs.pooler import ThreadPooler
from typing import Optional, Dict, Any, Callable, List, Union, TypeVar, Tuple, Awaitable, Type, overload, TYPE_CHECKING

if TYPE_CHECKING:
    from kvdb.components.client import ClientT
    from kvdb.components.session import KVDBSession
    from kvdb.configs import KVDBSettings

ReturnValue = TypeVar('ReturnValue')
ReturnValueT = Union[ReturnValue, Awaitable[ReturnValue]]
FunctionT = TypeVar('FunctionT', bound = Callable[..., ReturnValueT])


class CachifyConfig(KVDBCachifyConfig):
    """
    The Cachify Config
    """
    kwarg_override_prefix: Optional[str] = Field(None, description = 'The prefix for the kwargs that override the default config')
    has_async_loop: Optional[bool] = Field(None, description = 'Whether or not the async loop is running', exclude = True)
    session_available: Optional[bool] = Field(None, description = 'Whether or not the session is available', exclude = True)

    if TYPE_CHECKING:
        settings: KVDBSettings
    else:
        settings: Optional[Any] = Field(exclude=True)

    @classmethod
    def validate_callable(cls, v: Optional[Union[str, int, Callable]]) -> Optional[Union[Callable, Any]]:
        """
        Validates the callable
        """
        return lazy_import(v) if isinstance(v, str) else v
    
    @classmethod
    def validate_kws(cls, values: Dict[str, Any], is_update: Optional[bool] = None) -> Dict[str, Any]:
        """
        Validates the config
        """
        for key in {
            'name',
            'keybuilder',
            'encoder',
            'decoder',
            'hit_setter',
            'hit_getter',
            'disabled',
            'invalidate_if',
            'invalidate_after',
            'overwrite_if',
            'bypass_if',
            'post_init_hook',
            'post_call_hook',
        }:
            if key in values:
                values[key] = cls.validate_callable(values[key])
                if key in {'encoder', 'decoder'}:
                    if not inspect.isfunction(values[key]):
                        func_value = 'loads' if key == 'decoder' else 'dumps'
                        if hasattr(values[key], func_value) and inspect.isfunction(getattr(values[key], func_value)):
                            values[key] = getattr(values[key], func_value)
                        else:
                            raise ValueError(f'`{key}` must be callable or have a callable "{func_value}" method')

        if 'cache_max_size' in values:
            values['cache_max_size'] = int(values['cache_max_size']) if values['cache_max_size'] else None
            if 'cache_max_size_policy' in values:
                values['cache_max_size_policy'] = CachePolicy(values['cache_max_size_policy'])
            elif not is_update:
                values['cache_max_size_policy'] = CachePolicy.LFU
        elif 'cache_max_size_policy' in values:
            values['cache_max_size_policy'] = CachePolicy(values['cache_max_size_policy'])
        return values
        
    @root_validator()
    def validate_attrs(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates the attributes
        """
        return cls.validate_kws(values)

    @model_validator(mode = 'after')
    def validate_cachify_config(self):
        """
        Validates the cachify config
        """
        if self.encoder is None or self.decoder is None:
            serializer = self.get_serializer()
            self.encoder = serializer.dumps
            self.decoder = serializer.loads
        if self.kwarg_override_prefix:
            if self.disabled_kws: self.disabled_kws = [f'{self.kwarg_override_prefix}{kw}' for kw in self.disabled_kws]
            if self.invalidate_kws: self.invalidate_kws = [f'{self.kwarg_override_prefix}{kw}' for kw in self.invalidate_kws]
            if self.overwrite_kws: self.overwrite_kws = [f'{self.kwarg_override_prefix}{kw}' for kw in self.overwrite_kws]
            if self.ttl_kws: self.ttl_kws = [f'{self.kwarg_override_prefix}{kw}' for kw in self.ttl_kws]
        from kvdb.configs import settings
        self.settings = settings
        self.has_async_loop = self.settings.is_in_async_loop()
        return self
    
    def extract_cache_kwargs(self, **kwargs) -> Tuple[Dict[str, Union[bool, int, float, Any]], Dict[str, Any]]:
        """
        Extracts the cache kwargs from the kwargs

        Returns the cache kwargs and the remaining kwargs
        """
        cache_kwargs = {}
        if self.disabled_kws:
            for kw in self.disabled_kws:
                if kw in kwargs:
                    cache_kwargs['disabled'] = kwargs.pop(kw)
                    break
        if self.invalidate_kws:
            for kw in self.invalidate_kws:
                if kw in kwargs:
                    cache_kwargs['invalidate'] = kwargs.pop(kw)
                    break
        if self.overwrite_kws:
            for kw in self.overwrite_kws:
                if kw in kwargs:
                    cache_kwargs['overwrite'] = kwargs.pop(kw)
                    break
        if self.ttl_kws:
            for kw in self.ttl_kws:
                if kw in kwargs:
                    cache_kwargs['ttl'] = kwargs.pop(kw)
                    break
        return cache_kwargs, kwargs


    def get_key(self, key: str) -> str:
        """
        Gets the Key
        """
        return key if self.hset_enabled else f'{self.cache_field}:{key}'
    
    def update(self, **kwargs):
        """
        Validates and updates the kwargs
        """
        kwargs = self.validate_kws(kwargs, is_update = True)
        for k, v in kwargs.items():
            if not hasattr(self, k): continue
            setattr(self, k, v)

    def build_hash_name(self, func: Callable, *args, **kwargs) -> str:
        """
        Builds the name for the function
        """
        if self.cache_field is not None: return self.cache_field
        if self.name:  self.cache_field = self.name(func, *args, **kwargs) if callable(self.name) else self.name
        else: self.cache_field = full_name(func)
        return self.cache_field
    
    async def abuild_hash_name(self, func: Callable, *args, **kwargs) -> str:
        """
        Builds the name for the function
        """
        if self.cache_field is not None: return self.cache_field
        if self.name:  self.cache_field = await ThreadPooler.asyncish(self.name, func, *args, **kwargs) if callable(self.name) else self.name
        else: self.cache_field = full_name(func)
        return self.cache_field
    

    def build_hash_key(self, *args, **kwargs) -> str:
        """
        Builds the key for the function
        """
        hash_func = self.keybuilder or create_cache_key_from_kwargs
        return hash_func(
            base = self.prefix,
            args = args, 
            kwargs = kwargs, 
            typed = self.typed, 
            exclude_keys = self.exclude_keys,
            exclude_null_values = self.exclude_null_values_in_hash,
            exclude_default_values = self.exclude_default_values_in_hash,
            is_classmethod = self.is_class_method,
        )
    

    async def abuild_hash_key(self, *args, **kwargs) -> str:
        """
        Builds the key for the function
        """

        hash_func = self.keybuilder or create_cache_key_from_kwargs
        return await ThreadPooler.asyncish(
            hash_func, 
            base = self.prefix,
            args = args, 
            kwargs = kwargs, 
            typed = self.typed, 
            exclude_keys = self.exclude_keys,
            exclude_null_values = self.exclude_null_values_in_hash,
            exclude_default_values = self.exclude_default_values_in_hash,
            is_classmethod = self.is_class_method,
        )
    
    """
    Validators to determine the cache behavior
    """

    def should_disable(self, *args, cache_kwargs: Dict[str, Any] = None, **kwargs) -> bool:
        """
        Returns whether or not cache should be disabled for the function
        """
        if self.disabled is not None: self.disabled
        if self.disabled_kws and cache_kwargs.get('disabled') is True: return True
        return not self.disabled(*args, **kwargs) if callable(self.disabled) else False
    
    async def ashould_disable(self, *args, cache_kwargs: Dict[str, Any] = None, **kwargs) -> bool:
        """
        Returns whether or not the function should be cached
        """
        if self.disabled is not None: self.disabled
        if self.disabled_kws and cache_kwargs.get('disabled') is True: return True
        return not await ThreadPooler.asyncish(self.disabled, *args, **kwargs) if callable(self.disabled) else False

    def should_invalidate(self, *args, _hits: Optional[int] = None, cache_kwargs: Dict[str, Any] = None, **kwargs) -> bool:
        """
        Returns whether or not the function should be invalidated
        """
        if self.invalidate_if is not None: return self.invalidate_if(*args, **kwargs)
        if self.invalidate_kws and cache_kwargs.get('invalidate') is True: return True
        if self.invalidate_after is not None: 
            if _hits and isinstance(self.invalidate_after, int):
                return _hits >= self.invalidate_after
            return self.invalidate_after(*args, _hits = _hits, **kwargs)
        return False
    
    async def ashould_invalidate(self, *args, cache_kwargs: Dict[str, Any] = None, **kwargs) -> bool:
        """
        Returns whether or not the function should be invalidated
        """
        if self.invalidate_if is not None: return await ThreadPooler.asyncish(self.invalidate_if, *args, **kwargs)
        if self.invalidate_kws and cache_kwargs.get('invalidate') is True: return True
        if self.invalidate_after is not None: 
            _hits = await self.anum_hits
            if _hits and isinstance(self.invalidate_after, int):
                return _hits >= self.invalidate_after
            return await ThreadPooler.asyncish(self.invalidate_after, *args, _hits = _hits, **kwargs)
        return False
    
    def should_overwrite(self, *args, cache_kwargs: Dict[str, Any] = None, **kwargs) -> bool:
        """
        Returns whether or not the value should be overwritten
        which is based on the overwrite_if function
        """
        if self.overwrite_if is not None: return self.overwrite_if(*args, **kwargs)
        if self.overwrite_kws and cache_kwargs.get('overwrite') is True: return True
        return False
    
    async def ashould_overwrite(self, *args, cache_kwargs: Dict[str, Any] = None, **kwargs) -> bool:
        """
        Returns whether or not the value should be overwritten
        which is based on the overwrite_if function
        """
        if self.overwrite_if is not None: 
            return await ThreadPooler.asyncish(self.overwrite_if, *args, **kwargs)
        if self.overwrite_kws and cache_kwargs.get('overwrite') is True: return True
        return False


    def should_cache_value(self, val: Any) -> bool:
        """
        Returns whether or not the value should be cached
        """
        if self.exclude_null and val is None: return False
        if self.exclude_exceptions:
            if isinstance(self.exclude_exceptions, list): 
                return not isinstance(val, tuple(self.exclude_exceptions))
            if isinstance(val, Exception): return False
        return True
    

    async def ashould_cache_value(self, val: Any) -> bool:
        """
        Returns whether or not the value should be cached
        """
        if self.exclude_null and val is None: return False
        if self.exclude_exceptions:
            if isinstance(self.exclude_exceptions, list): 
                return not isinstance(val, tuple(self.exclude_exceptions))
            if isinstance(val, Exception): return False
        return True
    

    """
    Client Methods
    """

    @property
    def client(self) -> 'ClientT':
        """
        Returns the client
        """
        return self.session.aclient if self.is_async else self.session.client
    
    def _get(self, key: str) -> ReturnValueT:
        """
        Fetches the value from the cache
        """
        if self.hset_enabled: return self.client.hget(self.cache_field, key)
        return self.client.get(self.get_key(key))
            
    def _set(self, key: str, value: Any) -> None:
        """
        Sets the value in the cache
        """
        if self.hset_enabled: return self.client.hset(self.cache_field, key, value)
        return self.client.set(self.get_key(key), value)

    def _delete(self, key: str) -> None:
        """
        Deletes the value in the cache
        """
        if self.hset_enabled: return self.client.hdel(self.cache_field, key)
        return self.client.delete(self.get_key(key))
    
    def _clear(self, *keys: str) -> None:
        """
        Clears the keys in the cache
        """
        if self.hset_enabled:
            if keys: return self.client.hdel(self.cache_field, *keys)
            return self.client.delete(self.cache_field)
        if keys: return self.client.delete(*[self.get_key(k) for k in keys])
        return self.client.delete(self.get_key(self.cache_field, '*'))
    
    def _exists(self, key: str) -> bool:
        """
        Returns whether or not the key exists
        """
        if self.hset_enabled:
            return self.client.hexists(self.cache_field, key)
        return self.client.exists(self.get_key(key))
    
    def _expire(self, key: str, ttl: int) -> None:
        """
        Expires the key
        """
        if self.hset_enabled: return self.client.expire(self.cache_field, ttl)
        return self.client.expire(self.get_key(key), ttl)
    
    def _incr(self, key: str, amount: int = 1) -> Union[int, Awaitable[int]]:
        """
        Increments the key
        """
        if self.hset_enabled: return self.client.hincrby(self.cache_field, key, amount)
        return self.client.incr(self.get_key(key), amount)
    

    def _length(self) -> int:
        """
        Returns the size of the cache
        """
        if self.hset_enabled: return self.session.client.hlen(self.cache_field)
        return len(self.session.client.keys(self.get_key(self.cache_field, '*')))
    
    async def _alength(self) -> int:
        """
        Returns the size of the cache
        """
        if self.hset_enabled: return await self.session.aclient.hlen(self.cache_field)
        return len(await self.session.aclient.keys(self.get_key(self.cache_field, '*')))
    
    
    def _keys(self, decode: Optional[bool] = True) -> List[str]:
        """
        Returns the keys
        """
        if self.hset_enabled: keys = self.session.client.hkeys(self.cache_field)
        else: keys = self.session.client.keys(self.get_key(self.cache_field, '*'))
        if keys and decode: return [k.decode() if isinstance(k, bytes) else k for k  in keys]
        return keys or []
    
    async def _akeys(self, decode: Optional[bool] = True) -> List[str]:
        """
        Returns the keys
        """
        if self.hset_enabled: keys = await self.session.aclient.hkeys(self.cache_field)
        else: keys = await self.session.aclient.keys(self.get_key(self.cache_field, '*'))
        if keys and decode: return [k.decode() if isinstance(k, bytes) else k for k  in keys]
        return keys or []
    
    def _values(self, decode: Optional[bool] = False) -> List[Any]:
        """
        Returns the values
        """
        if self.hset_enabled: values = self.session.client.hvals(self.cache_field)
        else: values = self.session.client.mget(self._keys(decode = False))
        if values and decode: return [v.decode() if isinstance(v, bytes) else v for v  in values]
        return values or []
    
    async def _avalues(self, decode: Optional[bool] = False) -> List[Any]:
        """
        Returns the values
        """
        if self.hset_enabled: values = await self.session.aclient.hvals(self.cache_field)
        else: values = await self.session.aclient.mget(self._keys(decode = False))
        if values and decode: return [v.decode() if isinstance(v, bytes) else v for v  in values]
        return values or []

    def _items(self, decode: Optional[bool] = True) -> Dict[str, Any]:
        """
        Returns the items
        """
        if self.hset_enabled: items = self.session.client.hgetall(self.cache_field)
        else: items = self.session.client.mget(self._keys(decode = False))
        if items and decode: return {(k.decode() if isinstance(k, bytes) else k): self.decode(v) for k, v in items.items()}
        return items or {}

    async def _aitems(self, decode: Optional[bool] = True) -> Dict[str, Any]:
        """
        Returns the items
        """
        if self.hset_enabled: items = await self.session.aclient.hgetall(self.cache_field)
        else: items = await self.session.aclient.mget(self._keys(decode = False))
        if items and decode: return {(k.decode() if isinstance(k, bytes) else k): self.decode(v) for k, v in items.items()}
        return items or {}
    

    def clear(self, keys: Union[str, List[str]] = None) -> Optional[int]:
        """
        Clears the cache
        """
        with self.safely():
            if keys: return self.client.hdel(self.cache_field, keys)
            return self.client.delete(self.cache_field)
    

    """
    Properties
    """

    @property
    def is_enabled(self) -> bool:
        """
        Returns whether or not the cache is enabled [session is available]
        """
        if not self.session_available:
            with self.safely():
                with contextlib.suppress(Exception):
                    self.session.ping()
                    self.session_available = True
        return self.session_available

    @property
    def has_post_init_hook(self) -> bool:
        """
        Returns whether or not there is a post init hook
        """
        return self.post_init_hook is not None
    
    @property
    def has_post_call_hook(self) -> bool:
        """
        Returns whether or not there is a post call hook
        """
        return self.post_call_hook is not None

    @property
    def num_default_keys(self) -> int:
        """
        Returns the number of default keys
        """
        n = 1
        if self.cache_max_size is not None: n += 3
        return n
    
    @property
    def super_verbose(self) -> bool:
        """
        Returns whether or not the cache is super verbose
        """
        return self.verbosity and self.verbosity > 1
    

    @property
    def num_hits(self) -> int:
        """
        Returns the number of hits
        """
        with self.safely():
            val = self._get('hits')
            return int(val) if val else 0
    

    @property
    async def anum_hits(self) -> int:
        """
        Returns the number of hits
        """
        with self.safely():
            val = await self._get('hits')
            return int(val) if val else 0
            
    @property
    def num_keys(self) -> int:
        """
        Returns the number of keys
        """
        with self.safely():
            val = self._length()
            return max(int(val) - self.num_default_keys, 0) if val else 0
        
    @property
    async def anum_keys(self) -> int:
        """
        Returns the number of keys
        """
        with self.safely():
            val = await self._alength()
            return max(int(val) - self.num_default_keys, 0) if val else 0
    
    @property
    def cache_keys(self) -> List[str]:
        """
        Returns the keys
        """
        with self.safely():
            return self._keys()
            
        
    @property
    async def acache_keys(self) -> List[str]:
        """
        Returns the keys
        """
        with self.safely():
            return await self._akeys()
            
    @property
    def cache_values(self) -> List[Any]:
        """
        Returns the values
        """
        with self.safely():
            return self._values()
    
    @property
    async def acache_values(self) -> List[Any]:
        """
        Returns the values
        """
        with self.safely():
            return await self._avalues()
    
    @property
    def cache_items(self) -> Dict[str, Any]:
        """
        Returns the items
        """
        with self.safely():
            return self._items()
    
    @property
    async def acache_items(self) -> Dict[str, Any]:
        """
        Returns the items
        """
        with self.safely():
            return await self._aitems()
       
    @property
    def cache_keyhits(self) -> Dict[str, int]:
        """
        Returns the keyhits of the cache
        """
        with self.safely():
            val = self._get('keyhits')
            return {k.decode(): int(v) for k, v in val.items()} if val else {}
        
        
    @property
    async def acache_keyhits(self) -> Dict[str, int]:
        """
        Returns the keyhits of the cache
        """
        with self.safely():
            val = await self._get('keyhits')
            return {k.decode(): int(v) for k, v in val.items()} if val else {}
        
    @property
    def cache_timestamps(self) -> Dict[str, float]:
        """
        Returns the timestamps of the cache
        """
        with self.safely():
            val = self._get('timestamps')
            return {k.decode(): float(v) for k, v in val.items()} if val else {}
    
    @property
    async def acache_timestamps(self) -> Dict[str, float]:
        """
        Returns the timestamps of the cache
        """
        with self.safely():
            val = await self._get('timestamps')
            return {k.decode(): float(v) for k, v in val.items()} if val else {}
        
    
    @property
    def cache_expirations(self) -> Dict[str, float]:
        """
        Returns the expirations of the cache
        """
        with self.safely():
            val = self._get('expirations')
            return {k.decode(): float(v) for k, v in val.items()} if val else {}
    
    @property
    async def acache_expirations(self) -> Dict[str, float]:
        """
        Returns the expirations of the cache
        """
        with self.safely():
            val = await self._get('expirations')
            return {k.decode(): float(v) for k, v in val.items()} if val else {}
    
    @property
    def cache_info(self) -> Dict[str, Any]:
        """
        Returns the info for the cache
        """
        return {
            'name': self.cache_field,
            'hits': self.num_hits,
            'keys': self.num_keys,
            'keyhits': self.cache_keyhits,
            'timestamps': self.cache_timestamps,
            'expirations': self.cache_expirations,
            'max_size': self.cache_max_size,
            'max_size_policy': self.cache_max_size_policy,
        }
    
    @property
    async def acache_info(self) -> Dict[str, Any]:
        """
        Returns the info for the cache
        """
        return {
            'name': self.cache_field,
            'hits': await self.anum_hits,
            'keys': await self.anum_keys,
            'keyhits': await self.acache_keyhits,
            'timestamps': await self.acache_timestamps,
            'expirations': await self.acache_expirations,
            'max_size': self.cache_max_size,
            'max_size_policy': self.cache_max_size_policy,
        }
    
    """
    Methods
    """
            
    @contextlib.contextmanager
    def safely(self):
        """
        Safely wraps the function
        """
        if self.is_async and self.has_async_loop:
            with anyio.move_on_after(timeout = self.timeout):
                yield
        else:
            with timeout(self.timeout, raise_errors = False):
                yield
    

    def encode(self, value: Any) -> bytes:
        """
        Encodes the value
        """
        if self.session.session_serialization_enabled: return value
        return self.encoder(value)
    
    def decode(self, value: bytes) -> Any:
        """
        Decodes the value
        """
        if self.session.session_serialization_enabled: return value
        return self.decoder(value)


    def encode_hit(self, value: Any, *args, **kwargs) -> bytes:
        """
        Encodes the hit
        """
        if self.hit_setter is not None: 
            value = self.hit_setter(value, *args, **kwargs)
        return self.encode(value)
    
    def decode_hit(self, value: bytes, *args, **kwargs) -> Any:
        """
        Decodes the hit
        """
        value = self.decode(value)
        if self.hit_getter is not None: 
            value = self.hit_getter(value, *args, **kwargs)
        return value
    
    def invalidate_cache(self, key: str) -> int:
        """
        Invalidates the cache
        """
        with self.safely():
            return self._delete(key, 'hits', 'timestamps', 'expirations', 'keyhits')

    def add_hit(self):
        """
        Adds a hit to the cache
        """
        with self.safely():
            return self._incr('hits')

    def add_key_hit(self, key: str):
        """
        Adds a hit to the cache key
        """
        with self.safely():
            key_hits = self._get('keyhits') or {}
            if key not in key_hits: key_hits[key] = 0
            key_hits[key] += 1
            self._set('keyhits', key_hits)

    async def aadd_key_hit(self, key: str):
        """
        Adds a hit to the cache key
        """
        with self.safely():
            key_hits = await self._get('keyhits') or {}
            if key not in key_hits: key_hits[key] = 0
            key_hits[key] += 1
            await self._set('keyhits', key_hits)

    async def aadd_key_timestamp(self, key: str):
        """
        Adds a timestamp to the cache key
        """
        with self.safely():
            timestamps = await self._get('timestamps') or {}
            timestamps[key] = time.time()
            await self._set('timestamps', timestamps)
    
    def add_key_timestamp(self, key: str):
        """
        Adds a timestamp to the cache key
        """
        with self.safely():
            timestamps = self._get('timestamps') or {}
            timestamps[key] = time.time()
            self._set('timestamps', timestamps)

    def add_key_expiration(self, key: str, ttl: int):
        """
        Adds an expiration to the cache key
        """
        with self.safely():
            if self.hset_enabled:
                expirations = self._get('expirations') or {}
                expirations[key] = time.time() + ttl
                self._set('expirations', expirations)
                return
            self._expire(key, ttl)

    async def aadd_key_expiration(self, key: str, ttl: int):
        """
        Adds an expiration to the cache key
        """
        with self.safely():
            if self.hset_enabled:
                expirations = await self._get('expirations') or {}
                expirations[key] = time.time() + ttl
                await self._set('expirations', expirations)
                return
            await self._expire(key, ttl)

    def expire_cache_expired_keys(self):  # sourcery skip: extract-method
        """
        Expires the cache keys
        """
        with self.safely():
            expirations = self._get('expirations') or {}
            to_delete = [
                key
                for key, expiration in expirations.items()
                if time.time() > expiration
            ]
            if to_delete: 
                keyhits = self._get('keyhits') or {}
                timestamps = self._get('timestamps') or {}
                for key in to_delete:
                    keyhits.pop(key, None)
                    timestamps.pop(key, None)
                    expirations.pop(key, None)
                self._set('expirations', expirations)
                self._set('keyhits', keyhits)
                self._set('timestamps', timestamps)
                self.clear(to_delete)
    
    async def aexpire_cache_expired_keys(self):
        """
        Expires the cache keys
        """
        with self.safely():
            expirations = await self._get('expirations') or {}
            to_delete = [
                key
                for key, expiration in expirations.items()
                if time.time() > expiration
            ]
            if to_delete: 
                keyhits = await self._get('keyhits') or {}
                timestamps = await self._get('timestamps') or {}
                for key in to_delete:
                    keyhits.pop(key, None)
                    timestamps.pop(key, None)
                    expirations.pop(key, None)
                await self._set('expirations', expirations)
                await self._set('keyhits', keyhits)
                await self._set('timestamps', timestamps)
                await self.clear(to_delete)


    def check_cache_policies(self, key: str, *args, cache_kwargs: Dict[str, Union[bool, int, float, Any]] = None, **kwargs) -> None:
        # sourcery skip: low-code-quality
        """
        Runs the cache policies
        """
        if self.num_keys <= self.cache_max_size: return
        num_keys = self.num_keys
        if self.verbosity: logger.info(f'[{self.cache_field}] Cache Max Size Reached: {num_keys}/{self.cache_max_size}. Running Cache Policy: {self.cache_max_size_policy}')
        if self.cache_max_size_policy == CachePolicy.LRU:
            # Least Recently Used
            timestamps = self._get('timestamps') or {}
            keys_to_delete = sorted(timestamps, key = timestamps.get)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity: logger.info(f'[{self.cache_field}] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            self.clear(keys_to_delete)
            return
        
        if self.cache_max_size_policy == CachePolicy.LFU:
            # Least Frequently Used
            key_hits = self._get('keyhits') or {}
            keys_to_delete = sorted(key_hits, key = key_hits.get)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity: logger.info(f'[{self.cache_field}] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            self.clear(keys_to_delete)
            return
        
        if self.cache_max_size_policy == CachePolicy.FIFO:
            # First In First Out
            timestamps = self._get('timestamps') or {}
            keys_to_delete = sorted(timestamps, key = timestamps.get, reverse = True)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity: logger.info(f'[{self.cache_field}] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            self.clear(keys_to_delete)
            return
        
        if self.cache_max_size_policy == CachePolicy.LIFO:
            # Last In First Out
            timestamps = self._get('timestamps') or {}
            keys_to_delete = sorted(timestamps, key = timestamps.get)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity: logger.info(f'[{self.cache_field}] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            self.clear(keys_to_delete)
            return
    

    async def acheck_cache_policies(self, key: str, *args, cache_kwargs: Dict[str, Union[bool, int, float, Any]] = None, **kwargs) -> None:
        # sourcery skip: low-code-quality
        """
        Runs the cache policies
        """
        if await self.anum_keys <= self.cache_max_size: return
        num_keys = await self.anum_keys
        if self.verbosity: logger.info(f'[{self.cache_field}] Cache Max Size Reached: {num_keys}/{self.cache_max_size}. Running Cache Policy: {self.cache_max_size_policy}')
        if self.cache_max_size_policy == CachePolicy.LRU:
            # Least Recently Used
            timestamps = await self.session.aclient.hget(self.cache_field, 'timestamps') or {}
            keys_to_delete = sorted(timestamps, key = timestamps.get)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity: logger.info(f'[{self.cache_field}] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            await self.clear(keys_to_delete)
            return
        
        if self.cache_max_size_policy == CachePolicy.LFU:
            # Least Frequently Used
            key_hits = await self.session.aclient.hget(self.cache_field, 'keyhits') or {}
            keys_to_delete = sorted(key_hits, key = key_hits.get)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity: logger.info(f'[{self.cache_field}] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            await self.clear(keys_to_delete)
            return
        
        if self.cache_max_size_policy == CachePolicy.FIFO:
            # First In First Out
            timestamps = await self.session.aclient.hget(self.cache_field, 'timestamps') or {}
            keys_to_delete = sorted(timestamps, key = timestamps.get, reverse = True)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity: logger.info(f'[{self.cache_field}] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            await self.clear(keys_to_delete)
            return
        
        if self.cache_max_size_policy == CachePolicy.LIFO:
            # Last In First Out
            timestamps = await self.session.aclient.hget(self.cache_field, 'timestamps') or {}
            keys_to_delete = sorted(timestamps, key = timestamps.get)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity: logger.info(f'[{self.cache_field}] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            await self.clear(keys_to_delete)
            return

    def validate_cache_policies(self, key: str, *args, cache_kwargs: Dict[str, Union[bool, int, float, Any]] = None, **kwargs) -> None:
        """
        Runs the cache policies
        """
        self.add_hit()
        self.expire_cache_expired_keys()
        if not self.hset_enabled or self.cache_max_size is None: return
        self.add_key_hit(key)
        self.add_key_timestamp(key)
        self.check_cache_policies(key, *args, cache_kwargs = cache_kwargs, **kwargs)

    async def avalidate_cache_policies(self, key: str, *args, cache_kwargs: Dict[str, Union[bool, int, float, Any]] = None, **kwargs) -> None:
        """
        Runs the cache policies
        """
        await self.add_hit()
        if not self.hset_enabled or self.cache_max_size is None: return
        await self.aadd_key_timestamp(key)
        await self.aadd_key_hit(key)
        await self.acheck_cache_policies(key, *args, cache_kwargs = cache_kwargs, **kwargs)

    
    def retrieve(self, key: str, *args, cache_kwargs: Dict[str, Union[bool, int, float, Any]] = None, **kwargs) -> Any:
        """
        Retrieves the value from the cache
        """
        if self.should_overwrite(*args, cache_kwargs = cache_kwargs, **kwargs): 
            if self.super_verbose: logger.info(f'[{self.cache_field}:{key}] Overwriting Cache')
            return ENOVAL
        value = None
        try:
            with self.safely():
                if not self._exists(key):
                    if self.super_verbose: logger.info(f'[{self.cache_field}:{key}] Not Found')
                    return ENOVAL
                value = self._get(key)
            if value is None: return ENOVAL

        except TimeoutError:
            if self.super_verbose: logger.error(f'[{self.cache_field}:{key}] Retrieve Timeout')
            return ENOVAL
        
        except Exception as e:
            if self.verbosity: logger.trace(f'[{self.cache_field}:{key}] Retrieve Exception', error = e)
            return ENOVAL
        
        ThreadPooler.background(self.validate_cache_policies, key, *args, cache_kwargs = cache_kwargs, **kwargs)
        try:
            result = self.decode_hit(value, *args, **kwargs)
            if result is not None: return result
        except Exception as e:
            if self.verbosity: logger.trace(f'[{self.cache_field}:{key}] Decode Exception', error = e)
        return ENOVAL
    

    async def aretrieve(self, key: str, *args, cache_kwargs: Dict[str, Union[bool, int, float, Any]] = None, **kwargs) -> Any:
        """
        Retrieves the value from the cache
        """
        if await self.ashould_overwrite(*args, cache_kwargs = cache_kwargs, **kwargs): 
            if self.super_verbose: logger.info(f'[{self.cache_field}:{key}] Overwriting Cache')
            return ENOVAL
        value = None
        try:
            with self.safely():
                if not await self._exists(key):
                    if self.super_verbose: logger.info(f'[{self.cache_field}:{key}] Not Found')
                    return ENOVAL
                value = await self._get(key)
            if value is None: return ENOVAL

        except TimeoutError:
            if self.super_verbose: logger.error(f'[{self.cache_field}:{key}] Retrieve Timeout')
            return ENOVAL
        
        except Exception as e:
            if self.verbosity: logger.trace(f'[{self.cache_field}:{key}] Retrieve Exception', error = e)
            return ENOVAL
        
        ThreadPooler.background_task(self.avalidate_cache_policies, key, *args, cache_kwargs = cache_kwargs, **kwargs)
        try:
            result = self.decode_hit(value, *args, **kwargs)
            if result is not None: return result
        except Exception as e:
            if self.verbosity: logger.trace(f'[{self.cache_field}:{key}] Decode Exception', error = e)
        return ENOVAL

    def set(self, key: str, value: Any, *args, cache_kwargs: Dict[str, Union[bool, int, float, Any]] = None, **kwargs) -> None:
        """
        Sets the value in the cache
        """
        try:
            with self.safely():
                self._set(key, self.encode_hit(value, *args, **kwargs))
                self.add_key_expiration(key, cache_kwargs.get('ttl') or self.ttl)
        except TimeoutError:
            if self.super_verbose: logger.error(f'[{self.cache_field}:{key}] Set Timeout')
        except Exception as e:
            if self.verbosity: logger.trace(f'[{self.cache_field}:{key}] Set Exception: {value}', error = e)
    
    async def aset(self, key: str, value: Any, *args, cache_kwargs: Dict[str, Union[bool, int, float, Any]] = None, **kwargs) -> None:
        """
        Sets the value in the cache
        """
        try:
            with self.safely():
                await self._set(key, self.encode_hit(value, *args, **kwargs))
                await self.aadd_key_expiration(key, cache_kwargs.get('ttl') or self.ttl)
        except TimeoutError:
            if self.super_verbose: logger.error(f'[{self.cache_field}:{key}] Set Timeout')
        except Exception as e:
            if self.verbosity: logger.trace(f'[{self.cache_field}:{key}] Set Exception: {value}', error = e)


    def validate_is_class_method(self, func: Callable):
        """
        Validates if the function is a class method
        """
        if self.is_class_method is not None: return
        self.is_class_method = hasattr(func, '__class__') and inspect.isclass(func.__class__) and is_classmethod(func)
    

    def run_post_init_hook(self, func: Callable, *args, **kwargs) -> None:
        """
        Runs the post init hook which fires once after the function is initialized
        """
        if not self.has_post_init_hook: return
        if self.has_ran_post_init_hook: return
        if self.verbosity: logger.info(f'[{self.cache_field}] Running Post Init Hook')
        ThreadPooler.background(self.post_init_hook, func, *args, **kwargs)
        self.has_ran_post_init_hook = True


    async def arun_post_init_hook(self, func: Callable, *args, **kwargs) -> None:
        """
        Runs the post init hook which fires once after the function is initialized
        """
        if not self.has_post_init_hook: return
        if self.has_ran_post_init_hook: return
        if self.verbosity: logger.info(f'[{self.cache_field}] Running Post Init Hook')
        ThreadPooler.background_task(self.post_init_hook, func, *args, **kwargs)
        self.has_ran_post_init_hook = True

    def run_post_call_hook(self, result: Any, *args, is_hit: Optional[bool] = None, **kwargs) -> None:
        """
        Runs the post call hook which fires after the function is called
        """
        if not self.has_post_call_hook: return
        if self.super_verbose: logger.info(f'[{self.cache_field}] Running Post Call Hook')
        ThreadPooler.background(self.post_call_hook, result, *args, is_hit = is_hit, **kwargs)


    async def arun_post_call_hook(self, result: Any, *args, is_hit: Optional[bool] = None, **kwargs) -> None:
        """
        Runs the post call hook which fires after the function is called
        """
        if not self.has_post_call_hook: return
        if self.super_verbose: logger.info(f'[{self.cache_field}] Running Post Call Hook')
        ThreadPooler.background_task(self.post_call_hook, result, *args, is_hit = is_hit, **kwargs)



def cachify_sync(
    session: 'KVDBSession',
    _cachify: CachifyConfig,
) -> FunctionT:
    """
    [Sync] Creates a cachified function
    """

    _cachify.session = session
    _cachify.is_async = False
    if _cachify.retry_enabled:
        _retry_func_wrapper = functools.partial(
            backoff.on_exception,
            backoff.expo, 
            exception = Exception, 
            giveup = _cachify.retry_giveup_callable,
            factor = 5,
        )

    def decorator(func: FunctionT):
        if _cachify.retry_enabled:
            func = _retry_func_wrapper(max_tries = _cachify.retry_max_attempts + 1)(func)
        
        _current_cache_key = None
        _current_was_cached = False

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal _current_cache_key, _current_was_cached

            # Set the cache field
            _cachify.build_hash_name(func, *args, **kwargs)
            _cachify.validate_is_class_method(func)
            _cachify.run_post_init_hook(func, *args, **kwargs)
            
            cachify_kwargs, kwargs = _cachify.extract_cache_kwargs(**kwargs)

            # Check if we should disable the cache
            if _cachify.should_disable(*args, cache_kwargs = cachify_kwargs, **kwargs):
                if _cachify.super_verbose: logger.info('Disabling', prefix = _cachify.cache_field, colored = True)
                return func(*args, **kwargs)
            
            # Get the cache key
            cache_key = wrapper.__cache_key__(*args, **kwargs)
            _current_cache_key = cache_key

            
            # Check if we should invalidate
            if _cachify.should_invalidate(*args, cache_kwargs = cachify_kwargs, **kwargs):
                if _cachify.verbosity: logger.info('Invalidating', prefix = f'{_cachify.cache_field}:{cache_key}', colored = True)
                _cachify.invalidate_cache(cache_key)
            
            # Check if we have a cache hit
            value = _cachify.retrieve(cache_key, *args, cache_kwargs = cachify_kwargs, **kwargs)
            if value == ENOVAL:
                try:
                    value = func(*args, **kwargs)
                    if _cachify.should_cache_value(value):
                        if _cachify.super_verbose: logger.info('Caching Value', prefix = f'{_cachify.cache_field}:{cache_key}', colored = True)
                        _cachify.set(cache_key, value, *args, cache_kwargs = cachify_kwargs, **kwargs)
                    if _cachify.super_verbose: logger.info('Cache Miss', prefix = f'{_cachify.cache_field}:{cache_key}', colored = True)
                    _cachify.run_post_call_hook(value, *args, is_hit = False, **kwargs)
                    return value
                
                except Exception as e:
                    if _cachify.verbosity: logger.trace(f'[{_cachify.cache_field}:{cache_key}] Exception', error = e)
                    if _cachify.raise_exceptions: raise e
                    return None
            _current_was_cached = True
            if _cachify.super_verbose: logger.info('Cache Hit', prefix = f'{_cachify.cache_field}:{cache_key}', colored = True)
            _cachify.run_post_call_hook(value, *args, is_hit = True, **kwargs)
            return value

        def __cache_key__(*args, **kwargs) -> str:
            """
            Returns the cache key
            """
            return _cachify.build_hash_key(*args, **kwargs)
        
        def is_cached() -> bool:
            """
            Returns whether or not the function is cached
            """
            return _cachify._exists(_current_cache_key)
        
        def was_cached() -> bool:
            """
            Returns whether or not the function was cached
            """
            return _current_was_cached
        
        wrapper.__cache_key__ = __cache_key__
        wrapper.is_cached = is_cached
        wrapper.was_cached = was_cached
        return wrapper
    
    return decorator


def cachify_async(
    session: 'KVDBSession',
    _cachify: CachifyConfig,
) -> Callable[..., ReturnValueT]:
    """
    [Async] Creates a cachified function
    """
    _cachify.session = session
    _cachify.is_async = True
    if _cachify.retry_enabled:
        _retry_func_wrapper = functools.partial(
            backoff.on_exception,
            backoff.expo, 
            exception = Exception, 
            giveup = _cachify.retry_giveup_callable,
            factor = 5,
        )

    def decorator(func: FunctionT):
        if _cachify.retry_enabled: func = _retry_func_wrapper(max_tries = _cachify.retry_max_attempts + 1)(func)
        
        _current_cache_key = None
        _current_was_cached = False

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            nonlocal _current_cache_key, _current_was_cached

            # Set the cache field
            await _cachify.abuild_hash_name(func, *args, **kwargs)
            _cachify.validate_is_class_method(func)
            await _cachify.arun_post_init_hook(func, *args, **kwargs)
            cachify_kwargs, kwargs = _cachify.extract_cache_kwargs(**kwargs)

            # Check if we should disable the cache
            if await _cachify.ashould_disable(*args, cache_kwargs = cachify_kwargs, **kwargs):
                if _cachify.super_verbose: logger.info('Disabling', prefix = _cachify.cache_field, colored = True)
                return func(*args, **kwargs)
            
            # Get the cache key
            cache_key = await wrapper.__cache_key__(*args, **kwargs)
            _current_cache_key = cache_key
            
            # Check if we should invalidate
            if await _cachify.ashould_invalidate(*args, cache_kwargs = cachify_kwargs, **kwargs):
                if _cachify.verbosity: logger.info('Invalidating', prefix = f'{_cachify.cache_field}:{cache_key}', colored = True)
                await _cachify.invalidate_cache(cache_key)
            
            # Check if we have a cache hit
            value = await _cachify.aretrieve(cache_key, *args, cache_kwargs = cachify_kwargs, **kwargs)
            if value == ENOVAL:
                try:
                    value = func(*args, **kwargs)
                    if await _cachify.ashould_cache_value(value):
                        if _cachify.super_verbose: logger.info('Caching Value', prefix = f'{_cachify.cache_field}:{cache_key}', colored = True)
                        await _cachify.aset(cache_key, value, *args, cache_kwargs = cachify_kwargs, **kwargs)
                    if _cachify.super_verbose: logger.info('Cache Miss', prefix = f'{_cachify.cache_field}:{cache_key}', colored = True)
                    await _cachify.arun_post_call_hook(value, *args, is_hit = False, **kwargs)
                    return value
                
                except Exception as e:
                    if _cachify.verbosity: logger.trace(f'[{_cachify.cache_field}:{cache_key}] Exception', error = e)
                    if _cachify.raise_exceptions: raise e
                    return None
            
            _current_was_cached = True
            if _cachify.super_verbose: logger.info('Cache Hit', prefix = f'{_cachify.cache_field}:{cache_key}', colored = True)
            await _cachify.arun_post_call_hook(value, *args, is_hit = True, **kwargs)
            return value

        async def __cache_key__(*args, **kwargs) -> str:
            """
            Returns the cache key
            """
            return await _cachify.abuild_hash_key(*args, **kwargs)
        
        def is_cached() -> bool:
            """
            Returns whether or not the function is cached
            """
            return _cachify._exists(_current_cache_key)
        
        def was_cached() -> bool:
            """
            Returns whether or not the function was cached
            """
            return _current_was_cached
        
        wrapper.__cache_key__ = __cache_key__
        wrapper.is_cached = is_cached
        wrapper.was_cached = was_cached
        return wrapper
    
    return decorator



def fallback_sync_wrapper(
    func: FunctionT, 
    session: 'KVDBSession', 
    _cachify: CachifyConfig,
) -> FunctionT:
    """
    [Sync] Handles the fallback wrapper
    """

    _sess_ctx: Optional['KVDBSession'] = None

    def _get_sess():
        nonlocal _sess_ctx
        if _sess_ctx is None:
            with contextlib.suppress(Exception):
                if session.client.ping(): _sess_ctx = session
        return _sess_ctx
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        """
        The wrapper for cachify
        """
        _sess = _get_sess()
        if _sess is None:
            with contextlib.suppress(Exception):
                return timed_cache(secs = _cachify.ttl)(func)(*args, **kwargs)
            return func(*args, **kwargs)
        return cachify_sync(_sess, _cachify)(func)(*args, **kwargs)

    def clear(keys: Optional[Union[str, List[str]]] = None, **kwargs) -> Optional[int]:
        """
        Clears the cache
        """
        return _cachify.clear(keys = keys)
    
    def num_hits(*args, **kwargs) -> int:
        """
        Returns the number of hits
        """
        return _cachify.num_hits
    
    def num_keys(**kwargs) -> int:
        """
        Returns the number of keys
        """
        return _cachify.num_keys
    
    def cache_keys(**kwargs) -> List[str]:
        """
        Returns the keys
        """
        return _cachify.cache_keys
    
    def cache_values(**kwargs) -> List[Any]:
        """
        Returns the values
        """
        return _cachify.cache_values
    
    def cache_items(**kwargs) -> Dict[str, Any]:
        """
        Returns the items
        """
        return _cachify.cache_items
    
    def invalidate_key(key: str, **kwargs) -> int:
        """
        Invalidates the cache
        """
        return _cachify.invalidate_cache(key)
    
    def cache_timestamps(**kwargs) -> Dict[str, float]:
        """
        Returns the timestamps
        """
        return _cachify.cache_timestamps
    
    def cache_keyhits(**kwargs) -> Dict[str, int]:
        """
        Returns the keyhits
        """
        return _cachify.cache_keyhits
    
    def cache_policy(**kwargs) -> Dict[str, Union[int, CachePolicy]]:
        """
        Returns the cache policy
        """
        return {
            'max_size': _cachify.cache_max_size,
            'max_size_policy': _cachify.cache_max_size_policy,
        }

    def cache_config(**kwargs) -> Dict[str, Any]:
        """
        Returns the cache config
        """
        values = _cachify.model_dump(exclude = {'session'})
        for k, v in values.items():
            if callable(v): values[k] = get_function_name(v)
        return values

    def cache_info(**kwargs) -> Dict[str, Any]:
        """
        Returns the info for the cache
        """
        return _cachify.cache_info
    
    def cache_update(**kwargs) -> Dict[str, Any]:
        """
        Updates the cache config
        """
        _cachify.update(**kwargs)
        return cache_config(**kwargs)

    wrapper.clear = clear
    wrapper.num_hits = num_hits
    wrapper.num_keys = num_keys
    wrapper.cache_keys = cache_keys
    wrapper.cache_values = cache_values
    wrapper.cache_items = cache_items
    wrapper.invalidate_key = invalidate_key
    wrapper.cache_timestamps = cache_timestamps
    wrapper.cache_keyhits = cache_keyhits
    wrapper.cache_policy = cache_policy
    wrapper.cache_config = cache_config
    wrapper.cache_info = cache_info
    wrapper.cache_update = cache_update
    return wrapper



def fallback_async_wrapper(
    func: FunctionT, 
    session: 'KVDBSession', 
    _cachify: CachifyConfig,
) -> FunctionT:
    """
    [Async] Handles the fallback wrapper
    """

    _sess_ctx: Optional['KVDBSession'] = None

    async def _get_sess():
        nonlocal _sess_ctx
        if _sess_ctx is None:
            with contextlib.suppress(Exception):
                with anyio.fail_after(1.0):
                    if await session.aclient.ping(): _sess_ctx = session
            if _cachify.verbosity and _sess_ctx is None: logger.error('Could not connect to KVDB')
        return _sess_ctx

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        """
        The wrapper for cachify
        """
        _sess = await _get_sess()
        if _sess is None:
            with contextlib.suppress(Exception):
                return await timed_cache(secs = _cachify.ttl)(func)(*args, **kwargs)
            return await func(*args, **kwargs)
        return await cachify_async(_sess, _cachify)(func)(*args, **kwargs)

    async def clear(keys: Optional[Union[str, List[str]]] = None, **kwargs) -> Optional[int]:
        """
        Clears the cache
        """
        return await _cachify.aclear(keys = keys)
    
    async def num_hits(*args, **kwargs) -> int:
        """
        Returns the number of hits
        """
        return await _cachify.anum_hits
    
    async def num_keys(**kwargs) -> int:
        """
        Returns the number of keys
        """
        return await _cachify.anum_keys
    
    async def cache_keys(**kwargs) -> List[str]:
        """
        Returns the keys
        """
        return await _cachify.acache_keys
    
    async def cache_values(**kwargs) -> List[Any]:
        """
        Returns the values
        """
        return await _cachify.acache_values
    
    async def cache_items(**kwargs) -> Dict[str, Any]:
        """
        Returns the items
        """
        return await _cachify.acache_items
    
    async def invalidate_key(key: str, **kwargs) -> int:
        """
        Invalidates the cache
        """
        return await _cachify.invalidate_cache(key)
    
    async def cache_timestamps(**kwargs) -> Dict[str, float]:
        """
        Returns the timestamps
        """
        return await _cachify.acache_timestamps
    
    async def cache_keyhits(**kwargs) -> Dict[str, int]:
        """
        Returns the keyhits
        """
        return await _cachify.acache_keyhits
    
    async def cache_policy(**kwargs) -> Dict[str, Union[int, CachePolicy]]:
        """
        Returns the cache policy
        """
        return {
            'max_size': _cachify.cache_max_size,
            'max_size_policy': _cachify.cache_max_size_policy,
        }

    async def cache_config(**kwargs) -> Dict[str, Any]:
        """
        Returns the cache config
        """
        values = _cachify.model_dump(exclude = {'session'})
        for k, v in values.items():
            if callable(v): values[k] = get_function_name(v)
        return values

    async def cache_info(**kwargs) -> Dict[str, Any]:
        """
        Returns the info for the cache
        """
        return await _cachify.acache_info
    
    async def cache_update(**kwargs) -> Dict[str, Any]:
        """
        Updates the cache config
        """
        _cachify.update(**kwargs)
        return await cache_config(**kwargs)

    wrapper.clear = clear
    wrapper.num_hits = num_hits
    wrapper.num_keys = num_keys
    wrapper.cache_keys = cache_keys
    wrapper.cache_values = cache_values
    wrapper.cache_items = cache_items
    wrapper.invalidate_key = invalidate_key
    wrapper.cache_timestamps = cache_timestamps
    wrapper.cache_keyhits = cache_keyhits
    wrapper.cache_policy = cache_policy
    wrapper.cache_config = cache_config
    wrapper.cache_info = cache_info
    wrapper.cache_update = cache_update

    return wrapper


@overload
def cachify(
    ttl: Optional[int] = 60 * 10, # 10 minutes
    ttl_kws: Optional[List[str]] = ['cache_ttl'], # The keyword arguments to use for the ttl

    keybuilder: Optional[Callable] = None,
    name: Optional[Union[str, Callable]] = None,
    typed: Optional[bool] = True,
    exclude_keys: Optional[List[str]] = None,
    exclude_null: Optional[bool] = True,
    exclude_exceptions: Optional[Union[bool, List[Exception]]] = True,
    prefix: Optional[str] = '_kvc_', # The prefix to use for the cache if keybuilder is not present

    exclude_null_values_in_hash: Optional[bool] = None,
    exclude_default_values_in_hash: Optional[bool] = None,

    disabled: Optional[Union[bool, Callable]] = None,
    disabled_kws: Optional[List[str]] = ['cache_disable'], # If present and True, disable the cache
    
    invalidate_after: Optional[Union[int, Callable]] = None,
    
    invalidate_if: Optional[Callable] = None,
    invalidate_kws: Optional[List[str]] = ['cache_invalidate'], # If present and True, invalidate the cache

    overwrite_if: Optional[Callable] = None,
    overwrite_kws: Optional[List[str]] = ['cache_overwrite'], # If present and True, overwrite the cache

    retry_enabled: Optional[bool] = False,
    retry_max_attempts: Optional[int] = 3, # Will retry 3 times
    retry_giveup_callable: Optional[Callable[..., bool]] = None,

    timeout: Optional[float] = 5.0,
    verbosity: Optional[int] = None,

    raise_exceptions: Optional[bool] = True,

    encoder: Optional[Union[str, Callable]] = None,
    decoder: Optional[Union[str, Callable]] = None,

    # Allow for custom hit setters and getters
    hit_setter: Optional[Callable] = None,
    hit_getter: Optional[Callable] = None,

    # Allow for max cache size
    cache_max_size: Optional[int] = None,
    cache_max_size_policy: Optional[Union[str, CachePolicy]] = CachePolicy.LFU, # 'LRU' | 'LFU' | 'FIFO' | 'LIFO'

    # Allow for post-init hooks
    post_init_hook: Optional[Union[str, Callable]] = None,
    
    # Allow for post-call hooks
    post_call_hook: Optional[Union[str, Callable]] = None,
    hset_enabled: Optional[bool] = True,

    session: Optional['KVDBSession'] = None,
    session_name: Optional[str] = None,
    session_kwargs: Optional[Dict[str, Any]] = None,
) -> Callable[[FunctionT], FunctionT]:  # sourcery skip: default-mutable-arg
    """
    Creates a new cachify decorator

    Args:

        ttl (Optional[int], optional): The time to live for the cache. Defaults to 60 * 10 (10 minutes).
        ttl_kws (Optional[List[str]], optional): The keyword arguments to use for the ttl. Defaults to ['cache_ttl'].
        keybuilder (Optional[Callable], optional): The keybuilder function to use. Defaults to None.
        name (Optional[Union[str, Callable]], optional): The name of the cache. Defaults to None.
        typed (Optional[bool], optional): Whether or not to use typed caching. Defaults to True.
        exclude_keys (Optional[List[str]], optional): The keys to exclude from the cache. Defaults to None.
        exclude_null (Optional[bool], optional): Whether or not to exclude null values from the cache. Defaults to True.
        exclude_exceptions (Optional[Union[bool, List[Exception]]], optional): Whether or not to exclude exceptions from the cache. Defaults to True.
        prefix (Optional[str], optional): The prefix to use for the cache if keybuilder is not present. Defaults to '_kvc_'.
        exclude_null_values_in_hash (Optional[bool], optional): Whether or not to exclude null values from the hash. Defaults to None.
        exclude_default_values_in_hash (Optional[bool], optional): Whether or not to exclude default values from the hash. Defaults to None.
        disabled (Optional[Union[bool, Callable]], optional): Whether or not to disable the cache. Defaults to None.
        disabled_kws (Optional[List[str]], optional): The keyword arguments to use for the disabled flag. Defaults to ['cache_disable'].
        invalidate_after (Optional[Union[int, Callable]], optional): The time to invalidate the cache after. Defaults to None.
        invalidate_if (Optional[Callable], optional): The function to use to invalidate the cache. Defaults to None.
        invalidate_kws (Optional[List[str]], optional): The keyword arguments to use for the invalidate flag. Defaults to ['cache_invalidate'].
        overwrite_if (Optional[Callable], optional): The function to use to overwrite the cache. Defaults to None.
        overwrite_kws (Optional[List[str]], optional): The keyword arguments to use for the overwrite flag. Defaults to ['cache_overwrite'].
        retry_enabled (Optional[bool], optional): Whether or not to enable retries. Defaults to False.
        retry_max_attempts (Optional[int], optional): The maximum number of retries. Defaults to 3.
        retry_giveup_callable (Optional[Callable[..., bool]], optional): The function to use to give up on retries. Defaults to None.
        timeout (Optional[float], optional): The timeout for the cache. Defaults to 5.0.
        verbosity (Optional[int], optional): The verbosity level. Defaults to None.
        raise_exceptions (Optional[bool], optional): Whether or not to raise exceptions. Defaults to True.
        encoder (Optional[Union[str, Callable]], optional): The encoder to use. Defaults to None.
        decoder (Optional[Union[str, Callable]], optional): The decoder to use. Defaults to None.
        hit_setter (Optional[Callable], optional): The hit setter to use. Defaults to None.
        hit_getter (Optional[Callable], optional): The hit getter to use. Defaults to None.
        cache_max_size (Optional[int], optional): The maximum size of the cache. Defaults to None.
        cache_max_size_policy (Optional[Union[str, CachePolicy]], optional): The cache policy to use. Defaults to CachePolicy.LFU.
        post_init_hook (Optional[Union[str, Callable]], optional): The post init hook to use. Defaults to None.
        post_call_hook (Optional[Union[str, Callable]], optional): The post call hook to use. Defaults to None.
        hset_enabled (Optional[bool], optional): Whether or not to enable hset/hget/hdel/hmset/hmget/hmgetall. Defaults to True.
        session (Optional['KVDBSession'], optional): The session to use. Defaults to None.
        session_name (Optional[str], optional): The session name to use. Defaults to None.
        session_kwargs (Optional[Dict[str, Any]], optional): The session kwargs to use. Defaults to None.
    """
    ...



def cachify(
    session: Optional[Union['KVDBSession', str]] = None,
    session_name: Optional[str] = None,
    session_kwargs: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Callable[[FunctionT], FunctionT]:
    """
    This version implements a custom KeyDB caching decorator
    that utilizes hset/hget/hdel/hmset/hmget/hmgetall
    instead of the default set/get/del
    """
    from kvdb.configs import settings
    base_kwargs = settings.cache.model_dump(exclude_none=True, exclude_unset=True)
    base_kwargs.update(kwargs)
    _cachify = CachifyConfig(**base_kwargs)
    def decorator(func: FunctionT) -> FunctionT:
        """
        The decorator for cachify
        """
        nonlocal session, session_name, session_kwargs
        if session and isinstance(session, str):
            session_name = session
            session = None
        if session is None: 
            session_kwargs = session_kwargs or {}
            from kvdb.client import KVDBClient
            session = KVDBClient.get_session(
                name = session_name, 
                **session_kwargs
            )
        if inspect.iscoroutinefunction(func):
            return fallback_async_wrapper(func, session, _cachify)
        else:
            return fallback_sync_wrapper(func, session, _cachify)
    return decorator



@overload
def create_cachify(
    ttl: Optional[int] = 60 * 10, # 10 minutes
    ttl_kws: Optional[List[str]] = ['cache_ttl'], # The keyword arguments to use for the ttl

    keybuilder: Optional[Callable] = None,
    name: Optional[Union[str, Callable]] = None,
    typed: Optional[bool] = True,
    exclude_keys: Optional[List[str]] = None,
    exclude_null: Optional[bool] = True,
    exclude_exceptions: Optional[Union[bool, List[Exception]]] = True,
    prefix: Optional[str] = '_kvc_',

    exclude_null_values_in_hash: Optional[bool] = None,
    exclude_default_values_in_hash: Optional[bool] = None,

    disabled: Optional[Union[bool, Callable]] = None,
    disabled_kws: Optional[List[str]] = ['cache_disable'], # If present and True, disable the cache
    
    invalidate_after: Optional[Union[int, Callable]] = None,
    
    invalidate_if: Optional[Callable] = None,
    invalidate_kws: Optional[List[str]] = ['cache_invalidate'], # If present and True, invalidate the cache

    overwrite_if: Optional[Callable] = None,
    overwrite_kws: Optional[List[str]] = ['cache_overwrite'], # If present and True, overwrite the cache

    retry_enabled: Optional[bool] = False,
    retry_max_attempts: Optional[int] = 3, # Will retry 3 times
    retry_giveup_callable: Optional[Callable[..., bool]] = None,
    
    timeout: Optional[float] = 5.0,
    verbosity: Optional[int] = None,

    raise_exceptions: Optional[bool] = True,

    encoder: Optional[Union[str, Callable]] = None,
    decoder: Optional[Union[str, Callable]] = None,

    # Allow for custom hit setters and getters
    hit_setter: Optional[Callable] = None,
    hit_getter: Optional[Callable] = None,

    # Allow for max cache size
    cache_max_size: Optional[int] = None,
    cache_max_size_policy: Optional[Union[str, CachePolicy]] = CachePolicy.LFU, # 'LRU' | 'LFU' | 'FIFO' | 'LIFO'

    # Allow for post-init hooks
    post_init_hook: Optional[Union[str, Callable]] = None,
    
    # Allow for post-call hooks
    post_call_hook: Optional[Union[str, Callable]] = None,
    hset_enabled: Optional[bool] = True,

    session: Optional['KVDBSession'] = None,
    session_name: Optional[str] = None,
    session_kwargs: Optional[Dict[str, Any]] = None,
) -> Callable[[FunctionT], FunctionT]:  # sourcery skip: default-mutable-arg
    """
    Creates a new cachify partial decorator that
    passes the kwargs to the cachify decorator before it is applied

    Args:

        ttl (Optional[int], optional): The time to live for the cache. Defaults to 60 * 10 (10 minutes).
        ttl_kws (Optional[List[str]], optional): The keyword arguments to use for the ttl. Defaults to ['cache_ttl'].
        keybuilder (Optional[Callable], optional): The keybuilder function to use. Defaults to None.
        name (Optional[Union[str, Callable]], optional): The name of the cache. Defaults to None.
        typed (Optional[bool], optional): Whether or not to use typed caching. Defaults to True.
        exclude_keys (Optional[List[str]], optional): The keys to exclude from the cache. Defaults to None.
        exclude_null (Optional[bool], optional): Whether or not to exclude null values from the cache. Defaults to True.
        exclude_exceptions (Optional[Union[bool, List[Exception]]], optional): Whether or not to exclude exceptions from the cache. Defaults to True.
        prefix (Optional[str], optional): The prefix to use for the cache if keybuilder is not present. Defaults to '_kvc_'.
        exclude_null_values_in_hash (Optional[bool], optional): Whether or not to exclude null values from the hash. Defaults to None.
        exclude_default_values_in_hash (Optional[bool], optional): Whether or not to exclude default values from the hash. Defaults to None.
        disabled (Optional[Union[bool, Callable]], optional): Whether or not to disable the cache. Defaults to None.
        disabled_kws (Optional[List[str]], optional): The keyword arguments to use for the disabled flag. Defaults to ['cache_disable'].
        invalidate_after (Optional[Union[int, Callable]], optional): The time to invalidate the cache after. Defaults to None.
        invalidate_if (Optional[Callable], optional): The function to use to invalidate the cache. Defaults to None.
        invalidate_kws (Optional[List[str]], optional): The keyword arguments to use for the invalidate flag. Defaults to ['cache_invalidate'].
        overwrite_if (Optional[Callable], optional): The function to use to overwrite the cache. Defaults to None.
        overwrite_kws (Optional[List[str]], optional): The keyword arguments to use for the overwrite flag. Defaults to ['cache_overwrite'].
        retry_enabled (Optional[bool], optional): Whether or not to enable retries. Defaults to False.
        retry_max_attempts (Optional[int], optional): The maximum number of retries. Defaults to 3.
        retry_giveup_callable (Optional[Callable[..., bool]], optional): The function to use to give up on retries. Defaults to None.
        timeout (Optional[float], optional): The timeout for the cache. Defaults to 5.0.
        verbosity (Optional[int], optional): The verbosity level. Defaults to None.
        raise_exceptions (Optional[bool], optional): Whether or not to raise exceptions. Defaults to True.
        encoder (Optional[Union[str, Callable]], optional): The encoder to use. Defaults to None.
        decoder (Optional[Union[str, Callable]], optional): The decoder to use. Defaults to None.
        hit_setter (Optional[Callable], optional): The hit setter to use. Defaults to None.
        hit_getter (Optional[Callable], optional): The hit getter to use. Defaults to None.
        cache_max_size (Optional[int], optional): The maximum size of the cache. Defaults to None.
        cache_max_size_policy (Optional[Union[str, CachePolicy]], optional): The cache policy to use. Defaults to CachePolicy.LFU.
        post_init_hook (Optional[Union[str, Callable]], optional): The post init hook to use. Defaults to None.
        post_call_hook (Optional[Union[str, Callable]], optional): The post call hook to use. Defaults to None.
        hset_enabled (Optional[bool], optional): Whether or not to enable hset/hget/hdel/hmset/hmget/hmgetall. Defaults to True.
        session (Optional['KVDBSession'], optional): The session to use. Defaults to None.
        session_name (Optional[str], optional): The session name to use. Defaults to None.
        session_kwargs (Optional[Dict[str, Any]], optional): The session kwargs to use. Defaults to None.
    """
    ...



def create_cachify(
    **kwargs,
):
    """
    Creates a new `cachify` partial decorator with the given kwargs
    """
    return functools.partial(cachify, **kwargs)

