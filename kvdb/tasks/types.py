from __future__ import annotations

"""
Base Task Types
"""
import abc
import collections.abc
from inspect import signature, Signature
from pydantic import Field, model_validator
from kvdb.types.base import BaseModel
from kvdb.utils.logs import logger
from kvdb.utils.helpers import is_coro_func, lazy_import, ensure_coro
from lazyops.libs.proxyobj import ProxyObject
from lazyops.libs.pooler import ThreadPooler
from lazyops.libs.abcs.utils.helpers import update_dict
from typing import Optional, Dict, Any, Union, TypeVar, Callable, Awaitable, TypeAlias, List, Type, Tuple, Literal, TYPE_CHECKING, overload
from .utils import AttributeMatchType, determine_match_from_attributes, get_func_name
from .debug import get_autologger

if TYPE_CHECKING:
    from kvdb.components.session import KVDBSession
    from kvdb.components.pipeline import AsyncPipelineT
    from kvdb.types.jobs import Job, CronJob
    from .queue import TaskQueue
    from .worker import TaskWorker
    CtxObject = Union[Job, Dict[str, TaskQueue], TaskWorker, Any]
else:
    CtxObject = Union[Dict[str, Any], Any]

# CtxObject = TypeVar('CtxObject', 'Job', Dict[str, 'TaskQueue'], 'TaskWorker', Any)
# CtxObject = Union['Job', Dict[str, 'TaskQueue'], 'TaskWorker', Any]
Ctx = Dict[str, CtxObject]
ObjT = TypeVar('ObjT')
ObjectType = Type[ObjT]
# ObjT = TypeVar('ObjT', abc.ABC, object)
# ObjectType = TypeAlias('ObjectType', bound = object)
# ObjectType = Type[object]
# TypeVar('ObjectType', bound = type)
ReturnValue = TypeVar('ReturnValue')
ReturnValueT = Union[ReturnValue, Awaitable[ReturnValue]]
FunctionT = TypeVar('FunctionT', bound = Callable[..., ReturnValueT])

TaskResult = TypeVar('TaskResult', 'Job', Any, Awaitable[Any])
TaskPhase = Literal['context', 'dependency', 'startup', 'shutdown']


autologger = get_autologger('types')

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

    # is_cronjob: Optional[bool] = None
    cron: Optional[str] = None

    # Allow deterministic queue
    queue_name: Optional[str] = None

    # Enable/Disable Patching
    disable_patch: Optional[bool] = None
    disable_ctx_in_patch: Optional[bool] = None

    # Filter Functions for the Task Function
    worker_attributes: Optional[Dict[str, Any]] = Field(default_factory = dict)
    attribute_match_type: Optional[AttributeMatchType] = None
    
    # Private Attributes
    function_signature: Optional[Signature] = Field(None, exclude=True)
    function_inject_ctx: Optional[bool] = Field(None, exclude=True)
    function_inject_args: Optional[bool] = Field(None, exclude=True)
    function_inject_kwargs: Optional[bool] = Field(None, exclude=True)

    function_default_kwargs: Optional[Dict[str, Any]] = Field(None, exclude=True)

    function_is_method: Optional[bool] = Field(None, exclude=True)
    function_parent_type: Optional[Literal['class', 'instance']] = Field(None, exclude=True)

    fallback_enabled: Optional[bool] = None

    if TYPE_CHECKING:
        cronjob: Optional[Union[CronJob, bool, str]] = None
    else:
        cronjob: Optional[Any] = None

    on_failure_callback: Optional[Union[Callable, str]] = None

    @classmethod
    def build_function_name(cls, func: Callable) -> str:
        """
        Builds the function name

        - Can be subclassed to change the function name
        """
        return get_func_name(func)

    @model_validator(mode = 'after')
    def validate_function(self):
        """
        Validates the function
        """
        # We defer this until after we startup the worker
        if isinstance(self.func, str): self.func = lazy_import(self.func)
        if self.function_signature is None: self.function_signature = signature(self.func)
        self.function_inject_ctx = 'ctx' in self.function_signature.parameters
        # Check if has positional args
        self.function_inject_args = 'args' in self.function_signature.parameters or any(p.kind in [p.VAR_POSITIONAL, p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD] for p in self.function_signature.parameters.values())
        # self.function_inject_args = 'args' in self.function_signature.parameters
        # Check if has keyword args
        self.function_inject_kwargs = 'kwargs' in self.function_signature.parameters or any(p.kind in [p.VAR_KEYWORD, p.KEYWORD_ONLY, p.POSITIONAL_OR_KEYWORD] for p in self.function_signature.parameters.values())
        self.function_is_method = hasattr(self.func, '__class__')
        if self.function_is_method:
            if 'self' in self.function_signature.parameters:
                self.function_parent_type = 'instance'
            elif 'cls' in self.function_signature.parameters:
                self.function_parent_type = 'class'
        
        if self.default_kwargs is not None:
            self.function_default_kwargs = {
                k: v.default for k, v in self.function_signature.parameters.items() if k in self.default_kwargs
            }
        
        if self.cronjob:
            if isinstance(self.cronjob, str):
                # Move to cron
                self.cron = self.cronjob
                self.cronjob = None
            elif isinstance(self.cronjob, bool):
                # Set a default value
                self.cron = ''
                self.cronjob = None

        if not self.name: self.name = self.build_function_name(self.func)
        self.func = ensure_coro(self.func)
        if 'silenced' in self.kwargs:
            self.silenced = self.kwargs.pop('silenced')
        if 'silenced_stages' in self.kwargs:
            self.silenced_stages = self.kwargs.pop('silenced_stages')
        if 'default_kwargs' in self.kwargs:
            self.default_kwargs = self.kwargs.pop('default_kwargs')
        if self.silenced_stages is None: self.silenced_stages = []
        if self.silenced is None: self.silenced = False
        if self.on_failure_callback is not None and isinstance(self.on_failure_callback, str):
            self.on_failure_callback = lazy_import(self.on_failure_callback)
        return self
    
    @property
    def is_cronjob(self) -> bool:
        """
        Checks if the function is a cronjob
        """
        return self.cron is not None

    @property
    def include_phase_as_function(self) -> bool:
        """
        Checks if the phase should be included as a function
        """
        return self.kwargs.get('include_phase_as_function', False)

    @property
    def function_name(self) -> str:
        """
        Returns the function name
        """
        return self.name
    
    def configure_cronjob(
        self, 
        cronjob_class: Type['CronJob'], 
        cron_schedules: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        """
        Configures the cronjob
        """
        if self.cronjob is not None: return
        _kwargs = self.kwargs.copy()
        _kwargs.update(kwargs)
        _kwargs = {k: v for k, v in _kwargs.items() if k in cronjob_class.model_fields}
        cron_schedules = cron_schedules or {}
        if 'cron' in _kwargs:
            cron = _kwargs.pop('cron')
        else:
            cron = cron_schedules.get(self.name, self.cron)
        self.cronjob = cronjob_class(
            function = self.func,
            cron_name = self.name,
            cron = cron,
            default_kwargs = self.default_kwargs,
            **_kwargs,
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
            # if verbose: logger.info(f'Setting ctx[{self.name}]: result of |g|`{self.func.__name__}`|e|', colored = True, prefix = self.phase)
            ctx = await self.func(ctx, **self.kwargs) if is_coro_func(self.func) else self.func(ctx, **self.kwargs)
        else:
            # if verbose: logger.info(f'Running task {self.name} = |g|`{self.func.__name__}`|e|', colored = True, prefix = self.phase)
            result = await self.func(**self.kwargs) if is_coro_func(self.func) else self.func(**self.kwargs)
            if result is not None: ctx[self.name] = result
        return ctx
    
    def is_enabled(self, worker_attributes: Optional[Dict[str, Any]] = None, attribute_match_type: Optional[AttributeMatchType] = None, queue_name: Optional[str] = None) -> bool:
        """
        Checks if the function is enabled
        """
        if queue_name is not None and self.queue_name is not None and queue_name != self.queue_name: return False
        if self.phase and not self.include_phase_as_function: return False
        if not self.worker_attributes: return True
        attribute_match_type = attribute_match_type or self.attribute_match_type
        if not attribute_match_type: return True
        if worker_attributes is None: worker_attributes = {}
        return determine_match_from_attributes(worker_attributes, self.worker_attributes, attribute_match_type)
    
    @property
    def function_class_initialized(self) -> bool:
        """
        Checks if the function class is initialized
        """
        if self.function_is_method:
            if self.function_parent_type == 'instance':
                return hasattr(self.func, '__self__') and self.func.__self__ is not None
            elif self.function_parent_type == 'class':
                return True
            return False
        return True

    def __call__(self, ctx: Ctx, *args, **kwargs) -> ReturnValueT:
        """
        Calls the function
        """
        # logger.info(f'[{self.name}] running task {self.func.__name__} with args: {args} and kwargs: {kwargs}')
        # if self.default_kwargs: 
        #     _kwargs = self.default_kwargs.copy()
        #     _kwargs.update(kwargs)
        #     kwargs = _kwargs
        if self.function_inject_ctx:
            if self.function_inject_args and self.function_inject_kwargs:
                return self.func(ctx, *args, **kwargs)
            elif self.function_inject_args:
                return self.func(ctx, *args)
            elif self.function_inject_kwargs:
                return self.func(ctx, **kwargs)
            return self.func(ctx)
        if self.function_inject_args and self.function_inject_kwargs:
            return self.func(*args, **kwargs)
        elif self.function_inject_args:
            try:
                return self.func(*args)
            except Exception as e:
                return self.func(*args, **kwargs)
        elif self.function_inject_kwargs:
            try:
                return self.func(**kwargs)
            except Exception as e:
                return self.func(*args, **kwargs)
        return self.func()
    
    async def run_on_failure_callback(self, job: 'Job'):
        """
        Runs the on failure callback
        """
        if self.on_failure_callback is None: return
        if is_coro_func(self.on_failure_callback):
            return await self.on_failure_callback(job)
        return self.on_failure_callback(job)

    def update_function_kwargs(self, **kwargs) -> Dict[str, Any]:
        """
        Merges the default kwargs
        """
        if not self.default_kwargs: return kwargs
        default_kws = self.default_kwargs.copy()
        extra_kws = {k:v for k,v in default_kws.items() if k not in kwargs}
        for k,v in kwargs.items():
            if k in default_kws and self.function_default_kwargs.get(k) == v:
                if isinstance(v, collections.abc.Mapping):
                    kwargs[k] = update_dict(default_kws[k], v)
                elif isinstance(v, list):
                    kwargs[k] = list(set(default_kws[k] + v))
                else:
                    kwargs[k] = v
        kwargs.update(extra_kws)
        # logger.info(f'Updated Kwargs: {kwargs}')
        return kwargs



class PushQueue:
    def __init__(
        self, 
        ctx: 'KVDBSession',
        push_to_queue_enabled: Optional[bool] = None,
        push_to_queue_key: Optional[str] = None,
        push_to_queue_ttl: Optional[int] = None,
        **kwargs
    ):
        self.ctx = ctx
        self.queue_key = push_to_queue_key
        self.enabled = push_to_queue_enabled and self.queue_key is not None
        self.ttl = push_to_queue_ttl or 600
        self._kwargs = kwargs

    async def push_pipeline(
        self, 
        pipeline: 'AsyncPipelineT',
        job: Optional[Job] = None,
        job_id: Optional[str] = None,
        **kwargs,
    ):
        """
        Push a job via the pipeline
        """
        if not self.enabled or (job is None and job_id is None): return pipeline
        return pipeline.rpush(self.queue_key, job_id or job.id).expire(self.queue_key, self.ttl)

    async def _push_bg(
        self, 
        job: Optional[Job] = None,
        job_id: Optional[str] = None,
        **kwargs,
    ):
        """
        Push a job via the background task
        """
        await self.ctx.aclient.rpush(self.queue_key, job_id or job.id)
        await self.ctx.aclient.expire(self.queue_key, self.ttl)
    
    async def push_bg(
        self, 
        job: Optional[Job] = None,
        job_id: Optional[str] = None, 
        **kwargs
    ):
        """
        Push a job via the background task
        """
        if not self.enabled or (job is None and job_id is None): return
        await ThreadPooler.create_background_task(self._push_bg, job = job, job_id = job_id, **kwargs)

    async def push(
        self, 
        job: Optional[Job] = None,
        job_id: Optional[str] = None,
        pipeline: Optional['AsyncPipelineT'] = None,
        **kwargs,
    ):
        """
        Push a job to the queue
        """
        if pipeline is not None: return await self.push_pipeline(job = job, job_id = job_id, pipeline = pipeline, **kwargs)
        return await self.push_bg(job = job, job_id = job_id, pipeline = pipeline, **kwargs)
    
    async def remove_pipeline(
        self, 
        pipeline: 'AsyncPipelineT',
        job: Optional[Job] = None,
        job_id: Optional[str] = None,
        **kwargs,
    ):
        """
        Remove a job via the pipeline
        """
        if not self.enabled or (job is None and job_id is None): return pipeline
        return pipeline.lrem(self.queue_key, 1, job_id or job.id)
    
    async def _remove_bg(
        self,
        job: Optional[Job] = None,
        job_id: Optional[str] = None,
        **kwargs,
    ):
        """
        Remove a job via the background task
        """
        await self.ctx.aclient.lrem(self.queue_key, 1, job_id or job.id)
    
    async def remove_bg(
        self,
        job: Optional[Job] = None,
        job_id: Optional[str] = None, 
        **kwargs
    ):
        """
        Remove a job via the background task
        """
        if not self.enabled or (job is None and job_id is None): return
        await ThreadPooler.create_background_task(self._remove_bg, job = job, job_id = job_id, **kwargs)
    
    async def remove(
        self,
        job: Optional[Job] = None,
        job_id: Optional[str] = None,
        pipeline: Optional['AsyncPipelineT'] = None,
        **kwargs,
    ):
        """
        Remove a job from the queue
        """
        if pipeline is not None: return await self.remove_pipeline(job = job, job_id = job_id, pipeline = pipeline, **kwargs)
        return await self.remove_bg(job = job, job_id = job_id, **kwargs)
    
    @property
    async def alength(self) -> int:
        """
        Returns the length of the queue
        """
        return await self.ctx.aclient.llen(self.queue_key) if self.enabled else 0

    @property
    async def ajob_ids(self) -> List[str]:
        """
        Returns the job ids in the queue
        """
        return await self.ctx.aclient.lrange(self.queue_key, 0, -1) if self.enabled else []

