from __future__ import annotations

"""
Wrapper Functions
"""
import makefun
import functools
from kvdb.utils.logs import logger
from kvdb.utils.helpers import lazy_import, create_cache_key_from_kwargs
from kvdb.utils.patching import (
    patch_object_for_kvdb, 
    is_uninit_method, 
    get_function_parent_class_names,
    get_object_child_class_names,
    get_parent_object_class_names,

)
from typing import Optional, Dict, Any, Union, TypeVar, AsyncGenerator, Iterable, Callable, Type, Awaitable, List, Tuple, Literal, TYPE_CHECKING, overload
from types import ModuleType, FunctionType
from .types import (
    Ctx,
    FunctionT,
    TaskPhase,
    TaskResult,
    ReturnValue, 
    ReturnValueT,
    AttributeMatchType,
    TaskFunction,
    ObjectType,
)
from .utils import AttributeMatchType, get_func_name

if TYPE_CHECKING:
    from kvdb.types.jobs import Job, CronJob
    from .queue import TaskQueue
    from .worker import TaskWorker
    from .tasks import QueueTasks
    from .main import QueueTaskManager

"""
TaskManager Wrappers
"""

def create_unset_task_init_wrapper(
    manager: 'QueueTaskManager',
    queue_name: Union[str, Callable[..., str]],
    partial_kws: Union[str, Dict[str, Any], Callable[..., Dict[str, Any]]] = None,
    **_kwargs
) -> ObjectType:
    """
    Registers an unset object to a TDB queue name.
    """
    _kwargs = {k:v for k,v in _kwargs.items() if v is not None}

    def object_decorator(obj: ObjectType) -> ObjectType:
        """
        The decorator that patches the object
        """
        _obj_name = obj.__name__
        patch_object_for_kvdb(obj)
        if _obj_name not in manager._unset_registered_objects:
            manager._unset_registered_objects[_obj_name] = obj
        
        # if hasattr(obj, '__kvdb_unset_task_init__'): return obj
        if '__kvdb_unset_task_init__' in obj.__kvdb_initializers__: return obj
        # obj = create_register_abstract_object_subclass_function(obj)
        def __kvdb_unset_task_init__(_self, obj_id: str, *args, **kwargs):
            """
            Intiailizes the object for unset tasks
            """
            nonlocal partial_kws, queue_name
            
            if partial_kws is None: partial_kws = {}
            if isinstance(queue_name, str):
                if hasattr(_self, queue_name):
                    _queue_name = getattr(_self, queue_name)
                    if callable(_queue_name):
                        _queue_name = _queue_name()
                else:
                    try:
                        _queue_name = lazy_import(queue_name)
                        if callable(_queue_name):
                            _queue_name = _queue_name()

                    except Exception as e:
                        logger.error(f'Error getting queue name {queue_name} {e}')
                        _queue_name = manager.default_queue_name
            elif callable(queue_name):
                _queue_name = queue_name()
            else:
                logger.error(f'Invalid queue name {queue_name} {type(queue_name)}')
            
            logger.info(f'Initializing unset object {_obj_name} {obj_id} {_queue_name} {partial_kws}')

            if isinstance(partial_kws, str):
                if hasattr(_self, partial_kws):
                    partial_kws = getattr(_self, partial_kws)
                else:
                    try:
                        partial_kws = lazy_import(partial_kws)
                        if callable(partial_kws):
                            partial_kws = partial_kws()
                    except Exception as e:
                        partial_kws = {}
            elif callable(partial_kws):
                partial_kws = partial_kws()
            queue = manager.get_queue(_queue_name)
            # Get all the registered unset methods
            unset_func_methods: List[Callable] = manager._unset_registered_functions.get(_obj_name, [])
            if unset_func_methods:
                for src_func in unset_func_methods:
                    logger.warning(f'Patching unset function {src_func.__name__} {src_func}')
                    patched_func = queue.register_object_function_method(src_func)
                    setattr(_self, src_func.__name__, patched_func)

            task_init_func = queue.create_task_init_function(partial_kws=partial_kws)
            setattr(_self, '__kvdb_task_init__', task_init_func)
            getattr(_self, '__kvdb_task_init__')(_self, obj_id, *args, **kwargs)

            # _manager.__kvdb_task_init__(obj_id, *args, **kwargs)
        
        setattr(obj, '__kvdb_unset_task_init__', __kvdb_unset_task_init__)
        obj.__kvdb_initializers__.append('__kvdb_unset_task_init__')
        return obj
    return object_decorator


def create_register_abstract_function(
    manager: 'QueueTaskManager',
    func: FunctionT,
) -> Callable[[FunctionT], FunctionT]:
    """
    Registers a function that is part of an abstract class
    that is not yet initialized
    """
    func_src_obj = func.__qualname__.split('.')[0]
    if func_src_obj not in manager._unset_registered_functions:
        manager._unset_registered_functions[func_src_obj] = []
    manager._unset_registered_functions[func_src_obj].append(func)
    return func


def create_register_abstract_object_subclass_function(
    obj: ObjectType,
) -> ObjectType:
    """
    Adds a function to the abstract object subclass
    """
    # @classmethod
    def __init_task_subclass__(cls, **kwargs):
        cls._task_subclasses.append(cls)
        cls.__init_src_subclass__(**kwargs)
    

    if not hasattr(obj, '_task_subclasses'):
        setattr(obj, '_task_subclasses', [])
        setattr(obj, '__init_src_subclass__', obj.__init_subclass__)
        setattr(obj, '__init_subclass__', __init_task_subclass__)
    return obj



"""
QueueTask Wrappers
"""



def create_task_init_function(
    queue_task: 'QueueTasks',
    partial_kws: Optional[Dict[str, Any]] = None,
) -> FunctionType:
    """
    Creates the task init function
    """
    partial_kws = partial_kws or {}
    partial_kws = {k:v for k,v in partial_kws.items() if v is not None}
    
    def __kvdb_task_init__(_queue_task, obj_id: str, *args, **kwargs):
        """
        Intiailizes the object for tasks
        """
        task_functions = queue_task.registered_task_object[obj_id]
        child_obj_names = get_object_child_class_names(type(_queue_task), obj_id)
        parent_obj_names = get_parent_object_class_names(type(_queue_task), obj_id)
        # logger.warning(f'[{queue_task.queue_name}] [INIT] {obj_id} {parent_obj_names} {child_obj_names}')

        if parent_obj_names:
            queue_task.has_child_objects = True
            for parent_obj_name in parent_obj_names:
                # logger.info(f'[{queue_task.queue_name}] [PARENT] `{obj_id}` {parent_obj_name} {queue_task.registered_task_object.get(parent_obj_name)}')
                if parent_obj_name not in queue_task.registered_task_object: 
                    queue_task.registered_task_object[parent_obj_name] = {}
                    continue
                
                task_functions.update({k:v for k,v in queue_task.registered_task_object[parent_obj_name].items() if k not in task_functions})
                # task_functions.update(queue_task.registered_task_object[parent_obj_name])
        if child_obj_names:
            for child_obj_name in child_obj_names:
                # logger.info(f'[{queue_task.queue_name}] [CHILD] `{obj_id}` {child_obj_name} {queue_task.registered_task_object.get(child_obj_name)}')
                if child_obj_name not in queue_task.registered_task_object: 
                    queue_task.registered_task_object[child_obj_name] = {}
                    continue
                # logger.info(f'[{queue_task.queue_name}] [CHILD] `{obj_id}` {child_obj_name} {queue_task.registered_task_object[child_obj_name]}')
                task_functions.update({k:v for k,v in queue_task.registered_task_object[child_obj_name].items() if k not in task_functions})
                # task_functions.update(queue_task.registered_task_object[child_obj_name])

        # These are functions that could be used to customize the function name
        function_name_func = getattr(_queue_task, 'get_function_name', None)
        cron_name_func = getattr(_queue_task, 'get_cronjob_name', function_name_func)
        
        # These are functions that validate whether a function should be registered
        validate_function_func = getattr(_queue_task, 'validate_function', None)
        validate_cronjob_func = getattr(_queue_task, 'validate_cronjob', None)

        # Additional properties
        worker_attributes = getattr(_queue_task, 'worker_attributes', None)
        set_registered_function_func = getattr(_queue_task, 'set_registered_function', None)
        
        for func, task_partial_kws in task_functions.items():
            func_kws = partial_kws.copy()
            func_kws.update(task_partial_kws)
            logger.warning(f'[{queue_task.queue_name}] [TASK] {obj_id} {func} {func_kws}')

            if worker_attributes is not None:
                func_kws['worker_attributes'] = worker_attributes
            
            src_func = getattr(_queue_task, func)
            # Allow for customizing of function names
            # if func_kws.get('cron'):
            if 'cron' in func_kws or 'cronjob' in func_kws:
                if validate_cronjob_func is not None:
                    func_kws = validate_cronjob_func(func, **func_kws)
                    if not func_kws: continue
                if cron_name_func: func_kws['name'] = cron_name_func(src_func)
            else:
                if validate_function_func is not None:
                    func_kws = validate_function_func(func, **func_kws)
                if not func_kws: continue
                if function_name_func: func_kws['name'] = function_name_func(src_func)
            
            if 'name' not in func_kws and (child_obj_names or parent_obj_names): 
                _src_func_name = get_func_name(src_func)
                # Replace the first part of the function name with the object name
                _func_name = f'{_queue_task.__class__.__name__}.{_src_func_name.split(".", 1)[-1]}'
                func_kws['name'] = _func_name
                if queue_task.has_child_objects and _src_func_name not in queue_task.child_object_mapping:
                    queue_task.child_object_mapping[_src_func_name] = _func_name

            
            logger.error(f'[{queue_task.queue_name}] [SET] {obj_id} {func} {func_kws}')
            out_func = queue_task.register(function = src_func, **func_kws)
            if not func_kws.get('disable_patch'):
                setattr(_queue_task, func, out_func)
            if set_registered_function_func is not None:
                set_registered_function_func(queue_task.functions[queue_task.last_registered_function], **func_kws)

    return __kvdb_task_init__


def create_register_object_wrapper(
    queue_task: 'QueueTasks', 
    **_kwargs
) -> Callable[[ObjectType], ObjectType]:
    """
    Register the underlying object
    """
    partial_kws = {k:v for k,v in _kwargs.items() if v is not None}

    def object_decorator(obj: ObjectType) -> ObjectType:
        """
        The decorator that patches the object
        """
        _obj_id = f'{obj.__module__}.{obj.__name__}'
        patch_object_for_kvdb(obj)
        if _obj_id not in queue_task.registered_task_object: queue_task.registered_task_object[_obj_id] = {}

        # if hasattr(obj, '__kvdb_task_init__'): return obj
        if '__kvdb_task_init__' in obj.__kvdb_initializers__: return obj
        task_init_func = create_task_init_function(queue_task, partial_kws = partial_kws)
        setattr(obj, '__kvdb_task_init__', task_init_func)
        obj.__kvdb_initializers__.append('__kvdb_task_init__')
        return obj

    return object_decorator

def create_register_object_method_function(
    queue_task: 'QueueTasks', 
    func: 'FunctionT',
    **partial_kws
) -> Callable[..., ModuleType]:
    """
    Register the underlying object
    """
    if not is_uninit_method(func): return func
    task_obj_id = f'{func.__module__}.{func.__qualname__.split(".")[0]}'
    if task_obj_id not in queue_task.registered_task_object:
        queue_task.registered_task_object[task_obj_id] = {}
    func_name = func.__name__
    if func_name not in queue_task.registered_task_object[task_obj_id]:
        queue_task.registered_task_object[task_obj_id][func_name] = partial_kws
    return func


def create_register_object_method_wrapper(
    queue_task: 'QueueTasks', 
    **_kwargs
) -> Callable[..., TaskResult]:
    """
    Register the underlying object
    """
    partial_kws = {k:v for k,v in _kwargs.items() if v is not None}
    def function_decorator(func: FunctionT) -> Callable[..., TaskResult]:
        """
        The decorator
        """
        task_obj_id = f'{func.__module__}.{func.__qualname__.split(".")[0]}'
        if task_obj_id not in queue_task.registered_task_object:
            queue_task.registered_task_object[task_obj_id] = {}
        func_name = func.__name__
        if func_name not in queue_task.registered_task_object[task_obj_id]:
            queue_task.registered_task_object[task_obj_id][func_name] = partial_kws
        return func
    return function_decorator


def create_patch_registered_function_wrapper(
    queue_task: 'QueueTasks',
    function: FunctionT,
    task_function: 'TaskFunction',
    subclass_name: Optional[str] = None,
) -> Callable[..., TaskResult]:
    """
    Creates a wrapper for the registered function
    """
    async def patched_function(*args, blocking: Optional[bool] = True, **kwargs):
        # logger.info(f'[{task_function.name}] [NON METHOD] running task {function.__name__} with args: {args} and kwargs: {kwargs}')
        method_func = queue_task.queue.apply if blocking else queue_task.queue.enqueue
        return await method_func(task_function.name, *args, **kwargs)
    
    if task_function.function_is_method:
        if task_function.function_parent_type == 'instance':
            async def patched_function(_self, *args, blocking: Optional[bool] = True, **kwargs):
                # logger.info(f'[{task_function.name}] [INSTANCE] running task {function.__name__} with args: {args} and kwargs: {kwargs} {_self}')
                method_func = queue_task.queue.apply if blocking else queue_task.queue.enqueue
                return await method_func(task_function.name, *args, **kwargs)
        
        elif task_function.function_parent_type == 'class':
            async def patched_function(_cls, *args, blocking: Optional[bool] = True, **kwargs):
                method_func = queue_task.queue.apply if blocking else queue_task.queue.enqueue
                return await method_func(task_function.name, *args, **kwargs)
    
    qualname = f'{subclass_name}.{function.__name__}' if subclass_name is not None else function.__qualname__
    return makefun.wraps(
        function,
        queue_task.modify_function_signature(
            function, 
            args = ['ctx'] if task_function.function_inject_ctx else None,
            kwargs = {'blocking': True}, 
        ),
        qualname = qualname,
    )(patched_function)

