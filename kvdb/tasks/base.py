from __future__ import annotations

"""
Base Task Types
"""

import abc
import makefun
import functools
import contextlib
import asyncio
import threading
from inspect import signature, Parameter
from pydantic import Field, model_validator, validator
from kvdb.types.base import BaseModel
from kvdb.utils.logs import logger
from kvdb.utils.helpers import is_coro_func, lazy_import,  ensure_coro
from lazyops.libs.proxyobj import ProxyObject
from typing import Optional, Dict, Any, Union, TypeVar, Callable, Type, Awaitable, List, Tuple, Literal, TYPE_CHECKING, overload
from .utils import AttributeMatchType, determine_match_from_attributes

if TYPE_CHECKING:
    from kvdb.types.jobs import CronJob, Job, JobStatus
    from .queue import TaskQueue
    from .worker import TaskWorker

CtxObject = TypeVar('CtxObject', 'Job', Dict[str, 'TaskQueue'], Any)
Ctx = Dict[str, CtxObject]


ReturnValue = TypeVar('ReturnValue')
ReturnValueT = Union[ReturnValue, Awaitable[ReturnValue]]
FunctionT = TypeVar('FunctionT', bound = Callable[..., ReturnValueT])

TaskResult = TypeVar('TaskResult', 'Job', Any, Awaitable[Any])
TaskPhase = Literal['context', 'dependency', 'startup', 'shutdown']

"""
The major rework here are the following:

- A worker can handle multiple queues vs the previous version where a worker can only handle one queue

Example:

- Worker 1:
    attrs: ...
    queues: ['queue1', 'queue2']
        functions: ['queue1.func1', 'queue2.func2']
- Worker 2:
    attrs: ...
    queues: ['queue1', 'queue3']
        functions: ['queue1.func1', 'queue3.func3']


Usage:

from kvdb import tasks

# Using non-object functions

# Registers it to the default global task queue
@tasks.register(
    name = 'my_task',
    silenced_stages = ['enqueue'],
    disable_patch = True,
)
async def my_task():
    print('Hello World')


# Registers it to a specific task queue
@tasks.register(
    name = 'my_task',
    queue = 'my_queue',
)
async def my_task():
    print('Hello World')

# Register it to a specific task queue
# that has specific worker attributes

@tasks.register(
    name = 'my_task',
    queue = 'my_queue',
    worker_attributes = {
        'my_attribute': 'my_value',
    }
)
async def my_task():
    print('Hello World')

# Create a context wrapper
task_ctx = tasks.create_context(
    queue = 'my_queue',
    worker_attributes = {
        'my_attribute': 'my_value',
    }
)

@task_ctx.register(
    name = 'my_task',
)
async def my_task():
    print('Hello World')

"""

class TaskFunction(BaseModel):
    """
    The Task Function Class
    """
    func: Union[Callable, str]
    name: Optional[str] = None
    phase: Optional[TaskPhase] = None
    silenced: Optional[bool] = None
    silenced_stages: Optional[List[str]] = Field(default_factory = list)
    kwargs: Optional[Dict[str, Any]] = Field(default_factory = dict)
    default_kwargs: Optional[Dict[str, Any]] = None

    is_cronjob: Optional[bool] = None

    # Allow deterministic queue
    # queue_name: Optional[str] = None

    # Enable/Disable Patching
    disable_patch: Optional[bool] = None

    # Filter Functions for the Task Function
    worker_attributes: Optional[Dict[str, Any]] = Field(default_factory = dict)
    attribute_match_type: Optional[AttributeMatchType] = None

    if TYPE_CHECKING:
        cronjob: Optional[CronJob] = None
    else:
        cronjob: Optional[Any] = None

    @model_validator(mode = 'after')
    def validate_function(self):
        """
        Validates the function
        """
        # We defer this until after we startup the worker
        if isinstance(self.func, str):
            self.func = lazy_import(self.func)
            self.func = ensure_coro(self.func)
        # if not self.name and callable(self.func): self.name = self.func.__qualname__ if self.cronjob else self.func.__name__
        if not self.name: self.name = self.func.__qualname__ if self.cronjob else self.func.__name__
        if 'silenced' in self.kwargs:
            self.silenced = self.kwargs.pop('silenced')
        if 'silenced_stages' in self.kwargs:
            self.silenced_stages = self.kwargs.pop('silenced_stages')
        if 'default_kwargs' in self.kwargs:
            self.default_kwargs = self.kwargs.pop('default_kwargs')
        if self.silenced_stages is None: self.silenced_stages = []
        if self.silenced is None: self.silenced = False
        return self
    
    @property
    def function_name(self) -> str:
        """
        Returns the function name
        """
        return self.name
    
    def configure_cronjob(self, cronjob_class: Type['CronJob'], **kwargs):
        """
        Configures the cronjob
        """
        if self.cronjob is not None: return
        self.cronjob = cronjob_class(
            function = self.func,
            cron_name = self.name,
            default_kwargs = self.default_kwargs,
            **self.kwargs, **kwargs,
        )
    
    def is_silenced(self, stage: str) -> bool:
        """
        Checks if the function is silenced
        """
        return self.silenced or stage in self.silenced_stages
    
    def should_run_for_phase(self, phase: TaskPhase) -> bool:
        """
        Checks if the function should run for phase
        """
        return self.phase and self.phase == phase
    
    @property
    def should_set_ctx(self) -> bool:
        """
        Checks if the function should set the context
        """
        return self.kwargs.get('set_ctx', False)
    
    async def run_phase(self, ctx: Ctx, verbose: Optional[bool] = None):
        """
        Runs the phase
        """
        if self.should_set_ctx:
            if verbose: logger.info(f'[{self.phase}] setting ctx[{self.name}]: result of {self.func.__name__}')
            ctx = await self.func(ctx, **self.kwargs) if is_coro_func(self.func) else self.func(ctx, **self.kwargs)
        else:
            if verbose: logger.info(f'[{self.phase}] running task {self.name} = {self.func.__name__}')
            result = await self.func(**self.kwargs) if is_coro_func(self.func) else self.func(**self.kwargs)
            if result is not None: ctx[self.name] = result
        return ctx
    
    def is_enabled(self, worker_attributes: Optional[Dict[str, Any]] = None, attribute_match_type: Optional[Literal['any', 'all']] = None) -> bool:
        """
        Checks if the function is enabled
        """
        if not self.worker_attributes: return True
        attribute_match_type = attribute_match_type or self.attribute_match_type
        if not attribute_match_type: return True
        if worker_attributes is None: worker_attributes = {}
        return determine_match_from_attributes(worker_attributes, self.worker_attributes, attribute_match_type)
    
    def __call__(self, ctx: Ctx, *args, **kwargs) -> ReturnValueT:
        """
        Calls the function
        """
        return self.func(ctx, *args, **kwargs)

class QueueTasks(abc.ABC):
    """
    The Queue Tasks Object
    """

    queue_name: Optional[str] = None # The Queue Name
    context: Dict[str, Any] = {}
    functions: Dict[str, TaskFunction] = {}
    queue: Optional['TaskQueue'] = None
    queue_function: Union[Callable[..., 'TaskQueue'], 'TaskQueue'] = None
    verbose: Optional[bool] = None

    def __init__(
        self, 
        queue: Optional[str] = None, 
        context: Optional[Dict[str, Any]] = None, 
        task_function_class: Optional[Type[TaskFunction]] = None,
        cronjob_class: Optional[Type['CronJob']] = None,
        **kwargs
    ):
        """
        Initialize the Worker Tasks
        """
        if queue is not None: self.queue_name = queue
        if context is not None: self.context = context
        from kvdb.configs import settings
        self.settings = settings
        self.logger = self.settings.logger
        self.autologger = self.settings.autologger
        if self.verbose is None: self.verbose = self.settings.debug_enabled

        self.configure_classes(task_function_class = task_function_class, cronjob_class = cronjob_class, is_init = True)


    def configure_classes(
        self,
        task_function_class: Optional[Type[TaskFunction]] = None,
        cronjob_class: Optional[Type['CronJob']] = None,
        is_init: Optional[bool] = False,
    ):
        """
        Configures the classes
        """
        if task_function_class is None and is_init:
            task_function_class = TaskFunction
        elif task_function_class and isinstance(task_function_class, str):
            task_function_class = lazy_import(task_function_class)
        if task_function_class is not None:
            self.task_function_class = task_function_class
        
        if cronjob_class is None and is_init:
            from kvdb.types.jobs import CronJob
            cronjob_class = CronJob
        elif cronjob_class and isinstance(cronjob_class, str):
            cronjob_class = lazy_import(cronjob_class)
        if cronjob_class is not None:
            self.cronjob_class = cronjob_class
        

    def get_functions(
        self, 
        worker_attributes: Optional[Dict[str, Any]] = None,
        attribute_match_type: Optional[AttributeMatchType] = None,
    ) -> List[TaskFunction]:
        """
        Compiles all the worker functions that were registered
        """
        
        return [
            func
            for func in self.functions.values()
            if not func.cronjob and func.is_enabled(worker_attributes, attribute_match_type)
        ]
    
    def get_cronjobs(
        self,
        worker_attributes: Optional[Dict[str, Any]] = None,
        attribute_match_type: Optional[AttributeMatchType] = None,
    ) -> List['TaskFunction']:
        """
        Compiles all the cronjobs that were registered
        """
        cronjobs: List[TaskFunction] = []
        for func in self.functions.values():
            if not func.cronjob: continue
            if not func.is_enabled(worker_attributes, attribute_match_type): continue
            func.configure_cronjob(self.cronjob_class, queue_name = self.queue_name)
            cronjobs.append(func)
        return cronjobs
    
    async def prepare_ctx(self, ctx: Ctx):
        """
        Prepare the context
        """
        for name, obj in self.context.items():
            if name not in ctx: 
                if callable(obj):
                    if self.verbose: self.logger.info(f'[context] setting ctx[{name}]: result of {obj.__name__}')
                    result = await obj(ctx) if is_coro_func(obj) else obj(ctx)
                    if result is not None: ctx[name] = result
                else:
                    if self.verbose: self.logger.info(f'[context] setting ctx[{name}]: {obj}')
                    ctx[name] = obj
        return ctx

    async def run_phase(self, ctx: Ctx, phase: TaskPhase):
        """
        Runs the phase
        """
        for func in self.functions.values():
            if not func.should_run_for_phase(phase): continue
            ctx = await func.run_phase(ctx, self.verbose)
        return ctx

    async def get_worker_context(self, ctx: Ctx) -> Ctx:
        """
        Gets the worker context
        """
        ctx = await self.prepare_ctx(ctx)
        ctx = await self.run_phase(ctx, 'dependency')
        ctx = await self.run_phase(ctx, 'context')
        ctx = await self.run_phase(ctx, 'startup')
        return ctx

    def add_function_to_silenced(
        self, 
        function_name: str, 
        stages: Optional[List[str]] = None,
    ):
        """
        Adds a function to the silenced list
        """
        if stages:
            self.functions[function_name].silenced_stages.extend(stages)
            self.functions[function_name].silenced_stages = list(set(self.functions[function_name].silenced_stages))
        else:
            self.functions[function_name].silenced = True

    def is_function_silenced(
        self, 
        function_name: str, 
        stage: str,
    ) -> bool:
        """
        Checks if a function is silenced
        """
        return self.functions[function_name].is_silenced(stage)
    

    def modify_function_signature(
        self,
        function: Callable[..., TaskResult],
        args: Optional[List[str]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ):
        """
        Modifies the function signature
        """
        signature_params = signature(function)
        params = list(signature_params.parameters.values())
        if args:
            start_pos = 0 if 'self' not in params[0].name else 1
            for arg in args:
                if arg in signature_params.parameters: continue
                params.insert(start_pos, Parameter(arg, kind = Parameter.POSITIONAL_OR_KEYWORD, annotation = Ctx if arg == 'ctx' else None))
        if kwargs:
            for key, value in kwargs.items():
                if key in signature_params.parameters: continue
                insert_pos = len(params) - 1 if 'kwargs' in params[-1].name else len(params)
                params.insert(insert_pos, Parameter(key, kind = Parameter.KEYWORD_ONLY, default = value, annotation = Optional[type(value)]))
        self.autologger.info(f'Modifying function signature for {function.__name__}: {signature_params} {params}')
        return signature_params.replace(parameters=params)

    
    def add_function(
        self,
        function: Union[Callable, str],
        name: Optional[str] = None,
        phase: Optional[TaskPhase] = None,
        silenced: Optional[bool] = None,
        silenced_stages: Optional[List[str]] = None,
        default_kwargs: Optional[Dict[str, Any]] = None,
        cronjob: Optional[bool] = None,
        disable_patch: Optional[bool] = None,
        worker_attributes: Optional[Dict[str, Any]] = None,
        attribute_match_type: Optional[AttributeMatchType] = None,
        **kwargs
    ) -> TaskFunction:
        """
        Adds a function to the worker
        """
        task_function = self.task_function_class(
            func = function,
            name = name,
            phase = phase,
            silenced = silenced,
            silenced_stages = silenced_stages,
            default_kwargs = default_kwargs,
            cronjob = cronjob,
            disable_patch = disable_patch,
            worker_attributes = worker_attributes,
            attribute_match_type = attribute_match_type,
            kwargs = kwargs,
        )
        self.functions[task_function.name] = task_function
        return task_function
    

    def register(
        self,
        name: Optional[str] = None,
        phase: Optional[TaskPhase] = None,
        silenced: Optional[bool] = None,
        silenced_stages: Optional[List[str]] = None,
        default_kwargs: Optional[Dict[str, Any]] = None,
        cronjob: Optional[bool] = None,
        disable_patch: Optional[bool] = None,
        worker_attributes: Optional[Dict[str, Any]] = None,
        attribute_match_type: Optional[AttributeMatchType] = None,
        **function_kwargs,
    ) -> Callable[[FunctionT], FunctionT]:
        """
        Registers a function to queue
        """
        
        def decorator(func: FunctionT) -> Callable[..., TaskResult]:
            """
            The decorator
            """
            func_signature = self.modify_function_signature(func, args = ['ctx'])
            func_with_ctx = makefun.with_signature(func_signature)(func)
            task_function = self.add_function(
                function = func_with_ctx, 
                name = name,
                phase = phase,
                silenced = silenced,
                silenced_stages = silenced_stages,
                default_kwargs = default_kwargs,
                cronjob = cronjob,
                disable_patch = disable_patch,
                worker_attributes = worker_attributes,
                attribute_match_type = attribute_match_type,
                **function_kwargs,
            )
            if task_function.disable_patch: 
                return func

            @makefun.wraps(
                func, self.modify_function_signature(func, kwargs = {'blocking': True})
            )
            async def task_func(*args, blocking: Optional[bool] = True, **kwargs):
                method_func = self.queue.apply if blocking else self.queue.enqueue
                return await method_func(func, *args, **kwargs)
            
            return task_func
        
        return decorator


# TODO: Create a Task Manager that distinguishes the tasks to add
# Based on the worker name and attributes
    
class QueueTaskManager(abc.ABC):
    """
    The Queue Task Manager
    """
    queues: Dict[str, QueueTasks] = {}
    queue_task_class: Type[QueueTasks] = QueueTasks

    task_queues: Dict[str, 'TaskQueue'] = {}
    task_queue_class: Type['TaskQueue'] = None

    task_workers: Dict[str, 'TaskWorker'] = {}
    task_worker_class: Type['TaskWorker'] = None

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
        queue_name = queue_name or 'global'
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
        queue_name = queue_name or 'global'
        if queue_name not in self.queues:
            self.queues[queue_name] = self.create_queue(queue_name, context = context, queue_task_class = queue_task_class, **kwargs)
        return self.queues[queue_name]

    def get_queues(
        self,
        queue_names: Optional[Union[str, List[str]]] = None,
    ) -> List[QueueTasks]:
        """
        Gets the queues
        """
        if queue_names is None: queue_names = ['global']
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

    def modify_function_signature(
        self,
        function: Callable[..., TaskResult],
        args: Optional[List[str]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
    ):
        """
        Modifies the function signature
        """
        signature_params = signature(function)
        params = list(signature_params.parameters.values())
        if args:
            start_pos = 0 if 'self' not in params[0].name else 1
            for arg in args:
                if arg in signature_params.parameters: continue
                params.insert(start_pos, Parameter(arg, kind = Parameter.POSITIONAL_OR_KEYWORD, annotation = Ctx if arg == 'ctx' else None))
        if kwargs:
            for key, value in kwargs.items():
                if key in signature_params.parameters: continue
                insert_pos = len(params) - 1 if 'kwargs' in params[-1].name else len(params)
                params.insert(insert_pos, Parameter(key, kind = Parameter.KEYWORD_ONLY, default = value, annotation = Optional[type(value)]))
        self.autologger.info(f'Modifying function signature for {function.__name__}: {signature_params} {params}')
        return signature_params.replace(parameters=params)


    def register(
        self,
        queue_name: Optional[str] = None,
        **kwargs,
    ) -> Callable[[FunctionT], FunctionT]:
        """
        Registers a function to the queue_name
        """
        queue_name = queue_name or 'global'
        task_queue = self.get_queue(queue_name)

        def decorator(func: FunctionT) -> Callable[..., TaskResult]:
            """
            The decorator
            """
            func_signature = self.modify_function_signature(func, args = ['ctx'])
            func_with_ctx = makefun.with_signature(func_signature)(func)
            task_function = task_queue.add_function(function = func_with_ctx, **kwargs)
            if task_function.disable_patch: 
                # logger.info(f'[{task_function.name}] patching disabled')
                return func

            @makefun.wraps(
                func, self.modify_function_signature(func, kwargs = {'blocking': True})
            )
            async def task_func(*args, blocking: Optional[bool] = True, **kwargs):
                self.autologger.info(f'[{task_function.name}] running task {func.__name__}')
                method_func = task_queue.queue.apply if blocking else task_queue.queue.enqueue
                return await method_func(func, *args, **kwargs)
            
            return task_func
        
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
        queue_name = queue_name or 'global'
        task_queue = self.get_queue(queue_name, context = context)
        # Create a partial
        task_queue.register = makefun.partial(task_queue.register, **kwargs)
        return task_queue

    """
    These methods chain the methods of the task queue
    """

    def get_functions(
        self,
        queue_names: Optional[Union[str, List[str]]] = None,
        worker_attributes: Optional[Dict[str, Any]] = None,
        attribute_match_type: Optional[AttributeMatchType] = None,
    ) -> List[TaskFunction]:
        """
        Gets the functions
        """
        if queue_names is None: queue_names = ['global']
        if isinstance(queue_names, str): queue_names = [queue_names]
        return [
            func
            for queue_name in queue_names
            for func in self.get_queue(queue_name).get_functions(worker_attributes, attribute_match_type)
        ]


    def get_cronjobs(
        self,
        queue_names: Optional[Union[str, List[str]]] = None,
        worker_attributes: Optional[Dict[str, Any]] = None,
        attribute_match_type: Optional[AttributeMatchType] = None,
    ) -> List['CronJob']:
        """
        Gets the cronjobs
        """
        if queue_names is None: queue_names = ['global']
        if not isinstance(queue_names, list): queue_names = [queue_names]
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
        if queue_names is None: queue_names = ['global']
        if not isinstance(queue_names, list): queue_names = [queue_names]
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
        if queue_names is None: queue_names = ['global']
        if not isinstance(queue_names, list): queue_names = [queue_names]
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
        if queue_names is None: queue_names = ['global']
        if not isinstance(queue_names, list): queue_names = [queue_names]
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
        queue_name = queue_name or 'global'
        if queue_name not in self.task_queues:
            self.configure_classes(task_queue_class = task_queue_class)
            with self.lock:
                task_queue_class = task_queue_class or self.task_queue_class
                self.task_queues[queue_name] = task_queue_class(
                    queue_name = queue_name,
                    **kwargs
                )
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
        if queues is None: queues = ['global']
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
        worker_name = worker_name or 'global'
        if worker_name not in self.task_workers:
            self.configure_classes(task_worker_class = task_worker_class)
            with self.lock:
                task_worker_class = task_worker_class or self.task_worker_class
                self.task_workers[worker_name] = task_worker_class(
                    worker_name = worker_name,
                    queues = queues,
                    **kwargs
                )
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