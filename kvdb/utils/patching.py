"""
Object Patching Methods
"""
import sys
import inspect
import importlib
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
    # if not hasattr(obj, '__kvdb_init__'):
    if not hasattr(obj, '__kvdb_patched__'):
        obj_id = f'{obj.__module__}.{obj.__name__}'

        setattr(obj, '__src_init__', obj.__init__)
        # setattr(obj, '__src_new__', obj.__new__)
        setattr(obj, '__kvdb_obj_id__', obj_id)
        setattr(obj, '__kvdb_initializers__', [])

        def __new__(cls, *args, **kwargs): # type: ignore
            """
            The patched new method
            """
            instance = cls.__src_new__(cls)
            # obj = cls.__src_new__(*args, **kwargs)
            instance.__kvdb_post_init_hook__(*args, **kwargs)
            return instance

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
                initializer(self.__kvdb_obj_id__, *args, **kwargs)

        setattr(obj, '__init__', __kvdb_init__)
        # setattr(obj, '__new__', __new__)
        setattr(obj, '__kvdb_post_init_hook__', __kvdb_post_init_hook__)
        setattr(obj, '__kvdb_patched__', True)
    
    return obj

    
def is_cls_or_self_method(func: Callable) -> bool:
    """
    Checks if the method is from a class or self
    """
    sig = inspect.signature(func)
    return 'self' in sig.parameters or 'cls' in sig.parameters


def is_uninit_method(func: Callable) -> bool:
    """
    Checks if the method is from an non-initialized object
    """
    return type(func) == FunctionType and is_cls_or_self_method(func)

def get_parent_object_class_names(obj: object, *exclude: str) -> Optional[List[str]]:
    """
    Get the parent object class names
    """
    if hasattr(obj, 'mro'):
        bases = [
            f'{base.__module__}.{base.__name__}' for base in obj.mro() if \
                base.__module__ not in {'builtins', 'abc'}
        ]
        if exclude:
            bases = [base for base in bases if base not in exclude]
        return bases
    return None


def get_object_child_class_names(obj: object, *exclude: str) -> Optional[List[str]]:
    """
    Get the child object class names
    """
    subclasses = []
    callers_module = sys._getframe(1).f_globals['__name__']
    classes = inspect.getmembers(sys.modules[callers_module], inspect.isclass)
    for name, child in classes:
        if (child is not obj) and (obj in inspect.getmro(child)):
            if child.__module__ in {'builtins', 'abc'}: continue
            subclasses.append(f'{child.__module__}.{child.__name__}')
    if exclude:
        subclasses = [sub for sub in subclasses if sub not in exclude]
    return subclasses


def get_parent_class_of_function(
    func: Callable,
) -> Optional[Type]:
    """
    Get the parent class of the function
    """
    if hasattr(func, '__qualname__'):
        src_obj_name = func.__qualname__.split('.')[0]
        try:
            src_obj = globals()[src_obj_name]
            bases = [
                base for base in src_obj.mro() if \
                    base.__module__ not in {'builtins', 'abc'}
            ]
            return bases[1] if len(bases) > 1 else None
        except KeyError as e:
            from kvdb.utils.logs import logger
            logger.error(f'Error getting function parent class names: {e}: {globals().keys()}')

    return None

def reload_sys_modules():
    for module in sys.modules.values():
        importlib.reload(module)

def get_function_parent_class_names(
    func: Callable, 
    *exclude: str,
    include_module_name: Optional[bool] = False
) -> Optional[List[str]]:
    """
    Get the parent object class names
    """
    # reload(sys)
    # reload_sys_modules()
    # importlib.reload(sys.modules['kvdb.utils.patching'])
    # importlib.reload(sys.modules['__main__'])
    
    if hasattr(func, '__qualname__'):
        # inspect.getmro(func.__class__)
        src_obj_name = func.__qualname__.split('.')[0]
        try:
            src_obj = globals()[src_obj_name]
            # src_obj = eval(f'{func.__module__}.{src_obj_name}')
            bases = [
                (f'{base.__module__}.{base.__name__}' if include_module_name else base.__name__) for base in src_obj.mro() if \
                    base.__module__ not in {'builtins', 'abc'}
            ]
            if exclude:
                bases = [base for base in bases if base not in exclude]
            return bases
        except KeyError as e:
            from kvdb.utils.logs import logger
            logger.info( inspect.currentframe().f_back.f_locals.keys())
            logger.error(f'[{func.__qualname__}] Error getting function parent class names: {e}: {globals().keys()}')

    return None


