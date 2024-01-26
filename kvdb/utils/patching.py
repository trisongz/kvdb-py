"""
Object Patching Methods
"""
from inspect import signature
from types import MethodType, ModuleType, FunctionType
from typing import Optional, Dict, Any, Callable, List, Union, TypeVar, Tuple, Awaitable, Type, overload, TYPE_CHECKING

def patch_object_for_kvdb(
    obj: ModuleType,
) -> ModuleType:
    """
    Patch an object for KVDB

    - Supports the following
        - tasks
        - cachify
    """
    if not hasattr(obj, '__kvdb_init__'):
        obj_id = f'{obj.__module__}.{obj.__name__}'

        setattr(obj, '__src_init__', obj.__init__)
        setattr(obj, '__kvdb_obj_id__', obj_id)
        setattr(obj, '__kvdb_initializers__', [])

        def __kvdb_init__(self, *args, **kwargs):
            """
            The patched init method
            """
            self.__kvdb_post_init_hook__(*args, **kwargs)

        def __kvdb_post_init_hook__(self, *args, **kwargs):
            """
            The patched post init hook
            """
            self.__src_init__(*args, **kwargs)
            for initializer in self.__kvdb_initializers__:
                if isinstance(initializer, str):
                    initializer = getattr(self, initializer)
                initializer(obj_id = self.__kvdb_obj_id__, *args, **kwargs)

        setattr(obj, '__init__', __kvdb_init__)
        setattr(obj, '__kvdb_post_init_hook__', __kvdb_post_init_hook__)
    
    return obj

    


def is_cls_or_self_method(func: Callable) -> bool:
    """
    Checks if the method is from a class or self
    """
    sig = signature(func)
    return 'self' in sig.parameters or 'cls' in sig.parameters


def is_uninit_method(func: Callable) -> bool:
    """
    Checks if the method is from an non-initialized object
    """
    return type(func) == FunctionType and is_cls_or_self_method(func)







