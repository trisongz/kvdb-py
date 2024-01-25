from __future__ import annotations

"""
The Main Task Queue Manager
"""

import abc
import makefun
import threading
from kvdb.utils.logs import logger
from kvdb.utils.helpers import lazy_import, create_cache_key_from_kwargs
from lazyops.libs.proxyobj import ProxyObject, LockedSingleton
from types import ModuleType
from typing import Optional, Dict, Any, Union, TypeVar, Callable, Type, Awaitable, List, Tuple, Literal, TYPE_CHECKING, overload
from .types import (
    Ctx,
    FunctionT,
    TaskPhase,
    TaskResult,
    ReturnValue, 
    ReturnValueT,
    AttributeMatchType,
    TaskFunction,
)
from .tasks import QueueTasks

if TYPE_CHECKING:
    from kvdb.types.jobs import Job, CronJob
    from .queue import TaskQueue
    from .worker import TaskWorker


class QueueTaskManager(abc.ABC, LockedSingleton):
    """
    The Queue Task Manager
    """
    default_queue_name: Optional[str] = 'global'
    queues: Dict[str, QueueTasks] = {}


    queue_task_class: Type[QueueTasks] = QueueTasks

    task_queues: Dict[str, 'TaskQueue'] = {}
    task_queue_class: Type['TaskQueue'] = None
    task_queue_hashes: Dict[str, str] = {} # Stores the hash of the task queue to determine whether to reconfigure the task queue

    task_workers: Dict[str, 'TaskWorker'] = {}
    task_worker_class: Type['TaskWorker'] = None
    task_worker_hashes: Dict[str, str] = {} # Stores the hash of the task worker to determine whether to reconfigure the task worker

    def __init__(self, *args, **kwargs):
        """
        Initializes the Queue Task Manager
        """
        from kvdb.configs import settings
        self.settings = settings
        self.logger = self.settings.logger
        self.autologger = self.settings.autologger
        self.verbose = self.settings.debug_enabled
        self.lock = threading.RLock()

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
        worker_attributes: Optional[Dict[str, Any]] = None,
        attribute_match_type: Optional[AttributeMatchType] = None,
        **kwargs
    ) -> Callable[[FunctionT], FunctionT]:
        """
        Registers a function to the queue_name
        """
        ...


    def register_object(self, queue_name: Optional[str] = None, **_kwargs) -> ModuleType:
        """
        Register the underlying object
        """
        queue_name = queue_name or self.default_queue_name
        task_queue = self.get_queue(queue_name)
        return task_queue.register_object(**_kwargs)


    def register(
        self,
        queue_name: Optional[str] = None,
        **kwargs,
    ) -> Callable[[FunctionT], FunctionT]:
        """
        Registers a function to the queue_name
        """
        queue_name = queue_name or self.default_queue_name
        task_queue = self.get_queue(queue_name)
        # logger.error(f'Registering function to queue {task_queue.queue_name}')
        return task_queue.register(**kwargs)


    def register_object_method(self, queue_name: Optional[str] = None, **kwargs) -> Callable[[FunctionT], FunctionT]:
        """
        Registers an object method function to queue
        """
        queue_name = queue_name or self.default_queue_name
        task_queue = self.get_queue(queue_name)
        return task_queue.register_object_method(**kwargs)

    
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
        worker_attributes: Optional[Dict[str, Any]] = None,
        attribute_match_type: Optional[Literal['any', 'all']] = None,
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
    
    def get_task_queue(
        self,
        queue_name: Optional[str] = None,
        task_queue_class: Optional[Type['TaskQueue']] = None,
        **kwargs
    ) -> 'TaskQueue':
        """
        Gets the task queue
        """
        queue_name = queue_name or self.default_queue_name
        task_queue_hash = create_cache_key_from_kwargs(base = 'task_queue', kwargs = kwargs)
        if queue_name not in self.task_queues:
            self.configure_classes(task_queue_class = task_queue_class)
            with self.lock:
                task_queue_class = task_queue_class or self.task_queue_class
                self.task_queues[queue_name] = task_queue_class(
                    queue_name = queue_name,
                    **kwargs
                )
                self.task_queue_hashes[queue_name] = task_queue_hash
        
        elif task_queue_hash != self.task_queue_hashes.get(queue_name):
            with self.lock:
                self.task_queues[queue_name].configure(**kwargs)
                self.task_queue_hashes[queue_name] = task_queue_hash

        return self.task_queues[queue_name]
    

    def get_worker_queues(
        self,
        queues: Union[List[Union['TaskQueue', str]], 'TaskQueue', str] = None,
        task_queue_class: Optional[Type['TaskQueue']] = None,
        **kwargs
    ) -> List['TaskQueue']:
        """
        Gets the worker context
        """
        if queues is None: queues = [self.default_queue_name]
        elif isinstance(queues, str) and queues == 'all': queues = list(self.task_queues.keys())
        if not isinstance(queues, list): queues = [queues]

        worker_queues: List['TaskQueue'] = []
        self.configure_classes(task_queue_class = task_queue_class)
        for queue_name in queues:
            if isinstance(queue_name, str):
                queue  = self.get_task_queue(queue_name, **kwargs)
            else:
                queue = queue_name
            worker_queues.append(queue)
        return worker_queues
    
    def get_task_worker(
        self,
        worker_name: Optional[str] = None,
        queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
        task_worker_class: Optional[Type['TaskWorker']] = None,
        **kwargs
    ) -> 'TaskWorker':
        """
        Gets the task worker
        """
        worker_name = worker_name or self.default_queue_name
        task_worker_hash = create_cache_key_from_kwargs(base = 'task_worker',kwargs = kwargs)
        if worker_name not in self.task_workers:
            self.configure_classes(task_worker_class = task_worker_class)
            with self.lock:
                task_worker_class = task_worker_class or self.task_worker_class
                self.task_workers[worker_name] = task_worker_class(
                    worker_name = worker_name,
                    queues = self.get_worker_queues(queues, kwargs.get('task_queue_class', None), **kwargs),
                    **kwargs
                )
                self.task_worker_hashes[worker_name] = task_worker_hash
        
        elif task_worker_hash != self.task_worker_hashes.get(worker_name):
            with self.lock:
                self.task_workers[worker_name].configure(
                    queues = self.get_worker_queues(queues, kwargs.get('task_queue_class', None), **kwargs),
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


TaskManager: QueueTaskManager = ProxyObject(obj_cls = QueueTaskManager)