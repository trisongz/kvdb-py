from __future__ import annotations

"""
KVDB - Key Value Database Python Client
"""
from . import io
from . import tasks
from .client import KVDBClient

from typing import Any, Dict, Optional, Union, Type, Mapping, List, TYPE_CHECKING, overload

if TYPE_CHECKING:
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
    from .tasks.tasks import QueueTasks
    from .tasks.queue import TaskQueue
    from .tasks.worker import TaskWorker, WorkerTimerConfig
    from .tasks.main import Ctx, ReturnValue, ReturnValueT, TaskPhase, TaskResult, QueueTaskManager

    from .types.jobs import Job, CronJob
    from .types.common import CachePolicy
    from .types.base import KVDBUrl
    from .types.contexts import SessionPools

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

