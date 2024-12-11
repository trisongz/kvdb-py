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
import makefun
import contextlib


from pydantic import Field, model_validator, validator, root_validator
from kvdb.types.base import BaseModel, computed_field
from kvdb.types.common import CachePolicy
from kvdb.types.generic import ENOVAL, ParamSpec
from kvdb.configs.caching import KVDBCachifyConfig
from kvdb.utils.logs import logger
from kvdb.utils.lazy import lazy_import
from kvdb.utils.helpers import create_cache_key_from_kwargs, is_coro_func, ensure_coro, full_name, timeout, is_classmethod
from lazyops.utils import timed_cache
from lazyops.utils.helpers import is_in_async_loop
from lazyops.utils.lazy import get_function_name
from lazyops.libs.persistence import PersistentDict
from lazyops.libs.pooler import ThreadPooler
from typing import Optional, Dict, Any, Callable, List, Union, TypeVar, Tuple, Awaitable, Type, overload, TYPE_CHECKING

if TYPE_CHECKING:
    from kvdb.components.client import ClientT
    from kvdb.components.session import KVDBSession
    from kvdb.configs import KVDBSettings

ReturnValue = TypeVar('ReturnValue')
ReturnValueT = Union[ReturnValue, Awaitable[ReturnValue]]
FunctionT = TypeVar('FunctionT', bound = Callable[..., ReturnValueT])
FuncT = TypeVar('FuncT')
FuncP = ParamSpec('FuncP')

class Cachify(KVDBCachifyConfig):
    """
    The Cachify Config
    """
    function_name: Optional[str] = Field(None, description = 'The name of the function')
    kwarg_override_prefix: Optional[str] = Field(None, description = 'The prefix for the kwargs that override the default config')
    # has_async_loop: Optional[bool] = Field(None, description = 'Whether or not the async loop is running', exclude = True)
    session_available: Optional[bool] = Field(None, description = 'Whether or not the session is available', exclude = True)
    silenced_stages: Optional[List[str]] = Field(default_factory=list, description = 'The stages to silence')

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
        _validated_serializer = False
        if 'serializer' in values:
            serializer = values.pop('serializer')
            from kvdb.io.serializers import get_serializer, BaseSerializer
            if isinstance(serializer, str):
                serializer_kwargs = values.pop('serializer_kwargs', {})
                if 'compression' not in serializer_kwargs:
                    serializer_kwargs['compression'] = values.pop('compression', None)
                if 'compression_level' not in serializer_kwargs:
                    serializer_kwargs['compression_level'] = values.pop('compression_level', None)
                serializer = get_serializer(serializer, **serializer_kwargs)
            if not isinstance(serializer, BaseSerializer):
                raise ValueError('`serializer` must be an instance of `BaseSerializer`')
            values['encoder'] = serializer.dumps
            values['decoder'] = serializer.loads
            _validated_serializer = True

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
            'exclude_if',
            # 'bypass_if',
            'post_init_hook',
            'post_call_hook',
        }:
            if key in values:
                try:
                    values[key] = cls.validate_callable(values[key])
                except Exception as e:
                    if key in {'name'}: continue
                    raise e
                if key in {'encoder', 'decoder'}:
                    if _validated_serializer: continue
                    # if not inspect.isfunction(values[key]):
                    if not callable(values[key]):
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
        
    @root_validator(pre = True)
    def validate_attrs(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates the attributes
        """
        return cls.validate_kws(values)

    @model_validator(mode = 'after')
    def validateself_config(self):
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
            if self.exclude_kws: self.exclude_kws = [f'{self.kwarg_override_prefix}{kw}' for kw in self.exclude_kws]
        from kvdb.configs import settings
        self.settings = settings
        # self.has_async_loop = self.settings.is_in_async_loop()
        return self
    
    # @timed_cache(secs = 60, cache_if_result = True)
    # def _has_async_loop(self) -> bool:
    #     """
    #     Checks if the current process is running in an async loop
    #     """
    #     return self.settings.is_in_async_loop()

    @property
    def has_async_loop(self) -> bool:
        """
        Checks if the current process is running in an async loop
        """
        return is_in_async_loop()
        # if self._has_async_loop is None:
        #     self._has_async_loop = self._has_async_loop()
        # return self._has_async_loop

        
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
        if self.exclude_kws:
            for kw in self.exclude_kws:
                if kw in kwargs:
                    cache_kwargs['exclude'] = kwargs.pop(kw)
                    break
        return cache_kwargs, kwargs
    
    @computed_field
    @property
    def data(self) -> PersistentDict:
        """
        Returns the persistent data
        """
        return self.session.create_persistence(
            base_key=f'{self.cache_field}:data',
            serializer=self.serializer,
        )

    def is_silenced(self, *stages: str) -> bool:
        """
        Returns whether or not the stage is silenced
        """
        if not self.silenced_stages: return False
        return any(stage in self.silenced_stages for stage in stages)
        # return stage in self.silenced_stages

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
        if self.name: self.cache_field = self.name(func, *args, **kwargs) if callable(self.name) else self.name
        else: 
            self.cache_field = full_name(func)
            if self.prefix: self.cache_field = f'{self.prefix}:{self.cache_field}'
        return self.cache_field
    
    async def abuild_hash_name(self, func: Callable, *args, **kwargs) -> str:
        """
        Builds the name for the function
        """
        if self.cache_field is not None: return self.cache_field
        if self.name: self.cache_field = await ThreadPooler.asyncish(self.name, func, *args, **kwargs) if callable(self.name) else self.name
        else: 
            self.cache_field = full_name(func)
            if self.prefix: self.cache_field = f'{self.prefix}:{self.cache_field}'
        return self.cache_field
    

    def build_hash_key(self, *args, **kwargs) -> str:
        """
        Builds the key for the function
        """
        hash_func = self.keybuilder or create_cache_key_from_kwargs
        return hash_func(
            # base = self.prefix,
            args = args, 
            kwargs = kwargs, 
            typed = self.typed, 
            exclude_keys = self.exclude_keys,
            exclude_null = self.exclude_null_values_in_hash,
            exclude_defaults = self.exclude_default_values_in_hash,
            is_classmethod = self.is_class_method,
        )
    

    async def abuild_hash_key(self, *args, **kwargs) -> str:
        """
        Builds the key for the function
        """

        hash_func = self.keybuilder or create_cache_key_from_kwargs
        return await ThreadPooler.asyncish(
            hash_func, 
            # base = self.prefix,
            args = args, 
            kwargs = kwargs, 
            typed = self.typed, 
            exclude_keys = self.exclude_keys,
            exclude_null = self.exclude_null_values_in_hash,
            exclude_defaults = self.exclude_default_values_in_hash,
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
        return self.disabled(*args, **kwargs) if callable(self.disabled) else False
    
    async def ashould_disable(self, *args, cache_kwargs: Dict[str, Any] = None, **kwargs) -> bool:
        """
        Returns whether or not the function should be cached
        """
        if self.disabled is not None: self.disabled
        if self.disabled_kws and cache_kwargs.get('disabled') is True: return True
        return await ThreadPooler.asyncish(self.disabled, *args, **kwargs) if callable(self.disabled) else False

    def should_invalidate(self, *args, _hits: Optional[int] = None, cache_kwargs: Dict[str, Any] = None, **kwargs) -> bool:
        """
        Returns whether or not the function should be invalidated
        """
        if self.invalidate_if is not None: return self.invalidate_if(*args, **kwargs)
        if self.invalidate_kws and cache_kwargs.get('invalidate') is True: return True
        if self.invalidate_after is not None: 
            if isinstance(self.invalidate_after, int):
                return _hits is not None and _hits >= self.invalidate_after
            # if _hits and isinstance(self.invalidate_after, int):
            #     return _hits >= self.invalidate_after
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
            if isinstance(self.invalidate_after, int):
                return _hits is not None and _hits >= self.invalidate_after
            # if _hits and isinstance(self.invalidate_after, int):
            #     return _hits >= self.invalidate_after
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


    def should_cache_value(self, val: Any, *args, cache_kwargs: Dict[str, Any] = None, **kwargs) -> bool:
        """
        Returns whether or not the value should be cached
        """
        if self.exclude_null and val is None: return False
        if self.exclude_exceptions:
            if isinstance(self.exclude_exceptions, list): 
                return not isinstance(val, tuple(self.exclude_exceptions))
            if isinstance(val, Exception): return False
        if self.exclude_kws and cache_kwargs.get('exclude') is True: return False
        if self.exclude_if is not None: return not self.exclude_if(val, *args, **kwargs)
        return True
    

    async def ashould_cache_value(self, val: Any,  *args, cache_kwargs: Dict[str, Any] = None, **kwargs) -> bool:
        """
        Returns whether or not the value should be cached
        """
        if self.exclude_null and val is None: return False
        if self.exclude_exceptions:
            if isinstance(self.exclude_exceptions, list): 
                return not isinstance(val, tuple(self.exclude_exceptions))
            if isinstance(val, Exception): return False
        if self.exclude_kws and cache_kwargs.get('exclude') is True: return False
        if self.exclude_if is not None: return not (await ThreadPooler.asyncish(self.exclude_if, val, *args, **kwargs))
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
        if self.hset_enabled: return self.client.hset(self.cache_field, key = key, value = value)
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
            if keys: 
                if self.hset_enabled: return self.client.hdel(self.cache_field, *keys)
                return self.client.delete(*[self.get_key(k) for k in keys])
            self.data.clear()
            if self.hset_enabled: 
                return self.client.delete(self.cache_field)
            keys = self.client.keys(self.get_key(self.cache_field, '*'))
            return self.client.delete(*keys)
    

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
        return 0
        # n = 1
        # if self.cache_max_size is not None: n += 3
        # return n
    
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
            return self.data.get('hits', 0)
            # val = self._get('hits')
            # return int(val) if val else 0
    

    @property
    async def anum_hits(self) -> int:
        """
        Returns the number of hits
        """
        with self.safely():
            return await self.data.aget('hits', 0)
            # val = await self._get('hits')
            # return int(val) if val else 0
            
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
            return self.data.get('keyhits', {})
        
        
    @property
    async def acache_keyhits(self) -> Dict[str, int]:
        """
        Returns the keyhits of the cache
        """
        with self.safely():
            return await self.data.aget('keyhits', {})
        
    @property
    def cache_timestamps(self) -> Dict[str, float]:
        """
        Returns the timestamps of the cache
        """
        with self.safely():
            return self.data.get('timestamps', {})
    
    @property
    async def acache_timestamps(self) -> Dict[str, float]:
        """
        Returns the timestamps of the cache
        """
        with self.safely():
            return await self.data.aget('timestamps', {})
        
    
    @property
    def cache_expirations(self) -> Dict[str, float]:
        """
        Returns the expirations of the cache
        """
        with self.safely():
            return self.data.get('expirations', {})
    
    @property
    async def acache_expirations(self) -> Dict[str, float]:
        """
        Returns the expirations of the cache
        """
        with self.safely():
            return await self.data.aget('expirations', {})
    
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
            with anyio.move_on_after(self.timeout):
                yield
        else:
            with timeout(int(self.timeout), raise_errors = False):
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
            if key in self.cache_keyhits:
                _ = self.data['keyhits'].pop(key, None)
            if key in self.cache_timestamps:
                _ = self.data['timestamps'].pop(key, None)
            if key in self.cache_expirations:
                _ = self.data['expirations'].pop(key, None)
            self.data.flush()
            return self._delete(key)
            # return self._delete(key, 'hits', 'timestamps', 'expirations', 'keyhits')

    def add_hit(self):
        """
        Adds a hit to the cache
        """
        with self.safely():
            if not self.data.contains('hits'): self.data.set('hits', 0)
            try:
                self.data['hits'] += 1
            except Exception as e:
                self.data.set('hits', 1)

    async def aadd_hit(self):
        """
        Adds a hit to the cache
        """
        with self.safely():
            if not await self.data.acontains('hits'): await self.data.aset('hits', 0)
            try:
                self.data['hits'] += 1
            except Exception as e:
                await self.data.aset('hits', 1)

    def add_key_hit(self, key: str):
        """
        Adds a hit to the cache key
        """
        with self.safely():
            key_hits = self.data.get('keyhits', {})
            if key not in key_hits: key_hits[key] = 0
            key_hits[key] += 1
            self.data['keyhits'] = key_hits

    async def aadd_key_hit(self, key: str):
        """
        Adds a hit to the cache key
        """
        with self.safely():
            key_hits = await self.data.aget('keyhits', {}) #  or {}
            if key not in key_hits: key_hits[key] = 0
            key_hits[key] += 1
            await self.data.aset('keyhits', key_hits)

    async def aadd_key_timestamp(self, key: str):
        """
        Adds a timestamp to the cache key
        """
        with self.safely():
            timestamps = await self.data.aget('timestamps', {})
            timestamps[key] = time.time()
            await self.data.aset('timestamps', timestamps)
    
    def add_key_timestamp(self, key: str):
        """
        Adds a timestamp to the cache key
        """
        with self.safely():
            timestamps = self.data.get('timestamps', {})
            timestamps[key] = time.time()
            self.data['timestamps'] = timestamps

    def add_key_expiration(self, key: str, ttl: int):
        """
        Adds an expiration to the cache key
        """
        if ttl is None: return
        with self.safely():
            if self.hset_enabled:
                expirations = self.data.get('expirations', {})
                expirations[key] = time.time() + ttl
                self.data['expirations'] = expirations
                return
            self._expire(key, ttl)

    async def aadd_key_expiration(self, key: str, ttl: int):
        """
        Adds an expiration to the cache key
        """
        if ttl is None: return
        with self.safely():
            if self.hset_enabled:
                expirations = await self.data.aget('expirations', {})
                expirations[key] = time.time() + ttl
                await self.data.aset('expirations', expirations)
                return
            await self._expire(key, ttl)

    def expire_cache_expired_keys(self):  # sourcery skip: extract-method
        """
        Expires the cache keys
        """
        with self.safely():
            expirations = self.data.get('expirations', {})
            if not isinstance(expirations, dict): expirations = {}
            to_delete = [
                key
                for key, expiration in expirations.items()
                if time.time() > expiration
            ]
            if to_delete: 
                keyhits = self.data.get('keyhits', {})
                if not isinstance(keyhits, dict): keyhits = {}
                timestamps = self.data.get('timestamps', {})
                if not isinstance(timestamps, dict): timestamps = {}
                for key in to_delete:
                    keyhits.pop(key, None)
                    timestamps.pop(key, None)
                    expirations.pop(key, None)
                self.data['expirations'] = expirations
                self.data['keyhits'] = keyhits
                self.data['timestamps'] = timestamps
                if self.verbosity and not self.is_silenced('expire'): 
                    logger.info(f'[{self.cache_field}] Deleting {len(to_delete)} Expired Keys: {to_delete}')
                self.clear(to_delete)
    
    async def aexpire_cache_expired_keys(self):
        """
        Expires the cache keys
        """
        with self.safely():
            expirations = await self.data.aget('expirations', {})
            if not isinstance(expirations, dict): expirations = {}
            to_delete = [
                key
                for key, expiration in expirations.items()
                if time.time() > expiration
            ]
            if to_delete: 
                keyhits = await self.data.aget('keyhits', {})
                if not isinstance(keyhits, dict): keyhits = {}
                timestamps = await self.data.aget('timestamps', {})
                if not isinstance(timestamps, dict): timestamps = {}
                for key in to_delete:
                    keyhits.pop(key, None)
                    timestamps.pop(key, None)
                    expirations.pop(key, None)
                await self.data.aset('expirations', expirations)
                await self.data.aset('keyhits', keyhits)
                await self.data.aset('timestamps', timestamps)
                if self.verbosity and not self.is_silenced('expire'): logger.info(f'[{self.cache_field}] Deleting {len(to_delete)} Expired Keys: {to_delete}')
                await self.clear(to_delete)


    def check_cache_policies(self, key: str, *args, cache_kwargs: Dict[str, Union[bool, int, float, Any]] = None, **kwargs) -> None:
        # sourcery skip: low-code-quality
        """
        Runs the cache policies
        """
        if self.num_keys <= self.cache_max_size: return
        num_keys = self.num_keys
        if self.verbosity and not self.is_silenced('cache_policy'): logger.info(f'[{self.cache_field}] Cache Max Size Reached: {num_keys}/{self.cache_max_size}. Running Cache Policy: {self.cache_max_size_policy}')
        if self.cache_max_size_policy == CachePolicy.LRU:
            # Least Recently Used
            timestamps = self.data.get('timestamps', {})
            keys_to_delete = sorted(timestamps, key = timestamps.get)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity and not self.is_silenced('cache_policy'): logger.info(f'[{self.cache_field}- LRU] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            self.clear(keys_to_delete)
            return
        
        if self.cache_max_size_policy == CachePolicy.LFU:
            # Least Frequently Used
            key_hits = self.data.get('keyhits', {})
            keys_to_delete = sorted(key_hits, key = key_hits.get)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity and not self.is_silenced('cache_policy'): logger.info(f'[{self.cache_field} - LFU] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            self.clear(keys_to_delete)
            return
        
        if self.cache_max_size_policy == CachePolicy.FIFO:
            # First In First Out
            timestamps = self.data.get('timestamps', {})
            keys_to_delete = sorted(timestamps, key = timestamps.get, reverse = True)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity and not self.is_silenced('cache_policy'): logger.info(f'[{self.cache_field} - FIFO] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            self.clear(keys_to_delete)
            return
        
        if self.cache_max_size_policy == CachePolicy.LIFO:
            # Last In First Out
            timestamps = self.data.get('timestamps', {})
            keys_to_delete = sorted(timestamps, key = timestamps.get)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity and not self.is_silenced('cache_policy'): logger.info(f'[{self.cache_field} - LIFO] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            self.clear(keys_to_delete)
            return
    

    async def acheck_cache_policies(self, key: str, *args, cache_kwargs: Dict[str, Union[bool, int, float, Any]] = None, **kwargs) -> None:
        # sourcery skip: low-code-quality
        """
        Runs the cache policies
        """
        if await self.anum_keys <= self.cache_max_size: return
        num_keys = await self.anum_keys
        if self.verbosity and not self.is_silenced('cache_policy'): logger.info(f'[{self.cache_field}] Cache Max Size Reached: {num_keys}/{self.cache_max_size}. Running Cache Policy: {self.cache_max_size_policy}')
        if self.cache_max_size_policy == CachePolicy.LRU:
            # Least Recently Used
            timestamps = await self.data.aget('timestamps', {})
            keys_to_delete = sorted(timestamps, key = timestamps.get, reverse=True)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity and not self.is_silenced('cache_policy'): logger.info(f'[{self.cache_field} - LRU] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            await self.clear(keys_to_delete)
            return
        
        if self.cache_max_size_policy == CachePolicy.LFU:
            # Least Frequently Used
            key_hits = await self.data.aget('keyhits', {})
            keys_to_delete = sorted(key_hits, key = key_hits.get)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity and not self.is_silenced('cache_policy'): logger.info(f'[{self.cache_field} - LFU] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            await self.clear(keys_to_delete)
            return
        
        if self.cache_max_size_policy == CachePolicy.FIFO:
            # First In First Out
            timestamps = await self.data.aget('timestamps', {})
            keys_to_delete = sorted(timestamps, key = timestamps.get, reverse = True)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity and not self.is_silenced('cache_policy'): logger.info(f'[{self.cache_field} - FIFO] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
            await self.clear(keys_to_delete)
            return
        
        if self.cache_max_size_policy == CachePolicy.LIFO:
            # Last In First Out
            timestamps = await self.data.aget('timestamps', {})
            keys_to_delete = sorted(timestamps, key = timestamps.get)[:num_keys - self.cache_max_size]
            if key in keys_to_delete: keys_to_delete.remove(key)
            if self.verbosity and not self.is_silenced('cache_policy'): logger.info(f'[{self.cache_field} - LIFO] Deleting {len(keys_to_delete)} Keys: {keys_to_delete}')
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
        await self.aadd_hit()
        await self.aexpire_cache_expired_keys()
        if not self.hset_enabled or self.cache_max_size is None: return
        await self.aadd_key_timestamp(key)
        await self.aadd_key_hit(key)
        await self.acheck_cache_policies(key, *args, cache_kwargs = cache_kwargs, **kwargs)

    
    def retrieve(self, key: str, *args, cache_kwargs: Dict[str, Union[bool, int, float, Any]] = None, **kwargs) -> Any:
        """
        Retrieves the value from the cache
        """
        if self.should_overwrite(*args, cache_kwargs = cache_kwargs, **kwargs): 
            if self.super_verbose and not self.is_silenced('cache_overwrite', 'cache', 'retrieve'): logger.info(f'[{self.cache_field}:{key}] Overwriting Cache')
            return ENOVAL
        value = None
        try:
            with self.safely():
                if not self._exists(key):
                    if self.super_verbose and not self.is_silenced('cache_miss', 'cache', 'retrieve'): logger.info(f'[{self.cache_field}:{key}] Not Found')
                    return ENOVAL
                value = self._get(key)
            if value is None: return ENOVAL

        except TimeoutError:
            if self.super_verbose and not self.is_silenced('retrieve'): logger.error(f'[{self.cache_field}:{key}] Retrieve Timeout')
            return ENOVAL
        
        except Exception as e:
            if self.verbosity: logger.trace(f'[{self.cache_field}:{key}] Retrieve Exception', error = e)
            return ENOVAL
        
        # ThreadPooler.threadpool_task(self.validate_cache_policies, key, *args, cache_kwargs = cache_kwargs, **kwargs)
        self.validate_cache_policies(key, *args, cache_kwargs = cache_kwargs, **kwargs)
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
            if self.super_verbose and not self.is_silenced('cache_ovewrite', 'cache', 'retrieve'): logger.info(f'[{self.cache_field}:{key}] Overwriting Cache')
            return ENOVAL
        value = None
        try:
            with self.safely():
                if not await self._exists(key):
                    if self.super_verbose and not self.is_silenced('cache_miss', 'cache', 'retrieve'): logger.info(f'[{self.cache_field}:{key}] Not Found')
                    return ENOVAL
                value = await self._get(key)
            if value is None: return ENOVAL

        except TimeoutError:
            if self.super_verbose: logger.error(f'[{self.cache_field}:{key}] Retrieve Timeout')
            return ENOVAL
        
        except Exception as e:
            if self.verbosity: logger.trace(f'[{self.cache_field}:{key}] Retrieve Exception', error = e)
            return ENOVAL
        
        if not self.disable_background_tasks:
            ThreadPooler.background_task(self.avalidate_cache_policies, key, *args, cache_kwargs = cache_kwargs, **kwargs)
        else:
            await self.avalidate_cache_policies(key, *args, cache_kwargs = cache_kwargs, **kwargs)
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
                self.add_key_expiration(key, (cache_kwargs.get('ttl') or self.ttl))
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
                await self.aadd_key_expiration(key, (cache_kwargs.get('ttl') or self.ttl))
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
        if self.verbosity and not self.is_silenced('post_init'): logger.info(f'[{self.cache_field}] Running Post Init Hook')
        # ThreadPooler.threadpool_task(self.post_init_hook, func, *args, **kwargs)
        self.post_init_hook(func, *args, **kwargs)
        self.has_ran_post_init_hook = True


    async def arun_post_init_hook(self, func: Callable, *args, **kwargs) -> None:
        """
        Runs the post init hook which fires once after the function is initialized
        """
        if not self.has_post_init_hook: return
        if self.has_ran_post_init_hook: return
        if self.verbosity and not self.is_silenced('post_init'): logger.info(f'[{self.cache_field}] Running Post Init Hook')
        ThreadPooler.background_task(self.post_init_hook, func, *args, **kwargs)
        self.has_ran_post_init_hook = True

    def run_post_call_hook(self, result: Any, *args, is_hit: Optional[bool] = None, **kwargs) -> None:
        """
        Runs the post call hook which fires after the function is called
        """
        if not self.has_post_call_hook: return
        if self.super_verbose and not self.is_silenced('post_call'): logger.info(f'[{self.cache_field}] Running Post Call Hook')
        self.post_call_hook(result, *args, is_hit = is_hit, **kwargs)
        # ThreadPooler.threadpool_task(self.post_call_hook, result, *args, is_hit = is_hit, **kwargs)

    async def arun_post_call_hook(self, result: Any, *args, is_hit: Optional[bool] = None, **kwargs) -> None:
        """
        Runs the post call hook which fires after the function is called
        """
        if not self.has_post_call_hook: return
        if self.super_verbose and not self.is_silenced('post_call'): logger.info(f'[{self.cache_field}] Running Post Call Hook')
        ThreadPooler.background_task(self.post_call_hook, result, *args, is_hit = is_hit, **kwargs)
    

    async def _arun_cache_operation(self, cache_key: str, value: Any, *args, cachify_kwargs: Dict[str, Any] = None, **kwargs) -> None:
        """
        Runs the cache operation
        """
        if await self.ashould_cache_value(value, *args, cache_kwargs = cachify_kwargs, **kwargs):
            if self.super_verbose and not self.is_silenced('cache_value', 'cache'): logger.info('Caching Value', prefix = f'{self.cache_field}:{cache_key}', colored = True)
            await self.aset(cache_key, value, *args, cache_kwargs = cachify_kwargs, **kwargs)
        await self.arun_post_call_hook(value, *args, is_hit = False, **kwargs)

    async def arun_cache_operation(self, cache_key: str, value: Any, *args, cachify_kwargs: Dict[str, Any] = None, **kwargs) -> None:
        """
        Runs the cache operation
        """
        if self.disable_background_tasks:
            return await self._arun_cache_operation(cache_key, value, *args, cachify_kwargs = cachify_kwargs, **kwargs)
        ThreadPooler.background_task(self._arun_cache_operation, cache_key, value, *args, cachify_kwargs = cachify_kwargs, **kwargs)


    # def create_sync_decorator(self, func: FunctionT) -> Callable[..., ReturnValueT]:
    def create_sync_decorator(self, func: Callable[FuncP, FuncT]) -> Callable[FuncP, FuncT]:
        """
        Creates the sync wrapper
        """
        self.is_async = False
        if self.retry_enabled:
            _retry_func_wrapper = functools.partial(
                backoff.on_exception,
                backoff.expo, 
                exception = Exception, 
                giveup = self.retry_giveup_callable,
                factor = 5,
            )
            func = _retry_func_wrapper(max_tries = self.retry_max_attempts + 1)(func)
        
        _current_cache_key = None
        _current_was_cached = False

        def is_session_available():
            if self.session_available is None:
                with contextlib.suppress(Exception):
                    self.session.ping()
                    self.session_available = True
            return self.session_available
        

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            """
            Inner wrapper
            """
            nonlocal _current_cache_key, _current_was_cached

            if not is_session_available():
                with contextlib.suppress(Exception):
                    return timed_cache(secs = self.ttl)(func)(*args, **kwargs)
                return func(*args, **kwargs)

            # Set the cache field
            self.build_hash_name(func, *args, **kwargs)
            self.validate_is_class_method(func)
            self.run_post_init_hook(func, *args, **kwargs)
            
            cachify_kwargs, kwargs = self.extract_cache_kwargs(**kwargs)

            # Check if we should disable the cache
            if self.should_disable(*args, cache_kwargs = cachify_kwargs, **kwargs):
                if self.super_verbose and not self.is_silenced('cache_disable', 'cache'): logger.info('Disabling', prefix = self.cache_field, colored = True)
                return func(*args, **kwargs)
            
            # Get the cache key
            cache_key = wrapper.__cache_key__(*args, **kwargs)
            _current_cache_key = cache_key

            
            # Check if we should invalidate
            if self.should_invalidate(*args, cache_kwargs = cachify_kwargs, **kwargs):
                if self.verbosity and not self.is_silenced('cache_invalidate', 'cache'): logger.info('Invalidating', prefix = f'{self.cache_field}:{cache_key}', colored = True)
                self.invalidate_cache(cache_key)
            
            # Check if we have a cache hit
            value = self.retrieve(cache_key, *args, cache_kwargs = cachify_kwargs, **kwargs)
            if value == ENOVAL:
                if self.super_verbose and not self.is_silenced('cache_miss', 'cache'): logger.info('Cache Miss', prefix = f'{self.cache_field}:{cache_key}', colored = True)
                try:
                    value = func(*args, **kwargs)
                    if self.should_cache_value(value, *args, cache_kwargs = cachify_kwargs, **kwargs):
                        if self.super_verbose and not self.is_silenced('cache_value', 'cache'): logger.info('Caching Value', prefix = f'{self.cache_field}:{cache_key}', colored = True)
                        self.set(cache_key, value, *args, cache_kwargs = cachify_kwargs, **kwargs)
                    
                    self.run_post_call_hook(value, *args, is_hit = False, **kwargs)
                    return value
                
                except Exception as e:
                    if self.verbosity: logger.trace(f'[{self.cache_field}:{cache_key}] Exception', error = e)
                    if self.raise_exceptions and e is not None: raise e
                    return None
            _current_was_cached = True
            if self.super_verbose and not self.is_silenced('cache_hit', 'cache'): logger.info('Cache Hit', prefix = f'{self.cache_field}:{cache_key}', colored = True)
            self.run_post_call_hook(value, *args, is_hit = True, **kwargs)
            return value

        def __cache_key__(*args, **kwargs) -> str:
            """
            Returns the cache key
            """
            return self.build_hash_key(*args, **kwargs)
        
        def is_cached() -> bool:
            """
            Returns whether or not the function is cached
            """
            return self._exists(_current_cache_key)
        
        def was_cached() -> bool:
            """
            Returns whether or not the function was cached
            """
            return _current_was_cached
        
        def clear(keys: Optional[Union[str, List[str]]] = None, **kwargs) -> Optional[int]:
            """
            Clears the cache
            """
            return self.clear(keys = keys)
        
        def num_hits(*args, **kwargs) -> int:
            """
            Returns the number of hits
            """
            return self.num_hits
        
        def num_keys(**kwargs) -> int:
            """
            Returns the number of keys
            """
            return self.num_keys
        
        def cache_keys(**kwargs) -> List[str]:
            """
            Returns the keys
            """
            return self.cache_keys
        
        def cache_values(**kwargs) -> List[Any]:
            """
            Returns the values
            """
            return self.cache_values
        
        def cache_items(**kwargs) -> Dict[str, Any]:
            """
            Returns the items
            """
            return self.cache_items
        
        def invalidate_key(key: str, **kwargs) -> int:
            """
            Invalidates the cache
            """
            return self.invalidate_cache(key)
        
        def cache_timestamps(**kwargs) -> Dict[str, float]:
            """
            Returns the timestamps
            """
            return self.cache_timestamps
        
        def cache_keyhits(**kwargs) -> Dict[str, int]:
            """
            Returns the keyhits
            """
            return self.cache_keyhits
        
        def cache_policy(**kwargs) -> Dict[str, Union[int, CachePolicy]]:
            """
            Returns the cache policy
            """
            return {
                'max_size': self.cache_max_size,
                'max_size_policy': self.cache_max_size_policy,
            }

        def cache_config(**kwargs) -> Dict[str, Any]:
            """
            Returns the cache config
            """
            values = self.model_dump(exclude = {'session'})
            for k, v in values.items():
                if callable(v): values[k] = get_function_name(v)
            return values

        def cache_info(**kwargs) -> Dict[str, Any]:
            """
            Returns the info for the cache
            """
            return self.cache_info
        
        def cache_update(**kwargs) -> Dict[str, Any]:
            """
            Updates the cache config
            """
            self.update(**kwargs)
            return cache_config(**kwargs)
        
        wrapper.__cache_key__ = __cache_key__
        wrapper.is_cached = is_cached
        wrapper.was_cached = was_cached
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



    def create_async_decorator(
        self,
        func: Callable[FuncP, FuncT]
    ) -> Callable[FuncP, Awaitable[FuncT]]:
        # func: FunctionT,
    # ) -> Callable[..., ReturnValueT]:
        """
        Creates the async wrapper
        """
        self.is_async = True
        if self.retry_enabled:
            _retry_func_wrapper = functools.partial(
                backoff.on_exception,
                backoff.expo, 
                exception = Exception, 
                giveup = self.retry_giveup_callable,
                factor = 5,
            )
            func = _retry_func_wrapper(max_tries = self.retry_max_attempts + 1)(func)
        
        _current_cache_key = None
        _current_was_cached = False

        async def is_session_available():
            if self.session_available is None:
                with contextlib.suppress(Exception):
                    with anyio.move_on_after(1.0):
                        if await self.session.aping():
                            self.session_available = True
            return self.session_available

        

        @functools.wraps(func)
        async def wrapper(*args: FuncP.args, **kwargs: FuncP.kwargs) -> FuncT:
            """
            Inner wrapper
            """
            nonlocal _current_cache_key, _current_was_cached
            if not await is_session_available():
                with contextlib.suppress(Exception):
                    return await timed_cache(secs = self.ttl)(func)(*args, **kwargs)
                return await func(*args, **kwargs)

            # Set the cache field
            await self.abuild_hash_name(func, *args, **kwargs)
            self.validate_is_class_method(func)
            await self.arun_post_init_hook(func, *args, **kwargs)
            cachify_kwargs, kwargs = self.extract_cache_kwargs(**kwargs)

            # Check if we should disable the cache
            if await self.ashould_disable(*args, cache_kwargs = cachify_kwargs, **kwargs):
                if self.super_verbose and not self.is_silenced('cache_disable', 'cache'): logger.info('Disabling', prefix = self.cache_field, colored = True)
                return await func(*args, **kwargs)
            
            # Get the cache key
            cache_key = await wrapper.__cache_key__(*args, **kwargs)
            _current_cache_key = cache_key
            
            # Check if we should invalidate
            if await self.ashould_invalidate(*args, cache_kwargs = cachify_kwargs, **kwargs):
                if self.verbosity and not self.is_silenced('cache_invalidate', 'cache'): logger.info('Invalidating', prefix = f'{self.cache_field}:{cache_key}', colored = True)
                await self.invalidate_cache(cache_key)
            
            # Check if we have a cache hit
            value = await self.aretrieve(cache_key, *args, cache_kwargs = cachify_kwargs, **kwargs)
            if value == ENOVAL:
                if self.super_verbose and not self.is_silenced('cache_miss', 'cache'): logger.info('Cache Miss', prefix = f'{self.cache_field}:{cache_key}', colored = True)
                try:
                    value = await func(*args, **kwargs)
                    await self.arun_cache_operation(cache_key, value, *args, cachify_kwargs = cachify_kwargs, **kwargs)
                    # if await self.ashould_cache_value(value, *args, cache_kwargs = cachify_kwargs, **kwargs):
                    #     if self.super_verbose and not self.is_silenced('cache_value', 'cache'): logger.info('Caching Value', prefix = f'{self.cache_field}:{cache_key}', colored = True)
                    #     await self.aset(cache_key, value, *args, cache_kwargs = cachify_kwargs, **kwargs)
                    # await self.arun_post_call_hook(value, *args, is_hit = False, **kwargs)
                    return value
                
                except Exception as e:
                    if self.verbosity: logger.trace(f'[{self.cache_field}:{cache_key}] Exception', error = e)
                    if self.raise_exceptions and e is not None: raise e
                    return None
            
            _current_was_cached = True
            if self.super_verbose and not self.is_silenced('cache_hit', 'cache'): logger.info('Cache Hit', prefix = f'{self.cache_field}:{cache_key}', colored = True)
            await self.arun_post_call_hook(value, *args, is_hit = True, **kwargs)
            return value

        async def __cache_key__(*args, **kwargs) -> str:
            """
            Returns the cache key
            """
            return await self.abuild_hash_key(*args, **kwargs)
        
        def is_cached() -> bool:
            """
            Returns whether or not the function is cached
            """
            return self._exists(_current_cache_key)
        
        def was_cached() -> bool:
            """
            Returns whether or not the function was cached
            """
            return _current_was_cached
                

        async def clear(keys: Optional[Union[str, List[str]]] = None, **kwargs) -> Optional[int]:
            """
            Clears the cache
            """
            return await self.clear(keys = keys)
        
        async def num_hits(*args, **kwargs) -> int:
            """
            Returns the number of hits
            """
            return await self.anum_hits
        
        async def num_keys(**kwargs) -> int:
            """
            Returns the number of keys
            """
            return await self.anum_keys
        
        async def cache_keys(**kwargs) -> List[str]:
            """
            Returns the keys
            """
            return await self.acache_keys
        
        async def cache_values(**kwargs) -> List[Any]:
            """
            Returns the values
            """
            return await self.acache_values
        
        async def cache_items(**kwargs) -> Dict[str, Any]:
            """
            Returns the items
            """
            return await self.acache_items
        
        async def invalidate_key(key: str, **kwargs) -> int:
            """
            Invalidates the cache
            """
            return await self.invalidate_cache(key)
        
        async def cache_timestamps(**kwargs) -> Dict[str, float]:
            """
            Returns the timestamps
            """
            return await self.acache_timestamps
        
        async def cache_keyhits(**kwargs) -> Dict[str, int]:
            """
            Returns the keyhits
            """
            return await self.acache_keyhits
        
        async def cache_policy(**kwargs) -> Dict[str, Union[int, CachePolicy]]:
            """
            Returns the cache policy
            """
            return {
                'max_size': self.cache_max_size,
                'max_size_policy': self.cache_max_size_policy,
            }

        async def cache_config(**kwargs) -> Dict[str, Any]:
            """
            Returns the cache config
            """
            values = self.model_dump(exclude = {'session'})
            for k, v in values.items():
                if callable(v): values[k] = get_function_name(v)
            return values

        async def cache_info(**kwargs) -> Dict[str, Any]:
            """
            Returns the info for the cache
            """
            return await self.acache_info
        
        async def cache_update(**kwargs) -> Dict[str, Any]:
            """
            Updates the cache config
            """
            self.update(**kwargs)
            return await cache_config(**kwargs)


        wrapper.__cache_key__ = __cache_key__
        wrapper.is_cached = is_cached
        wrapper.was_cached = was_cached
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
    


    def __call__(
        self,
        function: Callable[FuncP, FuncT]
    ) -> Callable[FuncP, Union[FuncT, Awaitable[FuncT]]]:
    #     function: FunctionT,
    # ) -> Callable[..., ReturnValueT]:
        """
        Performs the decorator
        """
        try:
            if not self.is_enabled: return function
        except Exception as e:
            logger.error(f'Error in Cachify Function {function.__name__}: {e}')
            return function
        if self.verbosity and self.verbosity > 4:
            logger.info(f'[{self.cache_field}] Cachifying Function: {get_function_name(function)} ({is_coro_func(function)}), {self.model_dump()}')
        if is_coro_func(function):
            return self.create_async_decorator(function)
        return self.create_sync_decorator(function)
            