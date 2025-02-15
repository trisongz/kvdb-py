from __future__ import annotations

"""
Cachify Cache Component for KVDB

This component is used to cache the results of a function call
"""
import abc
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
from kvdb.utils.logs import logger, null_logger
from kvdb.utils.lazy import lazy_import
from kvdb.utils.patching import patch_object_for_kvdb, is_uninit_method, get_parent_object_class_names, get_object_child_class_names
from kvdb.utils.helpers import create_cache_key_from_kwargs, is_coro_func, ensure_coro, full_name, timeout as timeout_ctx, is_classmethod

from lzl.load.utils import get_function_name
from lzo.utils.helpers import is_in_async_loop
from lzl.pool import ThreadPool as ThreadPooler
from lzl.proxied import ProxyObject

# from lazyops.utils import timed_cache
# from lazyops.utils.lazy import get_function_name
# from lazyops.utils.helpers import is_in_async_loop
# from lazyops.libs.pooler import ThreadPooler
# from lazyops.libs.proxyobj import ProxyObject
from types import ModuleType
from typing import Optional, Dict, Any, Callable, List, Union, TypeVar, Tuple, Awaitable, Type, overload, TYPE_CHECKING

from .base import Cachify, ReturnValue, ReturnValueT, FunctionT, FuncT, FuncP

if TYPE_CHECKING:
    from kvdb.components.client import ClientT
    from kvdb.components.session import KVDBSession
    from kvdb.tasks.types import ObjectType



def create_register_abstract_object_subclass_function(
    obj: 'ObjectType',
) -> 'ObjectType':
    """
    Adds a function to the abstract object subclass
    """
    # @classmethod
    def __init_cachify_subclass__(cls, **kwargs):
        cls._cachify_subclasses.append(cls)
        cls.__init_src_subclass__(**kwargs)
    
    if not hasattr(obj, '_cachify_subclasses'):
        setattr(obj, '_cachify_subclasses', [])
        setattr(obj, '__init_src_subclass__', obj.__init_subclass__)
        setattr(obj, '__init_subclass__', __init_cachify_subclass__)
    return obj


class CachifyContext(abc.ABC):
    """
    The CacheContext is used to manage the cache context
    """

    def __init__(
        self,
        cache_name: Optional[str] = None,
        cachify_class: Optional[Type['Cachify']] = None,
        session: Optional['KVDBSession'] = None,
        session_name: Optional[str] = None,
        partial_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initializes the CacheContext
        """
        from kvdb.configs import settings

        self.settings = settings.model_copy()
        self.config = self.settings.cache
        self.cache_name = cache_name
        self._session: Optional['KVDBSession'] = session
        self._session_name: Optional[str] = session_name
        
        self.cachify_contexts: Dict[str, 'Cachify'] = {}
        self.partial_kwargs = partial_kwargs or {}

        self._ctx_available: Optional[bool] = None
        
        cache_config, kwargs = self.config.extract_config_and_kwargs(**kwargs)
        self.config.update_config(**cache_config)
        self.configure_classes(cachify_class = cachify_class, is_init = True)
        self.registered_cachify_object: Dict[str, Dict[str, Dict]] = {}
        self.registered_cachify_validation_func: Dict[str, str] = {}
        self.logger = self.settings.logger
        self.autologger = self.settings.autologger
        self.verbose: Optional[bool] = kwargs.get('verbose', self.settings.debug_enabled)
        # self.has_async_loop = self.settings.is_in_async_loop()
        self._kwargs = kwargs
    
    def configure_classes(
        self,
        cachify_class: Optional[Type['Cachify']] = None,
        is_init: Optional[bool] = False,
    ):
        """
        Configures the classes
        """
        if cachify_class is None and is_init:
            cachify_class = Cachify
        elif cachify_class and isinstance(cachify_class, str):
            cachify_class = lazy_import(cachify_class)
        if cachify_class is not None:
            self.cachify_class = cachify_class

    def bind_session(self, session: 'KVDBSession'):
        """
        Binds the session
        """
        self._session = session

    def _extract_session_kwargs(self) -> Dict[str, Any]:
        """
        Extracts the Session Kwargs
        """
        config = self.settings.client_config.extract_kwargs(
            _prefix = 'session_',
            **self._kwargs,
        )
        for field in self.settings.model_fields:
            if field in self._kwargs:
                config[field] = self._kwargs[field]
            elif f'session_{field}' in self._kwargs:
                config[field] = self._kwargs[f'session_{field}']
        return config
    
    @property
    def has_async_loop(self) -> bool:
        """
        Checks if the current process is running in an async loop
        """
        return is_in_async_loop()

    @property
    def session(self) -> 'KVDBSession':
        """
        Returns the session
        """
        if self._session is None:
            from kvdb.client import KVDBClient
            if self._session_name is not None:
                self._session = KVDBClient.get_session(
                    name = self._session_name,
                    set_as_ctx = False,
                )
            else:
                kwargs = self._extract_session_kwargs()
                if 'url' not in kwargs: kwargs['url'] = self._kwargs.get('url', None)
                if 'db_id' not in kwargs: kwargs['db_id'] = self._kwargs.get('db_id', self.config.db_id)
                self._session = KVDBClient.get_session(
                    name = f'cachify:{self.cache_name}',
                    set_as_ctx = False,
                    **kwargs,
                )
                self._session_name = self._session.name
        return self._session
    
    def create_cachify(self, **kwargs) -> 'Cachify':
        """
        Creates a cachify object
        """
        base_kwargs = self.config.model_dump(exclude_none=True)
        base_kwargs.update(kwargs)
        base_kwargs.update(self.partial_kwargs)
        # self.logger.debug(f'Creating Cachify with kwargs: {base_kwargs}')
        return self.cachify_class(session = self.session, settings = self.settings, **kwargs)


    @contextlib.contextmanager
    def safely(self, timeout: Optional[float] = 2.0):
        """
        Safely wraps the function
        """
        if self.has_async_loop:
            with anyio.move_on_after(timeout = timeout):
                yield
        else:
            with timeout_ctx(timeout, raise_errors = False):
                yield

    @property
    def ctx(self) -> Optional['KVDBSession']:
        """
        Returns the KV Session if it is available
        """
        if self._ctx_available is None:
            with contextlib.suppress(Exception):
                with self.safely():
                    if self.session.ping():
                        self._ctx_available = True
        return self.session if self._ctx_available else None
    

    def add_function(
        self,
        function: Union[Callable, str],
        function_name: Optional[str] = None,
        **kwargs
    ) -> Cachify:
        """
        Adds a function to the cachify context
        """
        cachify = self.create_cachify(
            function_name = function_name or get_function_name(function),
            **kwargs
        )
        if cachify.function_name not in self.cachify_contexts:
            self.cachify_contexts[cachify.function_name] = cachify
        return self.cachify_contexts[cachify.function_name]

    def register_object_method(self, **kwargs) -> Callable[[FunctionT], FunctionT]:
        """
        Registers an object method function to be cached
        """
        kwargs = {k:v for k,v in kwargs.items() if v is not None}
        
        def decorator(func: FunctionT) -> Callable[..., ReturnValueT]:
            """
            The decorator
            """
            task_obj_id = f'{func.__module__}.{func.__qualname__.split(".")[0]}'
            if task_obj_id not in self.registered_cachify_object:
                self.registered_cachify_object[task_obj_id] = {}
            func_name = func.__name__
            if func_name not in self.registered_cachify_object[task_obj_id]:
                self.registered_cachify_object[task_obj_id][func_name] = kwargs
            return func
        return decorator


    def register_object(
        self, 
        validator_function_name: Optional[str] = None,
        debug_enabled: Optional[bool] = None,
        **_kwargs
    ) -> ModuleType:
        """
        Register the underlying object
        """
        partial_kws = {k:v for k,v in _kwargs.items() if v is not None}
        validator_function_name = validator_function_name or 'validate_cachify'
        autologger = logger if debug_enabled else null_logger

        def object_decorator(obj: ModuleType) -> ModuleType:
            """
            The decorator that patches the object
            """
            _obj_id = f'{obj.__module__}.{obj.__name__}'
            autologger.info(f'Registering |g|{_obj_id}|e|', colored = True)
            patch_object_for_kvdb(obj)

            # create_register_abstract_object_subclass_function(obj)
            if _obj_id not in self.registered_cachify_object: self.registered_cachify_object[_obj_id] = {}
            if _obj_id not in self.registered_cachify_validation_func: self.registered_cachify_validation_func[_obj_id] = validator_function_name

            if not hasattr(obj, '__cachify_init__'):

                def __cachify_init__(_self, obj_id: str, *args, **kwargs):
                    """
                    Initializes the object
                    """
                    parent_obj_names = get_parent_object_class_names(obj, _obj_id)
                    __obj_id = f'{_self.__class__.__module__}.{_self.__class__.__name__}'
                    __obj_bases = [f'{base.__module__}.{base.__name__}' for base in _self.__class__.__bases__]
                    __obj_bases = [o for o in __obj_bases if o != __obj_id and o not in parent_obj_names]

                    autologger.info(f'Initializing |g|{__obj_id}|e| with bases: {__obj_bases}', colored = True)
                    autologger.info(f'Parent Objects: {parent_obj_names}, for {_obj_id}, {_self.__cachify_subcls__}', prefix = __obj_id, colored = True)
                    
                    cachify_functions = {}

                    # Register the parent functions first
                    parent_obj_functions = self.registered_cachify_object[obj_id]
                    parent_obj_validator_func = getattr(_self, self.registered_cachify_validation_func[obj_id], None)
                    cachify_validators = {
                        f: parent_obj_validator_func
                        for f in parent_obj_functions
                    }

                    cachify_functions.update(parent_obj_functions)

                    # Handle Subclass level objects
                    for sub_obj_id in _self.__cachify_subcls__:
                        if sub_obj_id not in self.registered_cachify_object: continue
                        subcls_functions = self.registered_cachify_object[sub_obj_id]
                        subcls_validator_func = getattr(_self, self.registered_cachify_validation_func[sub_obj_id], None)
                        cachify_validators.update({
                            f: subcls_validator_func
                            for f in subcls_functions
                        })
                        cachify_functions.update(subcls_functions)
                    
                    # Handle Base Class level objects
                    for base_obj_id in __obj_bases:
                        if base_obj_id not in self.registered_cachify_object: continue
                        base_obj_functions = self.registered_cachify_object[base_obj_id]
                        base_obj_validator_func = getattr(_self, self.registered_cachify_validation_func[base_obj_id], None)
                        cachify_validators.update({
                            f: base_obj_validator_func
                            for f in base_obj_functions
                        })
                        cachify_functions.update(base_obj_functions)
                    
                    # Now we do the actual patching
                    for func, task_partial_kws in cachify_functions.items():
                        if not hasattr(_self, func): 
                            autologger.info(f'Skipping {func} for {__obj_id}')
                            continue
                        
                        autologger.info(f'Patching {func} for {__obj_id}')
                        func_kws = partial_kws.copy()
                        func_kws.update(task_partial_kws)

                        if cachify_validators[func] is not None:
                            func_kws = cachify_validators[func](func, **func_kws)
                            if func_kws is None: continue
                        
                        if 'function_name' not in func_kws:
                            func_kws['function_name'] = f'{_self.__class__.__name__}.{func}'

                        patched_func = self.register(function = getattr(_self, func), **func_kws)
                        setattr(_self, func, patched_func)


                setattr(obj, '__cachify_init__', __cachify_init__)
                setattr(obj, '__cachify_subcls__', [])
                obj.__kvdb_initializers__.append('__cachify_init__')
            else:
                obj.__cachify_subcls__.append(_obj_id)
            
            return obj
        return object_decorator
    


    

    @overload
    def register(
        self,
        function: Callable[FuncP, FuncT],
        **kwargs,
    ) -> Union[Awaitable[FuncT], FuncT]:
        """
        Registers a function to cachify
        """
        ...

    
    @overload
    def register(
        self,
        function: Callable[FuncP, FuncT],
        **kwargs,
    ) -> Callable[FuncP, Union[Awaitable[FuncT], FuncT]]:
        """
        Registers a function to cachify
        """
        async def wrapper(*args: FuncP.args, **kwargs: FuncP.kwargs) -> FuncT:
            ...
        return wrapper
        

    
    @overload
    def register(
        self,
        function: Optional[Union[FunctionT, Callable[FuncP, FuncT]]] = None,
        ttl: Optional[int] = 60 * 10, # 10 minutes
        ttl_kws: Optional[List[str]] = ['cache_ttl'], # The keyword arguments to use for the ttl

        keybuilder: Optional[Callable] = None,
        name: Optional[Union[str, Callable]] = None,
        typed: Optional[bool] = True,
        exclude_keys: Optional[List[str]] = None,
        exclude_null: Optional[bool] = True,
        exclude_exceptions: Optional[Union[bool, List[Exception]]] = True,
        exclude_if: Optional[Callable] = None,
        
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
        silenced_stages: Optional[List[str]] = None,
    ) -> Callable[FuncP, Union[Awaitable[FuncT], FuncT]]:
    # ) -> Callable[[FunctionT], FunctionT]:  # sourcery skip: default-mutable-arg
        
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
        """
        async def wrapper(*args: FuncP.args, **kwargs: FuncP.kwargs) -> FuncT:
            ...
    
        return wrapper



    def register(
        self,
        function: Optional[FunctionT] = None,
        **kwargs,
    ) -> Callable[[FunctionT], FunctionT]:
        """
        Registers a function to cachify
        """
        if function is not None:
            if is_uninit_method(function):
                return self.register_object_method(**kwargs)(function)
            cachify = self.add_function(
                function = function,
                **kwargs,
            )
            return cachify(function)
        
        def decorator(func: FunctionT) -> Callable[..., ReturnValueT]:
            """
            The decorator
            """
            if is_uninit_method(func):
                return self.register_object_method(**kwargs)(func)
            cachify = self.add_function(
                function = func,
                **kwargs,
            )
            return cachify(func)
        return decorator

