from __future__ import annotations

"""
KVDB - Key Value Database Python Client
"""
from . import io
from . import tasks
from .client import KVDBClient

from typing import Any, Dict, Optional, Union, Type, Mapping, Callable, List, TYPE_CHECKING, overload

if TYPE_CHECKING:
    import asyncio
    import multiprocessing as mp
    from .configs import KVDBSettings
    from .configs.base import SerializerConfig
    
    from .components.lock import Lock, AsyncLock, LockT
    from .components.pubsub import PubSub, AsyncPubSub, PubSubT, AsyncPubSubT
    from .components.pipeline import Pipeline, AsyncPipeline, PipelineT, AsyncPipelineT
    from .components.connection_pool import ConnectionPool, AsyncConnectionPool, ConnectionPoolT, AsyncConnectionPoolT
    from .components.client import KVDB, AsyncKVDB, ClientT
    from .components.persistence import PersistentDict, KVDBStatefulBackend
    from .components.session import KVDBSession

    from .io.encoder import Encoder
    from .io.serializers import SerializerT
    from .io.cachify import Cachify, FunctionT
    from .io.cachify.cache import CachifyContext
    from .io.cachify.main import CachifyContextManager

    from .tasks.types import TaskFunction, AttributeMatchType
    from .tasks.abstract import TaskABC
    from .tasks.tasks import QueueTasks
    from .tasks.queue import TaskQueue
    from .tasks.worker import TaskWorker, WorkerTimerConfig
    from .tasks.main import Ctx, ReturnValue, ReturnValueT, TaskPhase, TaskResult, QueueTaskManager, ModuleType

    from .types.jobs import Job, CronJob
    from .types.common import CachePolicy
    from .types.base import KVDBUrl
    from .types.contexts import SessionPools

"""
Session / Client Methods
"""

@overload
def from_url(
    name: Optional[str] = 'default',
    url: Optional[Union[str, 'KVDBUrl']] = None,
    db_id: Optional[int] = None,

    # Pool Config
    pool_class: Optional[Union[str, Type['ConnectionPoolT']]] = None,
    pool_max_connections: Optional[int] = None,
    apool_class: Optional[Union[str, Type['AsyncConnectionPoolT']]] = None,
    apool_max_connections: Optional[int] = None,

    # Serializer Config
    serializer: Optional[str] = None,
    serializer_kwargs: Optional[Dict[str, Any]] = None,
    compression: Optional[str] = None,
    compression_level: Optional[int] = None,
    compression_enabled: Optional[bool] = None,
    encoding: Optional[str] = None,
    decode_responses: Optional[bool] = None,

    # Client Config
    socket_timeout: Optional[float] = None,
    socket_connect_timeout: Optional[float] = None,
    socket_keepalive: Optional[bool] = None,
    socket_keepalive_options: Optional[Mapping[int, Union[int, bytes]]] = None,
    unix_socket_path: Optional[str] = None,
    ssl: Optional[bool] = None,
    ssl_keyfile: Optional[str] = None,
    ssl_certfile: Optional[str] = None,
    ssl_cert_reqs: Optional[str] = None,
    ssl_ca_certs: Optional[str] = None,
    ssl_ca_data: Optional[str] = None,
    ssl_check_hostname: bool = None,

    # Retry Config
    retry_on_timeout: Optional[bool] = None,
    retry_on_error: Optional[List[Exception]] = None,
    retry_on_connection_error: Optional[bool] = None,
    retry_on_connection_reset_error: Optional[bool] = None,
    retry_on_response_error: Optional[bool] = None,
    retry_enabled: Optional[bool] = None,

    retry_client_enabled: Optional[bool] = None,
    retry_client_max_attempts: Optional[int] = None,
    retry_client_max_delay: Optional[float] = None,
    retry_client_logging_level: Optional[str] = None,

    retry_pubsub_enabled: Optional[bool] = None,
    retry_pubsub_max_attempts: Optional[int] = None,
    retry_pubsub_max_delay: Optional[float] = None,
    retry_pubsub_logging_level: Optional[str] = None,

    retry_pipeline_enabled: Optional[bool] = None,
    retry_pipeline_max_attempts: Optional[int] = None,
    retry_pipeline_max_delay: Optional[float] = None,
    retry_pipeline_logging_level: Optional[str] = None,

    # Persistence Config
    persistence_base_key: Optional[str] = None,
    persistence_expiration: Optional[int] = None,
    persistence_hset_disabled: Optional[bool] = None,
    persistence_keyjoin: Optional[str] = None,
    persistence_async_enabled: Optional[bool] = None,

    set_as_ctx: Optional[bool] = None,
    overwrite: Optional[bool] = None,
    **kwargs,
) -> 'KVDBSession':
    """
    Initializes a KVDB Session that is managed by the KVDB Session Manager

    - If the session already exists, returns the existing session

    For retry options, if enabled, the underlying client will wrap executions
    in a retry wrapper using `tenacity`.

    Arguments:
        name: The name of the session
        url: The KVDB URL
        db_id: The KVDB Database ID
        pool_class: The pool class to use
        pool_max_connections: The maximum number of connections in the pool
        apool_class: The async pool class to use
        apool_max_connections: The maximum number of connections in the async pool
        serializer: The serializer to use
        serializer_kwargs: The kwargs to pass to the serializer
        compression: The compression to use
        compression_level: The compression level to use
        compression_enabled: Whether compression is enabled
        encoding: The encoding to use
        decode_responses: Whether to decode responses
        socket_timeout: The socket timeout
        socket_connect_timeout: The socket connect timeout
        socket_keepalive: Whether to keep the socket alive
        socket_keepalive_options: The socket keepalive options
        unix_socket_path: The unix socket path
        ssl: Whether to use SSL
        ssl_keyfile: The SSL keyfile
        ssl_certfile: The SSL certfile
        ssl_cert_reqs: The SSL cert requirements
        ssl_ca_certs: The SSL CA certs
        ssl_ca_data: The SSL CA data
        ssl_check_hostname: Whether to check the SSL hostname

        retry_on_timeout: Whether to retry on timeout
        retry_on_error: The errors to retry on
        retry_on_connection_error: Whether to retry on connection error
        retry_on_connection_reset_error: Whether to retry on connection reset error
        retry_on_response_error: Whether to retry on response error
        retry_enabled: Whether retry is enabled

        retry_client_enabled: Whether client retry is enabled
        retry_client_max_attempts: The maximum number of client retry attempts
        retry_client_max_delay: The maximum client retry delay
        retry_client_logging_level: The client retry logging level

        retry_pubsub_enabled: Whether pubsub retry is enabled
        retry_pubsub_max_attempts: The maximum number of pubsub retry attempts
        retry_pubsub_max_delay: The maximum pubsub retry delay
        retry_pubsub_logging_level: The pubsub retry logging level

        retry_pipeline_enabled: Whether pipeline retry is enabled
        retry_pipeline_max_attempts: The maximum number of pipeline retry attempts
        retry_pipeline_max_delay: The maximum pipeline retry delay
        retry_pipeline_logging_level: The pipeline retry logging level


        persistence_base_key: The persistence base key
        persistence_expiration: The persistence expiration
        persistence_hset_disabled: Whether hset is disabled
        persistence_keyjoin: The persistence keyjoin. Defaults to ':'
        persistence_async_enabled: Whether certain persistence operations are async and runs in a threadpool
        set_as_ctx: Whether to set the session as the current session
        overwrite: Whether to overwrite the existing session
        **kwargs: Additional arguments to pass to the KVDB Session
    """
    ...


def from_url(
    **kwargs,
) -> 'KVDBSession':
    """
    Initializes a KVDB Session that is managed by the KVDB Session Manager
    """
    return KVDBClient.get_session(**kwargs)


get_session = from_url


"""
Task / Worker Methods
"""


@overload
def create_task_context(
    queue_name: Optional[str] = None,
    name: Optional[str] = None,
    phase: Optional[TaskPhase] = None,
    silenced: Optional[bool] = None,
    silenced_stages: Optional[List[str]] = None,
    default_kwargs: Optional[Dict[str, Any]] = None,
    cronjob: Optional[bool] = None,
    disable_patch: Optional[bool] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,
    attribute_match_type: Optional['AttributeMatchType'] = None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> 'QueueTasks':
    """
    Creates a task context
    """
    ...


def create_task_context(
    queue_name: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> 'QueueTasks':
    """
    Creates a task context
    """
    return tasks.create_context(queue_name = queue_name, context = context, **kwargs)


@overload
def register_task(
    name: Optional[str] = None,
    function: Optional['FunctionT'] = None,
    phase: Optional['TaskPhase'] = None,
    silenced: Optional[bool] = None,
    silenced_stages: Optional[List[str]] = None,
    default_kwargs: Optional[Dict[str, Any]] = None,
    cronjob: Optional[bool] = None,
    queue_name: Optional[str] = None,
    disable_patch: Optional[bool] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,
    attribute_match_type: Optional['AttributeMatchType'] = None,
    task_abc: Optional[bool] = None,
    **kwargs
) -> Callable[['FunctionT'], 'FunctionT']:
    """
    Registers a function to a task queue with queue_name
    """
    ...


def register_task(
    queue_name: Optional[str] = None,
    **kwargs
) -> Callable[['FunctionT'], 'FunctionT']:
    """
    Registers a function to a task queue with queue_name
    """
    return tasks.register(queue_name = queue_name, **kwargs)


@overload
def register_task_object(
    queue_name: Optional[str] = None,
    name: Optional[str] = None,
    phase: Optional[TaskPhase] = None,
    silenced: Optional[bool] = None,
    silenced_stages: Optional[List[str]] = None,
    default_kwargs: Optional[Dict[str, Any]] = None,
    cronjob: Optional[bool] = None,
    disable_patch: Optional[bool] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,
    attribute_match_type: Optional['AttributeMatchType'] = None,
    context: Optional[Dict[str, Any]] = None,
    is_unset: Optional[bool] = False,
    **kwargs,
) -> 'ModuleType':
    """
    Registers a module to a task queue with queue_name

    Additional kwargs are passed as the partial function arguments
    that are subsequently overridden by present values when @register
    is called
    """
    ...


def register_task_object(
    queue_name: Optional[str] = None,
    is_unset: Optional[bool] = False,
    **kwargs,
) -> 'ModuleType':
    """
    Registers a module to a task queue with queue_name

    Additional kwargs are passed as the partial function arguments
    that are subsequently overridden by present values when @register
    is called
    """
    return tasks.register_object(queue_name = queue_name, is_unset = is_unset, **kwargs)



@overload
def register_task_abc(
    cls_or_func: Optional[Union[Type['TaskABC'], FunctionT, Callable[..., ReturnValue]]] = None,
    phase: Optional[TaskPhase] = None,
    silenced: Optional[bool] = None,
    silenced_stages: Optional[List[str]] = None,
    default_kwargs: Optional[Dict[str, Any]] = None,
    cronjob: Optional[bool] = None,
    queue_name: Optional[str] = None,
    disable_patch: Optional[bool] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,
    attribute_match_type: Optional[AttributeMatchType] = None,
    **kwargs
) -> Callable[..., 'ReturnValue']:
    """
    Registers an abstract class or function to the task queue
    """
    ...


@overload
def register_task_abc(
    cls_or_func: Optional[Union[Type['TaskABC'], FunctionT, Callable[..., ReturnValue]]] = None,
    phase: Optional[TaskPhase] = None,
    silenced: Optional[bool] = None,
    silenced_stages: Optional[List[str]] = None,
    default_kwargs: Optional[Dict[str, Any]] = None,
    cronjob: Optional[bool] = None,
    queue_name: Optional[str] = None,
    disable_patch: Optional[bool] = False,
    worker_attributes: Optional[Dict[str, Any]] = None,
    attribute_match_type: Optional[AttributeMatchType] = None,
    **kwargs
) -> Callable[['Job'], 'Job']:
    """
    Registers an abstract class or function to the task queue
    """
    ...


@overload
def register_task_abc(
    name: Optional[str] = None,
    cls_or_func: Optional[Union[Type['TaskABC'], FunctionT, Callable[..., ReturnValue]]] = None,
    phase: Optional[TaskPhase] = None,
    silenced: Optional[bool] = None,
    silenced_stages: Optional[List[str]] = None,
    default_kwargs: Optional[Dict[str, Any]] = None,
    cronjob: Optional[bool] = None,
    queue_name: Optional[str] = None,
    disable_patch: Optional[bool] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,
    attribute_match_type: Optional[AttributeMatchType] = None,
    **kwargs
) -> Callable[..., 'ReturnValue']:
    """
    Registers an abstract class or function to the task queue
    """
    ...

@overload
def register_task_abc(
    phase: Optional[TaskPhase] = None,
    silenced: Optional[bool] = None,
    silenced_stages: Optional[List[str]] = None,
    default_kwargs: Optional[Dict[str, Any]] = None,
    cronjob: Optional[bool] = None,
    queue_name: Optional[str] = None,
    disable_patch: Optional[bool] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,
    attribute_match_type: Optional[AttributeMatchType] = None,
    **kwargs
) -> Callable[['ReturnValue'], 'ReturnValue']:
    """
    Registers an abstract class or function to the task queue
    """
    ...


def register_task_abc(
    cls_or_func: Optional[Union[Type['TaskABC'], FunctionT]] = None,
    **kwargs
) -> Callable[['FunctionT'], 'FunctionT']:
    """
    Registers an abstract class or function to the task queue
    """
    return tasks.register_abc(cls_or_func = cls_or_func, **kwargs)


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
    return tasks.get_task_queue(queue_name = queue_name, task_queue_class = task_queue_class, **kwargs)



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
    return tasks.get_task_worker(worker_name = worker_name, queues = queues, task_worker_class = task_worker_class, **kwargs)


@overload
def spawn_new_task_worker(
    worker_name: Optional[str] = None,
    worker_imports: Optional[Union[str, List[str]]] = None,
    worker_cls: Optional[str] = None,
    worker_class: Optional[Type['TaskWorker']] = None,
    worker_config: Optional[Dict[str, Any]] = None,
    worker_queues: Optional[Union[str, List[str]]] = None,
    
    worker_functions: Optional[List['TaskFunction']] = None,
    worker_cron_jobs: Optional[List['CronJob']] = None,
    worker_startup: Optional[Union[List[Callable], Callable,]] = None,
    worker_shutdown: Optional[Union[List[Callable], Callable,]] = None,
    worker_before_process: Optional[Callable] = None,
    worker_after_process: Optional[Callable] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,

    queue_names: Optional[Union[str, List[str]]] = None,
    queue_config: Optional[Dict[str, Any]] = None,
    queue_class: Optional[Type['TaskQueue']] = None,

    max_concurrency: Optional[int] = None,
    max_broadcast_concurrency: Optional[int] = None,

    debug_enabled: Optional[bool] = False,
    
    # Controls the method in which the worker is spawned
    use_new_event_loop: Optional[bool] = None,
    use_asyncio_task: Optional[bool] = False,
    disable_worker_start: Optional[bool] = False,

    **kwargs,
) -> 'TaskWorker':  # sourcery skip: low-code-quality
    """
    Spawns a new task worker 

    This method allows initialization of a new task worker with a new process through
    various mechanisms.

    If `worker_cls` is specified, then the worker class is imported and instantiated
      - If the `worker_cls` is a Type[TaskWorker], then it is instantiated directly
      - If the `worker_cls` is an initialized TaskWorker, then it is used directly and configured
    
    If `worker_class` is specified, then it is instantiated directly and configured
    
    If `worker_imports` is specified, then the provided functions/modules are imported to
    initialize any registrations of tasks/cron jobs
        Example: worker_imports = ['my_module.tasks', 'my_module.tasks.init_function']

    `queue_names` are initialized prior to `worker_queues` to ensure that
    all tasks are registered before the worker starts
    """
    ...

def spawn_new_task_worker(
    **kwargs,
) -> 'TaskWorker':  # sourcery skip: low-code-quality
    """
    Spawns a new task worker
    """
    return tasks.spawn_new_task_worker(**kwargs)


@overload
def start_task_workers(
    num_workers: Optional[int] = 1,
    start_index: Optional[int] = None,

    worker_name: Optional[str] = 'global',
    worker_name_sep: Optional[str] = '-',

    worker_imports: Optional[Union[str, List[str]]] = None,
    worker_cls: Optional[str] = None,
    worker_class: Optional[Type['TaskWorker']] = None,
    worker_config: Optional[Dict[str, Any]] = None,
    worker_queues: Optional[Union[str, List[str]]] = None,
    
    worker_functions: Optional[List['TaskFunction']] = None,
    worker_cron_jobs: Optional[List['CronJob']] = None,
    worker_startup: Optional[Union[List[Callable], Callable,]] = None,
    worker_shutdown: Optional[Union[List[Callable], Callable,]] = None,
    worker_before_process: Optional[Callable] = None,
    worker_after_process: Optional[Callable] = None,
    worker_attributes: Optional[Dict[str, Any]] = None,

    queue_names: Optional[Union[str, List[str]]] = None,
    queue_config: Optional[Dict[str, Any]] = None,
    queue_class: Optional[Type['TaskQueue']] = None,

    max_concurrency: Optional[int] = None,
    max_broadcast_concurrency: Optional[int] = None,

    debug_enabled: Optional[bool] = False,
    disable_env_name: Optional[bool] = False,
    method: Optional[str] = 'mp',
    use_new_event_loop: Optional[bool] = None,
    disable_worker_start: Optional[bool] = False,
    terminate_timeout: Optional[float] = 5.0,
    **kwargs,
) -> Union[Dict[str, Dict[str, Union['mp.Process', 'asyncio.Task', 'TaskWorker']]], List['TaskWorker']]:
    """
    Starts multiple task workers using either multiprocessing or asyncio.tasks

    Method can be either `Multiprocessing` (`mp`, `process`) or `asyncio.Task` (`tasks`, `asyncio`)

    If `disable_worker_start` is True, then the workers are initialized but not started and 
    the worker objects are returned

    This method allows initialization of multiple task workers with new processes through
    various mechanisms.

    - `num_workers` specifies the number of workers to start
    - `start_index` specifies the starting index for the worker names
    - `worker_name` specifies the worker name prefix
    - `worker_name_sep` specifies the worker name separator

    If `worker_cls` is specified, then the worker class is imported and instantiated
      - If the `worker_cls` is a Type[TaskWorker], then it is instantiated directly
      - If the `worker_cls` is an initialized TaskWorker, then it is used directly and configured
    
    If `worker_imports` is specified, then the provided functions/modules are imported to
    initialize any registrations of tasks/cron jobs
        Example: worker_imports = ['my_module.tasks', 'my_module.tasks.init_function']

    `queue_names` are initialized prior to `worker_queues` to ensure that
    all tasks are registered before the worker starts
    """
    ...


def start_task_workers(
    **kwargs
) -> Union[Dict[str, Dict[str, Union['mp.Process', 'asyncio.Task', 'TaskWorker']]], List['TaskWorker']]:
    """
    Starts multiple task workers using either multiprocessing or asyncio.tasks

    Method can be either `Multiprocessing` (`mp`, `process`) or `asyncio.Task` (`tasks`, `asyncio`)

    If `disable_worker_start` is True, then the workers are initialized but not started and 
    the worker objects are returned

    This method allows initialization of multiple task workers with new processes through
    various mechanisms.

    - `num_workers` specifies the number of workers to start
    - `start_index` specifies the starting index for the worker names
    - `worker_name` specifies the worker name prefix
    - `worker_name_sep` specifies the worker name separator

    If `worker_cls` is specified, then the worker class is imported and instantiated
      - If the `worker_cls` is a Type[TaskWorker], then it is instantiated directly
      - If the `worker_cls` is an initialized TaskWorker, then it is used directly and configured
    
    If `worker_imports` is specified, then the provided functions/modules are imported to
    initialize any registrations of tasks/cron jobs
        Example: worker_imports = ['my_module.tasks', 'my_module.tasks.init_function']

    `queue_names` are initialized prior to `worker_queues` to ensure that
    all tasks are registered before the worker starts
    """
    return tasks.start_task_workers(**kwargs)



"""
Cachify Methods
"""


@overload
def create_cachify_context(
    cache_name: Optional[str] = None,
    cachify_class: Optional[Type['Cachify']] = None,
    cachify_context_class: Optional[Type['CachifyContext']] = None,
    session: Optional['KVDBSession'] = None,
    session_name: Optional[str] = None,
    partial_kwargs: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> 'CachifyContext':
    """
    Creates a CachifyContext for registering functions and objects
    """
    ...


def create_cachify_context(
    cache_name: Optional[str] = None,
    **kwargs,
) -> 'CachifyContext':
    """
    Creates a CachifyContext for registering functions and objects
    """
    from .io import cachify
    return cachify.create_context(cache_name = cache_name, **kwargs)


@overload
def register_cachify(
    function: Optional[FunctionT] = None,
    cache_name: Optional[str] = None,
    ttl: Optional[int] = 60 * 10, # 10 minutes
    ttl_kws: Optional[List[str]] = ['cache_ttl'], # The keyword arguments to use for the ttl

    keybuilder: Optional[Callable] = None,
    name: Optional[Union[str, Callable]] = None,
    typed: Optional[bool] = True,
    exclude_keys: Optional[List[str]] = None,
    exclude_null: Optional[bool] = True,
    exclude_exceptions: Optional[Union[bool, List[Exception]]] = True,
    prefix: Optional[str] = '_kvc_',

    exclude_null_values_in_hash: Optional[bool] = None,
    exclude_default_values_in_hash: Optional[bool] = None,

    disabled: Optional[Union[bool, Callable]] = None,
    disabled_kws: Optional[List[str]] = ['cache_disable'], # If present and True, disable the cache
    
    invalidate_after: Optional[Union[int, Callable]] = None,
    
    invalidate_if: Optional[Callable] = None,
    invalidate_kws: Optional[List[str]] = ['cache_invalidate'], # If present and True, invalidate the cache

    overwrite_if: Optional[Callable] = None,
    overwrite_kws: Optional[List[str]] = ['cache_overwrite'], # If present and True, overwrite the cache

    retry_enabled: Optional[bool] = False,
    retry_max_attempts: Optional[int] = 3, # Will retry 3 times
    retry_giveup_callable: Optional[Callable[..., bool]] = None,
    
    timeout: Optional[float] = 5.0,
    verbosity: Optional[int] = None,

    raise_exceptions: Optional[bool] = True,

    encoder: Optional[Union[str, Callable]] = None,
    decoder: Optional[Union[str, Callable]] = None,

    # Allow for custom hit setters and getters
    hit_setter: Optional[Callable] = None,
    hit_getter: Optional[Callable] = None,

    # Allow for max cache size
    cache_max_size: Optional[int] = None,
    cache_max_size_policy: Optional[Union[str, 'CachePolicy']] = None, # 'LRU' | 'LFU' | 'FIFO' | 'LIFO'

    # Allow for post-init hooks
    post_init_hook: Optional[Union[str, Callable]] = None,
    
    # Allow for post-call hooks
    post_call_hook: Optional[Union[str, Callable]] = None,
    hset_enabled: Optional[bool] = True,

    session: Optional['KVDBSession'] = None,
    session_name: Optional[str] = None,
    session_kwargs: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Callable[[FunctionT], FunctionT]:  # sourcery skip: default-mutable-arg
    
    """
    Creates a new cachify partial decorator that
    passes the kwargs to the cachify decorator before it is applied

    Args:

        ttl (Optional[int], optional): The time to live for the cache. Defaults to 60 * 10 (10 minutes).
        ttl_kws (Optional[List[str]], optional): The keyword arguments to use for the ttl. Defaults to ['cache_ttl'].
        keybuilder (Optional[Callable], optional): The keybuilder function to use. Defaults to None.
        name (Optional[Union[str, Callable]], optional): The name of the cache. Defaults to None.
        typed (Optional[bool], optional): Whether or not to use typed caching. Defaults to True.
        exclude_keys (Optional[List[str]], optional): The keys to exclude from the cache. Defaults to None.
        exclude_null (Optional[bool], optional): Whether or not to exclude null values from the cache. Defaults to True.
        exclude_exceptions (Optional[Union[bool, List[Exception]]], optional): Whether or not to exclude exceptions from the cache. Defaults to True.
        prefix (Optional[str], optional): The prefix to use for the cache if keybuilder is not present. Defaults to '_kvc_'.
        exclude_null_values_in_hash (Optional[bool], optional): Whether or not to exclude null values from the hash. Defaults to None.
        exclude_default_values_in_hash (Optional[bool], optional): Whether or not to exclude default values from the hash. Defaults to None.
        disabled (Optional[Union[bool, Callable]], optional): Whether or not to disable the cache. Defaults to None.
        disabled_kws (Optional[List[str]], optional): The keyword arguments to use for the disabled flag. Defaults to ['cache_disable'].
        invalidate_after (Optional[Union[int, Callable]], optional): The time to invalidate the cache after. Defaults to None.
        invalidate_if (Optional[Callable], optional): The function to use to invalidate the cache. Defaults to None.
        invalidate_kws (Optional[List[str]], optional): The keyword arguments to use for the invalidate flag. Defaults to ['cache_invalidate'].
        overwrite_if (Optional[Callable], optional): The function to use to overwrite the cache. Defaults to None.
        overwrite_kws (Optional[List[str]], optional): The keyword arguments to use for the overwrite flag. Defaults to ['cache_overwrite'].
        retry_enabled (Optional[bool], optional): Whether or not to enable retries. Defaults to False.
        retry_max_attempts (Optional[int], optional): The maximum number of retries. Defaults to 3.
        retry_giveup_callable (Optional[Callable[..., bool]], optional): The function to use to give up on retries. Defaults to None.
        timeout (Optional[float], optional): The timeout for the cache. Defaults to 5.0.
        verbosity (Optional[int], optional): The verbosity level. Defaults to None.
        raise_exceptions (Optional[bool], optional): Whether or not to raise exceptions. Defaults to True.
        encoder (Optional[Union[str, Callable]], optional): The encoder to use. Defaults to None.
        decoder (Optional[Union[str, Callable]], optional): The decoder to use. Defaults to None.
        hit_setter (Optional[Callable], optional): The hit setter to use. Defaults to None.
        hit_getter (Optional[Callable], optional): The hit getter to use. Defaults to None.
        cache_max_size (Optional[int], optional): The maximum size of the cache. Defaults to None.
        cache_max_size_policy (Optional[Union[str, CachePolicy]], optional): The cache policy to use. Defaults to CachePolicy.LFU.
        post_init_hook (Optional[Union[str, Callable]], optional): The post init hook to use. Defaults to None.
        post_call_hook (Optional[Union[str, Callable]], optional): The post call hook to use. Defaults to None.
        hset_enabled (Optional[bool], optional): Whether or not to enable hset/hget/hdel/hmset/hmget/hmgetall. Defaults to True.
        session (Optional['KVDBSession'], optional): The session to use. Defaults to None.
        session_name (Optional[str], optional): The session name to use. Defaults to None.
        session_kwargs (Optional[Dict[str, Any]], optional): The session kwargs to use. Defaults to None.
    """
    ...


def register_cachify(
    cache_name: Optional[str] = None,
    function: Optional[FunctionT] = None,
    **kwargs,
) -> Union[Callable[[FunctionT], FunctionT], FunctionT]:
    """
    Registers a function for caching

    :param cache_name: The name of the cache
    :param function: The function to register
    """
    from .io import cachify
    return cachify.register(cache_name = cache_name, function = function, **kwargs)


def register_cachify_object(
    cache_name: Optional[str] = None, 
    **kwargs,
) -> object:
    """
    Registers an object for caching

    Args:
        cache_name (Optional[str], optional): The name of the cache. Defaults to None.

    """
    from .io import cachify
    return cachify.register_object(cache_name = cache_name, **kwargs)


def create_persistence(
    name: Optional[str] = None,
    base_key: Optional[str] = None,
    expiration: Optional[int] = None,
    hset_disabled: Optional[bool] = False,
    keyjoin: Optional[str] = None,
    async_enabled: Optional[bool] = False,
    url: Optional[Union[str, KVDBUrl]] = None,
    serializer: Optional[str] = None,
    serializer_kwargs: Optional[Dict[str, Any]] = None,
    session_name: Optional[str] = None,
    **kwargs,
) -> 'PersistentDict':
    """
    Create a new persistence instance

    Args:
        name (Optional[str], optional): The name of the persistence. Defaults to None.
        base_key (Optional[str], optional): The base key of the persistence. Defaults to None.
        expiration (Optional[int], optional): The expiration of the persistence. Defaults to None.
        hset_disabled (Optional[bool], optional): Whether or not hset is disabled. Defaults to False.
        keyjoin (Optional[str], optional): The keyjoin. Defaults to None.
        async_enabled (Optional[bool], optional): Whether or not async is enabled. Defaults to False.
        url (Optional[Union[str, KVDBUrl]], optional): The url of the persistence. Defaults to None.
        serializer (Optional[str], optional): The serializer to use. Defaults to None.
        serializer_kwargs (Optional[Dict[str, Any]], optional): The serializer kwargs to use. Defaults to None.
        session_name (Optional[str], optional): The session name to use. Defaults to None.
    """
    session = get_session(name = session_name, url = url)
    return session.create_persistence(name = name, base_key = base_key, expiration = expiration, hset_disabled = hset_disabled, keyjoin = keyjoin, async_enabled = async_enabled, serializer = serializer, serializer_kwargs = serializer_kwargs, **kwargs)


def is_available(
    name: Optional[str] = 'default',
    url: Optional[Union[str, KVDBUrl]] = None,
) -> bool:
    """
    Checks if the KVDB is available
    """
    s = KVDBClient.create_session(name = name, url = url, disable_store = True)
    try:
        return s.ping()
    except Exception as e:
        return False