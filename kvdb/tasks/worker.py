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
import contextvars
import kvdb.errors as errors
from kvdb.utils.logs import logger
from kvdb.configs import settings
from kvdb.configs.tasks import KVDBTaskQueueConfig
from kvdb.configs.base import WorkerTimerConfig
from kvdb.types.jobs import CronJob, Job, JobStatus
from redis import exceptions as rerrors

from kvdb.utils.helpers import is_coro_func, lazy_import
from lzl.proxied import ProxyObject
from lzo.utils import Timer
from typing import Optional, Dict, Any, Union, TypeVar, AsyncGenerator, Iterable, Callable, Set, Type, Awaitable, List, Tuple, Literal, TYPE_CHECKING, overload
from .static import ColorMap
from .utils import get_exc_error, get_func_name
from .debug import get_autologger

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
    from .queue import TaskQueue
    from .tasks import TaskFunction, Ctx

autologger = get_autologger('worker')

class TaskWorker(abc.ABC):

    SIGNALS = [signal.SIGINT, signal.SIGTERM] if os.name != "nt" else [signal.SIGTERM]

    # config: Optional[KVDBTaskQueueConfig] = None

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
        self.worker_settings = settings.model_copy()
        if isinstance(kwargs.get('config'), KVDBTaskQueueConfig):
            self.config = kwargs.pop('config')
        else:
            self.config = self.worker_settings.tasks
        config_kwargs, kwargs = self.config.extract_config_and_kwargs(**kwargs)
        self.config.update_config(**config_kwargs)
        self.timers = WorkerTimerConfig()
        if timers and isinstance(timers, dict):
            self.timers.update_config(timers)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.main_task: Optional[asyncio.Task] = None
        self._is_primary_process: Optional[bool] = None
        self._is_leader_process: Optional[bool] = None
        self.cls_preinit(**kwargs)
        self.init_queues(queues = queues, task_queue_class = task_queue_class, **kwargs)
        self.cls_init(**kwargs)
        self.pre_init(**kwargs)
        self.init_functions(functions = functions, cronjobs = cronjobs, **kwargs)
        self.init_processes(startup = startup, shutdown = shutdown, before_process = before_process, after_process = after_process, **kwargs)
        self.post_init(**kwargs)
        self.finalize_init(**kwargs)

    @property
    def is_primary_worker(self) -> bool:
        """
        Checks if the worker is the primary worker
        """
        return self.worker_attributes.get('is_primary_index')
    
    @property
    def is_primary_process(self) -> bool:
        """
        Checks if the worker is the primary process
        """
        if self._is_primary_process is None:
            # self.autologger.info('Checking if Primary Process', prefix = self.name, colored = True)
            self._is_primary_process = not self.worker_settings.temp_data.has_logged(f'primary_process.worker:{self.name}')
            # self.worker_attributes['is_primary_process'] = self._is_primary_process
        return self._is_primary_process
    
    @property
    def is_leader_process(self) -> bool:
        """
        Checks if the worker is the leader process
        """
        if self._is_leader_process is None:
            # self.autologger.info('Checking if Leader Process', prefix = self.name, colored = True)
            if self.worker_settings.in_k8s:
                self._is_leader_process = self.node_name[-1].isdigit() and int(self.node_name[-1]) == 0 and self.is_primary_process
            else:
                self._is_leader_process = self.is_primary_process
            # self.worker_attributes['is_leader_process'] = self._is_leader_process
        return self._is_leader_process

    @classmethod
    def build_function_name(cls, func: Callable) -> str:
        """
        Builds the function name

        - Can be subclassed to change the function name
        """
        return get_func_name(func)
    
    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """
        Returns the event loop
        """
        if not self._loop: 
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError as e:
                logger.error(f"Error getting running loop: {e}")
                try:
                    self._loop = asyncio.get_event_loop()
                except RuntimeError as e:
                    logger.error(f"Error getting event loop: {e}")
                    self._loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(self._loop)
        return self._loop

    def should_run_worker(self, **kwargs) -> bool:
        """
        Checks if the worker should run
        """
        return True

    def configure(self, **kwargs):
        """
        Configures the worker
        """
        config_kwargs, kwargs = self.config.extract_config_and_kwargs(**kwargs)
        self.config.update_config(**config_kwargs)
        if kwargs.get('timers') and isinstance(kwargs['timers'], dict):
            self.timers.update_config(kwargs['timers'])
        if 'queues' in kwargs: self.init_queues(queues = kwargs['queues'], **kwargs)
        if 'functions' in kwargs: self.init_functions(functions = kwargs['functions'], **kwargs)
        if 'startup' in kwargs or 'shutdown' in kwargs or 'before_process' in kwargs or 'after_process' in kwargs:
            self.init_processes(startup = kwargs.get('startup'), shutdown = kwargs.get('shutdown'), before_process = kwargs.get('before_process'), after_process = kwargs.get('after_process'), **kwargs)
        self.pre_init(**kwargs)
        self.post_init(**kwargs)
        self.finalize_init(**kwargs)

    async def start(self, **kwargs):
        """
        Start processing jobs and upkeep tasks.
        """
        if not self.should_run_worker(**kwargs): return
        await self.aworker_prestart_init(**kwargs)
        if not self.queue_eager_init:
            for queue in self.queues:
                await queue.aregister_worker(self)
        self.ctx = {"worker": self, "queues": self.queue_dict, "vars": {}}
        self.task_manager.register_task_worker(self)
        error = None
        await self.aworker_onstart_pre_init(**kwargs)
        # Run Startup Functions
        try:
            # loop = asyncio.get_running_loop()
            # for signum in self.SIGNALS: loop.add_signal_handler(signum, self.event.set)
            # loop = asyncio.get_running_loop()
            for signum in self.SIGNALS: self.loop.add_signal_handler(signum, self.event.set)
            for queue in self.queues:
                await queue.ctx.aclient.initialize()
            
            if self.startup: 
                for func in self.startup:
                    await func(self.ctx)
            
            if self.display_on_startup: self.logger.info(self.build_startup_display_message(), prefix = self.name)

            await self.heartbeat()        
            self.tasks.update(await self.upkeep())
            for cid in range(self.max_concurrency):
                self.process_task(concurrency_id = cid)
            
            for _ in range(self.max_broadcast_concurrency):
                self.broadcast_process_task()

            await self.aworker_onstart_post_init(**kwargs)
            await self.event.wait()

        except Exception as e:
            error = e
            raise error from error

        finally:
            self.log(kind = "shutdown").warning(f'{self.worker_identity} is shutting down. Error: {error}')
            self.event.set()
            await self.reschedule_jobs(error = f'{self.worker_identity} is shutting down. Error: {error}')
            await self.aworker_onstop_pre(**kwargs)
            if self.shutdown:
                for func in self.shutdown:
                    await func(self.ctx)
            await self.aworker_onstop_post(**kwargs)
            await self.stop()
    
    def run(self, **kwargs):
        """
        Sync Function to run the worker
        """
        self.main_task = self.loop.create_task(self.start(**kwargs))
        try:
            self.loop.run_until_complete(self.main_task)
        except asyncio.CancelledError:  # pragma: no cover
            # happens on shutdown, fine
            pass
        finally:
            self.loop.run_until_complete(self.stop)

    async def async_run(self, **kwargs):
        """
        Async Function to run the worker
        """
        self.main_task = asyncio.create_task(self.start(**kwargs))
        await self.main_task

    async def stop(self):
        """
        Stop the worker and cleanup.
        """
        # self.event.set()
        all_tasks = list(self.tasks)
        self.tasks.clear()
        for task in all_tasks:
            if not task.done():
                task.cancel()
        if self.main_task: self.main_task.cancel()
        for queue in self.queues:
            await queue.close_connections()
        await asyncio.gather(*all_tasks, return_exceptions=True)


    def log(self, job: 'Job' = None, kind: str = "enqueue", queue: Optional['TaskQueue'] = None) -> 'Logger':
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
        return self.worker_settings.logger.bind(**_kwargs)


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
                self.log(kind = "scheduled").info(f'↻ node={queue.node_name}, function={cronjob.function_name}, {scheduled}')

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
    
    async def check_stuck_jobs(self, *args, **kwargs):
        """
        Checks for stuck jobs that are queued but have may be stuck waiting in the queue
        """
        for queue in self.queues:
            await queue.check_stuck_jobs()

    async def upkeep(self) -> List[asyncio.Task]:
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
        
        tasks = [
            self.loop.create_task(poll(self.abort, self.timers.abort)),
            self.loop.create_task(poll(self.schedule, self.timers.schedule)),
            self.loop.create_task(poll(self.sweep, self.timers.sweep)),
            self.loop.create_task(
                poll(self.heartbeat, self.timers.heartbeat, self.heartbeat_ttl)
            ),
        ]
        # Only schedule this on the leader process
        if self.is_leader_process and self.is_primary_worker:
            self.logger.info('Adding Stuck Job Checker', prefix = self.worker_name, colored = True)
            tasks.append(self.loop.create_task(poll(self.check_stuck_jobs, self.timers.stuck)))
        return tasks
    
    async def sort_jobs(self, jobs: List['Job']) -> Dict[str, List['Job']]:
        """
        Sort the jobs into their respective queues.
        """
        queues: Dict[str, List['Job']] = {}
        for job in jobs:
            queue = queues.setdefault(job.queue_name, [])
            queue.append(job)
        return queues

    async def reschedule_jobs(self, wait_time: Optional[float] = 10.0, error: Optional[str] = None):
        """
        Reschedule Jobs in the Queue

        - Used when the worker is shutting down
        """
        existing_jobs = self.job_task_contexts
        if not existing_jobs: return
        jobs_by_queues = await self.sort_jobs(existing_jobs)
        for queue_name, jobs in jobs_by_queues.items():
            queue = self.queue_dict[queue_name]
            for job in jobs:
                await queue.reschedule(job, wait_time, error = error)


    async def abort(self, abort_threshold: int):
        """
        Abort jobs that have been running for too long.
        """
        existing_jobs = [
            job
            for job in self.job_task_contexts
            if (job.get_duration("running") or 0.0) >= millis(abort_threshold)
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
                        self.log(job = job, kind = "abort").info(f"⊘ {job.get_duration('running')}ms, node={self.node_name}, func={job.function}, id={job.id}")
    
    async def wait_until_connection_restored(self, queue: 'TaskQueue'):
        """
        Waits until the connection is restored in the event of a connection error
        """
        attempts = 0
        t = Timer()
        while True:
            try:
                if await queue.ctx.aping():
                    self.logger.info(f"Connection restored in {t.total_s} after |g|{attempts}|e| attempts", colored = True, prefix = self.name)
                    return
            except (rerrors.ConnectionError, errors.ConnectionError, ConnectionError) as e:
                self.autologger.error(f"Connection Error: {e}")
                await asyncio.sleep(10.0)
            except Exception as e:
                self.autologger.error(f"Unknown Error: [{type(e)}] {e}")
                await asyncio.sleep(10.0)
            attempts += 1

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
        job, context, function = None, None, None
        queue = self.queue_dict[queue_name]
        
        try:
            with contextlib.suppress(ConnectionError):
                job = await queue.dequeue(
                    self.dequeue_timeout, 
                    worker_id = self.worker_id if broadcast else None, 
                    worker_name = self.name if broadcast else None,
                )
                # self.autologger.info(f"Dequeued job {job}")

            if not job: 
                # self.autologger.info(f"No job found in queue {queue_name}")
                return
            if job.worker_id and job.worker_id != self.worker_id:
                if self.config.debug_enabled:
                    self.log(job = job, kind = "process").info(f"⊘ Rejected job, queued_key={job.queued_key}, func={job.function}, id={job.id} | worker_id={job.worker_id} != {self.worker_id}")
                return
            
            if job.worker_name and job.worker_name != self.name:
                if self.config.debug_enabled:
                    self.log(job = job, kind = "process").info(f"⊘ Rejected job, queued_key={job.queued_key}, func={job.function}, id={job.id} | worker_name={job.worker_name} != {self.name}")
                return
                
            if (job.worker_name or job.worker_id) and self.config.debug_enabled:
                self.log(job = job, kind = "process").info(f"☑ Accepted job, func={job.function}, id={job.id}, worker_name={job.worker_name}, worker_id={job.worker_id}")
            
            self.tasks_idx += 1
            job.started = now()
            job.status = JobStatus.ACTIVE
            job.attempts += 1
            await job.update()
            # if self.queue.function_tracker_enabled:
            #     await self.queue.track_job_id(job)
            context = {**self.ctx, "job": job}
            await self.before_process(context)
            job = queue.queue_tasks.ensure_job_in_functions(job)
            # if job.function not in self.silenced_functions:
            if not queue.queue_tasks.is_function_silenced(job.function, stage = "process"):
                _msg = f"← duration={job.get_duration('running')}ms, node={self.node_name}, func={job.function}"
                # if self.verbose_concurrency:
                #     _msg = _msg.replace("node=", f"idx={self._tasks_idx}, conn=({concurrency_id}/{self.concurrency}), node=")
                self.log(job = job, kind = "process").info(_msg)

            function = self.functions[job.function]
            # res = await function(context, *(job.args or ()), **(job.kwargs or {}))
            try:
                #contextvar = contextvars.copy_context()
                #task = self.loop.create_task(function(context, *(job.args or ()), **(job.kwargs or {})), context = contextvar)
                task = self.loop.create_task(function(context, *(job.args or ()), **(job.kwargs or {})))
            except Exception as e:
                # self.log(job = job, kind = "process").error(
                #     f"Failed to create task for [{job.function}] {function} with error: {e}.\nKwargs: {job.kwargs}"
                # )
                self.autologger.trace(f"Failed to create task for [{job.function}] {function} with error: {e}.\nKwargs: {job.kwargs}", e)
                # get_and_log_exc(job = job)
                self.tasks_idx -= 1
                raise e
            self.job_task_contexts[job] = {"task": task, "aborted": False}
            result = await asyncio.wait_for(task, job.timeout)
            await job.finish(JobStatus.COMPLETE, result=result)
            if function.is_cronjob and not queue.queue_tasks.is_function_silenced(job.function, stage = "finish"):
                function.cronjob.get_next_cron_run_data(verbose = True)
        
        except errors.JobError as job_e:
            error = get_exc_error(job = job)
            err_msg = 'JobError in `process_queue` for job '
            if job is not None:
                err_msg += f'[status={job.status}, duration={job.duration_secs}, function={job.function}, id={job.id}]'
            else:
                err_msg += f'[queue={self.queue_name}] {function}'
            err_msg += f': {error}'
            self.autologger.error(err_msg)
            if job is not None:
                if job.attempts > job.retries: 
                    await job.finish(JobStatus.FAILED, error=error)
                    await function.run_on_failure_callback(job)
                elif function.should_retry_on_error(job.error or job_e):
                    # self.autologger.info(f'Retrying job {job.id} with error: {job.error or job_e}', prefix = function.name)
                    await job.retry(error)
                else:
                    # self.autologger.warning(f'Skipping job {job.id} with error: {job.error or job_e}', prefix = function.name)
                    job.retries = 0
                    await job.update()
                    await job.finish(JobStatus.FAILED, error=job_e)
                    await function.run_on_failure_callback(job)

        except asyncio.CancelledError as job_e:
            if job and not job.is_complete and not self.job_task_contexts.get(job, {}).get("aborted") and function.should_retry_on_error(job.error or job_e):
                # self.autologger.info(f'Cancelled job {job.id}', prefix = function.name)
                await job.retry("cancelled")
        

        except Exception as job_e:
            error = get_exc_error(job = job)
            err_msg = 'Unknown Error in `process_queue` for job '
            if job is not None:
                err_msg += f'[status={job.status}, duration={job.duration_secs}, function={job.function}, id={job.id}]'
            else:
                err_msg += f'[queue={self.queue_name}] {function}'
            err_msg += f': {error}'
            self.autologger.error(err_msg)
            if job is not None:
                if job.attempts > job.retries: 
                    await job.finish(JobStatus.FAILED, error=error)
                    await function.run_on_failure_callback(job)
                elif function.should_retry_on_error(job_e):
                    # self.autologger.info(f'Retrying job {job.id} with error: {job.error or job_e}', prefix = function.name)
                    await job.retry(error)
                else:
                    # self.autologger.warning(f'Skipping job {job.id} with error: {job.error or job_e}', prefix = function.name)
                    job.retries = 0
                    await job.finish(JobStatus.FAILED, error=job_e)
                    await function.run_on_failure_callback(job)
                # else: await job.retry(error)
        
        finally:
            self.tasks_idx -= 1
            if context:
                self.job_task_contexts.pop(job, None)
                try: await self.after_process(context)
                except (Exception, asyncio.CancelledError) as e: 
                    error = get_exc_error(job = job)
                    err_msg = 'Error in `after_process` for job '
                    if job is not None:
                        err_msg += f'[status={job.status}, duration={job.duration_secs}, function={job.function}, id={job.id}]'
                    else:
                        err_msg += f'[queue={self.queue_name}] {function}'
                    err_msg += f': {error}'
                    self.autologger.error(err_msg)
                    # self.autologger.error(f"Error in `after_process` for job [status={job.status}, duration={job.duration_secs}] {job}: {error}")

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
        try:
            await self.process_queue(broadcast = True, queue_name = queue_name)

            await queue.schedule(lock = 1, worker_id = self.worker_id)
            await queue.schedule(lock = 1, worker_id = self.name)

            await queue.sweep(worker_id = self.worker_id)
            await queue.sweep(worker_id = self.name)
        
        except Exception as e:
            self.autologger.error(f"Error: {type(e)} {e} in process_broadcast for queue {queue_name}")
            await self.wait_until_connection_restored(queue)
            return 


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
                new_task = self.loop.create_task(self.process_queue(queue_name = queue_name, concurrency_id = concurrency_id))
                self.tasks.add(new_task)
                new_task.add_done_callback(functools.partial(self.process_task, concurrency_id = concurrency_id))
    
    def broadcast_process_task(self, previous_task: Optional[asyncio.Task] = None):
        """
        This is a separate process that runs in the background to process broadcasts.
        """
        if previous_task and isinstance(previous_task, asyncio.Task): self.tasks.discard(previous_task)
        if not self.event.is_set():
            for queue_name in self.queue_names:
                new_task = self.loop.create_task(self.process_broadcast(queue_name))
                self.tasks.add(new_task)
                new_task.add_done_callback(self.broadcast_process_task)
                

    """
    Initialize the Worker
    """

    def cls_preinit(
        self,
        **kwargs
    ):
        """
        Pre-Initializes the Worker
        """
        pass

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
        from lzo.utils.system import get_host_name
        self.node_name = get_host_name()
        self.name = kwargs.get('name', kwargs.get('worker_name')) or self.node_name
        self.worker_name = self.name
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
            for cronjob in self.cronjobs.values():
                cronjob.cronjob.get_next_cron_run_data(verbose = True)
    
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
        from .main import TaskManager
        self.task_manager = TaskManager
        self.queues = self.task_manager.get_worker_queues(
            queues = queues, 
            task_queue_class = task_queue_class, 
            **kwargs
        )
        self.queue_names = [q.queue_name for q in self.queues]
        self.queue_dict = {q.queue_name: q for q in self.queues}
        self.queue_name = '[' + '|'.join(self.queue_names) + ']'

    @property
    def logger(self) -> 'Logger':
        """
        Returns the logger
        """
        return self.worker_settings.logger

    @property
    def autologger(self) -> 'Logger':
        """
        Returns the autologger
        """
        return self.worker_settings.logger if self.config.debug_enabled else self.worker_settings.autologger
    

    def build_startup_display_message(self):  # sourcery skip: low-code-quality
        """
        Builds the startup log message.
        """
        # _msg = f'{self._worker_identity}: {self.worker_host}.{self.name} v{self.worker_settings.version}'
        _msg = f'{self.worker_identity}: v{self.worker_settings.version}'
        _msg += f'\n- {ColorMap.cyan}[Worker ID]{ColorMap.reset}: {ColorMap.bold}{self.worker_id}{ColorMap.reset} {ColorMap.cyan}[Worker Name]{ColorMap.reset}: {ColorMap.bold}{self.name}{ColorMap.reset} {ColorMap.cyan}[Node Name]{ColorMap.reset}: {ColorMap.bold}{self.node_name} {ColorMap.cyan}'
        
        if self.is_leader_process:
            _msg += '[Leader]'
        elif self.is_primary_process:
            _msg += '[Primary]'
        else:
            _msg += '[Follower]'
        if self.is_primary_worker:
            _msg += '[Primary Worker]'

        # _msg += f'\n- {ColorMap.cyan}[Worker ID]{ColorMap.reset}: {ColorMap.bold}{self.worker_id}{ColorMap.reset}'
        if self.config.debug_enabled:
            _msg += f'\n- {ColorMap.cyan}[Concurrency]{ColorMap.reset}: {ColorMap.bold}{self.max_concurrency}/jobs, {self.max_broadcast_concurrency}/broadcasts{ColorMap.reset}'
            if len(self.queues) == 1:
                _msg += f'\n- {ColorMap.cyan}[Queue]{ColorMap.reset}: {ColorMap.bold}{self.queues[0].queue_name} @ {self.queues[0].ctx.url.safe_url} [S: {self.queues[0].serializer.name if self.queues[0].serializer else None}]{ColorMap.reset}'
                _msg += f'\n- {ColorMap.cyan}[Registered]{ColorMap.reset}: {ColorMap.bold}{len(self.functions)} functions, {len(self.cronjobs)} cron jobs{ColorMap.reset}'
                _msg += f'\n      \t[Functions]: `{list(self.functions.keys())}`'
                if self.cronjobs:
                    _msg += f'\n      \t[Cron Jobs]: `{list(self.cronjobs.keys())}`'
                
            else:
                _msg += f'\n- {ColorMap.cyan}[Queues]{ColorMap.reset}:'
                for queue in self.queues:
                    queue_funcs = [f for f in self.functions.values() if f.queue_name == queue.queue_name]
                    _msg += f'\n   - {ColorMap.bold}[{queue.queue_name}]\t @ {queue.ctx.url} [S: {queue.serializer.name if queue.serializer else None}], {len(queue_funcs)} functions, {len(self.cronjobs)} cron jobs{ColorMap.reset}'
                    _msg += f'\n      \t[Functions]: `{[f.function_name for f in queue_funcs]}`'
                    if self.cronjobs:
                        _msg += f'\n      \t[Cron Jobs]: `{[f.function_name for f in self.cronjobs.values() if f.queue_name == queue.queue_name]}`'
        else:
            _msg += f'\n- {ColorMap.cyan}[Queue]{ColorMap.reset}: {ColorMap.bold}{self.queues[0].queue_name} @ {self.queues[0].ctx.url.safe_url} [S: {self.queues[0].serializer.name if self.queues[0].serializer else None}]{ColorMap.reset}'
        return _msg
        
    """
    Overrideable Methods
    """

    async def aworker_prestart_init(self, **kwargs):
        """
        Async startup worker init
        """
        pass


    async def aworker_onstart_pre_init(self, **kwargs):
        """
        Async startup worker init
        """
        pass

    async def aworker_onstart_post_init(self, **kwargs):
        """
        Async startup worker init
        """
        pass

    async def aworker_onstop_pre(self, **kwargs):
        """
        Async On Stop Worker
        """
        pass

    async def aworker_onstop_post(self, **kwargs):
        """
        Async On Stop Worker
        """
        pass


    """
    Queue Methods
    """

    def _get_queue(
        self, 
        job_or_func: Union['Job', str, Callable],
        queue_name: Optional[str] = None, 
        **kwargs
    ) -> 'TaskQueue':
        """
        Gets the queue
        """
        if queue_name is None:
            if len(self.queues) == 1: queue_name = self.queues[0].queue_name
            else:
                function_name = self.build_function_name(job_or_func)
                if function_name not in self.functions:
                    raise ValueError(f"Function {function_name} not found in worker {self.name}")
                queue_name = self.functions[function_name].queue_name
        
        if queue_name not in self.queue_dict:
            raise ValueError(f"Queue {queue_name} not found in worker {self.name}")
        return self.queue_dict[queue_name]
        

    @overload
    async def enqueue(
        self,
        job_or_func: Union['Job', str, Callable],
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
    ) -> Optional['Job']:
        """
        Enqueue a job by instance or string.

        Kwargs can be arguments of the function or properties of the job.
        If a job instance is passed in, it's properties are overriden.
        """
        ...

    async def enqueue(
        self,
        job_or_func: Union['Job', str, Callable],
        *args,
        queue_name: Optional[str] = None,
        **kwargs
    ) -> Optional['Job']:
        """
        Enqueue a job by instance or string.

        Kwargs can be arguments of the function or properties of the job.
        If a job instance is passed in, it's properties are overriden.
        """
        queue = self._get_queue(job_or_func, queue_name = queue_name, **kwargs)
        return await queue.enqueue(job_or_func, *args, **kwargs)

            
    @overload
    async def apply(
        self,
        job_or_func: Union['Job', str, Callable],
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
        job_or_func: Union['Job', str, Callable],
        queue_name: Optional[str] = None,
        **kwargs
    ) -> Optional[Any]:
        """
        Enqueue a job and wait for its result.

        If the job is successful, this returns its result.
        If the job is unsuccessful, this raises a JobError.
        """
        queue = self._get_queue(job_or_func, queue_name = queue_name, **kwargs)
        return await queue.apply(job_or_func, **kwargs)


    @overload    
    async def broadcast(
        self,
        job_or_func: Union['Job', str],
        enqueue: Optional[bool] = True,
        queue_name: Optional[str] = None,
        worker_names: Optional[List[str]] = None,
        worker_selector: Optional[Callable] = None,
        worker_selector_args: Optional[List] = None,
        worker_selector_kwargs: Optional[Dict] = None,
        workers_selected: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> List['Job']:
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
        job_or_func: Union['Job', str],
        queue_name: Optional[str] = None,
        **kwargs
    ) -> List['Job']:
        """
        Broadcast a job to all nodes and collect all of their results.
        
        job_or_func: Same as Queue.enqueue
        kwargs: Same as Queue.enqueue
        timeout: How long to wait for the job to complete before raising a TimeoutError
        worker_names: List of worker names to run the job on. If provided, will run on these specified workers.
        worker_selector: Function that takes in a list of workers and returns a list of workers to run the job on. If provided, worker_names will be ignored.
        """

        queue = self._get_queue(job_or_func, queue_name = queue_name, **kwargs)
        return await queue.broadcast(job_or_func, **kwargs)
    

    @overload
    async def wait_for_job(
        self,
        job: 'Job',
        source_job: Optional['Job'] = None,
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
        job: 'Job',
        source_job: Optional['Job'] = None,
        queue_name: Optional[str] = None,
        verbose: Optional[bool] = False,
        raise_exceptions: Optional[bool] = False,
        refresh_interval: Optional[float] = 0.5,
        **kwargs,
    ) -> Any:  # sourcery skip: low-code-quality
        """
        Waits for job to finish
        """
        queue_name = queue_name or job.queue_name
        queue = self.queue_dict[queue_name]
        return await queue.wait_for_job(job, source_job = source_job, verbose = verbose, raise_exceptions = raise_exceptions, refresh_interval = refresh_interval, **kwargs)

        
    @overload
    async def wait_for_jobs(
        self,
        jobs: List['Job'],
        source_job: Optional['Job'] = None,
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
        jobs: List['Job'],
        source_job: Optional['Job'] = None,
        queue_name: Optional[str] = None,
        verbose: Optional[bool] = False,
        raise_exceptions: Optional[bool] = False,
        refresh_interval: Optional[float] = 0.5,
        **kwargs,
    ) -> List[Any]:  # sourcery skip: low-code-quality
        """
        Waits for jobs to finish
        """
        queue_name = queue_name or jobs[0].queue_name
        queue = self.queue_dict[queue_name]
        return await queue.wait_for_jobs(jobs, source_job = source_job, verbose = verbose, raise_exceptions = raise_exceptions, refresh_interval = refresh_interval, **kwargs)


    @overload
    def as_jobs_complete(
        self,
        jobs: List['Job'],
        source_job: Optional['Job'] = None,
        queue_name: Optional[str] = None,
        verbose: Optional[bool] = False,
        raise_exceptions: Optional[bool] = False,
        refresh_interval: Optional[float] = 0.5,
        return_results: Optional[bool] = True,
        cancel_func: Optional[Callable] = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:
        """
        Generator that yields results as they complete
        """
        ...

    def as_jobs_complete(
        self,
        jobs: List['Job'],
        source_job: Optional['Job'] = None,
        queue_name: Optional[str] = None,
        verbose: Optional[bool] = False,
        raise_exceptions: Optional[bool] = False,
        refresh_interval: Optional[float] = 0.5,
        return_results: Optional[bool] = True,
        cancel_func: Optional[Callable] = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:
        """
        Generator that yields results as they complete
        """
        queue_name = queue_name or jobs[0].queue_name
        queue = self.queue_dict[queue_name]
        return queue.as_jobs_complete(jobs, source_job = source_job, verbose = verbose, raise_exceptions = raise_exceptions, refresh_interval = refresh_interval, return_results = return_results, cancel_func = cancel_func, **kwargs)

        
