from __future__ import annotations

"""
Base Task Types
"""

import abc
import makefun
import functools
import contextlib
from inspect import signature, Parameter
from pydantic import Field, model_validator, validator
from kvdb.types.base import BaseModel
from kvdb.utils.logs import logger
from kvdb.utils.helpers import is_coro_func, lazy_import
from lazyops.libs.proxyobj import ProxyObject
from lazyops.libs.pooler import ThreadPooler
from typing import Optional, Dict, Any, Union, TypeVar, Callable, Awaitable, List, Tuple, Literal, TYPE_CHECKING, overload

if TYPE_CHECKING:
    from kvdb.components.session import KVDBSession
    from kvdb.components.pipeline import AsyncPipelineT
    from kvdb.types.jobs import Job


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

