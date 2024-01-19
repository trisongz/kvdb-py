from __future__ import annotations

import typing
import datetime
import croniter
import contextlib

from pydantic import Field, validator, computed_field, model_validator
from lazyops.libs.pooler import ThreadPooler
from kvdb.utils.logs import logger
from kvdb.utils.helpers import (
    lazy_import,
    get_func_full_name,
    now, 
    seconds, 
)
from kvdb.utils.retry import exponential_backoff
from kvdb.configs import settings

from .base import BaseModel
from .common import (
    JobStatus, 
    TERMINAL_JOB_STATUSES, 
    UNSUCCESSFUL_TERMINAL_JOB_STATUSES, 
    INCOMPLETE_JOB_STATUSES
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
    Mapping, 
    TypeVar,
    TYPE_CHECKING
)


if TYPE_CHECKING:
    from aiokeydb.types.task_queue import TaskQueue


JobResultT = TypeVar('JobResultT')

class BaseJobProperties(BaseModel):
    """
    Base job properties
    """
    timeout: Optional[int] = None
    retries: Optional[int] = None
    ttl: Optional[int] = None
    retry_delay: Optional[float] = None
    retry_backoff: Union[bool, float] = True
    max_stuck_duration: Optional[float] = None

    @model_validator(mode = 'after')
    def validate_job_props(self):
        """
        Validates the job properties
        """
        if self.timeout is None: self.timeout = settings.tasks.job_timeout
        if self.retries is None: self.retries = settings.tasks.job_retries
        if self.retry_delay is None: self.retry_delay = settings.tasks.job_retry_delay
        if self.ttl is None: self.ttl = self.timeout * 2
        if self.max_stuck_duration is None: self.max_stuck_duration = self.timeout * 4
        return self

class JobQueueMixin(BaseModel):
    """
    Holds the queue for a job
    """

    if TYPE_CHECKING:
        queue: Optional['TaskQueue'] = None
        worker_id: Optional[str] = None
        worker_name: Optional[str] = None
        key: Optional[str] = None
        completed: Optional[int] = None
    else:
        queue: Optional[Any] = Field(default = None, exclude = True)


    
    """
    Queue Keys for Job
    """

    @computed_field
    @property
    def queued_key(self) -> str:
        if self.worker_id:
            return f"{self.queue.queued_key}:{self.worker_id}"
        if self.worker_name:
            return f"{self.queue.queued_key}:{self.worker_name}"
        return self.queue.queued_key
    
    @computed_field
    @property
    def active_key(self) -> str:
        if self.worker_id:
            return f"{self.queue.active_key}:{self.worker_id}"
        if self.worker_name:
            return f"{self.queue.active_key}:{self.worker_name}"
        return self.queue.active_key
    
    @computed_field
    @property
    def incomplete_key(self) -> str:
        if self.worker_id:
            return f"{self.queue.incomplete_key}:{self.worker_id}"
        if self.worker_name:
            return f"{self.queue.incomplete_key}:{self.worker_name}"
        return self.queue.incomplete_key
    
    @computed_field
    @property
    def job_fields(self) -> List[str]:
        """
        Returns the job fields
        """
        return list(self.model_fields.keys()) - ['queue']

    @property
    def id(self):
        """
        Returns the job id.
        """
        return self.queue.job_id(self.key)

    @property
    def abort_id(self):
        """
        Returns the abort id.
        """
        return f"{self.queue.abort_id_prefix}:{self.key}"
    
    
    @classmethod
    def key_from_id(cls, job_id: str):
        """
        Returns the key from a job id.
        """
        return job_id.rsplit(":", 1)[-1]
    

    def replace(self, job: 'Job'):
        """
        Replace current attributes with job attributes.
        """
        for field in job.job_fields:
            setattr(self, field, getattr(job, field))


    async def refresh(self, until_complete: int = None):
        """
        Refresh the current job with the latest data from the db.

        until_complete: None or Numeric seconds. if None (default), don't wait,
            else wait seconds until the job is complete or the interval has been reached. 0 means wait forever
        """
        job = await self.queue.job(self.key)
        if not job: raise RuntimeError(f"{self} doesn't exist")
        
        self.replace(job)
        if until_complete is not None and not self.completed:
            async def callback(_id, status):
                if status in TERMINAL_JOB_STATUSES:
                    return True
            await self.queue.listen([self.key], callback, until_complete)
            await self.refresh()
    

    async def enqueue(self, queue: 'TaskQueue' = None):
        """
        Enqueues the job to it's queue or a provided one.

        A job that already has a queue cannot be re-enqueued. Job uniqueness is determined by its id.
        If a job has already been queued, it will update it's properties to match what is stored in the db.
        """
        queue = queue or self.queue
        assert queue, "Queue unspecified"
        if not await queue.enqueue(self):
            await self.refresh()

    async def abort(self, error: Optional[Any] = None, ttl: int = 5):
        """
        Tries to abort the job.
        """
        error = error or "Aborted"
        await self.queue.abort(self, error = error, ttl = ttl)

    async def finish(
        self, 
        status: JobStatus, 
        *, 
        result: Optional[Any] = None,
        error: Optional[Any] = None,
    ):
        """
        Finishes the job with a Job.Status, result, and or error.
        """
        await self.queue.finish(self, status = status, result = result, error = error)

    async def retry(
        self, 
        error: Optional[Any] = None,
    ):
        """
        Retries the job by removing it from active and requeueing it.
        """
        error = error or "Retrying"
        await self.queue.retry(self, error)

    async def update(
        self, 
        **kwargs
    ):
        """
        Updates the stored job in kvdb.

        Set properties with passed in kwargs.
        """
        for k, v in kwargs.items():
            setattr(self, k, v)
        # Allow Updates without breaking if something goes wrong
        with contextlib.suppress(Exception):
            await self.queue.update(self)
    
    @contextlib.asynccontextmanager
    async def do_save(self):
        """
        Saves the job after the context manager is done.
        """
        try:
            yield
            await self.queue.update(self)
        except Exception as e:
            raise e
        

class CronJob(BaseJobProperties, BaseModel):
    """
    Allows scheduling of repeated jobs with cron syntax.

    function: the async function to run
    cron: cron string for a job to be repeated, uses croniter
    unique: unique jobs only one once per queue, defaults true

    Remaining kwargs are pass through to Job
    """
    function: Union[str, Callable[..., JobResultT]]
    cron: str
    unique: Optional[bool] = True
    cron_name: Optional[str] = None
    default_kwargs: Optional[Dict[str, Any]] = None

    callback: Optional[Union[str, Callable[..., Any]]] = None
    callback_kwargs: Optional[Dict[str, Any]] = None

    bypass_lock: Optional[bool] = None

    @validator('function', pre = True)
    def validate_callables(cls, v: Optional[Union[str, Callable[..., Any]]]) -> Callable[..., Any]:
        """
        Validates the callables
        """
        if v is None: return v
        if isinstance(v, str): v = lazy_import(v)
        return v
    

    @validator("callback")
    def validate_callback(cls, v: Optional[Union[str, Callable]]) -> Optional[str]:
        """
        Validates the callback and returns the function name
        """
        return v if v is None else get_func_full_name(v)


    @model_validator(mode = 'after')
    def validate_cronjob(self):
        """
        Validates the cronjob
        """
        return self


    @property
    def function_name(self) -> str:
        """
        Returns the name of the function
        """
        return self.cron_name or self.function.__qualname__
    

    def next_scheduled(self) -> int:
        """
        Returns the next scheduled time for the cron job
        """
        return int(croniter.croniter(self.cron, seconds(now())).get_next())
    


class JobProgress(BaseModel):

    """
    Holds the progress of a job
    """
    total: Optional[int] = 0
    completed: Optional[int] = 0

    @property
    def value(self) -> float:
        """
        Returns the progress of a job as a float between 0.0 and 1.0
        """
        return 0.0 if self.total == 0 else self.completed / self.total
    
    @property
    def percent(self) -> float:
        """
        Returns the progress of a job as a float between 0.0 and 100.0
        """
        return self.value * 100.0
    
    def set(self, total: Optional[int] = None, completed: Optional[int] = None):
        """
        Sets the progress of a job
        """
        if total is not None: self.total = total
        if completed is not None: self.completed = completed

    def update(self, completed: int = 1):
        """
        Updates the progress of a job
        """
        self.completed += completed

    def __add__(self, value: Union[int, float]) -> JobProgress:
        """
        Adds a value to the progress
        """
        self.update(value)
        return self
    
    def __sub__(self, value: Union[int, float]) -> JobProgress:
        """
        Subtracts a value from the progress
        """
        self.update(-value)
        return self
    
    def __iadd__(self, value: Union[int, float]) -> JobProgress:
        """
        Adds a value to the progress
        """
        self.update(value)
        return self
    
    def __isub__(self, value: Union[int, float]) -> JobProgress:
        """
        Subtracts a value from the progress
        """
        self.update(-value)
        return self
    


class JobProperties(BaseModel):
    """
    The properties of a job
    
    heartbeat: the maximum amount of time a job can survive without a heartebat in seconds, defaults to 0 (disabled)
    scheduled: epoch seconds for when the job should be scheduled, defaults to 0 (schedule right away)
    progress: job progress 0.0..1.0
    
    attempts: number of attempts a job has had
    completed: job completion time epoch seconds
    queued: job enqueued time epoch seconds
    started: job started time epoch seconds
    touched: job touched/updated time epoch seconds
    """
    heartbeat: Optional[int] = 0
    scheduled: Optional[int] = 0
    progress: Optional[JobProgress] = Field(default_factory = JobProgress)
    # progress: Optional[float] = 0.0
    
    attempts: Optional[int] = 0
    completed: Optional[int] = 0
    queued: Optional[int] = 0
    started: Optional[int] = 0
    touched: Optional[int] = 0


class Job(BaseJobProperties, JobProperties, JobQueueMixin, BaseModel):
    """
    Main job class representing a run of a function.

    User Provided Arguments
        function: the async function name to run
        kwargs: kwargs to pass to the function
        queue: the saq.Queue object associated with the job
        key: unique identifier of a job, defaults to uuid1, can be passed in to avoid duplicate jobs
        timeout: the maximum amount of time a job can run for in seconds, defaults to 600 (0 means disabled)
        heartbeat: the maximum amount of time a job can survive without a heartebat in seconds, defaults to 0 (disabled)
            a heartbeat can be triggered manually within a job by calling await job.update()
        retries: the maximum number of attempts to retry a job, defaults to 1
        ttl: the maximum time in seconds to store information about a job including results, defaults to 600 (0 means indefinitely, -1 means disabled)
        retry_delay: seconds to delay before retrying the job
        retry_backoff: If true, use exponential backoff for retry delays.
            The first retry will have whatever retry_delay is.
            The second retry will have retry_delay*2. The third retry will have retry_delay*4. And so on.
            This always includes jitter, where the final retry delay is a random number between 0 and the calculated retry delay.
            If retry_backoff is set to a number, that number is the maximum retry delay, in seconds.
        scheduled: epoch seconds for when the job should be scheduled, defaults to 0 (schedule right away)
        progress: job progress 0.0..1.0
        meta: arbitrary metadata to attach to the job
    
    Framework Set Properties: JobProperties
    """

    function: str

    args: Optional[List[Any]] = Field(default_factory = list)
    kwargs: Optional[Dict[str, Any]] = Field(default_factory = dict)

    key: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[Union[str, Exception, Any]] = None
    status: Optional[JobStatus] = JobStatus.NEW
    metadata: Optional[Dict[str, Any]] = Field(default_factory = dict)

    worker_id: Optional[str] = None
    worker_name: Optional[str] = None

    job_callback: Optional[Union[str, Callable]] = None
    job_callback_kwargs: Optional[Dict[str, Any]] = Field(default_factory = dict)
    bypass_lock: Optional[bool] = None


    @validator("job_callback", pre = True)
    def validate_job_callback(cls, v: Optional[Union[str, Callable]]) -> Optional[str]:
        """
        Validates the callback and returns the function name
        """
        return v if v is None else get_func_full_name(v)
    
    @validator("key", pre = True)
    def validate_key(cls, v: Optional[str]) -> str:
        """
        Validates the key
        """
        return v if v is not None else settings.tasks.get_default_job_key()


    @classmethod
    def create(
        cls, 
        job_or_func: Union[str, 'Job', Callable], 
        *args,
        **kwargs
    ) -> 'Job':
        """
        create a job from kwargs.
        """
        job_kwargs = {"kwargs": {}, "args": args}
        job_fields = cls.model_fields.keys()
        for key in kwargs:
            if key in job_fields:
                job_kwargs[key] = kwargs.pop(key)
                continue
            job_kwargs["kwargs"][key] = kwargs.pop(key)
        
        if isinstance(job_or_func, str):
            job = cls(function = job_or_func, **job_kwargs)
        
        elif isinstance(job_or_func, Job):
            job = job_or_func
            for k, v in job_kwargs.items():
                setattr(job, k, v)
        elif callable(job_or_func):
            job = cls(function = job_or_func.__name__, **job_kwargs)
        
        else:
            raise ValueError(f"Invalid job_or_func: {job_or_func} {type(job_or_func)}")
        return job


    def next_retry_delay(self) -> Optional[float]:
        """
        Gets the next retry delay for the job.
        """
        if self.retry_backoff:
            max_delay = self.retry_delay
            if max_delay is True: max_delay = None
            return exponential_backoff(
                attempts = self.attempts,
                base_delay = self.retry_delay,
                max_delay = max_delay,
                jitter = True,
            )
        return self.retry_delay
        

    """
    Callbacks
    """

    @property
    def job_callback_function(self) -> Optional[Callable]:
        """
        Returns the job callback function
        """
        if self.job_callback is None: return None
        func = lazy_import(self.job_callback)
        return ThreadPooler.ensure_coro_function(func)
    

    @property
    def has_job_callback(self) -> bool:
        """
        Checks if the job has a callback
        """
        return self.job_callback is not None
    

    async def _run_job_callback(self):
        """
        Runs the job callback
        """
        if not self.has_job_callback: return
        if self.status not in TERMINAL_JOB_STATUSES: return
        try:
            await self.job_callback_function(
                status = self.status,
                job_id = self.id,
                function_name = self.function,
                duration = self.duration,
                result = self.result,
                error = self.error,
                **self.job_callback_kwargs or {},
            )
        except Exception as e:
            logger.error(f"Failed to run job callback for {self}: {e}")


    async def run_job_callback(self):
        """
        Runs the job callback in the background
        """
        ThreadPooler.background_task(self._run_job_callback())

    """
    Properties
    """

    @property
    def duration(self) -> Optional[int]:
        """
        Returns the duration of the job in ms.
        """
        for kind in {
            'process', 'total', 'start', 'running', 'queued'
        }:
            if duration := self.calc_duration(kind): return duration


    @property
    def stuck(self):
        """
        Checks if an active job is passed it's timeout or heartbeat.
        """
        current = now()
        return (self.status == JobStatus.ACTIVE) and (
            seconds(current - self.started) > \
                (self.timeout if self.timeout is not None else self.max_stuck_duration)
            or (
                self.heartbeat and \
                    seconds(current - self.touched) > self.heartbeat
                )
        )
    

    
    @property
    def in_progress(self) -> bool:
        """
        Checks if the job is in progress.
        """
        return self.status in INCOMPLETE_JOB_STATUSES
    
    @property
    def has_failed(self) -> bool:
        """
        Checks if the job has failed.
        """
        return self.status in UNSUCCESSFUL_TERMINAL_JOB_STATUSES
    
    @property
    def is_complete(self) -> bool:
        """
        Checks if the job is complete.
        """
        return self.status == JobStatus.COMPLETE

    @property
    def is_cronjob(self) -> bool:
        """
        Checks if the job is a cronjob.
        """
        return settings.tasks.cronjob_prefix in self.id

    """
    Utility Methods
    """

    def get_duration(self, kind: str) -> int:
        """
        Returns the duration of the job given kind.

        Kind can be process (how long it took to process),
        start (how long it took to start), or total.
        """
        if kind == "process":
            return self.calc_duration(self.completed, self.started)
        if kind == "start":
            return self.calc_duration(self.started, self.queued)
        if kind == "total":
            return self.calc_duration(self.completed, self.queued)
        if kind == "running":
            return self.calc_duration(now(), self.started)
        if kind == "queued":
            return self.calc_duration(now(), self.queued)
        raise ValueError(f"Unknown duration type: {kind}")

    def calc_duration(self, a: int, b: int) -> Optional[int]:
        """
        Returns the duration between two timestamps
        """
        return a - b if a and b else None


    def __hash__(self): return hash(self.key)

    def __eq__(self, other: Union[str, 'Job']):
        """
        Checks if the job is equal to another job or a string.
        """
        return self.key == other if isinstance(other, str) else self.key == other.key

    def set_progress(self, total: Optional[int] = None, completed: Optional[int] = None):
        """
        Sets the progress of a job
        """
        self.progress.set(total = total, completed = completed)

    def __add__(self, value: Union[int, float]) -> Job:
        """
        Adds a value to the progress
        """
        self.progress.update(value)
        return self
    
    def __sub__(self, value: Union[int, float]) -> Job:
        """
        Subtracts a value from the progress
        """
        self.progress.update(-value)
        return self
    
    def __iadd__(self, value: Union[int, float]) -> Job:
        """
        Adds a value to the progress
        """
        self.progress.update(value)
        return self
    
    def __isub__(self, value: Union[int, float]) -> Job:
        """
        Subtracts a value from the progress
        """
        self.progress.update(-value)
        return self
    
    def __setitem__(self, key: str, value: Any):
        """
        Sets the metadata or value
        """
        if key in {'result', 'error', 'status'}:
            setattr(self, key, value)
            return
        
        if key not in self.metadata:
            self.metadata[key] = value
            return
        
        if isinstance(self.metadata[key], dict) and isinstance(value, dict):
            self.metadata[key].update(value)
        elif isinstance(self.metadata[key], list) and isinstance(value, list):
            self.metadata[key].extend(value)
        elif isinstance(self.metadata[key], set) and isinstance(value, set):
            self.metadata[key].update(value)
        elif isinstance(self.metadata[key], tuple) and isinstance(value, tuple):
            self.metadata[key] += value
        elif isinstance(self.metadata[key], (int, float)) and isinstance(value, (int, float)):
            self.metadata[key] += value
        else:
            self.metadata[key] = value

    def __getitem__(self, key: str) -> Any:
        """
        Gets the metadata or value
        """
        if key in {'result', 'error', 'status'}:
            return getattr(self, key)
        return self.metadata.get(key)

