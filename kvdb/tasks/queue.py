from __future__ import annotations

"""
The Task Queue
"""

import os
import gc
import abc
import json
import time
import anyio
import asyncio
import typing
import atexit
import functools
import contextlib


from tenacity import RetryError
from pydantic import Field, model_validator, validator
from kvdb.configs import settings
from kvdb.configs.tasks import KVDBTaskQueueConfig
import kvdb.errors as errors
from lazyops.utils.times import Timer
from kvdb.types.base import BaseModel, KVDBUrl
from kvdb.types.jobs import (
    Job,
    JobStatus,
    TERMINAL_JOB_STATUSES,
    UNSUCCESSFUL_TERMINAL_JOB_STATUSES,
    INCOMPLETE_JOB_STATUSES,
)

from kvdb.utils.helpers import (
    now, 
    seconds, 
    ensure_coro,
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
    from .types import PushQueue
    from .worker import TaskWorker





class TaskQueue(abc.ABC):

    config: Optional[KVDBTaskQueueConfig] = None

    @overload
    def __init__(self, config: KVDBTaskQueueConfig, **kwargs): ...

    @overload
    def __init__(
        self,
        queue_name: Optional[str] = 'global',
        queue_prefix: Optional[str] = '_kvq_',
        queue_db_id: Optional[int] = 3,

        serializer: Optional[str] = 'json',
        serializer_kwargs: Optional[Dict[str, Any]] = None,
        compression: Optional[str] = None,
        compression_level: Optional[int] = None,
        max_concurrency: Optional[int] = None,
        max_broadcast_concurrency: Optional[int] = None,

        truncate_logs: Optional[Union[bool, int]] = None,
        debug_enabled: Optional[bool] = None,
        
        push_to_queue_enabled: Optional[bool] = None,
        push_to_queue_key: Optional[str] = None,
        push_to_queue_ttl: Optional[int] = None,
        **kwargs
    ): ...


    def __init__(
        self,
        uuid: Optional[str] = None,
        queue_name: Optional[str] = None,

        push_to_queue_enabled: Optional[bool] = None,
        push_to_queue_key: Optional[str] = None,
        push_to_queue_ttl: Optional[int] = None,
        **kwargs
    ):
        """
        Initializes the Task Queue
        """
        self.settings = settings.model_copy()
        if isinstance(kwargs.get('config'), KVDBTaskQueueConfig):
            self.config = kwargs.pop('config')
        else:
            self.config = self.settings.tasks
        
        config_kwargs, kwargs = self.config.extract_config_and_kwargs(**kwargs)
        self.config.update_config(**config_kwargs)
        self.uuid = uuid or self.config.get_default_job_key()
        self.serializer: 'SerializerT' = self.config.get_serializer(
            serializer = self.config.serializer,
            serializer_kwargs = self.config.serializer_kwargs,
            compression = self.config.compression,
            compression_level = self.config.compression_level,
        )
        self.queue_name = queue_name or 'global'
        self.queue_prefix = self.config.queue_prefix
        self.push_queue_kwargs = {
            'push_to_queue_enabled': push_to_queue_enabled,
            'push_to_queue_key': push_to_queue_key,
            'push_to_queue_ttl': push_to_queue_ttl,
        }
        self.cls_init(**kwargs)
        self.pre_init(**kwargs)
        self.post_init(**kwargs)
        self.finalize_init(**kwargs)
        self._kwargs = kwargs
    
    """
    Primary Methods
    """

    async def schedule(
        self, 
        lock: int = 1, 
        worker_id: Optional[str] = None
    ):
        """
        Schedule jobs.
        """
        if not self._schedule_script: await self.register_script('schedule')
        scheduled_key = self.scheduled_key if worker_id is None else f"{self.scheduled_key}:{worker_id}"
        incomplete_key = self.incomplete_key if worker_id is None else f"{self.incomplete_key}:{worker_id}"
        queued_key = self.queued_key if worker_id is None else f"{self.queued_key}:{worker_id}"
        return await self._schedule_script(
            keys=[scheduled_key, incomplete_key, queued_key],
            args=[lock, seconds(now())],
        )
        

    async def sweep(self, lock: int = 60, worker_id: Optional[str] = None):
        # sourcery skip: low-code-quality
        """
        Sweep jobs.
        """
        if not self._cleanup_script: await self.register_script('cleanup')
        active_key = self.active_key if worker_id is None else f"{self.active_key}:{worker_id}"
        sweep_key = self.sweep_key if worker_id is None else f"{self.sweep_key}:{worker_id}"
        incomplete_key = self.incomplete_key if worker_id is None else f"{self.incomplete_key}:{worker_id}"
        job_ids = await self._cleanup_script(
            keys = [sweep_key, active_key],
            args = [lock], 
            client = self.ctx.aclient,
        )
        swept = []
        if job_ids:
            for job_id, job_data in zip(job_ids, await self.ctx.amget(job_ids)):
                try:
                    job = await self.deserialize(job_data)
                except Exception as e:
                    job = None
                    self.logger(kind = "sweep").warning(f"Unable to deserialize job {job_id}: {e}")
                if not job: 
                    swept.append(job_id)
                    async with self.pipeline(transaction = True) as pipe:
                        pipe.lrem(active_key, 0, job_id).zrem(incomplete_key, job_id)
                        pipe = await self.push_queue.remove(job_id = job_id, pipeline = pipe)
                        await pipe.execute()
                    self.logger(kind = "sweep").info(f"Sweeping missing job {job_id}")
                elif job.status not in INCOMPLETE_JOB_STATUSES or job.stuck:
                    swept.append(job_id)
                    await job.finish(JobStatus.ABORTED, error="swept")
                    if self.queue_tasks.is_function_silenced(job.function, stage = 'sweep'): pass
                    elif self.logging_max_length:
                        job_result = job.get_truncated_result(self.logging_max_length)
                        self.logger(job=job, kind = "sweep").info(f"☇ duration={job.get_duration('total')}ms, node={self.node_name}, func={job.function}, result={job_result}")
                    else:
                        self.logger(job=job, kind = "sweep").info(f"☇ duration={job.get_duration('total')}ms, node={self.node_name}, func={job.function}")
        gc.collect()
        return swept


    async def abort(self, job: Job, error: Any, ttl: int = 5):
        """
        Abort a job.
        """
        async with self.op_sephamore(job.bypass_lock if job else False):
            # async with self.ctx.aclient.pipeline(transaction = True, retryable = True) as pipe:
            async with self.pipeline(transaction = True, retryable = True) as pipe:
                dequeued, *_ = await (
                    pipe.lrem(job.queued_key, 0, job.id)
                    .zrem(job.incomplete_key, job.id)
                    .expire(job.id, ttl + 1)
                    .setex(job.abort_id, ttl, error)
                    .execute()
                )

            if dequeued:
                await job.finish(JobStatus.ABORTED, error = error)
                await self.ctx.adelete(job.abort_id)
            else:
                await self.ctx.alrem(job.active_key, 0, job.id)
            
            await self.push_queue.remove(job_id = job.id)
            # await self.track_job(job)


    async def retry(self, job: Job, error: Any):
        """
        Retry an errored job.
        """
        job_id = job.id
        job.reset(
            status = JobStatus.QUEUED,
            error = error,
        )
        next_retry_delay = job.next_retry_delay()
        async with self.pipeline(transaction = True, retryable=True) as pipe:
            pipe = pipe.lrem(job.active_key, 1, job_id)
            pipe = pipe.lrem(job.queued_key, 1, job_id)
            if next_retry_delay:
                scheduled = time.time() + next_retry_delay
                pipe = pipe.zadd(job.incomplete_key, {job_id: scheduled})
            else:
                pipe = pipe.zadd(job.incomplete_key, {job_id: job.scheduled})
                pipe = pipe.rpush(job.queued_key, job_id)
            await self.push_queue.push(job_id = job_id)
            await pipe.set(job_id, await self.serialize(job)).execute()
            # self.retried += 1
            await self.notify(job)
            if not self.queue_tasks.is_function_silenced(job.function, stage = 'retry'):
                self.logger(job=job, kind = "retry").info(f"↻ duration={job.get_duration('running')}ms, node={self.node_name}, func={job.function}, error={job.error}")


    async def finish(
        self, 
        job: Job, 
        status: Union[JobStatus, str], 
        *, 
        result: Any = None, 
        error: Any = None
    ):
        """
        Publish a job result.
        """
        job_id = job.id
        job.complete(status = status, result = result, error = error)
        async with self.pipeline(transaction = True, retryable = True) as pipe:

            pipe = pipe.lrem(job.active_key, 1, job_id).zrem(job.incomplete_key, job_id)
            if job.ttl > 0: pipe = pipe.setex(job_id, job.ttl, await self.serialize(job))
            elif job.ttl == 0: pipe = pipe.set(job_id, await self.serialize(job))
            else: pipe.delete(job_id)
            pipe = await self.push_queue.remove(job_id = job_id, pipeline = pipe)
            await pipe.execute()
            # if status == JobStatus.COMPLETE:
            #     self.complete += 1
            # elif status == JobStatus.FAILED:
            #     self.failed += 1
            # elif status == JobStatus.ABORTED:
            #     self.aborted += 1


            await self.notify(job)
            # if self.debug_enabled:
            #     self.logger(job=job, kind = "finish").info(f"Finished {job}")
            if self.queue_tasks.is_function_silenced(job.function, stage = 'finish'):
                pass
            elif self.logging_max_length:
                job_result = job.get_truncated_result(self.logging_max_length)
                self.logger(job=job, kind = "finish").info(f"● duration={job.get_duration('total')}ms, node={self.node_name}, func={job.function}, result={job_result}")
            else:
                self.logger(job=job, kind = "finish").info(f"● duration={job.get_duration('total')}ms, node={self.node_name}, func={job.function}")
            # await self.track_job(job)
            


    async def defer(
        self, 
        job_or_func: Union[Job, str],
        wait_time: float = 10.0, 
        **kwargs
    ):
        """
        Enqueue a job by instance or string after a certain amount of time

        Kwargs can be arguments of the function or properties of the job.
        If a job instance is passed in, it's properties are overriden.

        If the job has already been enqueued, this returns None.
        will execute asyncronously and return immediately.
        """
        asyncio.create_task(self._deferred(job_or_func, wait_time = wait_time, **kwargs))


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

    
    @overload
    async def enqueue(
        self, 
        job_or_func: Union[Job, str, Callable],
        *args,
        _key: Optional[str] = None,
        _timeout: Optional[int] = None,
        _retries: Optional[int] = None,
        _ttl: Optional[int] = None,
        _retry_delay: Optional[int] = None,
        _retry_backoff: Optional[int] = None,
        _worker_id: Optional[str] = None,
        _worker_name: Optional[str] = None,
        _job_callback: Optional[Callable] = None,
        _job_callback_kwargs: Optional[Dict] = None,
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
        job_or_func: Callable,
        *args,
        return_existing_job: bool = False,
        **kwargs
    ) -> Job:
        """
        Enqueue a task
        """
        if self.config.job_function_kwarg_prefix:
            kwargs = Job.extract_kwargs(_prefix = self.config.job_function_kwarg_prefix, _include_prefix = False, **kwargs)
        job = Job.create(job_or_func, *args, **kwargs)
        if not self._enqueue_script: await self.register_script('enqueue')
        self.last_job = now()
        job.queue = self
        job.queued = now()
        job.status = JobStatus.QUEUED
        await self._before_enqueue(job)
        # settings.logger.info(f'Enqueueing Task: |y|{job_or_func}|e|', colored = True, prefix = "tasks")

        async with self.op_sephamore(job.bypass_lock):
            if not await self._enqueue_script(
                keys=[job.incomplete_key, job.id, job.queued_key, job.abort_id],
                args=[await self.serialize(job), job.scheduled],
                client = self.ctx.aclient,
            ):
                return await self.job(job.id) if return_existing_job else None
        
        if self.queue_tasks.is_function_silenced(job.function, stage = 'enqueue'):
            pass
        
        elif self.logging_max_length:
            job_kwargs = job.get_truncated_kwargs(self.logging_max_length)
            self.logger(job=job, kind="enqueue").info(
                f"→ duration={now() - job.queued}ms, node={self.node_name}, func={job.function}, timeout={job.timeout}, kwargs={job_kwargs}"
            )
        
        else:
            self.logger(job=job, kind="enqueue").info(
                f"→ duration={now() - job.queued}ms, node={self.node_name}, func={job.function}, timeout={job.timeout}"
            )


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
        job_or_func: Union[Job, str],
        broadcast: Optional[bool] = None,
        worker_names: Optional[List[str]] = None,
        worker_selector: Optional[Callable] = None,
        worker_selector_args: Optional[List] = None,
        worker_selector_kwargs: Optional[Dict] = None,
        workers_selected: Optional[List[Dict[str, str]]] = None,
        return_all_results: Optional[bool] = False,
        **kwargs
    ):
        """
        Enqueue a job and wait for its result.

        If the job is successful, this returns its result.
        If the job is unsuccessful, this raises a JobError.

        Example::
            try:
                assert await queue.apply("add", a=1, b=2) == 3
            except JobError:
                print("job failed")

        job_or_func: Same as Queue.enqueue
        kwargs: Same as Queue.enqueue
        timeout: How long to wait for the job to complete before raising a TimeoutError
        broadcast: Broadcast the job to all workers. If True, the job will be run on all workers.
        worker_names: List of worker names to run the job on. If provided, will run on these specified workers.
        worker_selector: Function that takes in a list of workers and returns a list of workers to run the job on. If provided, worker_names will be ignored.
        """
        results = await self.map(
            job_or_func, 
            iter_kwargs = [kwargs],
            broadcast = broadcast,
            worker_names = worker_names,
            worker_selector = worker_selector,
            worker_selector_args = worker_selector_args,
            worker_selector_kwargs = worker_selector_kwargs,
            workers_selected = workers_selected,
        )
        if return_all_results: return results
        return results[0] if results else None
        
    async def select_workers(
        self,
        func: Callable[..., List[Dict[str, str]]],
        *args,
        **kwargs,
    ) -> List[Dict[str, str]]:
        """
        Passes the dict of the worker attributes to the 
        provided function and returns a list of workers that
        are able to run the job.

        Function should expect kw: `worker_attributes`: Dict[str, Dict[str, Any]]
        and should return List[Dict[str, str]] where the Dict is either
            {'worker_id': str} or {'worker_name': str}
        """
        func = ensure_coro(func)
        return await func(*args, worker_attributes = await self.get_worker_attributes(), **kwargs)
    

    async def prepare_job_kws(
        self,
        iter_kwargs: Iterable[Dict], 
        broadcast: Optional[bool] = False,
        worker_names: Optional[List[str]] = None,
        worker_selector: Optional[Callable] = None,
        worker_selector_args: Optional[List] = None,
        worker_selector_kwargs: Optional[Dict] = None,
        workers_selected: Optional[List[Dict[str, str]]] = None,
        **kwargs
    ) -> Tuple[List[Dict[str, Any]], Optional[List[Dict[str, str]]]]:
        """
        Prepare jobs for broadcast or map.

        Returns:
            iter_kwargs: List of kwargs to pass to the job
            worker_kws: List of worker kwargs to pass to the job
        """
        timeout = kwargs.pop(self.job_timeout_kwarg, self.config.job_timeout)
        # Remove the job key from the kwargs
        _ = kwargs.pop(self.job_key_kwarg, None)
        if (
            not broadcast
            and not worker_selector
            and not worker_names
            and not workers_selected
        ):
            return [
                {
                    self.job_timeout_kwarg: timeout,
                    self.job_key_kwarg: kw.pop(self.job_key_kwarg, None) or self.config.get_default_job_key(),
                    **kwargs, **kw,
                }
                for kw in iter_kwargs
            ], None
        if workers_selected: worker_kws = workers_selected
        elif worker_selector:
            worker_selector_args = worker_selector_args or ()
            worker_selector_kwargs = worker_selector_kwargs or {}
            worker_kws = await self.select_workers(worker_selector, *worker_selector_args, **worker_selector_kwargs)
        elif worker_names: worker_kws = [{"worker_name": worker_name} for worker_name in worker_names]
        else: worker_kws = [{"worker_id": worker_id} for worker_id in await self.get_worker_ids()]
        broadcast_kwargs = []
        for kw in iter_kwargs:
            broadcast_kwargs.extend(
                {
                    self.job_timeout_kwarg: timeout,
                    self.job_key_kwarg: kw.pop(self.job_key_kwarg, None) or self.config.get_default_job_key(),
                    **kwargs, **kw, **worker_kw,
                }
                for worker_kw in worker_kws
            )
        return broadcast_kwargs, worker_kws

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
    ):
        """
        Broadcast a job to all nodes and collect all of their results.
        
        job_or_func: Same as Queue.enqueue
        kwargs: Same as Queue.enqueue
        timeout: How long to wait for the job to complete before raising a TimeoutError
        worker_names: List of worker names to run the job on. If provided, will run on these specified workers.
        worker_selector: Function that takes in a list of workers and returns a list of workers to run the job on. If provided, worker_names will be ignored.
        """
        if not enqueue:
            return await self.map(
                job_or_func, 
                iter_kwargs = [kwargs], 
                broadcast = True, 
                worker_names = worker_names,
                worker_selector = worker_selector,
                worker_selector_args = worker_selector_args,
                worker_selector_kwargs = worker_selector_kwargs,
                workers_selected = workers_selected,
            )
        
        iter_kwargs, _ = await self.prepare_job_kws(
            iter_kwargs = [kwargs], 
            broadcast = True, 
            worker_names = worker_names, 
            worker_selector = worker_selector,
            worker_selector_args = worker_selector_args,
            worker_selector_kwargs = worker_selector_kwargs,
            workers_selected = workers_selected,
            **kwargs
        )
        jobs: List[Job] = []
        for job_kwarg in iter_kwargs:
            jobs.append(await self.enqueue(job_or_func, **job_kwarg))
        return jobs


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
    ):
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
        timeout = kwargs.get(self.job_timeout_kwarg, self.config.job_timeout)
        iter_kwargs, worker_kws = await self.prepare_job_kws(
            iter_kwargs = iter_kwargs, 
            broadcast = broadcast, 
            worker_names = worker_names, 
            worker_selector = worker_selector, 
            workers_selected = workers_selected,
            worker_selector_args = worker_selector_args,
            worker_selector_kwargs = worker_selector_kwargs,
            **kwargs
        )
        if worker_kws:
            self.autologger.info(f"Broadcasting {job_or_func} to {len(worker_kws)} workers: {worker_kws}")
            
        job_keys = [key["key"] for key in iter_kwargs]
        pending_job_keys = set(job_keys)

        async def callback(job_key, status):
            if status in TERMINAL_JOB_STATUSES: pending_job_keys.discard(job_key)
            if status in UNSUCCESSFUL_TERMINAL_JOB_STATUSES and not return_exceptions: return True
            if not pending_job_keys: return True

        # Start listening before we enqueue the jobs.
        # This ensures we don't miss any updates.
        task = asyncio.create_task(self.listen(pending_job_keys, callback, timeout=None))
        try:
            await asyncio.gather(*[self.enqueue(job_or_func, **kw) for kw in iter_kwargs])
        except:
            task.cancel()
            raise

        await asyncio.wait_for(task, timeout = timeout)
        jobs: List[Job] = await asyncio.gather(*[self.job(job_key) for job_key in job_keys])
        results = []
        for job, job_key in zip(jobs, job_keys):
            if job is None:
                if not return_exceptions: raise ValueError(f"Job {job_key} not found")
                results.append(None)
            elif job.status in UNSUCCESSFUL_TERMINAL_JOB_STATUSES:
                exc = errors.JobError(job)
                if not return_exceptions: raise exc
                results.append(exc)
            else: results.append(job.result)
        return results

    """
    Job Management
    """

    async def listen(self, job_keys: List[str], callback: Callable, timeout: int = 10):
        """
        Listen to updates on jobs.

        job_keys: sequence of job keys
        callback: callback function, if it returns truthy, break
        timeout: if timeout is truthy, wait for timeout seconds
        """
        pubsub = self.ctx.aclient.pubsub(retryable=True)
        
        job_ids = [self.job_id(job_key) for job_key in job_keys]
        await pubsub.subscribe(*job_ids)
        async def listen():
            async for message in pubsub.listen():
                if message["type"] == "message":
                    job_id = message["channel"].decode("utf-8")
                    job_key = Job.key_from_id(job_id)
                    status = JobStatus[message["data"].decode("utf-8").upper()]
                    if asyncio.iscoroutinefunction(callback):
                        stop = await callback(job_key, status)
                    else:
                        stop = callback(job_key, status)
                    if stop: break

        try:
            if timeout: await asyncio.wait_for(listen(), timeout)
            else: await listen()
        finally: await pubsub.unsubscribe(*job_ids)

    async def notify(self, job: Job):
        """
        Notify subscribers of a job update.
        """
        await self.ctx.aclient.publish(job.id, job.status)
        await job.run_job_callback()


    async def update(self, job: Job):
        """
        Update a job.
        """
        job.touched = now()
        await self.ctx.aclient.set(job.id, await self.serialize(job))
        await self.notify(job)
        # if self.function_tracker_enabled: 
        #     await self.track_job_id(job)

    async def job(self, job: Union[str, Job]) -> Job:
        """
        Fetch a Job by key or refresh the job
        """
        job_id = self.job_id(job)
        return await self.get_job_by_id(job_id)


    async def job_exists(self, job: Union[str, Job]) -> bool:
        """
        Check if a job exists
        """
        job_id = self.job_id(job)
        return await self.ctx.aexists(job_id)


    async def dequeue_job_id(
        self,
        timeout: int = 0,
        postfix: str = None,
    ):
        """
        Dequeue a job from the queue.
        """
        queued_key, active_key = self.queued_key, self.active_key
        if postfix:
            queued_key = f'{self.queued_key}:{postfix}'
            active_key = f'{self.active_key}:{postfix}'
        
        
        # if self.version < (6, 2, 0):
        #     return await self.ctx.abrpoplpush(
        #         queued_key, 
        #         active_key, 
        #         timeout
        #     )
        # return await self.ctx.ablmove(
        #     queued_key, 
        #     active_key, 
        #     timeout,
        #     "RIGHT", 
        #     "LEFT", 
        # )
        return await self.dequeue_func_method(
            queued_key,  active_key,  timeout
        )
    

    async def dequeue(
        self, 
        timeout = 0, 
        worker_id: str = None, 
        worker_name: str = None
    ):
        """
        Dequeue a job from the queue.
        """
        job_id = await self.dequeue_job_id(timeout) if \
            worker_id is None and worker_name is None else None
        
        if job_id is None and worker_id:
            job_id = await self.dequeue_job_id(timeout, worker_id)
            
        if job_id is None and worker_name:
            job_id = await self.dequeue_job_id(timeout, worker_name)
        
        if job_id is not None:
            # logger.info(f'Fetched job id {job_id}: {queued_key}: {active_key}')
            # self.autologger.info(f'Fetched job id {job_id}')
            return await self.get_job_by_id(job_id)

        if not worker_id and not worker_name: self.logger(kind="dequeue").info("Dequeue timed out")
        return None

    async def _deferred(
        self, 
        job_or_func: Union[Job, str],
        wait_time: float = 10.0, 
        **kwargs
    ):
        """
        Defer a job by instance or string after a certain amount of time
        """
        await asyncio.sleep(wait_time)
        return await self.enqueue(job_or_func, **kwargs)
    



    """
    Utility Functions
    """

    async def get_job_by_id(self, job_id: str) -> Job:
        """
        Returns a job by id.
        """
        async with self.op_sephamore():
            return await self.deserialize(await self.ctx.aclient.get(job_id))

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
        t = Timer()
        while True:
            try: await job.refresh()
            except RuntimeError: await job.enqueue()
            except AttributeError as e:
                if verbose: self.autologger.error(f'Unable to refresh job {job}')
                if raise_exceptions: raise e
                break
            
            if job.status == JobStatus.COMPLETE:
                if source_job: source_job += 1
                break
            elif job.status == JobStatus.FAILED:
                if verbose: self.autologger.error(f'Job {job.id} failed: {job.error}')
                if raise_exceptions: raise job.error
                break
            await asyncio.sleep(refresh_interval)
        
        if verbose:
            if source_job: self.autologger.info(f'Completed {source_job.id} in {t.total_s}')
            else: self.autologger.info(f'Completed job {job.id} in {t.total_s}')
        return job.result
    

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
        results, num_jobs = [], len(jobs)
        t = Timer()
        while jobs:
            for job in jobs:
                try: await job.refresh()
                except RuntimeError: await job.enqueue()
                except AttributeError as e:
                    if verbose: self.autologger.error(f'Unable to refresh job {job}')
                    if raise_exceptions: raise e
                    jobs.remove(job)
                
                if job.status == JobStatus.COMPLETE:
                    results.append(job.result)
                    if source_job: source_job += 1
                    jobs.remove(job)
                elif job.status == JobStatus.FAILED:
                    if verbose: self.autologger.error(f'Job {job.id} failed: {job.error}')
                    if raise_exceptions: raise job.error
                    jobs.remove(job)
                if not jobs: break
            await asyncio.sleep(refresh_interval)
        
        if verbose: 
            if source_job: self.autologger.info(f'Completed {source_job.id} w/ {len(results)}/{num_jobs} in {t.total_s}')
            else: self.autologger.info(f'Completed {len(results)}/{num_jobs} jobs in {t.total_s}')
        return results        


    
    async def as_jobs_complete(
        self,
        jobs: List[Job],
        source_job: Optional[Job] = None,
        verbose: Optional[bool] = False,
        raise_exceptions: Optional[bool] = False,
        refresh_interval: Optional[float] = 0.5,
        return_results: Optional[bool] = True,
        cancel_func: Optional[Callable] = None,
        **kwargs,
    ) -> typing.AsyncGenerator[Any, None]:
        # sourcery skip: low-code-quality
        """
        Generator that yields results as they complete
        """
        t = Timer()
        num_results, num_jobs = 0, len(jobs)
        while jobs:
            for job in jobs:
                try: await job.refresh()
                except RuntimeError: await job.enqueue()
                except AttributeError as e:
                    if verbose: self.autologger.error(f'Unable to refresh job {job}')
                    if raise_exceptions: raise e
                    jobs.remove(job)
                
                if job.status == JobStatus.COMPLETE:
                    yield job.result if return_results else job
                    num_results += 1
                    if source_job: source_job += 1
                    jobs.remove(job)
                
                elif job.status == JobStatus.FAILED:
                    if verbose: self.autologger.error(f'Job {job.id} failed: {job.error}')
                    if raise_exceptions: raise job.error
                    jobs.remove(job)
                
                if not jobs: break
            if cancel_func and await cancel_func():
                if verbose: self.autologger.info(f'Cancelled {len(jobs)} jobs')
                await asyncio.gather(*[self.abort(job, "cancelled") for job in jobs])
                break
            await asyncio.sleep(refresh_interval)
        
        if verbose: 
            if source_job: self.autologger.info(f'Completed {source_job.id} w/ {num_results}/{num_jobs} in {t.total_s}')
            else: self.autologger.info(f'Completed {num_results}/{num_jobs} jobs in {t.total_s}')


    """
    Hooks
    """

    def register_before_enqueue(self, callback: Callable[..., Any]):
        """
        Registers a callback to run before enqueue.
        """
        self._before_enqueues[id(callback)] = callback


    def unregister_before_enqueue(self, callback: Callable[..., Any]):
        """
        Unregisters a callback to run before enqueue.
        """
        self._before_enqueues.pop(id(callback), None)


    async def _before_enqueue(self, job: Job):
        """
        Helper function to run before enqueue.
        """
        for cb in self._before_enqueues.values():
            await cb(job)

    """
    Context Managers
    """
    @contextlib.asynccontextmanager
    async def pipeline(self, transaction: bool = True, shard_hint: Optional[str] = None, raise_on_error: Optional[bool] = None, retryable: Optional[bool] = None):
        """
        Context manager to run a pipeline.

        This context manager is a wrapper around the redis pipeline context manager to ensure that it is
        properly deleted.
        """
        yield self.ctx.apipeline(transaction = transaction, shard_hint = shard_hint, raise_on_error = raise_on_error, retryable = retryable)

    @contextlib.asynccontextmanager
    async def op_sephamore(self, disabled: Optional[bool] = None, **kwargs):
        """
        Allow certain operations to be run concurrently without exceeding the max_concurrency.
        """
        if disabled is not True:
            async with self._op_sem:
                yield
        else: yield


    async def serialize(self, job: Job):
        """
        Serialize a job.
        """
        if self.ctx.session_serialization_enabled:
            return job
        try:
            return await self.serializer.adumps(job)
        except Exception as e:
            from lazyops.utils.debugging import inspect_serializability
            self.settings.logger.trace(f"Unable to serialize job: {job}", e, depth = 2)
            data = job.model_dump()
            for k,v in data.get('kwargs', {}).items():
                inspect_serializability(v, name = k)
            raise e
    
    async def deserialize(self, job: Union[bytes, str, Job]) -> Job:
        """
        Deserialize a job.
        """
        if isinstance(job, (bytes, str)):
            job = await self.serializer.aloads(job)
        assert job.queue_name == self.queue_name, f"Job is not for this queue: {job.queue_name} != {self.queue_name}"
        job.queue = self
        return job


    def job_id(self, job_key: Union[str, Job]) -> str:
        """
        Returns the job id for a job key.
        """
        if isinstance(job_key, Job): return job_key.id
        # self.autologger.info(f"job_id_prefix: {self.job_id_prefix}, {job_key}")
        return f"{self.job_id_prefix}:{job_key}" if self.job_id_prefix not in job_key else job_key


    async def count(self, kind: str, postfix: Optional[str] = None):
        """
        Returns the number of jobs in the given queue.
        """
        if kind == "queued":
            return await self.ctx.allen(f"{self.queued_key}:{postfix}" if postfix else self.queued_key)
        if kind == "active":
            return await self.ctx.allen(f"{self.active_key}:{postfix}" if postfix else self.active_key)
        if kind == "scheduled":
            return await self.ctx.azcount(f"{self.scheduled_key}:{postfix}" if postfix else self.scheduled_key, 1, "inf")
        if kind == "incomplete":
            return await self.ctx.azcard(f"{self.incomplete_key}:{postfix}" if postfix else self.incomplete_key)
        raise ValueError(f"Can't count unknown type {kind} {postfix}")


    def create_namespace(self, namespace: str) -> str:
        """
        Creates a namespace for the given namespace
        """
        return f"{self.queue_prefix}:{self.queue_name}:{namespace}"
    
    @property
    def ctx(self) -> 'KVDBSession':
        """
        Returns the KVDB Session
        """
        if self._ctx is None:
            from kvdb.client import KVDBClient
            self._ctx = KVDBClient.get_session(
                name = f'tasks:{self.queue_name}',
                db_id = self.config.queue_db_id,

                pool_max_connections = self.max_concurrency * 10,
                apool_max_connections = self.max_concurrency ** 2,

                serializer = self.config.serializer,
                serializer_kwargs = self.config.serializer_kwargs,
                compression = self.config.compression,
                compression_level = self.config.compression_level,

                socket_keepalive = self.config.socket_keepalive,
                socket_timeout = self.config.socket_timeout,
                socket_connect_timeout = self.config.socket_connect_timeout,
                health_check_interval = self.config.heartbeat_interval,
                
                persistence_name = f'{self.queue_name}.persistence',
                persistence_serializer = 'json',
                persistence_expiration = self.config.job_max_stuck_duration,
                persistence_async_enabled = True,
                persistence_base_key = f'{self.queue_prefix}.{self.queue_name}.persistence',
                persistence_hset_disabled = True,
                set_as_ctx = False,
            )
        return self._ctx
    
    @property
    def push_queue(self) -> PushQueue:
        """
        Returns the push queue
        """
        if self._push_queue is None:
            from .types import PushQueue
            self._push_queue = PushQueue(self.ctx, **self.push_queue_kwargs)
        return self._push_queue

    @property
    def version(self) -> Tuple[int, int, int]:
        """
        Returns the version of the Task Queue
        """
        if self._version is None:
            info = self.ctx.info()
            self._version = tuple(int(i) for i in info["redis_version"].split("."))
        return self._version
    
    @property
    def dequeue_func_method(self) -> Callable[..., Any]:
        """
        Returns the dequeue function method
        """
        if self._dequeue_func_method is None:
            if self.version < (6, 2, 0):
                self._dequeue_func_method = self.ctx.abrpoplpush
            else:
                self._dequeue_func_method = functools.partial(
                    self.ctx.ablmove, 
                    src = "RIGHT", 
                    dest = "LEFT"
                )
        return self._dequeue_func_method
    
    @property
    def autologger(self) -> 'Logger':
        """
        Returns the autologger
        """
        return self.settings.logger if self.config.debug_enabled else self.settings.autologger
    
    @property
    def data(self) -> 'PersistentDict':
        """
        Returns the data
        """
        if self._data is None: self._data = self.ctx.persistence
        return self._data

    def logger(
        self, 
        job: 'Job' = None, 
        kind: str = "enqueue", 
        job_id: Optional[str] = None,
    ) -> 'Logger':
        """
        Returns a logger for the queue.
        """
        _kwargs = {
            'worker_name': self.worker_log_name,
            'queue_name': self.queue_log_name,
            'kind': kind,
        }
        if job or job_id: _kwargs['job_id'] = job.id if job else job_id
        if job: _kwargs['status'] = job.status
        return self.settings.logger.bind(**_kwargs)

    """
    Worker Management
    """

    async def get_worker_ids(self) -> List[str]:
        """
        Returns the worker ids
        """
        return await self.data.aget_keys('heartbeats:*', exclude_base_key = True)
    
    async def get_worker_names(self) -> List[str]:
        """
        Returns the worker names
        """
        worker_ids = await self.get_worker_ids()
        return await self.data.aget_values(worker_ids)
    

    async def get_worker_attributes(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns the worker attributes
        """
        worker_ids = await self.get_worker_ids()
        data = await self.data.aget('workers', {})
        return {worker_id: data.get(worker_id, {}) for worker_id in worker_ids}


    async def add_heartbeat(
        self, 
        worker_id: str, 
        worker_name: str,
        heartbeat_ttl: Optional[int] = None,
    ):
        """
        Registers a heartbeat for the current worker.
        """
        heartbeat_ttl = heartbeat_ttl or self.config.heartbeat_interval
        heartbeat_key = f"heartbeats:{worker_id}"
        await self.data.aset(heartbeat_key, worker_name, ex = int(heartbeat_ttl))



    """
    Initialization
    """
    
    def pre_init(self, **kwargs):
        """
        Called before the Task Queue is initialized
        """
        pass

    def post_init(self, **kwargs):
        """
        Called after the Task Queue is initialized
        """
        pass

    def finalize_init(self, **kwargs):
        """
        Called after the Task Queue is initialized
        """
        self._register()


    def cls_init(self, **kwargs):
        """
        Called when a class is initialized
        """
        # Handles initialization of the init
        self._schedule_script: 'AsyncScript' = None
        self._enqueue_script: 'AsyncScript' = None
        self._cleanup_script: 'AsyncScript' = None
        self.process_id: int = os.getpid()
        self.max_concurrency = self.config.max_concurrency
        self.max_broadcast_concurrency = self.config.max_broadcast_concurrency
        self._op_sem = asyncio.Semaphore(self.max_concurrency)

        
        # Configure Misc Variables
        from lazyops.utils.system import get_host_name
        self.node_name = get_host_name()
        self.is_primary_process = self.settings.temp_data.has_logged(f'primary_process.queue:{self.queue_name}')
        
        if self.settings.in_k8s:
            self.is_leader_process = self.node_name[-1].isdigit() and int(self.node_name[-1]) == 0 and self.is_primary_process
        else:
            self.is_leader_process = self.is_primary_process
        
        # Configure the keys
        self.incomplete_key = self.create_namespace('incomplete')
        self.queued_key = self.create_namespace('queued')
        self.active_key = self.create_namespace('active')
        self.scheduled_key = self.create_namespace('scheduled')
        self.sweep_key = self.create_namespace('sweep')
        self.stats_key = self.create_namespace('stats')
        self.complete_key = self.create_namespace('complete')
        self.abort_id_prefix = self.create_namespace('abort')
        self.heartbeat_key = self.create_namespace('heartbeat')
        self.job_id_prefix = self.create_namespace(self.config.job_prefix)

        self.queue_info_key = self.create_namespace('queue_info')
        self.queue_job_ids_key = self.create_namespace('jobids')
        self.worker_map_key = self.create_namespace('worker_map')
        self.lock = anyio.Lock()
        self._ctx: Optional['KVDBSession'] = None
        self._push_queue: Optional[PushQueue] = None
        self._before_enqueues = {}
        self._version: Optional[Tuple[int, int, int]] = None
        self.logging_max_length = (
            self.config.truncate_logs if isinstance(self.config.truncate_logs, int) \
            else None if self.config.truncate_logs is True else 2000
        )

        self._data: Optional['PersistentDict'] = None

        self.worker_log_name = self.config.worker_log_name or f"{self.node_name}:{self.process_id}"
        self.queue_log_name = self.config.queue_log_name or self.queue_name
        self._dequeue_func_method: Callable[..., Any] = None

        self.job_key_kwarg = f'{self.config.job_function_kwarg_prefix}key' if self.config.job_function_kwarg_prefix else 'key'
        self.job_timeout_kwarg = f'{self.config.job_function_kwarg_prefix}timeout' if self.config.job_function_kwarg_prefix else 'timeout'

        # Worker Config that is set when the worker is registered
        # self.worker_id: Optional[str] = None
        self.worker_registered: Dict[str, bool] = {}

    async def disconnect(self):
        """
        Disconnects the queue.
        """
        await self.ctx.aclose()

    def _register(self):
        """
        Register the Task Queue with the Task Queue Manager
        """
        from kvdb.tasks import TaskManager
        self.queue_tasks = TaskManager.register_task_queue(self)


    async def register_script(self, kind: Literal['schedule', 'enqueue', 'cleanup']):
        """
        Registers a script.
        """
        from .static import QueueScripts
        script = self.ctx.aclient.register_script(QueueScripts[kind])
        setattr(self, f'_{kind}_script', script)
    

    async def aregister_worker(self, worker: 'TaskWorker'):
        """
        Register the worker with the queue
        """
        if self.worker_registered.get(worker.worker_id): return
        await self.data.asetdefault('workers', {})
        self.worker_registered[worker.worker_id] = True
        atexit.register(self.deregister_worker_on_exit, worker_id = worker.worker_id)
        # worker_id = worker.worker_id
        # worker_name = worker.worker_name
        # self.worker_id = worker_id
        # self.worker_name = worker_name
        # self.worker = worker
        self.data['workers'][worker.worker_id] = worker.worker_attributes
        await self.data.aset(f'heartbeats:{worker.worker_id}', worker.name, ex = int(self.config.heartbeat_interval))
        await self.data._asave_mutation_objects()
        
    
    def register_worker(self, worker: 'TaskWorker'):
        """
        Register the worker with the queue
        """
        if self.worker_registered.get(worker.worker_id): return
        self.data.setdefault('workers', {})
        self.worker_registered[worker.worker_id] = True
        atexit.register(self.deregister_worker_on_exit, worker_id = worker.worker_id)
        # worker_id = worker.worker_id
        # worker_name = worker.worker_name
        # self.worker_id = worker_id
        # self.worker_name = worker_name
        # self.worker = worker
        self.data['workers'][worker.worker_id] = worker.worker_attributes
        self.data.set(f'heartbeats:{worker.worker_id}', worker.name, ex = int(self.config.heartbeat_interval))
        self.data._save_mutation_objects()
        
    
    def deregister_worker_on_exit(self, worker_id: Optional[str] = None):
        """
        Handles deregistering the worker on exit
        """
        # worker_id = worker_id or self.worker_id
        self.data.delete(f'heartbeats:{worker_id}')
        _ = self.data['workers'].pop(worker_id, None)
        self.data._save_mutation_objects()

