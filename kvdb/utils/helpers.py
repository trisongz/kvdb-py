from __future__ import annotations

# Lazily handle stuff
import sys
import copy
import pathlib
import asyncio
import inspect
import functools
import importlib.util
from importlib import import_module

from typing import Any, Dict, Callable, Union, Optional, Awaitable, Type, TypeVar, List, Tuple, cast, TYPE_CHECKING
from types import ModuleType

# Lazy Importing
_imported_strings: Dict[str, Any] = {}
_valid_class_init_kwarg: Dict[str, List[str]] = {}

def import_string(dotted_path: str) -> Any:
    """
    Taken from pydantic.utils.
    """
    try:
        module_path, class_name = dotted_path.strip(' ').rsplit('.', 1)
    except ValueError as e:
        raise ImportError(f'"{dotted_path}" doesn\'t look like a module path') from e
    module = import_module(module_path)
    try:
        return getattr(module, class_name)
    except AttributeError as e:
        raise ImportError(f'Module "{module_path}" does not define a "{class_name}" attribute') from e


def lazy_import(dotted_path: str) -> Any:
    """
    Lazily imports a string with caching to avoid repeated imports
    """
    global _imported_strings
    if dotted_path not in _imported_strings:
        _imported_strings[dotted_path] = import_string(dotted_path)
    return _imported_strings[dotted_path]


def validate_callable(value: Optional[Union[str, Callable]]) -> Optional[Callable]:
    """
    Validates if the value is a callable
    """
    if value is None: return None
    return lazy_import(value) if isinstance(value, str) else value


def get_obj_class_name(obj: Any, is_parent: Optional[bool] = None) -> str:
    """
    Returns the module name + class name of an object

    args:
        obj: the object to get the class name of
        is_parent: if True, then it treats the object as unitialized and gets the class name of the parent
    """
    if is_parent is None: is_parent = inspect.isclass(obj)
    if is_parent: return f'{obj.__module__}.{obj.__name__}'
    return f'{obj.__class__.__module__}.{obj.__class__.__name__}'


def is_coro_func(obj, func_name: str = None):
    """
    This is probably in the library elsewhere but returns bool
    based on if the function is a coro
    """
    try:
        if inspect.iscoroutinefunction(obj): return True
        if inspect.isawaitable(obj): return True
        if func_name and hasattr(obj, func_name) and inspect.iscoroutinefunction(getattr(obj, func_name)):
            return True
        return bool(hasattr(obj, '__call__') and inspect.iscoroutinefunction(obj.__call__))

    except Exception:
        return False


def ensure_coro(
    func: Callable[..., Any]
) -> Callable[..., Awaitable[Any]]:
    """
    Ensure that the function is a coroutine
    """
    if asyncio.iscoroutinefunction(func): return func
    @functools.wraps(func)
    async def inner(*args, **kwargs):
        from .pool import Pooler
        return await Pooler.asyncish(func, *args, **kwargs)
    return inner


def extract_obj_init_kwargs(obj: object) -> List[str]:
    """
    Extracts the kwargs that are valid for an object
    """
    global _valid_class_init_kwarg
    obj_name = get_obj_class_name(obj)
    if obj_name not in _valid_class_init_kwarg:
        argspec = inspect.getfullargspec(obj.__init__)
        _args = list(argspec.args)
        _args.extend(iter(argspec.kwonlyargs))
        # Check if subclass of Connection
        if hasattr(obj, "__bases__"):
            for base in obj.__bases__:
                _args.extend(extract_obj_init_kwargs(base))
        _valid_class_init_kwarg[obj_name] = list(set(_args))
    return _valid_class_init_kwarg[obj_name]

