from __future__ import annotations

"""
Base Task Types
"""

import abc
import makefun
from inspect import signature, Parameter, Signature
from kvdb.utils.logs import logger
from kvdb.utils.helpers import is_coro_func, lazy_import
from typing import Optional, Dict, Any, Union, Callable, Type, List, Tuple, AsyncGenerator, Iterable, TYPE_CHECKING, overload
from types import ModuleType
from .types import (
    Ctx,
    FunctionT,
    TaskPhase,
    TaskResult,
    TaskFunction,
)

from .utils import AttributeMatchType, is_uninit_method, get_func_name

if TYPE_CHECKING:
    from kvdb.types.jobs import Job, CronJob
    from .queue import TaskQueue


class QueueTasks(abc.ABC):
    """
    The Queue Tasks Object
    """
    # queue_name: Optional[str] = None # The Queue Name
    # context: Dict[str, Any] = {}
    # functions: Dict[str, TaskFunction] = {}
    # queue: Optional['TaskQueue'] = None
    # queue_function: Union[Callable[..., 'TaskQueue'], 'TaskQueue'] = None
    # verbose: Optional[bool] = None
    # registered_task_object: Dict[str, Dict[str, Dict]] = {}

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
        self.queue_name = queue
        self.context: Dict[str, Any] = context or {}
        self.functions: Dict[str, TaskFunction] = {}
        self.queue: Optional['TaskQueue'] = None
        self.queue_function: Union[Callable[..., 'TaskQueue'], 'TaskQueue'] = None
        self.registered_task_object: Dict[str, Dict[str, Dict]] = {}

        # if queue is not None: self.queue_name = queue
        # if context is not None: self.context = context
        from kvdb.configs import settings
        self.settings = settings
        self.logger = self.settings.logger
        self.autologger = self.settings.autologger
        self.verbose: Optional[bool] = kwargs.get('verbose', self.settings.debug_enabled)
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
            if not func.cronjob and func.is_enabled(worker_attributes, attribute_match_type, queue_name = self.queue_name)
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
        if function_name not in self.functions:
            raise ValueError(f'Function {function_name} not found in queue `{self.queue_name}`: Valid Functions: `{self.functions.keys()}`')
        return self.functions[function_name].is_silenced(stage)
    

    def modify_function_signature(
        self,
        function: Callable[..., TaskResult],
        signature_params: Optional[Signature] = None,
        args: Optional[List[str]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        remove_self_or_cls: Optional[bool] = None,
    ):
        """
        Modifies the function signature
        """
        if signature_params is None: signature_params = signature(function)
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
        if remove_self_or_cls:
            if 'self' in params[0].name or 'cls' in params[0].name: params.pop(0)
        # self.autologger.info(f'Modifying function signature for {function.__name__}: {signature_params} {params}')
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
            queue_name = self.queue_name,
            kwargs = kwargs,
        )
        if task_function.name not in self.functions:
            # raise ValueError(f'Function {task_function.name} already registered in queue `{self.queue_name}`')
            self.functions[task_function.name] = task_function
        return self.functions[task_function.name]

    def patch_registered_function(
        self,
        function: FunctionT,
        task_function: TaskFunction,
    ) -> Callable[..., TaskResult]:
        """
        Patch the function
        """
        async def patched_function(*args, blocking: Optional[bool] = True, **kwargs):
            # logger.info(f'[{task_function.name}] [NON METHOD] running task {function.__name__} with args: {args} and kwargs: {kwargs}')
            method_func = self.queue.apply if blocking else self.queue.enqueue
            return await method_func(task_function.name, *args, **kwargs)
        
        if task_function.function_is_method:
            if task_function.function_parent_type == 'instance':
                async def patched_function(_self, *args, blocking: Optional[bool] = True, **kwargs):
                    # logger.info(f'[{task_function.name}] [INSTANCE] running task {function.__name__} with args: {args} and kwargs: {kwargs} {_self}')
                    method_func = self.queue.apply if blocking else self.queue.enqueue
                    return await method_func(task_function.name, *args, **kwargs)
            
            elif task_function.function_parent_type == 'class':
                async def patched_function(_cls, *args, blocking: Optional[bool] = True, **kwargs):
                    method_func = self.queue.apply if blocking else self.queue.enqueue
                    return await method_func(task_function.name, *args, **kwargs)
        
        return makefun.wraps(
            function,
            self.modify_function_signature(
                function, 
                args = ['ctx'] if task_function.function_inject_ctx else None,
                kwargs = {'blocking': True}, 
            )
        )(patched_function)


    def register_object(self, **_kwargs) -> ModuleType:
        """
        Register the underlying object
        """
        partial_kws = {k:v for k,v in _kwargs.items() if v is not None}

        def object_decorator(obj: ModuleType) -> ModuleType:
            """
            The decorator that patches the object
            """
            if not hasattr(obj, '__taskinit__'):
                task_obj_id = f'{obj.__module__}.{obj.__name__}'
                # logger.info(f'[{task_obj_id}] - Registering Task Object')

                setattr(obj, '__src_init__', obj.__init__)
                setattr(obj, '__task_obj_id__', task_obj_id)
                
                if task_obj_id not in self.registered_task_object: self.registered_task_object[task_obj_id] = {}

                def __taskinit__(_self, *args, **kwargs):
                    _self.__task_post_init_hook__(_self, *args, **kwargs)

                def __task_post_init_hook__(_self, *args, **kwargs):
                    # logger.info(f'[{_self}] - Initializing Task Functions')
                    _self.__src_init__(*args, **kwargs)
                    task_functions = self.registered_task_object[_self.__task_obj_id__]
                    for func, task_partial_kws in task_functions.items():
                        # logger.info(f'[{_self}] - Registering Task Function: {func}')
                        func_kws = partial_kws.copy()
                        func_kws.update(task_partial_kws)
                        out_func = self.register(function = getattr(_self, func), **func_kws)
                        # if self.functions[func]
                        if not func_kws.get('disable_patch'):
                            setattr(_self, func, out_func)
                
                setattr(obj, '__init__', __taskinit__)
                setattr(obj, '__task_post_init_hook__', __task_post_init_hook__)
            return obj
    
        return object_decorator
    
    def register_object_method(self, **kwargs) -> Callable[[FunctionT], FunctionT]:
        """
        Registers an object method function to queue
        """
        kwargs = {k:v for k,v in kwargs.items() if v is not None}
        def decorator(func: FunctionT) -> Callable[..., TaskResult]:
            """
            The decorator
            """
            task_obj_id = f'{func.__module__}.{func.__qualname__.split(".")[0]}'
            if task_obj_id not in self.registered_task_object:
                self.registered_task_object[task_obj_id] = {}
            func_name = func.__name__
            if func_name not in self.registered_task_object[task_obj_id]:
                self.registered_task_object[task_obj_id][func_name] = kwargs
            return func
        return decorator


    def register(
        self,
        name: Optional[str] = None,
        function: Optional[FunctionT] = None,
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
        if function is not None:
            # logger.info(f'Registering Task Function: PRE {self.queue_name}', prefix = function.__qualname__, colored = True)
            if is_uninit_method(function):
                return self.register_object_method(
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
                )(function)
            task_function = self.add_function(
                function = function, 
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
            if task_function.disable_patch: return function
            return self.patch_registered_function(function, task_function)
            
        def decorator(func: FunctionT) -> Callable[..., TaskResult]:
            """
            The decorator
            """
            
            if is_uninit_method(func):
                # logger.info(f'Registering Task Function: POST-PREINIT {self.queue_name}', prefix = func.__qualname__, colored = True)

                return self.register_object_method(
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
                )(func)
            # logger.info(f'Registering Task Function: POST-INIT {self.queue_name}', prefix = func.__qualname__, colored = True)
            task_function = self.add_function(
                function = func,
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
            if task_function.disable_patch: return func
            return self.patch_registered_function(func, task_function)
        
        return decorator

    """
    Apply Passthrough Methods
    """

    @overload
    async def enqueue(
        self, 
        job_or_func: Union[Job, str, Callable],
        *args,
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
        **kwargs
    ) -> Optional[Job]:
        """
        Enqueue a job by instance or string.

        Kwargs can be arguments of the function or properties of the job.
        If a job instance is passed in, it's properties are overriden.
        """
        return await self.queue.enqueue(job_or_func, *args, **kwargs)

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
        **kwargs
    ) -> Optional[Any]:
        """
        Enqueue a job and wait for its result.

        If the job is successful, this returns its result.
        If the job is unsuccessful, this raises a JobError.
        """
        return await self.queue.apply(job_or_func, **kwargs)

    @overload    
    async def broadcast(
        self,
        job_or_func: Union[Job, str],
        enqueue: Optional[bool] = True,
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
        return await self.queue.broadcast(job_or_func, **kwargs)

    @overload
    async def map(
        self, 
        job_or_func: Union[Job, str],
        iter_kwargs: Iterable[Dict], 
        return_exceptions: bool = False, 
        broadcast: Optional[bool] = False,
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
        **kwargs
    ) -> List[TaskResult]:
        """
        Enqueue multiple jobs and collect all of their results.
        """
        return await self.queue.map(job_or_func, iter_kwargs, **kwargs)
            

    @overload
    async def wait_for_job(
        self,
        job: Job,
        source_job: Optional[Job] = None,
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
        verbose: Optional[bool] = False,
        raise_exceptions: Optional[bool] = False,
        refresh_interval: Optional[float] = 0.5,
        **kwargs,
    ) -> Any:  # sourcery skip: low-code-quality
        """
        Waits for job to finish
        """
        return await self.queue.wait_for_job(job, source_job = source_job, verbose = verbose, raise_exceptions = raise_exceptions, refresh_interval = refresh_interval, **kwargs)

    @overload
    async def wait_for_jobs(
        self,
        jobs: List[Job],
        source_job: Optional[Job] = None,
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
        verbose: Optional[bool] = False,
        raise_exceptions: Optional[bool] = False,
        refresh_interval: Optional[float] = 0.5,
        **kwargs,
    ) -> List[Any]:  # sourcery skip: low-code-quality
        """
        Waits for jobs to finish
        """
        return await self.queue.wait_for_jobs(jobs, source_job = source_job, verbose = verbose, raise_exceptions = raise_exceptions, refresh_interval = refresh_interval, **kwargs)

    @overload
    def as_jobs_complete(
        self,
        jobs: List[Job],
        source_job: Optional[Job] = None,
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
        return self.queue.as_jobs_complete(jobs, source_job = source_job, verbose = verbose, raise_exceptions = raise_exceptions, refresh_interval = refresh_interval, return_results = return_results, cancel_func = cancel_func, **kwargs)


    @overload
    def __call__(
        self,
        job_or_func: Union[Job, str, Callable],
        *args,
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
        blocking: Optional[bool] = False,
        broadcast: Optional[bool] = None,
        return_existing_job: bool = True,
        **kwargs,
    ) -> TaskResult:
        """
        Enqueues or applies a job.
        """
        return self.queue(job_or_func, *args, blocking = blocking, broadcast = broadcast, return_existing_job = return_existing_job, **kwargs)
    

    # def __getstate__(self):
    #     # Copy the object's state from self.__dict__ which contains
    #     # all our instance attributes. Always use the dict.copy()
    #     # method to avoid modifying the original state.
    #     state = self.__dict__.copy()
    #     # Remove the unpicklable entries.
    #     # del state['']
    #     logger.info(f'PICKLING {state}')
    #     return state
    #     # raise NotImplementedError()

    # def __setstate__(self, state):
    #     # Restore instance attributes
    #     logger.info(f'UNPICKLING {state}')
    #     # self.__dict__.update(state)
    #     # raise NotImplementedError()