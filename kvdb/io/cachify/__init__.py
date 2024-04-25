from __future__ import annotations

"""
Cachify Functions
"""
from kvdb.types.common import CachePolicy
from typing import Optional, Dict, Any, Callable, Awaitable, List, Union, Type, AsyncGenerator, Iterable, Tuple, Literal, TYPE_CHECKING, overload

if TYPE_CHECKING:
    from .base import Cachify, FunctionT
    from kvdb.components.session import KVDBSession
    from .cache import CachifyContext

@overload
def register(
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
    exclude_if: Optional[Callable] = None,

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
        silenced_stages (Optional[List[str]], optional): The stages to silence. Defaults to None.
        session (Optional['KVDBSession'], optional): The session to use. Defaults to None.
        session_name (Optional[str], optional): The session name to use. Defaults to None.
        session_kwargs (Optional[Dict[str, Any]], optional): The session kwargs to use. Defaults to None.
    """
    ...


def register(
    cache_name: Optional[str] = None,
    function: Optional[FunctionT] = None,
    **kwargs,
) -> Union[Callable[[FunctionT], FunctionT], FunctionT]:
    """
    Registers a function for caching

    :param cache_name: The name of the cache
    :param function: The function to register
    """
    from .main import CachifyManager
    return CachifyManager.register(cache_name = cache_name, function = function, **kwargs)


@overload
def register_object(
    cache_name: Optional[str] = None, 
    **kwargs,
) -> object:
    """
    Registers an object for caching

    Args:
        cache_name (Optional[str], optional): The name of the cache. Defaults to None.

    """
    ...

def register_object(
    cache_name: Optional[str] = None, 
    **kwargs,
) -> object:
    """
    Registers an object for caching

    Args:
        cache_name (Optional[str], optional): The name of the cache. Defaults to None.

    """
    from .main import CachifyManager
    return CachifyManager.register_object(cache_name = cache_name, **kwargs)


def register_object_method(
    cache_name: Optional[str] = None, 
    **kwargs
) -> Callable[[FunctionT], FunctionT]:
    """
    Registers an object method for caching

    Args:
        cache_name (Optional[str], optional): The name of the cache. Defaults to None.

    """
    from .main import CachifyManager
    return CachifyManager.register_object_method(cache_name = cache_name, **kwargs)


@overload
def create_context(
    cache_name: Optional[str] = None,
    cachify_class: Optional[Type['Cachify']] = None,
    cachify_context_class: Optional[Type['CachifyContext']] = None,
    session: Optional['KVDBSession'] = None,
    session_name: Optional[str] = None,
    partial_kwargs: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> 'CachifyContext':
    """
    Creates a CachifyContext for registering functions and objects
    """
    ...


def create_context(
    cache_name: Optional[str] = None,
    **kwargs,
) -> 'CachifyContext':
    """
    Creates a CachifyContext for registering functions and objects
    """
    from .main import CachifyManager
    return CachifyManager.create_cachify_context(
        cache_name = cache_name,
        **kwargs,
    )