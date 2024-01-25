from __future__ import annotations


from .main import TaskManager
from .queue import TaskQueue
from typing import Optional, Dict, Any, Callable, Awaitable, List, Union, Type, AsyncGenerator, Iterable, Tuple, Literal, TYPE_CHECKING, overload

if TYPE_CHECKING:
    from .types import TaskFunction, AttributeMatchType
    from .main import Ctx, ReturnValue, ReturnValueT, FunctionT, TaskPhase, TaskResult, QueueTasks, ModuleType
    from .tasks import QueueTasks, Job
    from .worker import TaskWorker, WorkerTimerConfig, CronJob


@overload
def register(
    name: Optional[str] = None,
    function: Optional[FunctionT] = None,
    phase: Optional['TaskPhase'] = None,
    silenced: Optional[bool] = None,
    silenced_stages: Optional[List[str]] = None,
    default_kwargs: Optional[Dict[str, Any]] = None,
    cronjob: Optional[bool] = None,
    queue_name: Optional[str] = None,
    disable_patch: Optional[bool] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,
    attribute_match_type: Optional[AttributeMatchType] = None,
    **kwargs
) -> Callable[['FunctionT'], 'FunctionT']:
    """
    Registers a function to the queue_name
    """
    ...


def register(
    queue_name: Optional[str] = None,
    **kwargs
) -> Callable[['FunctionT'], 'FunctionT']:
    """
    Registers a function to the queue_name
    """
    return TaskManager.register(queue_name = queue_name, **kwargs)


@overload
def create_context(
    queue_name: Optional[str] = None,
    name: Optional[str] = None,
    phase: Optional[TaskPhase] = None,
    silenced: Optional[bool] = None,
    silenced_stages: Optional[List[str]] = None,
    default_kwargs: Optional[Dict[str, Any]] = None,
    cronjob: Optional[bool] = None,
    disable_patch: Optional[bool] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,
    attribute_match_type: Optional[AttributeMatchType] = None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> 'QueueTasks':
    """
    Creates a context
    """
    ...

def create_context(
    queue_name: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> 'QueueTasks':
    """
    Creates a context
    """
    return TaskManager.create_context(queue_name = queue_name, context = context, **kwargs)



@overload
def register_object(
    queue_name: Optional[str] = None,
    name: Optional[str] = None,
    phase: Optional[TaskPhase] = None,
    silenced: Optional[bool] = None,
    silenced_stages: Optional[List[str]] = None,
    default_kwargs: Optional[Dict[str, Any]] = None,
    cronjob: Optional[bool] = None,
    disable_patch: Optional[bool] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,
    attribute_match_type: Optional[AttributeMatchType] = None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> 'ModuleType':
    """
    Registers a module to the queue_name

    Additional kwargs are passed as the partial function arguments
    that are subsequently overridden by present values when @register
    is called
    """
    ...

def register_object(
    queue_name: Optional[str] = None,
    **kwargs,
) -> 'ModuleType':
    """
    Registers a module to the queue_name

    Additional kwargs are passed as the partial function arguments
    that are subsequently overridden by present values when @register
    is called
    """
    return TaskManager.register_object(queue_name = queue_name, **kwargs)


@overload
def get_task_queue(
    queue_name: Optional[str] = 'global',
    task_queue_class: Optional[Type['TaskQueue']] = None,

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
) -> 'TaskQueue':
    """
    Gets a task queue
    """
    ...


def get_task_queue(
    queue_name: Optional[str] = None,
    task_queue_class: Optional[Type['TaskQueue']] = None,
    **kwargs
) -> 'TaskQueue':
    """
    Gets a task queue
    """
    return TaskManager.get_task_queue(queue_name = queue_name, task_queue_class = task_queue_class, **kwargs)


@overload
def get_task_worker(
    worker_name: Optional[str] = None,
    queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
    task_worker_class: Optional[Type['TaskWorker']] = None,

    functions: Optional[List['TaskFunction']] = None,
    cron_jobs: Optional[List['CronJob']] = None,

    startup: Optional[Union[List[Callable], Callable,]] = None,
    shutdown: Optional[Union[List[Callable], Callable,]] = None,
    before_process: Optional[Callable] = None,
    after_process: Optional[Callable] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,

    timers: Optional[Union[Dict[str, int], 'WorkerTimerConfig']] = None,
    max_concurrency: Optional[int] = None,
    max_broadcast_concurrency: Optional[int] = None,
    task_queue_class: Optional[Type['TaskQueue']] = None,
    **kwargs
) -> 'TaskWorker':
    """
    Gets the task worker
    """
    ...


def get_task_worker(
    worker_name: Optional[str] = None,
    queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
    task_worker_class: Optional[Type['TaskWorker']] = None,
    **kwargs
) -> 'TaskWorker':
    """
    Gets the task worker
    """
    return TaskManager.get_task_worker(worker_name = worker_name, queues = queues, task_worker_class = task_worker_class, **kwargs)


@overload
async def aget_task_worker(
    worker_name: Optional[str] = None,
    queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
    task_worker_class: Optional[Type['TaskWorker']] = None,

    functions: Optional[List['TaskFunction']] = None,
    cron_jobs: Optional[List['CronJob']] = None,

    startup: Optional[Union[List[Callable], Callable,]] = None,
    shutdown: Optional[Union[List[Callable], Callable,]] = None,
    before_process: Optional[Callable] = None,
    after_process: Optional[Callable] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,

    timers: Optional[Union[Dict[str, int], 'WorkerTimerConfig']] = None,
    max_concurrency: Optional[int] = None,
    max_broadcast_concurrency: Optional[int] = None,
    task_queue_class: Optional[Type['TaskQueue']] = None,
    **kwargs
) -> 'TaskWorker':
    """
    Gets the task worker
    """
    ...


async def aget_task_worker(
    worker_name: Optional[str] = None,
    queues: Union[List['TaskQueue', str], 'TaskQueue', str] = None,
    task_worker_class: Optional[Type['TaskWorker']] = None,
    **kwargs
) -> 'TaskWorker':
    """
    Gets the task worker
    """
    return await TaskManager.aget_task_worker(worker_name = worker_name, queues = queues, task_worker_class = task_worker_class, **kwargs)



def set_default_global_queue_name(name: str):
    """
    Updates the default global queue name
    """
    TaskManager.default_queue_name = name


"""
Passthrough Queue Methods
"""


@overload
async def enqueue(
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
    return await TaskManager.enqueue(job_or_func, *args, queue_name = queue_name, **kwargs)

@overload
async def apply(
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
    job_or_func: Union['Job', str, Callable],
    queue_name: Optional[str] = None,
    **kwargs
) -> Optional[Any]:
    """
    Enqueue a job and wait for its result.

    If the job is successful, this returns its result.
    If the job is unsuccessful, this raises a JobError.
    """
    return await TaskManager.apply(job_or_func, queue_name = queue_name, **kwargs)

@overload    
async def broadcast(
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
    return await TaskManager.broadcast(job_or_func, queue_name = queue_name, **kwargs)


@overload
async def map(
    job_or_func: Union['Job', str],
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
    job_or_func: Union['Job', str],
    iter_kwargs: Iterable[Dict], 
    queue_name: Optional[str] = None,
    **kwargs
) -> List[TaskResult]:
    """
    Enqueue multiple jobs and collect all of their results.
    """
    return await TaskManager.map(job_or_func, iter_kwargs, queue_name = queue_name, **kwargs)
        

@overload
async def wait_for_job(
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
    return await TaskManager.wait_for_job(job, source_job = source_job, queue_name = queue_name, verbose = verbose, raise_exceptions = raise_exceptions, refresh_interval = refresh_interval, **kwargs)

    
@overload
async def wait_for_jobs(
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
    return await TaskManager.wait_for_jobs(jobs, source_job = source_job, queue_name = queue_name, verbose = verbose, raise_exceptions = raise_exceptions, refresh_interval = refresh_interval, **kwargs)


@overload
def as_jobs_complete(
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
    return TaskManager.as_jobs_complete(jobs, source_job = source_job, queue_name  = queue_name, verbose = verbose, raise_exceptions = raise_exceptions, refresh_interval = refresh_interval, return_results = return_results, cancel_func = cancel_func, **kwargs)
    
