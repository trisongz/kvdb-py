from __future__ import annotations

"""
Base Worker Types
"""
import os
import abc
import signal
import makefun
import anyio
import functools
import asyncio
import contextlib
import croniter

from inspect import signature, Parameter
from pydantic import Field, model_validator, validator
from kvdb.types.base import BaseModel
from kvdb.utils.logs import logger
from kvdb.configs import settings
from kvdb.configs.tasks import KVDBTaskQueueConfig
from kvdb.configs.base import WorkerTimerConfig
from kvdb.utils.helpers import is_coro_func, lazy_import
from lazyops.libs.proxyobj import ProxyObject
from typing import Optional, Dict, Any, Union, TypeVar, Callable, Set, Type, Awaitable, List, Tuple, Literal, TYPE_CHECKING, overload
from .static import ColorMap
from .utils import get_exc_error

from kvdb.utils.helpers import (
    now, 
    seconds, 
    ensure_coro,
    millis,
)
from typing import (
    Dict, 
    Any, 
    Optional, 
    Type, 
    Literal, 
    Union, 
    Callable, 
    List, 
    Tuple,
    Mapping, 
    TypeVar,
    Iterable,
    overload,
    TYPE_CHECKING
)

if TYPE_CHECKING:
    from kvdb.io.serializers import SerializerT
    from kvdb.components import AsyncScript
    from kvdb.components.session import KVDBSession
    from kvdb.components.persistence import PersistentDict
    from kvdb.utils.logs import Logger
    from kvdb.types.jobs import CronJob, Job, JobStatus
    from .queue import TaskQueue
    from .base import TaskFunction, Ctx



class TaskWorker(abc.ABC):

    SIGNALS = [signal.SIGINT, signal.SIGTERM] if os.name != "nt" else [signal.SIGTERM]

    config: Optional[KVDBTaskQueueConfig] = None

    @overload
    def __init__(self, config: KVDBTaskQueueConfig, **kwargs): ...

    @overload
    def __init__(
        self,
        queues: Union[List['TaskQueue', str], 'TaskQueue', str],
        *,
        name: Optional[str] = None,
        functions: Optional[List['TaskFunction']] = None,
        cron_jobs: Optional[List['CronJob']] = None,

        startup: Optional[Union[List[Callable], Callable,]] = None,
        shutdown: Optional[Union[List[Callable], Callable,]] = None,
        before_process: Optional[Callable] = None,
        after_process: Optional[Callable] = None,
        worker_attributes: Optional[Dict[str, Any]] = None,

        timers: Optional[Union[Dict[str, int], WorkerTimerConfig]] = None,
        max_concurrency: Optional[int] = None,
        max_broadcast_concurrency: Optional[int] = None,
        task_queue_class: Optional[Type['TaskQueue']] = None,
        **kwargs
    ): ...


    def __init__(
        self,
        queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,

        functions: Optional[List['TaskFunction']] = None,
        cronjobs: Optional[List['TaskFunction']] = None,

        startup: Optional[Union[List[Callable], Callable,]] = None,
        shutdown: Optional[Union[List[Callable], Callable,]] = None,
        before_process: Optional[Callable] = None,
        after_process: Optional[Callable] = None,

        timers: Optional[Union[Dict[str, int], WorkerTimerConfig]] = None,
        task_queue_class: Optional[Type['TaskQueue']] = None,
        **kwargs
    ):
        """
        Initializes the Worker
        """
        self.settings = settings.model_copy()
        if isinstance(kwargs.get('config'), KVDBTaskQueueConfig):
            self.config = kwargs.pop('config')
        else:
            self.config = self.settings.tasks
        config_kwargs, kwargs = self.config.extract_config_and_kwargs(**kwargs)
        self.config.update_config(**config_kwargs)
        self.timers = WorkerTimerConfig()
        if timers and isinstance(timers, dict):
            self.timers.update_config(timers)
        
        self.init_queues(queues = queues, task_queue_class = task_queue_class, **kwargs)
        self.cls_init(**kwargs)
        self.init_functions(functions = functions, cronjobs = cronjobs, **kwargs)
        self.init_processes(startup = startup, shutdown = shutdown, before_process = before_process, after_process = after_process, **kwargs)
        self.pre_init(**kwargs)
        self.post_init(**kwargs)

    
    async def start(self):
        """
        Start processing jobs and upkeep tasks.
        """
        if not self.queue_eager_init:
            for queue in self.queues:
                await queue.aregister_worker(self)
        self.ctx = {"worker": self, "queues": self.queue_dict, "vars": {}}
        self.task_manager.register_task_worker(self)
        error = None
        # Run Startup Functions
        try:
            loop = asyncio.get_running_loop()
            for signum in self.SIGNALS: loop.add_signal_handler(signum, self.event.set)
            for queue in self.queues:
                await queue.ctx.aclient.initialize()
            
            if self.startup: 
                for func in self.startup:
                    await func(self.ctx)
            
            if self.display_on_startup:
                self.autologger.info(self.build_startup_display_message(), prefix = self.name)

            await self.heartbeat()        

            self.tasks.update(await self.upkeep())
            for cid in range(self.max_concurrency):
                self.process_task(concurrency_id = cid)
            
            for _ in range(self.max_broadcast_concurrency):
                self.broadcast_process_task()

            await self.event.wait()

        except Exception as e:
            error = e
            raise error from error

        finally:
            self.logger(kind = "shutdown").warning(f'{self.worker_identity} is shutting down. Error: {error}')
            if self.shutdown:
                for func in self.shutdown:
                    await func(self.ctx)
            await self.stop()
    
    async def stop(self):
        """
        Stop the worker and cleanup.
        """
        self.event.set()
        all_tasks = list(self.tasks)
        self.tasks.clear()
        for task in all_tasks:
            task.cancel()
        await asyncio.gather(*all_tasks, return_exceptions=True)

    def logger(self, job: 'Job' = None, kind: str = "enqueue", queue: Optional['TaskQueue'] = None) -> 'Logger':
        """
        The logger for the worker.
        """
        _kwargs = {'kind': kind, 'worker_name': self.name}
        if job: 
            _kwargs['job_id'] = job.id
            _kwargs['status'] = job.status
            _kwargs['queue_name'] = job.queue_name
        if queue: _kwargs['queue_name'] = queue.queue_name
        if 'queue_name' not in _kwargs: _kwargs['queue_name'] = self.queue_name
        return self.settings.logger.bind(**_kwargs)


    async def before_process(self, ctx):
        """
        Handles the before process function.
        """
        if self._before_process:
            await self._before_process(ctx)

    async def after_process(self, ctx):
        """
        Handles the after process function.
        """
        if self._after_process:
            await self._after_process(ctx)

    """
    Process Functions
    """

    async def schedule(self, lock: int = 1):
        """
        Schedule jobs.
        """
        for function in self.cronjobs.values():
            cronjob = function.cronjob
            queue = self.queue_dict[cronjob.queue_name]
            enqueue_kwargs = cronjob.to_enqueue_kwargs(
                job_key = queue.job_id(f"{queue.config.cronjob_prefix}:{cronjob.function_name}") if cronjob.unique else None,
                exclude_none = True,
                job_function_kwarg_prefix = queue.config.job_function_kwarg_prefix,
            )
            await queue.enqueue(**enqueue_kwargs)
            scheduled = await queue.schedule(lock)
            if scheduled:
                self.logger(kind = "scheduled").info(f'↻ node={queue.node_name}, function={cronjob.function_name}, {scheduled}')

    async def heartbeat(self, ttl: Optional[int] = None):
        """
        Send a heartbeat to the queue.
        """
        ttl = ttl or self.heartbeat_ttl
        for queue in self.queues:
            await queue.add_heartbeat(
                worker_id = self.worker_id,
                worker_name = self.name,
                heartbeat_ttl = ttl,
            )

    async def sweep(self, lock: Optional[int] = None):
        """
        Sweep the queues.
        """
        for queue in self.queues:
            await queue.sweep(lock = lock)

    async def upkeep(self):
        """
        Start various upkeep tasks async.
        """
        async def poll(func, sleep, arg=None, **kwargs):
            while not self.event.is_set():
                try:
                    if asyncio.iscoroutinefunction(func):
                        await func(arg or sleep, **kwargs)
                    else: func(arg or sleep, **kwargs)
                except (Exception, asyncio.CancelledError) as e:
                    if self.event.is_set(): return
                    self.autologger.trace(f"Error in upkeep task {func.__name__}", e)
                await asyncio.sleep(sleep)

        return [
            asyncio.create_task(poll(self.abort, self.timers.abort)),
            asyncio.create_task(poll(self.schedule, self.timers.schedule)),
            asyncio.create_task(poll(self.sweep, self.timers.sweep)),
            # asyncio.create_task(
            #     poll(self.queue.stats, self.timers.stats, self.timers.stats + 1)
            # ),
            asyncio.create_task(
                poll(self.heartbeat, self.timers.heartbeat, self.heartbeat_ttl)
            ),
        ]
    
    async def sort_jobs(self, jobs: List['Job']) -> Dict[str, List['Job']]:
        """
        Sort the jobs into their respective queues.
        """
        queues: Dict[str, List['Job']] = {}
        for job in jobs:
            queue = queues.setdefault(job.queue_name, [])
            queue.append(job)
        return queues

    async def abort(self, abort_threshold: int):
        """
        Abort jobs that have been running for too long.
        """
        existing_jobs = [
            job
            for job in self.job_task_contexts
            if job.duration("running") >= millis(abort_threshold)
        ]
        if not existing_jobs: return
        jobs_by_queues = await self.sort_jobs(existing_jobs)
        for queue_name, jobs in jobs_by_queues.items():
            queue = self.queue_dict[queue_name]
            aborted = await queue.ctx.amget(job.abort_id for job in jobs)
            for job, abort in zip(jobs, aborted):
                job: 'Job'
                if not abort: continue

                task_data = self.job_task_contexts.get(job, {})
                task: asyncio.Task = task_data.get("task")
                if task and not task.done():
                    task_data["aborted"] = True
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    await job.finish(JobStatus.ABORTED, error = abort.decode("utf-8"))
                    await queue.ctx.adelete(job.abort_id)
                    if not queue.queue_tasks.is_function_silenced(job.function, stage = "abort"):
                        self.logger(job = job, kind = "abort").info(f"⊘ {job.duration('running')}ms, node={self.node_name}, func={job.function}, id={job.id}")
            

    async def process_queue(
        self, 
        queue_name: str,
        broadcast: Optional[bool] = False, 
        concurrency_id: Optional[int] = None
    ):
        """
        Process a job.
        """
        # sourcery skip: low-code-quality
        # pylint: disable=too-many-branches
        job, context = None, None
        queue = self.queue_dict[queue_name]
        try:
            with contextlib.suppress(ConnectionError):
                job = await queue.dequeue(
                    self.dequeue_timeout, 
                    worker_id = self.worker_id if broadcast else None, 
                    worker_name = self.name if broadcast else None,
                )

            if not job: 
                self.autologger.info(f"No job found in queue {queue_name}")
                return
            if job.worker_id and job.worker_id != self.worker_id:
                if self.config.debug_enabled:
                    self.logger(job = job, kind = "process").info(f"⊘ Rejected job, queued_key={job.queued_key}, func={job.function}, id={job.id} | worker_id={job.worker_id} != {self.worker_id}")
                return
            
            if job.worker_name and job.worker_name != self.name:
                if self.config.debug_enabled:
                    self.logger(job = job, kind = "process").info(f"⊘ Rejected job, queued_key={job.queued_key}, func={job.function}, id={job.id} | worker_name={job.worker_name} != {self.name}")
                return
                
            if job.worker_name or job.worker_id and self.config.debug_enabled:
                self.logger(job = job, kind = "process").info(f"☑ Accepted job, func={job.function}, id={job.id}, worker_name={job.worker_name}, worker_id={job.worker_id}")
            
            self.tasks_idx += 1
            job.started = now()
            job.status = JobStatus.ACTIVE
            job.attempts += 1
            await job.update()
            # if self.queue.function_tracker_enabled:
            #     await self.queue.track_job_id(job)
            context = {**self.ctx, "job": job}
            await self._before_process(context)
            # if job.function not in self.silenced_functions:
            if not queue.queue_tasks.is_function_silenced(job.function, stage = "process"):
                _msg = f"← duration={job.duration('running')}ms, node={self.node_name}, func={job.function}"
                # if self.verbose_concurrency:
                #     _msg = _msg.replace("node=", f"idx={self._tasks_idx}, conn=({concurrency_id}/{self.concurrency}), node=")
                self.logger(job = job, kind = "process").info(_msg)

            function = self.functions[job.function]
            try:
                task = asyncio.create_task(function(context, *(job.args or ()), **(job.kwargs or {})))
            except Exception as e:
                # self.logger(job = job, kind = "process").error(
                #     f"Failed to create task for [{job.function}] {function} with error: {e}.\nKwargs: {job.kwargs}"
                # )
                self.autologger.trace(f"Failed to create task for [{job.function}] {function} with error: {e}.\nKwargs: {job.kwargs}", e)
                # get_and_log_exc(job = job)
                self.tasks_idx -= 1
                raise e
            self.job_task_contexts[job] = {"task": task, "aborted": False}
            result = await asyncio.wait_for(task, job.timeout)
            await job.finish(JobStatus.COMPLETE, result=result)
        except asyncio.CancelledError:
            if job and not self.job_task_contexts.get(job, {}).get("aborted"):
                await job.retry("cancelled")
        except Exception:
            error = get_exc_error(job = job)

            if job:
                if job.attempts >= job.retries: await job.finish(JobStatus.FAILED, error=error)
                else: await job.retry(error)
        finally:
            self.tasks_idx -= 1
            if context:
                self.job_task_contexts.pop(job, None)
                try: await self.after_process(context)
                except (Exception, asyncio.CancelledError) as e: 
                    error = get_exc_error(job = job)
                    self.autologger.error(f"Error in after_process for job {job.id}: {error}")

    async def process(self, broadcast: Optional[bool] = False, concurrency_id: Optional[int] = None):
        """
        Process a job from all queues.
        """
        for queue in self.queues:
            await self.process_queue(queue.queue_name, broadcast = broadcast, concurrency_id = concurrency_id)


    async def process_broadcast(self, queue_name: str):
        """
        This is a separate process that runs in the background to process broadcasts.
        """
        queue = self.queue_dict[queue_name]
        await self.process_queue(broadcast = True, queue_name = queue_name)

        await queue.schedule(lock = 1, worker_id = self.worker_id)
        await queue.schedule(lock = 1, worker_id = self.name)

        await queue.sweep(worker_id = self.worker_id)
        await queue.sweep(worker_id = self.name)

    def process_task(
        self, 
        previous_task: Optional[asyncio.Task] = None, 
        concurrency_id: Optional[int] = None
    ):
        """
        Handles the processing of jobs.
        """
        if previous_task: self.tasks.discard(previous_task)
        if not self.event.is_set():
            for queue_name in self.queue_names:
                new_task = asyncio.create_task(self.process_queue(queue_name = queue_name, concurrency_id = concurrency_id))
                self.tasks.add(new_task)
                new_task.add_done_callback(functools.partial(self.process_task, concurrency_id = concurrency_id))
    
    def broadcast_process_task(self, previous_task: Optional[asyncio.Task] = None):
        """
        This is a separate process that runs in the background to process broadcasts.
        """
        if previous_task and isinstance(previous_task, asyncio.Task): self.tasks.discard(previous_task)
        if not self.event.is_set():
            for queue_name in self.queue_names:
                new_task = asyncio.create_task(self.process_broadcast(queue_name))
                self.tasks.add(new_task)
                new_task.add_done_callback(self.broadcast_process_task)
                
    

    """
    Initialize the Worker
    """

    def cls_init(
        self, 
        **kwargs
    ):
        """
        Initializes the Worker
        """
        self.worker_pid: int = os.getpid()
        self.worker_id = kwargs.get('uuid', kwargs.get('worker_id')) or self.config.get_default_job_key()
        self.worker_attributes = kwargs.get('worker_attributes') or {}
        self.attribute_match_type = kwargs.get('attribute_match_type')
        self.tasks: Set[asyncio.Task] = set()
        self.event = asyncio.Event()
        self.ctx: Ctx = {}
        self.job_task_contexts: Dict['Job', Dict[str, Any]] = {}

        self.dequeue_timeout = kwargs.get('dequeue_timeout') or self.config.job_timeout
        self.heartbeat_ttl = kwargs.get('heartbeat_ttl') or self.config.heartbeat_interval
        self.tasks_idx: int = 0

        # Configure Misc Variables
        from lazyops.utils.system import get_host_name
        self.node_name = get_host_name()
        self.name = kwargs.get('name') or self.node_name
        self.worker_name = self.name
        self.is_primary_process = self.settings.temp_data.has_logged(f'primary_process.worker:{self.name}')
        if self.settings.in_k8s:
            self.is_leader_process = self.node_name[-1].isdigit() and int(self.node_name[-1]) == 0 and self.is_primary_process
        else:
            self.is_leader_process = self.is_primary_process
        self.worker_identity = f"{self.name}:{self.worker_pid}"
        self.worker_attributes.update({
            'worker_id': self.worker_id,
            'worker_pid': self.worker_pid,
            'worker_name': self.name,
            'node_name': self.node_name,
            'is_primary_process': self.is_primary_process,
            'is_leader_process': self.is_leader_process,
        })
        
        self.display_on_startup = kwargs.get('display_on_startup', True)
        self.max_concurrency = kwargs.get('max_concurrency', self.config.max_concurrency)
        self.max_broadcast_concurrency = kwargs.get('max_broadcast_concurrency', self.config.max_broadcast_concurrency)

    def init_functions(
        self,
        functions: Optional[List['TaskFunction']] = None,
        cronjobs: Optional[List['TaskFunction']] = None,
        **kwargs
    ):
        """
        Initializes the functions
        """
        self.functions: Dict[str, 'TaskFunction'] = {}
        self.cronjobs: Dict[str, 'TaskFunction'] = {}
        if not functions:
            functions = self.task_manager.get_functions(
                queue_names = self.queue_names,
                worker_attributes = self.worker_attributes,
                attribute_match_type = self.attribute_match_type,
            )
        else:
            functions = [f for f in functions if f.is_enabled(self.worker_attributes, self.attribute_match_type)]
        self.functions = {f.name: f for f in functions}
        if not cronjobs:
            cronjobs = self.task_manager.get_cronjobs(
                queue_names = self.queue_names,
                worker_attributes = self.worker_attributes,
                attribute_match_type = self.attribute_match_type,
            )
        
        # We dont really validate it here.
        if cronjobs: 
            for job in cronjobs:
                if not croniter.croniter.is_valid(job.cronjob.cron):
                    raise ValueError(f"Invalid cron schedule {job.cronjob.cron} for job {job.function_name}")
                self.functions[job.function_name] = job
            self.cronjobs = {f.name: f for f in cronjobs}
        if self.is_leader_process:
            self.autologger.info(f"Initializing {len(functions)} functions and {len(cronjobs)} cronjobs", prefix = self.name)
    
    def init_processes(
        self, 
        startup: Optional[Union[List[Callable], Callable,]] = None,
        shutdown: Optional[Union[List[Callable], Callable,]] = None,
        before_process: Optional[Callable] = None,
        after_process: Optional[Callable] = None,
        **kwargs,
    ):
        """
        Initializes the processes
        """
        self.startup = startup or makefun.partial(self.task_manager.get_worker_context, queue_names = self.queue_names)
        if not isinstance(self.startup, list): self.startup = [self.startup]
        self.shutdown = shutdown or makefun.partial(self.task_manager.run_phase, queue_names = self.queue_names, phase = 'shutdown')
        if not isinstance(self.shutdown, list): self.shutdown = [self.shutdown]
        self._before_process = before_process or []
        self._after_process = after_process or []


    def pre_init(self, **kwargs):
        """
        Pre-Initialize the worker
        """
        pass

    def post_init(self, **kwargs):
        """
        Post-Initialize the worker
        """
        pass

    def finalize_init(self, **kwargs):
        """
        Finalizes the initialization
        """
        if self.queue_eager_init:
            for queue in self.queues:
                queue.register_worker(self)



    def init_queues(
        self, 
        queues: Union[List[Union['TaskQueue', str]], 'TaskQueue', str] = None,
        task_queue_class: Optional[Type['TaskQueue']] = None,
        **kwargs
    ):
        """
        Initializes the queues
        """
        self.queue_eager_init = kwargs.get('queue_eager_init', False)
        from .base import TaskManager
        self.task_manager = TaskManager
        self.queues = self.task_manager.get_worker_queues(
            queues = queues, 
            task_queue_class = task_queue_class, 
            **kwargs
        )
        self.queue_names = [q.queue_name for q in self.queues]
        self.queue_dict = {q.queue_name: q for q in self.queues}
        self.queue_name = ','.join(self.queue_names)

    @property
    def autologger(self) -> 'Logger':
        """
        Returns the autologger
        """
        return self.settings.logger if self.config.debug_enabled else self.settings.autologger
    

    def build_startup_display_message(self):  # sourcery skip: low-code-quality
        """
        Builds the startup log message.
        """
        # _msg = f'{self._worker_identity}: {self.worker_host}.{self.name} v{self.settings.version}'
        _msg = f'{self.worker_identity}: v{self.settings.version}'
        _msg += f'\n- {ColorMap.cyan}[Node Name]{ColorMap.reset}: {ColorMap.bold}{self.node_name}.{self.name}{ColorMap.reset}'
        _msg += f'\n- {ColorMap.cyan}[Worker ID]{ColorMap.reset}: {ColorMap.bold}{self.worker_id}{ColorMap.reset}'
        add = True
        # if self.is_primary_process:
        if add:
            if len(self.queues) == 1:
                _msg += f'\n- {ColorMap.cyan}[Queue]{ColorMap.reset}: {ColorMap.bold}{self.queues[0].queue_name} @ {self.queues[0].ctx.url.safe_url} DB: {self.queues[0].ctx.url.db_id}{ColorMap.reset}'
            else:
                _msg += f'\n- {ColorMap.cyan}[Queues]{ColorMap.reset}:'
                for queue in self.queues:
                    _msg += f'\n   - {ColorMap.bold}{queue.queue_name} @ {queue.ctx.url} DB: {queue.ctx.db_id}{ColorMap.reset}'
            _msg += f'\n- {ColorMap.cyan}[Registered]{ColorMap.reset}: {ColorMap.bold}{len(self.functions)} functions, {len(self.cronjobs)} cron jobs{ColorMap.reset}'
            _msg += f'\n- {ColorMap.cyan}[Concurrency]{ColorMap.reset}: {ColorMap.bold}{self.max_concurrency}/jobs, {self.max_broadcast_concurrency}/broadcasts{ColorMap.reset}'
            # if self.verbose_startup:
            #     _msg += f'\n- {ColorMap.cyan}[Worker Attributes]{ColorMap.reset}: {self.worker_attributes}'
            #     if self._is_ctx_retryable:
            #         _msg += f'\n- {ColorMap.cyan}[Retryable]{ColorMap.reset}: {self._is_ctx_retryable}'
            #     _msg += f'\n- {ColorMap.cyan}[Functions]{ColorMap.reset}:'
            #     for function_name in self.functions:
            #         _msg += f'\n   - {ColorMap.bold}{function_name}{ColorMap.reset}'
            #     if self.settings.worker.has_silenced_functions:
            #         _msg += f"\n - {ColorMap.cyan}[Silenced Functions]{ColorMap.reset}:"
            #         for stage, silenced_functions in self.settings.worker.silenced_function_dict.items():
            #             if silenced_functions:
            #                 _msg += f"\n   - {stage}: {silenced_functions}"
            #     if self.queue.function_tracker_enabled:
            #         _msg += f'\n- {ColorMap.cyan}[Function Tracker Enabled]{ColorMap.reset}: {self.queue.function_tracker_enabled}'
        return _msg
            