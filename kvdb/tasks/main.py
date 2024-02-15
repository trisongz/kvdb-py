from __future__ import annotations

"""
The Main Task Queue Manager
"""

import abc
import makefun
import asyncio
import threading
import signal
import contextlib
import multiprocessing as mp
from kvdb.utils.logs import logger, null_logger
from kvdb.utils.helpers import lazy_import, create_cache_key_from_kwargs
from kvdb.utils.patching import (
    patch_object_for_kvdb, 
    is_uninit_method, 
    get_function_parent_class_names,
    get_object_child_class_names,
    get_parent_object_class_names,
)
from lazyops.libs.proxyobj import ProxyObject, LockedSingleton
from lazyops.libs.abcs.utils.helpers import update_dict
from types import ModuleType
from typing import Optional, Dict, Any, Union, TypeVar, AsyncGenerator, Iterable, Callable, Set, Type, Awaitable, List, Tuple, Literal, TYPE_CHECKING, overload
from .types import (
    Ctx,
    FunctionT,
    TaskPhase,
    TaskResult,
    ReturnValue, 
    ReturnValueT,
    AttributeMatchType,
    ObjectType,
    TaskFunction,
)
from .tasks import QueueTasks
from . import wraps

if TYPE_CHECKING:
    from kvdb.types.jobs import Job, CronJob
    from .queue import TaskQueue
    from .worker import TaskWorker
    from .abstract import TaskABC



_DEBUG_MODE_ENABLED = False

class QueueTaskManager(abc.ABC, LockedSingleton):
    """
    The Queue Task Manager
    """
    default_queue_name: Optional[str] = 'global'

    def __init__(self, *args, **kwargs):
        """
        Initializes the Queue Task Manager
        """
        from kvdb.configs import settings
        self.queues: Dict[str, QueueTasks] = {}

        self.queue_task_class: Type[QueueTasks] = QueueTasks

        self.task_queues: Dict[str, 'TaskQueue'] = {}
        self.task_queue_class: Type['TaskQueue'] = None
        self.task_queue_hashes: Dict[str, str] = {} # Stores the hash of the task queue to determine whether to reconfigure the task queue

        self.task_workers: Dict[str, 'TaskWorker'] = {}
        self.task_worker_class: Type['TaskWorker'] = None
        self.task_worker_hashes: Dict[str, str] = {} # Stores the hash of the task worker to determine whether to reconfigure the task worker

        self.manager_settings = settings
        self.logger = self.manager_settings.logger
        self.autologger = self.manager_settings.autologger
        self.verbose = self.manager_settings.debug_enabled
        self.lock = threading.Lock()
        self.aqueue_lock = asyncio.Lock()
        self.aworker_lock = asyncio.Lock()
        self.exit_set = False
        self._task_worker_base_index = None
        self._task_compile_completed = False

        # TaskABC Registration
        self._task_registered_abcs: Dict[str, Type['TaskABC']] = {}
        self._task_unregistered_abc_functions: Dict[str, Dict[str, Callable[..., ReturnValueT]]] = {}
        self._task_registered_abc_functions: Dict[str, Set[str]] = {}
        self._task_unregistered_abc_partials: Dict[str, Dict[str, Dict[str, Any]]] = {}

        # Object Registration
        self._task_unregistered_objects: Dict[str, ObjectType] = {}
        self._task_unregistered_object_functions: Dict[str, Dict[str, Callable[..., ReturnValueT]]] = {}
        self._task_registered_object_functions: Dict[str, Set[str]] = {}
        self._task_unregistered_object_partials: Dict[str, Dict[str, Dict[str, Any]]] = {}

        # Defines which abstract classes have been initialized
        # Defines which objects have been initialized
        self._task_initialized_abcs: Dict[str, Set[str]] = {}
        self._task_initialized_objects: Dict[str, Set[str]] = {}

        self._unset_registered_objects: Dict[str, object] = {}
        self._unset_registered_functions: Dict[str, List[Callable[..., ReturnValueT]]] = {}

    def _remove_locks(self):
        """
        Removes the locks
        """
        self.lock = None
        self.aqueue_lock = None
        self.aworker_lock = None
        self.__instance_lock__ = None

    @property
    def task_worker_base_index(self) -> int:
        """
        Gets the task worker base index
        """
        if self._task_worker_base_index is None:
            from lazyops.utils.system import is_in_kubernetes, get_host_name
            if is_in_kubernetes() and get_host_name()[-1].isdigit():
                _base_worker_index = int(get_host_name()[-1])
            else:
                _base_worker_index = 0
            self._task_worker_base_index = _base_worker_index
        return self._task_worker_base_index

    def configure_classes(
        self,
        queue_task_class: Optional[Type[QueueTasks]] = None,
        task_function_class: Optional[Type[TaskFunction]] = None,
        cronjob_class: Optional[Type['CronJob']] = None,

        task_worker_class: Optional[Type['TaskWorker']] = None,
        task_queue_class: Optional[Type['TaskQueue']] = None,
    ):
        """
        Configures the classes
        """
        if queue_task_class and isinstance(queue_task_class, str):
            queue_task_class = lazy_import(queue_task_class)
        if queue_task_class is not None:
            self.queue_task_class = queue_task_class
        if cronjob_class or task_function_class:
            for queue in self.queues.values():
                queue.configure_classes(
                    task_function_class = task_function_class,
                    cronjob_class = cronjob_class,
                )
        if task_worker_class and isinstance(task_worker_class, str):
            task_worker_class = lazy_import(task_worker_class)
        if task_worker_class is None and self.task_worker_class is None:
            from .worker import TaskWorker
            task_worker_class = TaskWorker
        if task_worker_class is not None:
            self.task_worker_class = task_worker_class
        
        if task_queue_class and isinstance(task_queue_class, str):
            task_queue_class = lazy_import(task_queue_class)
        if task_queue_class is None and self.task_queue_class is None:
            from .queue import TaskQueue
            task_queue_class = TaskQueue
        if task_queue_class is not None:
            self.task_queue_class = task_queue_class
    
    
    def create_queue(
        self, 
        queue_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        queue_task_class: Optional[Type[QueueTasks]] = None,
        **kwargs
    ) -> QueueTasks:
        """
        Creates a queue
        """
        queue_name = queue_name or self.default_queue_name
        if queue_name not in self.queues:
            queue_task_class = queue_task_class or self.queue_task_class
            self.queues[queue_name] = queue_task_class(
                queue = queue_name, 
                context = context, 
                **kwargs
            )
        return self.queues[queue_name]

    def get_queue(
        self, 
        queue_name: Optional[str] = None, 
        context: Optional[Dict[str, Any]] = None,
        queue_task_class: Optional[Type[QueueTasks]] = None,
        **kwargs
    ):
        """
        Gets the queue
        """
        queue_name = queue_name or self.default_queue_name
        if queue_name not in self.queues:
            self.create_queue(queue_name = queue_name, context = context, queue_task_class = queue_task_class, **kwargs)
        return self.queues[queue_name]

    def get_queues(
        self,
        queue_names: Optional[Union[str, List[str]]] = None,
    ) -> List[QueueTasks]:
        """
        Gets the queues
        """
        if queue_names is None: queue_names = [self.default_queue_name]
        if isinstance(queue_names, str): queue_names = [queue_names]
        return [
            self.get_queue(queue_name)
            for queue_name in queue_names
        ]
    
    def register_task_queue(
        self, 
        task_queue: 'TaskQueue',
    ) -> QueueTasks:
        """
        Registers the task queue
        """
        if task_queue.queue_name not in self.queues:
            self.queues[task_queue.queue_name] = self.queue_task_class(
                queue = task_queue.queue_name,
            )
        self.queues[task_queue.queue_name].queue = task_queue
        return self.queues[task_queue.queue_name]


    """
    Task Registration Methods
    """

    @overload
    def register(
        self,
        name: Optional[str] = None,
        function: Optional[FunctionT] = None,
        phase: Optional[TaskPhase] = None,
        silenced: Optional[bool] = None,
        silenced_stages: Optional[List[str]] = None,
        default_kwargs: Optional[Dict[str, Any]] = None,
        cronjob: Optional[bool] = None,
        queue_name: Optional[str] = None,
        disable_patch: Optional[bool] = None,
        disable_ctx_in_patch: Optional[bool] = None,
        worker_attributes: Optional[Dict[str, Any]] = None,
        attribute_match_type: Optional[AttributeMatchType] = None,
        fallback_enabled: Optional[bool] = None,
        task_abc: Optional[bool] = None,
        **kwargs
    ) -> Callable[[FunctionT], FunctionT]:
        """
        Registers a function to the queue_name
        """
        ...


    def register(
        self,
        queue_name: Optional[str] = None,
        function: Optional[FunctionT] = None,
        task_abc: Optional[bool] = None,
        **kwargs,
    ) -> Callable[[FunctionT], FunctionT]:
        """
        Registers a function to the queue_name
        """
        if task_abc is True: return self.register_abc(cls_or_func = function, **kwargs)
        queue_name = queue_name or self.default_queue_name
        task_queue = self.get_queue(queue_name)
        return task_queue.register(function = function, **kwargs)

    
    def register_abstract(
        self,
        func: FunctionT,
    ) -> Callable[[FunctionT], FunctionT]:
        """
        Registers a function that is part of an abstract class
        that is not yet initialized
        """
        return wraps.create_register_abstract_function(self, func)

    def register_unset_object(
        self,
        queue_name: Union[str, Callable[..., str]],
        partial_kws: Union[str, Dict[str, Any], Callable[..., Dict[str, Any]]] = None,
        **_kwargs
    ) -> Callable[[ObjectType], ObjectType]:
        """
        Registers an unset object to a TDB queue name.
        """
        return wraps.create_unset_task_init_wrapper(
            self,
            queue_name = queue_name,
            partial_kws = partial_kws,
            **_kwargs
        )


    def register_object(
        self, 
        queue_name: Optional[Union[str, Callable[..., str]]] = None, 
        is_unset: Optional[bool] = False,
        **kwargs
    ) -> ObjectType:
        """
        Register the underlying object
        """
        if is_unset: return self.register_unset_object(queue_name = queue_name, partial_kws = kwargs)
        queue_name = queue_name or self.default_queue_name
        task_queue = self.get_queue(queue_name)
        return task_queue.register_object(**kwargs)

    def register_object_unset_method(
        self,
        **kwargs
    ) -> Callable[[FunctionT], FunctionT]:
        """
        Registers an unset object method function to queue
        """
        kwargs = {k:v for k,v in kwargs.items() if v is not None}

        def decorator(func: FunctionT) -> Callable[..., TaskResult]:
            """
            The decorator
            """
            func_src_obj = func.__qualname__.split('.')[0]
            if func_src_obj not in self._unset_registered_functions:
                self._unset_registered_functions[func_src_obj] = []
            self._unset_registered_functions[func_src_obj].append(func)
            return func
        return decorator


    def register_object_method(self, queue_name: Optional[str] = None, **kwargs) -> Callable[[FunctionT], FunctionT]:
        """
        Registers an object method function to queue
        """
        if queue_name is None and self._unset_registered_objects:
            return self.register_object_unset_method(**kwargs)
        queue_name = queue_name or self.default_queue_name
        task_queue = self.get_queue(queue_name)
        return task_queue.register_object_method(**kwargs)
    

    def _is_obj_method(
        self,
        func: Callable[..., ReturnValueT],
    ) -> bool:
        """
        Determines if the method is a method of a class
        """
        return func.__name__ != func.__qualname__
    
    @staticmethod
    def _get_task_obj_id__(cls_or_func: Union[Type['TaskABC'], Callable]) -> Union[str, Tuple[str, str]]:
        """
        Get the task object id
        """
        if isinstance(cls_or_func, type):
            return f'{cls_or_func.__module__}.{cls_or_func.__name__}'
        elif callable(cls_or_func):
            func_id = f'{cls_or_func.__module__}.{cls_or_func.__qualname__}'
            return func_id.rsplit('.', 1)
        raise ValueError(f'Invalid type {type(cls_or_func)} for cls_or_func')

    """
    v0.0.3 - Object Method Registration 
    :TODO - Add support for registering object methods
    """


    """
    v0.0.2 - Abstract Registration with TaskABC
    """


    def _register_abc_method(
        self,
        func: Callable[..., ReturnValueT],
        **kwargs,
    ):
        """
        Registers an abstract method
        """
        obj_id, func_id = self._get_task_obj_id__(func)
        # logger.info(f'Registering abstract method {obj_id} -> {func_id}: {kwargs}')
        if obj_id not in self._task_unregistered_abc_functions:
            self._task_unregistered_abc_functions[obj_id] = {}
            self._task_registered_abc_functions[obj_id] = set()
            self._task_unregistered_abc_partials[obj_id] = {}
        if func_id not in self._task_unregistered_abc_functions[obj_id]:
            self._task_unregistered_abc_functions[obj_id][func_id] = func
        if kwargs:
            if func_id not in self._task_unregistered_abc_partials[obj_id]:
                self._task_unregistered_abc_partials[obj_id][func_id] = {}
            self._task_unregistered_abc_partials[obj_id][func_id].update(kwargs)
        return func
    

    def _register_abc(
        self,
        cls: Type['TaskABC'],
        **kwargs,
    ) -> Type['TaskABC']:
        """
        Register an abstract `TaskABC` class
        """
        # logger.info(f'Registering abstract class {cls}')
        if cls.__kvdb_obj_id__ in self._task_registered_abcs:
            # logger.error(f'Abstract class {cls} already registered')
            if kwargs:
                if cls.__kvdb_obj_id__ not in self._task_unregistered_abc_partials: self._task_unregistered_abc_partials[cls.__kvdb_obj_id__] = {}
                if 'cls' not in self._task_unregistered_abc_partials[cls.__kvdb_obj_id__]: self._task_unregistered_abc_partials[cls.__kvdb_obj_id__]['cls'] = {}
                self._task_unregistered_abc_partials[cls.__kvdb_obj_id__]['cls'].update(kwargs)
                # logger.info(f'Updating partials for abstract class {cls.__kvdb_obj_id__}: {self._task_unregistered_abc_partials[cls.__kvdb_obj_id__]}')
            return cls
        
        self._task_registered_abcs[cls.__kvdb_obj_id__] = cls
        if cls.__kvdb_obj_id__ in self._task_unregistered_abc_functions:
            # logger.info(f'[L1] Registering abstract method {cls.__kvdb_obj_id__}: {kwargs}')
            for func_id in self._task_unregistered_abc_functions[cls.__kvdb_obj_id__]:
                # logger.info(f'[L1] Registering abstract method {func_id}')
                self._task_registered_abc_functions[cls.__kvdb_obj_id__].add(func_id)
            
            for subcls in cls.__subclasses__():
                # logger.info(f'[L2] Registering abstract subclass {subcls}')
                if subcls.__kvdb_obj_id__ not in self._task_unregistered_abc_functions: 
                    # logger.info(f'[L2] No unregistered functions for subclass {subcls}')
                    continue

                for func_id in self._task_unregistered_abc_functions.get(subcls.__kvdb_obj_id__, {}):
                    # logger.info(f'[L2.1] Compiling abstract subclass method {func_id}')
                    self._task_registered_abc_functions[subcls.__kvdb_obj_id__].add(func_id)

                for func_id in self._task_unregistered_abc_functions.get(cls.__kvdb_obj_id__, {}):
                    # logger.info(f'[L2.2] Compiling abstract method {func_id} for subclass {subcls}')
                    self._task_registered_abc_functions[subcls.__kvdb_obj_id__].add(func_id)

                for _obj_id, _obj_cls in self._task_registered_abcs.items():
                    if _obj_id == cls.__kvdb_obj_id__: continue
                    if _obj_id in _obj_cls.__task_subclasses__:
                        # logger.info(f'[L2.3] Compiling abstract method {func_id} for subclass {subcls}')
                        self._task_registered_abc_functions[subcls.__kvdb_obj_id__].update(self._task_registered_abc_functions[_obj_id])
        cls.__kvdb_initializers__.append('__register_abc_task_init__')
        return cls


    def _compile_abcs(self):  # sourcery skip: low-code-quality
        """
        Compiles the abstract classes
        """
        autologger = logger if _DEBUG_MODE_ENABLED else null_logger
        for obj_id, obj_cls in self._task_registered_abcs.items():
            autologger.info(f'|g|[L0]|e| Compiling abstract class {obj_id}', colored = True)
            base_partial_kws = self._task_unregistered_abc_partials.get(obj_id, {})
            cls_partial_kws = base_partial_kws.pop('cls', {})
            if cls_partial_kws: obj_cls.__add_task_function_partials__('cls', **cls_partial_kws)
            # current_kwargs: Dict[str, Any] = {}

            for subcls in obj_cls.__subclasses__():
                try:
                    parents = get_parent_object_class_names(subcls)
                    last_parent = parents[1]
                    last_parent_partial_kws = self._task_unregistered_abc_partials.get(last_parent, {})
                    autologger.info(f'|g|[L1]|e| Compiling abstract subclass {subcls} -> {last_parent}: {last_parent_partial_kws}', colored = True)
                    if last_parent_partial_kws: 
                        last_parent_partial_kws = {k: v for k, v in last_parent_partial_kws.items() if k not in cls_partial_kws}
                        self._task_unregistered_abc_partials[subcls.__kvdb_obj_id__] = update_dict(
                            self._task_unregistered_abc_partials.get(subcls.__kvdb_obj_id__, {}),
                            last_parent_partial_kws,
                        )
                except Exception as e:
                    autologger.error(f'|r|[L1]|e| Error compiling abstract subclass {subcls}: {e}', colored = True)
                
                if subcls.__kvdb_obj_id__ not in self._task_unregistered_abc_functions: 
                    autologger.info(f'|g|[L2]|e| No unregistered functions for subclass {subcls}', colored = True)
                    continue
                
                
                subcls_partial_kws = self._task_unregistered_abc_partials.get(subcls.__kvdb_obj_id__, {})
                if cls_partial_kws: subcls.__add_task_function_partials__('cls', **cls_partial_kws)
                subcls_cls_partial_kws = subcls_partial_kws.pop('cls', {})
                if subcls_cls_partial_kws: subcls.__add_task_function_partials__('cls', **subcls_cls_partial_kws)


                for func_id in self._task_unregistered_abc_functions.get(subcls.__kvdb_obj_id__, {}):
                    if not hasattr(subcls, func_id): continue
                    self._task_registered_abc_functions[subcls.__kvdb_obj_id__].add(func_id)
                    func_kws = base_partial_kws.get(func_id, {})
                    if func_id in subcls_partial_kws and subcls_partial_kws.get(func_id): func_kws.update(subcls_partial_kws[func_id])
                    if func_kws: 
                        subcls.__add_task_function_partials__(func_id, **func_kws)
                        # current_kwargs[func_id] = func_kws
                    autologger.info(f'|y|[L2.1]|e| Compiling abstract subclass method [{obj_id}] {subcls.__kvdb_obj_id__} -> {func_id}: {func_kws}', colored = True)
                    
                for func_id in self._task_unregistered_abc_functions.get(obj_id, {}):
                    if not hasattr(subcls, func_id): continue
                    # logger.info(f'[L2.2] Compiling abstract method {func_id} for subclass {subcls}')
                    self._task_registered_abc_functions[subcls.__kvdb_obj_id__].add(func_id)
                    func_kws = base_partial_kws.get(func_id, {})
                    if func_id in subcls_partial_kws and subcls_partial_kws.get(func_id): func_kws.update(subcls_partial_kws[func_id])
                    # if func_id in subcls_partial_kws: func_kws.update(subcls_partial_kws[func_id])
                    if func_kws: 
                        subcls.__add_task_function_partials__(func_id, **func_kws)
                        # current_kwargs[func_id] = func_kws

                    autologger.info(f'|b|[L2.2]|e| Compiling abstract subclass method [{obj_id}] {subcls.__kvdb_obj_id__} -> {func_id}: {func_kws}', colored = True)
                    autologger.info('----------')

                for _obj_id, _obj_cls in self._task_registered_abcs.items():
                    if _obj_id == obj_id: continue
                    if _obj_id in _obj_cls.__task_subclasses__ and _obj_id in self._task_registered_abc_functions:
                        obj_funcs = self._task_registered_abc_functions[_obj_id]
                        subcls_obj_funcs = list(filter(lambda x: hasattr(subcls, x), obj_funcs))
                        if not subcls_obj_funcs: continue
                        autologger.info(f'|y|[L2.3]|e| Compiling abstract method {func_id} for subclass {subcls}: {subcls_obj_funcs}', colored = True)
                        self._task_registered_abc_functions[subcls.__kvdb_obj_id__].update(subcls_obj_funcs)
                        for subcls_func_id in subcls_obj_funcs:
                            func_kws = base_partial_kws.get(subcls_func_id, {})
                            if subcls_func_id in subcls_partial_kws and subcls_partial_kws.get(subcls_func_id): func_kws.update(subcls_partial_kws[subcls_func_id])
                            # if current_kwargs.get(subcls_func_id): func_kws.update(current_kwargs[subcls_func_id])
                            if func_kws: subcls.__add_task_function_partials__(subcls_func_id, **func_kws)
                            autologger.info(f'|r|[L2.4]|e| Compiling abstract subclass method [{obj_id}] {subcls.__kvdb_obj_id__} -> {subcls_func_id}: {func_kws}', colored = True)
                    
                    autologger.info('----------')
            autologger.info('--------------------------------------------------')


    @overload
    def register_abc(
        self,
        name: Optional[str] = None,
        cls_or_func: Optional[Union[Type['TaskABC'], FunctionT]] = None,
        phase: Optional[TaskPhase] = None,
        silenced: Optional[bool] = None,
        silenced_stages: Optional[List[str]] = None,
        default_kwargs: Optional[Dict[str, Any]] = None,
        cronjob: Optional[bool] = None,
        queue_name: Optional[str] = None,
        disable_patch: Optional[bool] = None,
        disable_ctx_in_patch: Optional[bool] = None,
        worker_attributes: Optional[Dict[str, Any]] = None,
        attribute_match_type: Optional[AttributeMatchType] = None,
        fallback_enabled: Optional[bool] = None,
        **kwargs
    ) -> Callable[[Union[Type['TaskABC'], FunctionT, 'ReturnValue', 'ReturnValueT']], Union[Type['TaskABC'], FunctionT, 'ReturnValue', 'ReturnValueT']]:
        """
        Registers an abstract class or function to the task queue
        """
        ...

    def register_abc(
        self,
        cls_or_func: Optional[Union[Type['TaskABC'], FunctionT]] = None,
        **kwargs,
    ) -> Callable[[Union[Type['TaskABC'], FunctionT, 'ReturnValueT']], Union[Type['TaskABC'], FunctionT, 'ReturnValueT']]:
        """
        Registers an abstract class or function to the task queue
        """
        if cls_or_func is not None:
            if isinstance(cls_or_func, type):
                return self._register_abc(cls_or_func, **kwargs)
            elif callable(cls_or_func):
                return self._register_abc_method(cls_or_func, **kwargs)
            raise ValueError(f'Invalid type {type(cls_or_func)} for cls_or_func')
        
        def decorator(cls_or_func: Optional[Union[Type['TaskABC'], FunctionT]] = None,) -> Callable[[Union[Type['TaskABC'], FunctionT]], Union[Type['TaskABC'], FunctionT]]:
            """
            The decorator
            """
            if isinstance(cls_or_func, type):
                return self._register_abc(cls_or_func, **kwargs)
            elif callable(cls_or_func):
                return self._register_abc_method(cls_or_func, **kwargs)
            raise ValueError(f'Invalid type {type(cls_or_func)} for cls_or_func')
        return decorator


    
    @overload
    def create_context(
        self,
        queue_name: Optional[str] = None,
        name: Optional[str] = None,
        phase: Optional[TaskPhase] = None,
        silenced: Optional[bool] = None,
        silenced_stages: Optional[List[str]] = None,
        default_kwargs: Optional[Dict[str, Any]] = None,
        cronjob: Optional[bool] = None,
        disable_patch: Optional[bool] = None,
        disable_ctx_in_patch: Optional[bool] = None,
        worker_attributes: Optional[Dict[str, Any]] = None,
        attribute_match_type: Optional[AttributeMatchType] = None,
        fallback_enabled: Optional[bool] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> QueueTasks:
        """
        Creates a context
        """
        ...


    def create_context(
        self,
        queue_name: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> QueueTasks:
        """
        Creates a context
        """
        queue_name = queue_name or self.default_queue_name
        task_queue = self.get_queue(queue_name, context = context)
        # Create a partial
        task_queue.register = makefun.partial(task_queue.register, **kwargs)
        return task_queue

    """
    These methods chain the methods of the task queue
    """
    def _get_queue_names(
        self,
        queue_names: Optional[Union[str, List[str]]] = None,
    ) -> List[str]:
        """
        Gets the queue names
        """
        if isinstance(queue_names, str) and queue_names == 'all': return list(self.queues.keys())
        if queue_names is None: queue_names = [self.default_queue_name]
        if not isinstance(queue_names, list): queue_names = [queue_names]
        if 'all' in queue_names: queue_names = list(self.queues.keys())
        return queue_names


    def get_functions(
        self,
        queue_names: Optional[Union[str, List[str]]] = None,
        worker_attributes: Optional[Dict[str, Any]] = None,
        attribute_match_type: Optional[AttributeMatchType] = None,
    ) -> List[TaskFunction]:
        """
        Gets the functions
        """
        queue_names = self._get_queue_names(queue_names)
        functions = []
        for queue_name in queue_names:
            queue = self.get_queue(queue_name)
            # logger.info(f'Getting functions from queue {queue.queue_name} with {len(queue.functions)}')
            functions.extend(queue.get_functions(worker_attributes, attribute_match_type))
            # functions.extend(self.get_queue(queue_name).get_functions(worker_attributes, attribute_match_type))
        # logger.info(f'Got functions {functions}, ({len(functions)})')
        return functions


    def get_cronjobs(
        self,
        queue_names: Optional[Union[str, List[str]]] = None,
        worker_attributes: Optional[Dict[str, Any]] = None,
        attribute_match_type: Optional[AttributeMatchType] = None,
    ) -> List['CronJob']:
        """
        Gets the cronjobs
        """
        queue_names = self._get_queue_names(queue_names)
        return [
            cronjob
            for queue_name in queue_names
            for cronjob in self.get_queue(queue_name).get_cronjobs(worker_attributes, attribute_match_type)
        ]
    
    async def get_worker_context(
        self,
        ctx: Ctx,
        queue_names: Optional[Union[str, List[str]]] = None,
    ) -> Ctx:
        """
        Gets the worker context
        """
        queue_names = self._get_queue_names(queue_names)
        for queue_name in queue_names:
            ctx = await self.get_queue(queue_name).get_worker_context(ctx)
        return ctx

    async def run_phase(
        self,
        ctx: Ctx,
        phase: TaskPhase,
        queue_names: Optional[Union[str, List[str]]] = None,
    ) -> Ctx:
        """
        Runs the phase
        """
        queue_names = self._get_queue_names(queue_names)
        for queue_name in queue_names:
            ctx = await self.get_queue(queue_name).run_phase(ctx, phase)
        return ctx
    
    async def prepare_ctx(
        self,
        ctx: Ctx,
        queue_names: Optional[Union[str, List[str]]] = None,
    ) -> Ctx:
        """
        Prepares the context
        """
        queue_names = self._get_queue_names(queue_names)
        for queue_name in queue_names:
            ctx = await self.get_queue(queue_name).prepare_ctx(ctx)
        return ctx
    
    @contextlib.contextmanager
    def _get_lock(self, disabled: Optional[bool] = False):
        """
        Gets the lock
        """
        if disabled or self.lock is None:
            yield
        else:
            with self.lock:
                yield

    def compile_tasks(
        self,
        **kwargs
    ) -> None:
        """
        Compiles the unset functions
        """
        if self._task_compile_completed: return
        # Do stuff
        self._compile_abcs()
        self._task_compile_completed = True
    
    def get_task_queue(
        self,
        queue_name: Optional[str] = None,
        task_queue_class: Optional[Type['TaskQueue']] = None,
        disable_lock: Optional[bool] = None,
        **kwargs
    ) -> 'TaskQueue':
        """
        Gets the task queue
        """
        self.compile_tasks()
        queue_name = queue_name or self.default_queue_name
        task_queue_hash = create_cache_key_from_kwargs(base = 'task_queue', kwargs = kwargs)
        if queue_name not in self.task_queues:
            self.configure_classes(task_queue_class = task_queue_class)
            with self._get_lock(disable_lock):
                task_queue_class = task_queue_class or self.task_queue_class
                self.task_queues[queue_name] = task_queue_class(
                    queue_name = queue_name,
                    **kwargs
                )
                self.task_queue_hashes[queue_name] = task_queue_hash
        
        elif task_queue_hash != self.task_queue_hashes.get(queue_name):
            with self._get_lock(disable_lock):
                self.task_queues[queue_name].configure(**kwargs)
                self.task_queue_hashes[queue_name] = task_queue_hash

        return self.task_queues[queue_name]
    
    async def aget_task_queue(
        self,
        queue_name: Optional[str] = None,
        task_queue_class: Optional[Type['TaskQueue']] = None,
        **kwargs
    ) -> 'TaskQueue':
        """
        Gets the task queue
        """
        self.compile_tasks()
        queue_name = queue_name or self.default_queue_name
        task_queue_hash = create_cache_key_from_kwargs(base = 'task_queue', kwargs = kwargs)
        if queue_name not in self.task_queues:
            self.configure_classes(task_queue_class = task_queue_class)
            async with self.aqueue_lock:
                task_queue_class = task_queue_class or self.task_queue_class
                self.task_queues[queue_name] = task_queue_class(
                    queue_name = queue_name,
                    **kwargs
                )
                self.task_queue_hashes[queue_name] = task_queue_hash
        
        elif task_queue_hash != self.task_queue_hashes.get(queue_name):
            async with self.aqueue_lock:
                self.task_queues[queue_name].configure(**kwargs)
                self.task_queue_hashes[queue_name] = task_queue_hash

        return self.task_queues[queue_name]
    

    def get_worker_queues(
        self,
        queues: Union[List[Union['TaskQueue', str]], 'TaskQueue', str] = None,
        task_queue_class: Optional[Type['TaskQueue']] = None,
        disable_lock: Optional[bool] = None,
        **kwargs
    ) -> List['TaskQueue']:
        """
        Gets the worker context
        """
        self.compile_tasks()
        if queues is None: queues = [self.default_queue_name]
        elif isinstance(queues, str) and queues == 'all': queues = list(self.task_queues.keys())
        if not isinstance(queues, list): queues = [queues]

        worker_queues: List['TaskQueue'] = []
        self.configure_classes(task_queue_class = task_queue_class)
        for queue_name in queues:
            if isinstance(queue_name, str):
                queue  = self.get_task_queue(queue_name, disable_lock = disable_lock, **kwargs)
            else:
                queue = queue_name
            worker_queues.append(queue)
        return worker_queues
    
    async def aget_worker_queues(
        self,
        queues: Union[List[Union['TaskQueue', str]], 'TaskQueue', str] = None,
        task_queue_class: Optional[Type['TaskQueue']] = None,
        **kwargs
    ) -> List['TaskQueue']:
        """
        Gets the worker context
        """
        self.compile_tasks()
        if queues is None: queues = [self.default_queue_name]
        elif isinstance(queues, str) and queues == 'all': queues = list(self.task_queues.keys())
        if not isinstance(queues, list): queues = [queues]
        worker_queues: List['TaskQueue'] = []
        self.configure_classes(task_queue_class = task_queue_class)
        for queue_name in queues:
            if isinstance(queue_name, str):
                queue  = await self.aget_task_queue(queue_name, **kwargs)
            else:
                queue = queue_name
            worker_queues.append(queue)
        return worker_queues

    def get_task_worker(
        self,
        worker_name: Optional[str] = None,
        queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
        task_worker_class: Optional[Type['TaskWorker']] = None,
        disable_lock: Optional[bool] = None,
        queue_config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> 'TaskWorker':
        """
        Gets the task worker
        """
        self.compile_tasks()
        worker_name = worker_name or self.default_queue_name
        task_worker_hash = create_cache_key_from_kwargs(base = 'task_worker', kwargs = kwargs)
        queue_config = queue_config or {}
        if 'task_queue_class' in queue_config:
            task_queue_class = queue_config.pop('task_queue_class')
        else:
            task_queue_class = kwargs.pop('task_queue_class', None)
        if worker_name not in self.task_workers:
            self.configure_classes(task_worker_class = task_worker_class)
            with self._get_lock(disable_lock):
                task_worker_class = task_worker_class or self.task_worker_class
                self.task_workers[worker_name] = task_worker_class(
                    worker_name = worker_name,
                    queues = self.get_worker_queues(
                        queues, 
                        task_queue_class = task_queue_class, 
                        disable_lock = disable_lock, 
                        **queue_config
                    ),
                    **kwargs
                )
                self.task_worker_hashes[worker_name] = task_worker_hash
        
        elif task_worker_hash != self.task_worker_hashes.get(worker_name):
            with self._get_lock(disable_lock):
                self.task_workers[worker_name].configure(
                    queues = self.get_worker_queues(
                        queues, 
                        task_queue_class = task_queue_class, 
                        disable_lock = disable_lock, 
                        **queue_config
                    ),
                    **kwargs
                )
                self.task_worker_hashes[worker_name] = task_worker_hash
        return self.task_workers[worker_name]
    

    async def aget_task_worker(
        self,
        worker_name: Optional[str] = None,
        queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
        task_worker_class: Optional[Type['TaskWorker']] = None,
        **kwargs
    ) -> 'TaskWorker':
        """
        Gets the task worker
        """
        self.compile_tasks()
        worker_name = worker_name or self.default_queue_name
        task_worker_hash = create_cache_key_from_kwargs(base = 'task_worker',kwargs = kwargs)
        if worker_name not in self.task_workers:
            self.configure_classes(task_worker_class = task_worker_class)
            async with self.aworker_lock:
                task_worker_class = task_worker_class or self.task_worker_class
                self.task_workers[worker_name] = task_worker_class(
                    worker_name = worker_name,
                    queues = await self.aget_worker_queues(queues, kwargs.get('task_queue_class', None), **kwargs),
                    **kwargs
                )
                self.task_worker_hashes[worker_name] = task_worker_hash
        
        elif task_worker_hash != self.task_worker_hashes.get(worker_name):
            async with self.aworker_lock:
                self.task_workers[worker_name].configure(
                    queues = await self.aget_worker_queues(queues, kwargs.get('task_queue_class', None), **kwargs),
                    **kwargs
                )
                self.task_worker_hashes[worker_name] = task_worker_hash
        return self.task_workers[worker_name]

    def register_task_worker(
        self, 
        task_worker: 'TaskWorker',
    ) -> QueueTasks:
        """
        Registers the task worker
        """
        if task_worker.worker_name not in self.task_workers:
            self.task_workers[task_worker.worker_name] = task_worker

    def get_task_worker_from_import(
        self,
        worker_name: Optional[str] = None,
        worker_cls: Optional[str] = None,
        worker_config: Optional[Dict[str, Any]] = None,
        queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
        task_worker_class: Optional[Type['TaskWorker']] = None,
        disable_lock: Optional[bool] = None,
        queue_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> 'TaskWorker':
        """
        Initializes a TaskWorker from an imported worker_cls or worker_config
        """
        worker_config = worker_config or {}
        if isinstance(worker_cls, str):
            worker_cls: 'TaskQueue' = lazy_import(worker_cls)
            if isinstance(worker_cls, type):
                task_worker_class = worker_cls
            else:
                queue_kwargs = queue_kwargs or {}
                worker_cls.configure(
                    worker_name = worker_name,
                    queues = self.get_worker_queues(
                        queues, 
                        disable_lock = disable_lock, 
                        **queue_kwargs,
                    ),
                    **worker_config,
                    **kwargs
                )
                return worker_cls
        
        return self.get_task_worker(worker_name = worker_name, queues = queues, task_worker_class = task_worker_class, disable_lock = disable_lock, **worker_config, **kwargs)


    """
    Passthrough Methods
    """

    @overload
    async def enqueue(
        self, 
        job_or_func: Union[Job, str, Callable],
        *args,
        queue_name: Optional[str] = None,
        key: Optional[str] = None,
        timeout: Optional[int] = None,
        retries: Optional[int] = None,
        ttl: Optional[int] = None,
        retry_delay: Optional[int] = None,
        retry_backoff: Optional[int] = None,
        worker_id: Optional[str] = None,
        worker_name: Optional[str] = None,
        job_callback: Optional[Callable] = None,
        job_callback_kwargs: Optional[Dict] = None,
        return_existing_job: bool = False,
        **kwargs
    ) -> Optional[Job]:
        """
        Enqueue a job by instance or string.

        Kwargs can be arguments of the function or properties of the job.
        If a job instance is passed in, it's properties are overriden.
        """
        ...

    async def enqueue(
        self, 
        job_or_func: Union[Job, str, Callable],
        *args,
        queue_name: Optional[str] = None,
        **kwargs
    ) -> Optional[Job]:
        """
        Enqueue a job by instance or string.

        Kwargs can be arguments of the function or properties of the job.
        If a job instance is passed in, it's properties are overriden.
        """
        task_queue = self.get_task_queue(queue_name)
        return await task_queue.enqueue(job_or_func, *args, **kwargs)

    @overload
    async def apply(
        self, 
        job_or_func: Union[Job, str, Callable],
        key: Optional[str] = None,
        timeout: Optional[int] = None,
        retries: Optional[int] = None,
        ttl: Optional[int] = None,
        retry_delay: Optional[int] = None,
        retry_backoff: Optional[int] = None,
        worker_id: Optional[str] = None,
        worker_name: Optional[str] = None,
        job_callback: Optional[Callable] = None,
        job_callback_kwargs: Optional[Dict] = None,
        queue_name: Optional[str] = None,

        broadcast: Optional[bool] = None,
        worker_names: Optional[List[str]] = None,
        worker_selector: Optional[Callable] = None,
        worker_selector_args: Optional[List] = None,
        worker_selector_kwargs: Optional[Dict] = None,
        workers_selected: Optional[List[Dict[str, str]]] = None,
        return_all_results: Optional[bool] = False,
        
        **kwargs
    ) -> Optional[Any]:
        """
        Enqueue a job and wait for its result.

        If the job is successful, this returns its result.
        If the job is unsuccessful, this raises a JobError.
        """
        ...
    
    async def apply(
        self, 
        job_or_func: Union[Job, str, Callable],
        queue_name: Optional[str] = None,
        **kwargs
    ) -> Optional[Any]:
        """
        Enqueue a job and wait for its result.

        If the job is successful, this returns its result.
        If the job is unsuccessful, this raises a JobError.
        """
        task_queue = self.get_task_queue(queue_name)
        return await task_queue.apply(job_or_func, **kwargs)

    @overload    
    async def broadcast(
        self,
        job_or_func: Union[Job, str],
        enqueue: Optional[bool] = True,
        queue_name: Optional[str] = None,
        worker_names: Optional[List[str]] = None,
        worker_selector: Optional[Callable] = None,
        worker_selector_args: Optional[List] = None,
        worker_selector_kwargs: Optional[Dict] = None,
        workers_selected: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> List[Job]:
        """
        Broadcast a job to all nodes and collect all of their results.
        
        job_or_func: Same as Queue.enqueue
        kwargs: Same as Queue.enqueue
        timeout: How long to wait for the job to complete before raising a TimeoutError
        worker_names: List of worker names to run the job on. If provided, will run on these specified workers.
        worker_selector: Function that takes in a list of workers and returns a list of workers to run the job on. If provided, worker_names will be ignored.
        """
        ...

    async def broadcast(
        self,
        job_or_func: Union[Job, str],
        queue_name: Optional[str] = None,
        **kwargs
    ) -> List[Job]:
        """
        Broadcast a job to all nodes and collect all of their results.
        
        job_or_func: Same as Queue.enqueue
        kwargs: Same as Queue.enqueue
        timeout: How long to wait for the job to complete before raising a TimeoutError
        worker_names: List of worker names to run the job on. If provided, will run on these specified workers.
        worker_selector: Function that takes in a list of workers and returns a list of workers to run the job on. If provided, worker_names will be ignored.
        """
        task_queue = self.get_task_queue(queue_name)
        return await task_queue.broadcast(job_or_func, **kwargs)


    @overload
    async def map(
        self, 
        job_or_func: Union[Job, str],
        iter_kwargs: Iterable[Dict], 
        return_exceptions: bool = False, 
        broadcast: Optional[bool] = False,
        queue_name: Optional[str] = None,
        worker_names: Optional[List[str]] = None,
        worker_selector: Optional[Callable] = None,
        worker_selector_args: Optional[List] = None,
        worker_selector_kwargs: Optional[Dict] = None,
        workers_selected: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> List[TaskResult]:
        """
        Enqueue multiple jobs and collect all of their results.

        Example::
            try:
                assert await queue.map(
                    "add",
                    [
                        {"a": 1, "b": 2},
                        {"a": 3, "b": 4},
                    ]
                ) == [3, 7]
            except JobError:
                print("any of the jobs failed")

        job_or_func: Same as Queue.enqueue
        iter_kwargs: Enqueue a job for each item in this sequence. Each item is the same
            as kwargs for Queue.enqueue.
        timeout: Total seconds to wait for all jobs to complete. If None (default) or 0, wait forever.
        return_exceptions: If False (default), an exception is immediately raised as soon as any jobs
            fail. Other jobs won't be cancelled and will continue to run.
            If True, exceptions are treated the same as successful results and aggregated in the result list.
        broadcast: If True, broadcast the job to all nodes. Otherwise, only enqueue the job on this node.
        kwargs: Default kwargs for all jobs. These will be overridden by those in iter_kwargs.
        """
        ...

    async def map(
        self, 
        job_or_func: Union[Job, str],
        iter_kwargs: Iterable[Dict], 
        queue_name: Optional[str] = None,
        **kwargs
    ) -> List[TaskResult]:
        """
        Enqueue multiple jobs and collect all of their results.
        """
        task_queue = self.get_task_queue(queue_name)
        return await task_queue.map(job_or_func, iter_kwargs, **kwargs)
            

    @overload
    async def wait_for_job(
        self,
        job: Job,
        source_job: Optional[Job] = None,
        queue_name: Optional[str] = None,
        verbose: Optional[bool] = False,
        raise_exceptions: Optional[bool] = False,
        refresh_interval: Optional[float] = 0.5,
        **kwargs,
    ) -> Any:  # sourcery skip: low-code-quality
        """
        Waits for job to finish
        """
        ...

    async def wait_for_job(
        self,
        job: Job,
        source_job: Optional[Job] = None,
        queue_name: Optional[str] = None,
        verbose: Optional[bool] = False,
        raise_exceptions: Optional[bool] = False,
        refresh_interval: Optional[float] = 0.5,
        **kwargs,
    ) -> Any:  # sourcery skip: low-code-quality
        """
        Waits for job to finish
        """
        task_queue = self.get_task_queue(queue_name)
        return await task_queue.wait_for_job(job, source_job = source_job, verbose = verbose, raise_exceptions = raise_exceptions, refresh_interval = refresh_interval, **kwargs)


    @overload
    async def wait_for_jobs(
        self,
        jobs: List[Job],
        source_job: Optional[Job] = None,
        queue_name: Optional[str] = None,
        verbose: Optional[bool] = False,
        raise_exceptions: Optional[bool] = False,
        refresh_interval: Optional[float] = 0.5,
        **kwargs,
    ) -> List[Any]:  # sourcery skip: low-code-quality
        """
        Waits for jobs to finish
        """
        ...

    async def wait_for_jobs(
        self,
        jobs: List[Job],
        source_job: Optional[Job] = None,
        queue_name: Optional[str] = None,
        verbose: Optional[bool] = False,
        raise_exceptions: Optional[bool] = False,
        refresh_interval: Optional[float] = 0.5,
        **kwargs,
    ) -> List[Any]:  # sourcery skip: low-code-quality
        """
        Waits for jobs to finish
        """
        task_queue = self.get_task_queue(queue_name)
        return await task_queue.wait_for_jobs(jobs, source_job = source_job, verbose = verbose, raise_exceptions = raise_exceptions, refresh_interval = refresh_interval, **kwargs)
    
    @overload
    def as_jobs_complete(
        self,
        jobs: List[Job],
        source_job: Optional[Job] = None,
        queue_name: Optional[str] = None,
        verbose: Optional[bool] = False,
        raise_exceptions: Optional[bool] = False,
        refresh_interval: Optional[float] = 0.5,
        return_results: Optional[bool] = True,
        cancel_func: Optional[Callable] = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:
        # sourcery skip: low-code-quality
        """
        Generator that yields results as they complete
        """
        ...
    
    def as_jobs_complete(
        self,
        jobs: List[Job],
        source_job: Optional[Job] = None,
        queue_name: Optional[str] = None,
        verbose: Optional[bool] = False,
        raise_exceptions: Optional[bool] = False,
        refresh_interval: Optional[float] = 0.5,
        return_results: Optional[bool] = True,
        cancel_func: Optional[Callable] = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:
        # sourcery skip: low-code-quality
        """
        Generator that yields results as they complete
        """
        task_queue = self.get_task_queue(queue_name)
        return task_queue.as_jobs_complete(jobs, source_job = source_job, verbose = verbose, raise_exceptions = raise_exceptions, refresh_interval = refresh_interval, return_results = return_results, cancel_func = cancel_func, **kwargs)


    @overload
    def __call__(
        self,
        job_or_func: Union[Job, str, Callable],
        *args,
        queue_name: Optional[str] = None,
        blocking: Optional[bool] = False,
        broadcast: Optional[bool] = None,
        return_existing_job: bool = True,
        **kwargs,
    ) -> TaskResult:
        """
        Enqueues or applies a job.
        """
        ...

    def __call__(
        self,
        job_or_func: Union[Job, str, Callable],
        *args,
        queue_name: Optional[str] = None,
        blocking: Optional[bool] = False,
        broadcast: Optional[bool] = None,
        return_existing_job: bool = True,
        **kwargs,
    ) -> TaskResult:
        """
        Enqueues or applies a job.
        """
        task_queue = self.get_task_queue(queue_name)
        return task_queue(job_or_func, *args, blocking = blocking, broadcast = broadcast, return_existing_job = return_existing_job, **kwargs)



TaskManager: QueueTaskManager = ProxyObject(obj_cls = QueueTaskManager)