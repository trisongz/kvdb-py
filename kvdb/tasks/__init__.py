from __future__ import annotations


from .main import TaskManager
from .queue import TaskQueue
from typing import Optional, Dict, Any, Callable, Awaitable, List, Union, Type, Tuple, Literal, TYPE_CHECKING, overload

if TYPE_CHECKING:
    from .types import TaskFunction
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
    attribute_match_type: Optional[Literal['any', 'all']] = None,
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
    attribute_match_type: Optional[Literal['any', 'all']] = None,
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
    attribute_match_type: Optional[Literal['any', 'all']] = None,
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





def set_default_global_queue_name(name: str):
    """
    Updates the default global queue name
    """
    TaskManager.default_queue_name = name

