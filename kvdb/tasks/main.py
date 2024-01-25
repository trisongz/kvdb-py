from __future__ import annotations

"""
The Main Task Queue Manager
"""

import abc
import anyio
import atexit
import makefun
import asyncio
import threading
import signal
import contextlib
import multiprocessing as mp
from kvdb.utils.logs import logger
from kvdb.utils.helpers import lazy_import, create_cache_key_from_kwargs
from lazyops.libs.proxyobj import ProxyObject, LockedSingleton
from types import ModuleType
from typing import Optional, Dict, Any, Union, TypeVar, AsyncGenerator, Iterable, Callable, Type, Awaitable, List, Tuple, Literal, TYPE_CHECKING, overload
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
from .utils import create_task_worker_loop

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

    # If we start using multiple processes, we need to store the processes and tasks
    task_worker_processes: Dict[str, mp.Process] = {}
    # task_worker_tasks: Dict[str, Tuple[asyncio.Task, asyncio.BaseEventLoop]] = {}
    task_worker_tasks: Dict[str, Union[asyncio.Task, asyncio.BaseEventLoop]] = {}

    def __init__(self, *args, **kwargs):
        """
        Initializes the Queue Task Manager
        """
        from kvdb.configs import settings
        self.settings = settings
        self.logger = self.settings.logger
        self.autologger = self.settings.autologger
        self.verbose = self.settings.debug_enabled
        self.lock = threading.Lock()
        self.aqueue_lock = asyncio.Lock()
        self.aworker_lock = asyncio.Lock()
        self.exit_set = False
        self._task_worker_base_index = None

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
        **kwargs
    ) -> 'TaskWorker':
        """
        Gets the task worker
        """
        worker_name = worker_name or self.default_queue_name
        task_worker_hash = create_cache_key_from_kwargs(base = 'task_worker',kwargs = kwargs)
        task_queue_class = kwargs.pop('task_queue_class', None)
        if worker_name not in self.task_workers:
            self.configure_classes(task_worker_class = task_worker_class)
            with self._get_lock(disable_lock):
                task_worker_class = task_worker_class or self.task_worker_class
                self.task_workers[worker_name] = task_worker_class(
                    worker_name = worker_name,
                    queues = self.get_worker_queues(queues, task_queue_class = task_queue_class, disable_lock = disable_lock, **kwargs),
                    **kwargs
                )
                self.task_worker_hashes[worker_name] = task_worker_hash
        
        elif task_worker_hash != self.task_worker_hashes.get(worker_name):
            with self._get_lock(disable_lock):
                self.task_workers[worker_name].configure(
                    queues = self.get_worker_queues(queues, task_queue_class = task_queue_class, disable_lock = disable_lock, **kwargs),
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
        worker_cls: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
        queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
        task_worker_class: Optional[Type['TaskWorker']] = None,
        disable_lock: Optional[bool] = None,
        **kwargs
    ) -> 'TaskWorker':
        """
        Initializes a TaskWorker from an imported worker_cls or settings
        """
        if isinstance(worker_cls, str):
            worker_cls: 'TaskQueue' = lazy_import(worker_cls)
            if isinstance(worker_cls, type):
                task_worker_class = worker_cls
            else:
                worker_cls.configure(
                    queues = self.get_worker_queues(queues, disable_lock = disable_lock, **kwargs),
                    **kwargs
                )
                return worker_cls
        
        settings = settings or {}
        return self.get_task_worker(queues = queues, task_worker_class = task_worker_class, disable_lock = disable_lock, **settings, **kwargs)


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

    """
    Task Worker Start/Spawn Methods

    - Currently Spawn doesn't work due to thread.locks
    """

    def spawn_task_worker_init(
        self,
        worker_name: Optional[str] = None,
        worker_cls: Optional[str] = None,
        task_worker: Optional['TaskWorker'] = None,
        settings: Optional[Dict[str, Any]] = None,
        queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
        task_worker_class: Optional[Type['TaskWorker']] = None,
        index: Optional[int] = None,
        add_env_name: Optional[bool] = None,
        **kwargs
    ):
        """
        Spawns a TaskWorker from an imported worker_cls or settings
        """
        index = index or 0
        worker_name = worker_name or self.default_queue_name
        if add_env_name is None: add_env_name = self.settings.in_k8s
        if add_env_name and self.settings.app_env.name not in worker_name: worker_name = f'{worker_name}.{self.settings.app_env.name}'
        if str(index) not in worker_name:
            worker_name = f'{worker_name}.{index}'
        if not task_worker:
            task_worker = self.get_task_worker_from_import(worker_name = worker_name, worker_cls = worker_cls, settings = settings, queues = queues, task_worker_class = task_worker_class, disable_lock=True, **kwargs)
        else:
            task_worker.configure(queues = queues, worker_name = worker_name, **kwargs)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(task_worker.start())

    def spawn_task_worker(
        self,
        worker_name: Optional[str] = None,
        worker_cls: Optional[str] = None,
        task_worker: Optional['TaskWorker'] = None,
        settings: Optional[Dict[str, Any]] = None,
        queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
        task_worker_class: Optional[Type['TaskWorker']] = None,
        index: Optional[int] = None,
        add_env_name: Optional[bool] = None,
        **kwargs
    ) -> 'mp.Process':
        """
        Spawns a TaskWorker from an imported worker_cls or settings
        """
        index = index or 0
        if worker_name is None and task_worker: worker_name = task_worker.worker_name
        worker_name = worker_name or self.default_queue_name
        if add_env_name is None: add_env_name = self.settings.in_k8s
        if add_env_name and self.settings.app_env.name not in worker_name: worker_name = f'{worker_name}.{self.settings.app_env.name}'
        if str(index) not in worker_name:
            worker_name = f'{worker_name}.{index}'
        if worker_name in self.task_worker_processes:
            logger.warning(f'Worker {worker_name} already running')
            return
        if task_worker is None:
            task_worker = self.get_task_worker_from_import(worker_name = worker_name, worker_cls = worker_cls, settings = settings, queues = queues, task_worker_class = task_worker_class, disable_lock=True, **kwargs)
        else:
            task_worker.configure(queues = queues, worker_name = worker_name, **kwargs)
        # context = mp.get_context('fork')
        from .types import QueueProcess
        p = QueueProcess(target = create_task_worker_loop, args = (task_worker, ))
        p.start()
        self.task_worker_processes[worker_name] = p
        if not self.exit_set:
            atexit.register(self.stop_task_workers, method = 'spawn')
            self.exit_set = True
        return p

    def spawn_task_workers(
        self,
        num_workers: int = 1,
        worker_name: Optional[str] = None,
        worker_cls: Optional[str] = None,
        task_worker: Optional['TaskWorker'] = None,
        settings: Optional[Dict[str, Any]] = None,
        queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
        task_worker_class: Optional[Type['TaskWorker']] = None,
        index: Optional[Union[int, str]] = 'auto',
        add_env_name: Optional[bool] = None,
        **kwargs
    ) -> List['mp.Process']:
        """
        Spawns a Group of TaskWorkers from an imported worker_cls or settings
        """
        if index == 'auto': index = self.task_worker_base_index
        processes = []
        self._remove_locks()
        for i in range(num_workers):
            p = self.spawn_task_worker(
                worker_name = worker_name,
                worker_cls = worker_cls,
                task_worker = task_worker,
                settings = settings,
                queues = queues,
                task_worker_class = task_worker_class,
                index = index + i,
                add_env_name = add_env_name,
                **kwargs
            )
            processes.append(p)
        return processes


    def start_task_worker(
        self,
        worker_name: Optional[str] = None,
        worker_cls: Optional[str] = None,
        task_worker: Optional['TaskWorker'] = None,
        settings: Optional[Dict[str, Any]] = None,
        queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
        task_worker_class: Optional[Type['TaskWorker']] = None,
        index: Optional[int] = None,
        add_env_name: Optional[bool] = None,
        new_loop: Optional[bool] = True,
        **kwargs
    ) -> Union[asyncio.Task, 'asyncio.AbstractEventLoop']:
        """
        Spawns a TaskWorker from an imported worker_cls or settings
        """
        index = index or 0
        if worker_name is None and task_worker: worker_name = task_worker.worker_name
        worker_name = worker_name or self.default_queue_name
        if add_env_name is None: add_env_name = self.settings.in_k8s
        if add_env_name and self.settings.app_env.name not in worker_name: worker_name = f'{worker_name}.{self.settings.app_env.name}'
        if str(index) not in worker_name:
            worker_name = f'{worker_name}.{index}'
        if worker_name in self.task_worker_processes:
            logger.warning(f'Worker {worker_name} already running')
            return
        if task_worker is None:
            task_worker = self.get_task_worker_from_import(worker_name = worker_name, worker_cls = worker_cls, settings = settings, queues = queues, task_worker_class = task_worker_class, disable_lock=True, **kwargs)
        else:
            task_worker.configure(queues = queues, worker_name = worker_name, **kwargs)
        
        task_or_loop = create_task_worker_loop(task_worker, new_loop = new_loop)
        self.task_worker_tasks[worker_name] = task_or_loop
        if not self.exit_set:
            atexit.register(self.stop_task_workers, method = 'start')
            self.exit_set = True

        return task_or_loop
    
    async def start_task_workers(
        self,
        num_workers: int = 1,
        worker_name: Optional[str] = None,
        worker_cls: Optional[str] = None,
        task_worker: Optional['TaskWorker'] = None,
        settings: Optional[Dict[str, Any]] = None,
        queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
        task_worker_class: Optional[Type['TaskWorker']] = None,
        index: Optional[int] = 'auto',
        add_env_name: Optional[bool] = None,
        new_loop: Optional[bool] = False,
        **kwargs
    ) -> List[Union[asyncio.Task, 'asyncio.AbstractEventLoop']]:
        """
        Spawns a Group of TaskWorkers from an imported worker_cls or settings
        """
        if index == 'auto': index = self.task_worker_base_index
        tasks = []
        for i in range(num_workers):
            task_or_loop = self.start_task_worker(
                worker_name = worker_name,
                worker_cls = worker_cls,
                task_worker = task_worker,
                settings = settings,
                queues = queues,
                task_worker_class = task_worker_class,
                index = index + i,
                add_env_name = add_env_name,
                new_loop = new_loop,
                **kwargs
            )
            await asyncio.sleep(0.5)
            tasks.append(task_or_loop)
        return tasks


    def register_task_worker_start(
        self,
        task_worker: 'TaskWorker',
    ):
        """
        Registers the task worker start
        """
        pass

    def stop_task_worker_spawn(
        self,
        worker_name: str,
        timeout: Optional[int] = 5.0,
        **kwargs
    ):
        """
        Terminates the task worker process
        """
        process = self.task_worker_processes.pop(worker_name, None)
        if process is None: return
        if process._closed: return
        process.join(timeout)
        try:
            process.terminate()
        except Exception as e:
            logger.error(f'Error Stopping process {worker_name}: {e}')
        try:
            signal.pthread_kill(process.ident, signal.SIGKILL)
            process.join(timeout)
            process.terminate()
        except Exception as e:
            logger.error(f'Error Killing process {worker_name}: {e}')
            with contextlib.suppress(Exception):
                process.kill()
                process.close()
    

    def stop_task_worker_start(
        self,
        worker_name: str,
        timeout: Optional[int] = 5.0,
        **kwargs
    ):
        """
        Terminates the task worker loop
        """
        task_or_loop = self.task_worker_tasks.pop(worker_name, None)
        if task_or_loop is None: return

        with anyio.move_on_after(timeout):
            if isinstance(task_or_loop, asyncio.Task):
                task_or_loop.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    asyncio.run_coroutine_threadsafe(task_or_loop, task_or_loop.get_loop()).result()
            else:
                task_or_loop.stop()
                task_or_loop.close()
                

    
    def stop_task_workers(
        self,
        worker_names: Optional[List[str]] = None,
        method: Optional[Literal['spawn', 'start']] = 'start',
        **kwargs
    ):
        """
        Stops the task workers processes
        """
        worker_names = worker_names or list(self.task_worker_processes.keys())
        func = getattr(self, f'stop_task_worker_{method}')
        for worker_name in worker_names:
            func(worker_name, **kwargs)




TaskManager: QueueTaskManager = ProxyObject(obj_cls = QueueTaskManager)