from __future__ import annotations

import functools
from lazyops.libs.pooler import ensure_coro, is_coro_func
from lazyops.utils.lazy import (
    import_string,
    lazy_import,
    validate_callable,
    get_obj_class_name,
    extract_obj_init_kwargs,
)

from typing import Callable, Any, Optional, Union, Type, TypeVar, TYPE_CHECKING


RT = TypeVar('RT')

def lazy_function_wrapper(
    function: Callable[..., RT],
    *function_args,
    **function_kwargs,
) -> Callable[..., RT]:
    """
    Lazy Function
    """
    # Creates a lazily initialized wrapper for the function

    _initialized = False
    _initialized_function = None

    def wrapper_func(func: Callable[..., RT]) -> Callable[..., RT]:
        # Initializes the function
        # @functools.wraps(func)
        def _wrapper(*args, **kwargs) -> RT:
            nonlocal _initialized_function, _initialized
            if not _initialized:
                _initialized_function = function(*function_args, **function_kwargs)
                _initialized = True
            
            if _initialized_function is None:
                # If the function is None, return the original function
                return func(*args, **kwargs)
            
            return _initialized_function(func)(*args, **kwargs)
        return _wrapper
    return wrapper_func