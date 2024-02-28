from __future__ import annotations

import anyio
import time
import uuid
import inspect
import signal
import xxhash
import functools
from lazyops.libs.pooler import ensure_coro, is_coro_func
from lazyops.utils.lazy import (
    import_string,
    lazy_import,
    validate_callable,
    get_obj_class_name,
    extract_obj_init_kwargs,
)
from lazyops.libs.lazyload import lazy_function_wrapper
from typing import Callable, Any, Optional, Union, Type, TypeVar, List, Tuple, Dict, TYPE_CHECKING
from ..types.generic import ENOVAL


def now() -> int:
    """
    Returns the current time in milliseconds
    """
    return int(time.time() * 1000)

def uuid1() -> str:
    """
    Returns a uuid1 string
    """
    return str(uuid.uuid1())

def uuid4() -> str:
    """
    Returns a uuid4 string
    """
    return str(uuid.uuid4())

def millis(s: int) -> int:
    """
    Returns the milliseconds from seconds
    """
    return s * 1000

def seconds(ms: int) -> int:
    """
    Returns the seconds from milliseconds
    """
    return ms / 1000


def get_func_full_name(func: Union[str, Callable]) -> str:
    """
    Returns the function name
    """
    return f"{func.__module__}.{func.__qualname__}" if callable(func) else func


def full_name(func: Callable, follow_wrapper_chains: bool = True) -> str:
    """
    Return full name of `func` by adding the module and function name.

    If this function is decorated, attempt to unwrap it till the original function to use that
    function name by setting `follow_wrapper_chains` to True.
    """
    if follow_wrapper_chains: func = inspect.unwrap(func)
    return f'{func.__module__}.{func.__qualname__}'


def is_classmethod(method: Callable) -> bool:
    """
    Checks if the given method is a classmethod
    """
    bound_to = getattr(method, '__self__', None)
    if not isinstance(bound_to, type):
        # must be bound to a class
        return False
    name = method.__name__
    for cls in bound_to.__mro__:
        descriptor = vars(cls).get(name)
        if descriptor is not None:
            return isinstance(descriptor, classmethod)
    return False


def create_cache_key_from_kwargs(
    base: Optional[str] = None, 
    args: Optional[Tuple[Any]] = None, 
    kwargs: Optional[Dict[str, Any]] = None, 
    typed: Optional[bool] = False,
    exclude: Optional[List[str]] = None,
    exclude_keys: Optional[List[str]] = None,
    exclude_null: Optional[bool] = True,
    exclude_defaults: Optional[bool] = None,
    sep: Optional[str] = ":",
    is_classmethod: Optional[bool] = None,
) -> str:
    """
    Create cache key out of function arguments.
    :param tuple base: base of key
    :param tuple args: function arguments
    :param dict kwargs: function keyword arguments
    :param bool typed: include types in cache key
    :return: cache key tuple
    """
    if is_classmethod and args:  args = args[1:]
    key = args or ()
    if kwargs:
        if exclude: kwargs = {k: v for k, v in kwargs.items() if k not in exclude}
        if exclude_null: kwargs = {k: v for k, v in kwargs.items() if v is not None}
        if exclude_keys: kwargs = {k: v for k, v in kwargs.items() if k not in exclude_keys}
        if exclude_defaults: kwargs = {k: v for k, v in kwargs.items() if not inspect.Parameter.empty(v)}
        key += (ENOVAL,)
        sorted_items = sorted(kwargs.items())

        for item in sorted_items:
            key += item

    if typed:
        key += tuple(type(arg) for arg in args)
        if kwargs: key += tuple(type(value) for _, value in sorted_items)

    cache_key = f'{sep}'.join(str(k) for k in key)
    if base is not None: cache_key = f'{base}{sep}{cache_key}'
    return xxhash.xxh64(cache_key.encode()).hexdigest()


def get_ulimits():
    """
    Gets the system ulimits
    """
    import resource
    soft_limit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
    return soft_limit


def set_ulimits(
    max_connections: int = 500,
    verbose: bool = False,
):
    """
    Sets the system ulimits
    to allow for the maximum number of open connections

    - if the current ulimit > max_connections, then it is ignored
    - if it is less, then we set it.
    """
    import resource
    from .logs import logger
    from .lazy import temp_data

    soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft_limit > max_connections: return
    if hard_limit < max_connections and verbose and not temp_data.has_logged('ulimits:warning'):
        logger.warning(f"The current hard limit ({hard_limit}) is less than max_connections ({max_connections}).")
    new_hard_limit = max(hard_limit, max_connections)
    if verbose and not temp_data.has_logged('ulimits:set'): logger.info(f"Setting new ulimits to ({soft_limit}, {hard_limit}) -> ({max_connections}, {new_hard_limit})")
    resource.setrlimit(resource.RLIMIT_NOFILE, (max_connections + 10, new_hard_limit))
    new_soft, new_hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if verbose and not temp_data.has_logged('ulimits:new'): logger.info(f"New Limits: ({new_soft}, {new_hard})")


def patch_parent_class_obj(
    src: object,
    target: object,
    exclude: List[str] = None,
):
    """
    Patches over a child inherited subclass with the new target class
    """
    if exclude is None:
        exclude = [target.__class__.__name__]
    for child in src.__subclasses__():
        # prevent recursive inheritance
        if exclude and (child.__name__ in exclude or child.__qualname__ in exclude or child.__class__.__name__ in exclude):
            continue
        new_bases = tuple(
            b if b.__name__ != target.__name__ else target
            for b in child.__bases__
        )
        print(f"New Bases: {new_bases}")
        setattr(child, '__bases__', new_bases)
        globals()[child.__class__.__name__] = child


# https://stackoverflow.com/questions/2281850/timeout-function-if-it-takes-too-long-to-finish
class timeout:
    def __init__(
        self, 
        seconds: int = 1, 
        error_message: Optional[str] = 'Timeout',
        raise_errors: Optional[bool] = True,
    ):
        """
        A timeout context manager
        """
        self.seconds = seconds
        self.error_message = error_message
        self.raise_errors = raise_errors
    
    def handle_timeout(self, signum, frame):
        """
        Handles the timeout
        """
        if self.raise_errors:
            raise TimeoutError(self.error_message)
    
    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)
    
    def __exit__(self, type, value, traceback):
        signal.alarm(0)

