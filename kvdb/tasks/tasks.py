from __future__ import annotations

"""
Base Task Types
"""

import abc
import makefun
from inspect import signature, Parameter, Signature
from kvdb.utils.logs import logger
from kvdb.utils.helpers import is_coro_func, lazy_import
from typing import Optional, Dict, Any, Union, Callable, Type, List, Tuple, TYPE_CHECKING
from types import ModuleType
from .types import (
    Ctx,
    FunctionT,
    TaskPhase,
    TaskResult,
    TaskFunction,
)

from .utils import AttributeMatchType, is_uninit_method

if TYPE_CHECKING:
    from kvdb.types.jobs import Job, CronJob
    from .queue import TaskQueue


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

    registered_task_object: Dict[str, Dict[str, Dict]] = {}

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
