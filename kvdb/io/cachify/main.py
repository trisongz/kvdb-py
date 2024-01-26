from __future__ import annotations

"""
Cachify Component for KVDB

This component is used to cache the results of a function call
"""
import abc


from kvdb.types.common import CachePolicy
from kvdb.utils.lazy import lazy_import
from lazyops.utils import timed_cache
from lazyops.utils.lazy import get_function_name
from lazyops.libs.pooler import ThreadPooler
from lazyops.libs.proxyobj import ProxyObject
from types import ModuleType
from typing import Optional, Dict, Any, Callable, List, Union, TypeVar, Tuple, Awaitable, Type, overload, TYPE_CHECKING

from .base import Cachify, ReturnValue, ReturnValueT, FunctionT
from .cache import CachifyContext

if TYPE_CHECKING:
    from kvdb.components.client import ClientT
    from kvdb.components.session import KVDBSession
    from kvdb.configs import KVDBSettings


class CachifyContextManager(abc.ABC):
    """
    The CachifyManager handles management of the Cachify component
    """

    default_cache_name: Optional[str] = 'global'
    
    def __init__(self, *args, **kwargs):
        """
        Initializes the CachifyManager
        """
        from kvdb.configs import settings
        self.settings: 'KVDBSettings' = settings

        self.cachify_context_class: Type[CachifyContext] = CachifyContext
        self.cachify_contexts: Dict[str, CachifyContext] = {}

        self.cachify_class: Type[Cachify] = Cachify
        self.logger = self.settings.logger
        self.autologger = self.settings.autologger
    

    def configure_classes(
        self,
        cachify_context_class: Optional[Type[CachifyContext]] = None,
        cachify_class: Optional[Type[Cachify]] = None,
    ) -> None:
        """
        Configures the classes
        """
        if cachify_context_class and isinstance(cachify_context_class, str):
            cachify_context_class = lazy_import(cachify_context_class)
        if cachify_context_class is not None:
            self.cachify_context_class = cachify_context_class
        if cachify_class and isinstance(cachify_class, str):
            cachify_class = lazy_import(cachify_class)
        if cachify_class is not None:
            self.cachify_class = cachify_class

    def create_cachify_context(
        self,
        cache_name: Optional[str] = None,
        cachify_class: Optional[Type['Cachify']] = None,
        cachify_context_class: Optional[Type[CachifyContext]] = None,
        session: Optional['KVDBSession'] = None,
        session_name: Optional[str] = None,
        partial_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> CachifyContext:
        """
        Creates a CachifyContext
        """
        cache_name = cache_name or self.default_cache_name
        if cache_name not in self.cachify_contexts:
            cachify_context_class = cachify_context_class or self.cachify_context_class
            self.cachify_contexts[cache_name] = cachify_context_class(
                cache_name = cache_name,
                cachify_class = cachify_class or self.cachify_class,
                session = session,
                session_name = session_name,
                partial_kwargs = partial_kwargs,
                **kwargs,
            )
        return self.cachify_contexts[cache_name]
    
    def get_cachify_context(
        self,
        cache_name: Optional[str] = None,
        **kwargs,
    ) -> CachifyContext:
        """
        Gets a CachifyContext
        """
        cache_name = cache_name or self.default_cache_name
        if cache_name not in self.cachify_contexts:
            self.create_cachify_context(cache_name = cache_name, **kwargs)
        return self.cachify_contexts[cache_name]
    

    @overload
    def register(
        self,
        function: Optional[FunctionT] = None,
        cache_name: Optional[str] = None,
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
        **kwargs,
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

    def register(
        self,
        cache_name: Optional[str] = None,
        function: Optional[FunctionT] = None,
        session: Optional['KVDBSession'] = None,
        session_name: Optional[str] = None,
        session_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Callable[[FunctionT], FunctionT]:  # sourcery skip: default-mutable-arg
        """
        Registers a function with the CachifyManager

        Args:
            cache_name (Optional[str], optional): The name of the cache. Defaults to None.
            function (Optional[FunctionT], optional): The function to register. Defaults to None.
            session (Optional['KVDBSession'], optional): The session to use. Defaults to None.
            session_name (Optional[str], optional): The session name to use. Defaults to None.
            session_kwargs (Optional[Dict[str, Any]], optional): The session kwargs to use. Defaults to None.
        """
        cache_name = cache_name or self.default_cache_name
        cachify_context = self.get_cachify_context(
            cache_name = cache_name,
            session = session,
            session_name = session_name,
            session_kwargs = session_kwargs,
            partial_kwargs = kwargs,
        )
        return cachify_context.register(function = function, **kwargs)
    
    
    def register_object(
        self, 
        cache_name: Optional[str] = None, 
        **kwargs
    ) -> ModuleType:
        """
        Register the underlying object
        """
        cache_name = cache_name or self.default_cache_name
        cachify_context = self.get_cachify_context(cache_name=cache_name, **kwargs)
        return cachify_context.register_object(**kwargs)

    def register_object_method(
        self, 
        cache_name: Optional[str] = None, 
        **kwargs
    ) -> ModuleType:
        """
        Register the underlying object
        """
        cache_name = cache_name or self.default_cache_name
        cachify_context = self.get_cachify_context(cache_name=cache_name, **kwargs)
        return cachify_context.register_object_method(**kwargs)



CachifyManager: CachifyContextManager = ProxyObject(obj_cls = CachifyContextManager)