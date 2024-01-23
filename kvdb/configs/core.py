from __future__ import annotations

"""
Configuration for Core Components
"""
import logging
from pydantic import Field, model_validator, validator
from kvdb.types.base import BaseModel, computed_field
from typing import Dict, Any, Optional, Type, Literal, Union, Callable, List, Mapping, TYPE_CHECKING
from .base import SerializerConfig

if TYPE_CHECKING:
    from kvdb.components.connection import ConnectionPoolT, AsyncConnectionPoolT

class KVDBRetryConfig(BaseModel):
    """
    The KVDB Retry Config
    """
    on_timeout: Optional[bool] = True
    on_error: Optional[list] = None
    on_connection_error: Optional[bool] = True
    on_connection_reset_error: Optional[bool] = True
    on_response_error: Optional[bool] = True
    enabled: Optional[bool] = True

    client_enabled: Optional[bool] = True
    client_max_attempts: Optional[int] = 15
    client_max_delay: Optional[int] = 60
    client_logging_level: Optional[Union[str, int]] = logging.DEBUG

    pubsub_enabled: Optional[bool] = True
    pubsub_max_attempts: Optional[int] = 15
    pubsub_max_delay: Optional[int] = 60
    pubsub_logging_level: Optional[Union[str, int]] = logging.DEBUG

    pipeline_enabled: Optional[bool] = True
    pipeline_max_attempts: Optional[int] = 15
    pipeline_max_delay: Optional[int] = 60
    pipeline_logging_level: Optional[Union[str, int]] = logging.DEBUG

    def get_retry_config(self, name: Literal['client', 'pubsub', 'pipeline']) -> Dict[str, Any]:
        """
        Returns the retry config for the given name
        """
        return {
            'enabled': getattr(self, f'{name}_enabled'),
            'max_attempts': getattr(self, f'{name}_max_attempts'),
            'max_delay': getattr(self, f'{name}_max_delay'),
            'logging_level': getattr(self, f'{name}_logging_level'),
        }


class KVDBPoolConfig(BaseModel):
    """
    The KVDB Pool Config
    """
    pool_class: Optional[str] = None
    apool_class: Optional[str] = None

    pool_max_connections: Optional[int] = None
    apool_max_connections: Optional[int] = None

    auto_close_connection_pool: Optional[bool] = True
    auto_close_aconnection_pool: Optional[bool] = True

    single_connection_client: Optional[bool] = False
    auto_reset_enabled: Optional[bool] = True
    auto_pause_enabled: Optional[bool] = True # Pause connection attempts when the host is down
    auto_pause_interval: Optional[float] = 1.5 # 1500ms
    auto_pause_max_delay: Optional[float] = 60.0 * 2 # 2 minutes
    

    def get_pool_class(
        self,
        pool_class: Optional[str] = None,
        is_async: Optional[bool] = False,
    ) -> Type[Union[ConnectionPoolT, AsyncConnectionPoolT]]:
        """
        Returns the pool class
        """
        pool_class = (self.apool_class if is_async else self.pool_class) if pool_class is None else pool_class
        if pool_class is None:
            from kvdb.components.connection import ConnectionPool, AsyncConnectionPool
            return AsyncConnectionPool if is_async else ConnectionPool
        elif isinstance(pool_class, str):
            from kvdb.components import connection
            return getattr(connection, pool_class)
        return pool_class


class KVDBClientConfig(SerializerConfig, BaseModel):
    """
    The KVDB Client Config
    """
    socket_timeout: Optional[float] = None
    socket_connect_timeout: Optional[float] = None
    socket_keepalive: Optional[bool] = None
    socket_keepalive_options: Optional[Mapping[int, Union[int, bytes]]] = None
    unix_socket_path: Optional[str] = None

    ssl: Optional[bool] = None
    ssl_keyfile: Optional[str] = None
    ssl_certfile: Optional[str] = None
    ssl_cert_reqs: Optional[str] = None
    ssl_ca_certs: Optional[str] = None
    ssl_ca_data: Optional[str] = None
    ssl_check_hostname: bool = None


class KVDBSerializationConfig(BaseModel):
    """
    The KVDB Serialization Config
    """
    encoding_errors: Optional[str] = 'strict'

class KVDBPersistenceConfig(SerializerConfig, BaseModel):
    """
    The KVDB Persistence Config
    """
    base_key: Optional[str] = None
    expiration: Optional[int] = None
    hset_disabled: Optional[bool] = False
    keyjoin: Optional[str] = ':'
    async_enabled: Optional[bool] = False

    

