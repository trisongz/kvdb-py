from __future__ import annotations

"""
The Main KVDB Client that Manages KVDB Sessions

Usage:

    from kvdb import KVDBClient
    session = KVDBClient.get_session(
        name = "default", 
        url = "redis://localhost:6379/0", 
        serializer='json'
    )

    # Set a key
    session.set('key', 'value')

    # Get a key
    v = session.get('key')

"""

import abc
import contextlib
from lazyops.libs.proxyobj import ProxyObject, Singleton
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
)

# We design it this way to minimize imports until runtime

if TYPE_CHECKING:
    from kvdb.types.base import KVDBUrl
    from kvdb.types.contexts import SessionPools
    from kvdb.configs.base import SerializerConfig
    from kvdb.components.client import KVDB, AsyncKVDB
    from kvdb.components.session import KVDBSession
    from kvdb.components.connection_pool import ConnectionPoolT, AsyncConnectionPoolT


ResponseT = TypeVar('ResponseT')

class KVDBSessionManager(abc.ABC, Singleton):
    """
    The KVDB Session Manager
    """

    def __init__(
        self, 
        **kwargs
    ):
        """
        Initializes the KVDB Session Manager
        """
        self.session_class: Optional[Type['KVDBSession']] = None
        self.session_pool_class: Optional[Type['SessionPools']] = None
        self.serializer_config_class: Optional[Type['SerializerConfig']] = None
        self.url_class: Optional[Type['KVDBUrl']] = None
        self.configure_classes()
        
        from kvdb.configs import settings
        from kvdb.types.contexts import GlobalKVDBContext
        
        self.c = GlobalKVDBContext()
        self.pools = self.c.pools
        self.sessions = self.c.sessions
        self.settings = settings
        self.logger = self.settings.logger
        self.autologger = self.settings.autologger
        self.settings.configure(**kwargs)
    
    def configure_classes(
        self,
        session_class: Optional[Type['KVDBSession']] = None,
        session_pool_class: Optional[Type['SessionPools']] = None,
        serializer_config_class: Optional[Type['SerializerConfig']] = None,
        url_class: Optional[Type['KVDBUrl']] = None,
        **kwargs,
    ):
        """
        Configures the global classes that are used to initialize the KVDB Session

        This allows you to use your own custom classes for the 
        `KVDBSession`, `SessionPools`, `SerializerConfig`, and `KVDBUrl`
        enabling for full flexibility and customization of the KVDB
        """
        from lazyops.utils import lazy_import
        if session_class and isinstance(session_class, str):
            session_class = lazy_import(session_class)
        elif self.session_class is None:
            from kvdb.components.session import KVDBSession
            session_class = KVDBSession
        if session_class: self.session_class = session_class

        if serializer_config_class and isinstance(serializer_config_class, str):
            serializer_config_class = lazy_import(serializer_config_class)
        elif self.serializer_config_class is None:
            from kvdb.configs.base import SerializerConfig
            serializer_config_class = SerializerConfig
        if serializer_config_class: self.serializer_config_class = serializer_config_class

        if session_pool_class and isinstance(session_pool_class, str):
            session_pool_class = lazy_import(session_pool_class)
        elif self.session_pool_class is None:
            from kvdb.types.contexts import SessionPools
            session_pool_class = SessionPools
        if session_pool_class: self.session_pool_class = session_pool_class

        if url_class and isinstance(url_class, str):
            url_class = lazy_import(url_class)
        elif self.url_class is None:
            from kvdb.types.base import KVDBUrl
            url_class = KVDBUrl
        if url_class: self.url_class = url_class

    
    def configure(
        self,
        overwrite: Optional[bool] = None,
        **kwargs,
    ):
        """
        Configures the global settings
        """
        self.settings.configure(**kwargs)
        if overwrite is True: self.init_session(overwrite = overwrite, **kwargs)

    def get_pool(
        self,
        name: str,
        url: Optional[Union[str, 'KVDBUrl']] = None,
        serializer_config: Optional[Dict[str, Any]] = None,
        disable_store: Optional[bool] = None,
        **kwargs,
    ) -> SessionPools:
        """
        Configures the session pools
        """
        if url is None: url = self.settings.url
        if isinstance(url, str): url = self.url_class(url)
        # url.set_key(name = name, serializer_config = serializer_config, **kwargs)
        if url.key in self.pools: 
            if self.settings.debug:
                self.autologger.info(f'Using existing pool with name {name} and url {url}: {url.key}')
            return self.pools[url.key]
        if self.settings.debug:
            self.autologger.info(f'Creating newpool with name {name} and url {url}: {url.key}')

        # Get the serializer config
        # from kvdb.configs.base import SerializerConfig
        serializer_config = self.serializer_config_class.extract_kwargs(_exclude_none = True, **kwargs) \
            if serializer_config is None else serializer_config
        
        kwargs = {k : v for k, v in kwargs.items() if k not in serializer_config}

        # Get the pool config
        pool_config = self.settings.pool.model_dump(exclude_none = True)
        pool_kwargs = self.settings.pool.extract_kwargs(_exclude_none = True, **kwargs)
        if pool_kwargs: pool_config.update(pool_kwargs)
        kwargs = {k : v for k, v in kwargs.items() if k not in pool_config}

        # Get the pool class
        pool_class = self.settings.pool.get_pool_class(pool_class=pool_config.pop('pool_class', None), is_async=False)
        pool_max_connections = pool_config.pop('pool_max_connections', None)
        # pool_autoclose = pool_config.pop('auto_close_connection_pool', None)
        # pool_autoreset = pool_config.get('auto_reset_enabled')

        apool_class = self.settings.pool.get_pool_class(pool_class=pool_config.pop('apool_class', None), is_async=True)
        apool_max_connections = pool_config.pop('apool_max_connections', None)
        # apool_autoclose = pool_config.get('auto_close_aconnection_pool', None)
        if serializer_config: pool_config.update(serializer_config)

        pool = self.session_pool_class(
            name = name,
            pool = pool_class.from_url(
                url, max_connections = pool_max_connections, **pool_config,
            ),
            apool = apool_class.from_url(
                url, max_connections = apool_max_connections, **pool_config,
            ),
        )
        if not disable_store: self.pools[url.key] = pool
        return pool

    """
    Session Management
    """

    def create_session(
        self,
        name: Optional[str] = 'default',
        url: Optional[Union[str, 'KVDBUrl']] = None,
        db_id: Optional[int] = None,
        disable_store: Optional[bool] = None,
        **kwargs,
    ) -> 'KVDBSession':
        """
        Returns a new KVDB Session

        - Does not perform validation with the current contexts
        """

        if url is None: url = self.settings.url
        if db_id is None: db_id = self.settings.session_db_id

        # if isinstance(url, str): url = KVDBUrl(url)
        if isinstance(url, str): url = self.url_class(url)
        if db_id is not None and url.db_id != db_id: url = url.with_db_id(db_id)

        # Get the serializer config
        serializer_config = self.serializer_config_class.extract_kwargs(_exclude_none = True, **kwargs)
        kwargs = {k : v for k, v in kwargs.items() if k not in serializer_config}
        url.set_key(serializer_config = serializer_config, **kwargs)

        # Get the Client Config
        client_config = self.settings.client_config.model_dump(exclude_none = True)
        client_kwargs = self.settings.client_config.extract_kwargs(_exclude_none = True, **kwargs)
        if client_kwargs: client_config.update(client_kwargs)
        kwargs = {k : v for k, v in kwargs.items() if k not in client_config}

        # Get the pool
        pool = self.get_pool(name, url, serializer_config = serializer_config, disable_store = disable_store, **kwargs)
        if serializer_config: client_config.update(serializer_config)
        # self.autologger.info(f'Creating new KVDB Session with name {name} and url {url}, with client config {client_config} and kwargs {kwargs}')
        return self.session_class(
            name = name,
            url = url,
            pool = pool,
            **client_config,
            **kwargs,
        )
    
    @overload
    def session(
        self,
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
    

    def session(
        self,
        name: Optional[str] = 'default',
        url: Optional[Union[str, 'KVDBUrl']] = None,
        db_id: Optional[int] = None,
        set_as_ctx: Optional[bool] = None,
        overwrite: Optional[bool] = None,
        **kwargs,
    ) -> 'KVDBSession':
        """
        Initializes a KVDB Session that is managed by the KVDB Session Manager
        """
        if name in self.sessions and overwrite is not True:
            if set_as_ctx is True: self.c.set_ctx(name = name)
            return self.sessions[name]
        
        session = self.create_session(name = name, url = url, db_id = db_id, **kwargs)
        if set_as_ctx is None: set_as_ctx = not len(self.sessions)
        self.sessions[name] = session
        if set_as_ctx is True: self.c.set_ctx(name = name)
        return session
    

    @overload
    def init_session(
        self,
        name: Optional[str] = 'default',
        url: Optional[Union[str, 'KVDBUrl']] = None,
        db_id: Optional[int] = None,

        # Pool Config
        pool_class: Optional[Union[str, Type[ConnectionPoolT]]] = None,
        pool_max_connections: Optional[int] = None,
        apool_class: Optional[Union[str, Type[AsyncConnectionPoolT]]] = None,
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
    

    def init_session(
        self,
        name: Optional[str] = 'default',
        url: Optional[Union[str, KVDBUrl]] = None,
        db_id: Optional[int] = None,
        set_as_ctx: Optional[bool] = None,
        overwrite: Optional[bool] = None,
        **kwargs,
    ) -> 'KVDBSession':
        """
        Initializes a KVDB Session that is managed by the KVDB Session Manager

        - Raises an error if the session already exists
        """
        if name in self.sessions and overwrite is not True:
            raise ValueError(f'The session with name {name} already exists. Use overwrite = True to overwrite the session')
        return self.session(name = name, url = url, db_id = db_id, set_as_ctx = set_as_ctx, overwrite = overwrite, **kwargs)
    

    @overload
    def get_session(
        self,
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
            **kwargs: Additional arguments to pass to the KVDB Session
        """
        ...

    def get_session(
        self,
        name: Optional[str] = None,
        **kwargs,
    ) -> 'KVDBSession':
        """
        Returns the KVDB Session with the given name
        """
        if name is None: name = self.c.current
        if name is None: name = 'default'
        if name not in self.sessions:
            return self.session(name = name, **kwargs)
        return self.sessions[name]
    
    def set_session(
        self,
        name: str,
        **kwargs,
    ):
        """
        Set the current KVDB Session
        """
        if name not in self.sessions: raise ValueError(f'Invalid session name: {name}')
        self.c.set_ctx(name = name)    
    

    def add_session(
        self,
        session: 'KVDBSession',
        overwrite: Optional[bool] = None,
        set_as_ctx: Optional[bool] = None,
        **kwargs,
    ):
        """
        Adds a KVDB Session to the KVDB Session Manager
        """
        if not isinstance(session, 'KVDBSession'): raise ValueError(f'Invalid session type: {type(session)}')
        if session.name in self.sessions and overwrite is not True:
            raise ValueError(f'The session with name {session.name} already exists. Use overwrite = True to overwrite the session')
        if set_as_ctx is None: set_as_ctx = not len(self.sessions)
        self.sessions[session.name] = session
        if set_as_ctx is True: self.c.set_ctx(name = session.name)

    """
    Properties
    """

    @property
    def ctx(self) -> 'KVDBSession':
        """
        Returns the current session
        """
        if not self.c.ctx:
            self.session()
        return self.c.ctx
    
    @property
    def current(self) -> Optional[str]:
        """
        Returns the current session
        """
        return self.c.current or 'default'
    
    @property
    def client(self) -> 'KVDB':
        """
        Returns the current session
        """
        return self.ctx.client
    
    @property
    def aclient(self) -> 'AsyncKVDB':
        """
        Returns the current session
        """
        return self.ctx.aclient
    
    @contextlib.contextmanager
    def with_session(self, name: str) -> Iterator['KVDBSession']:
        """
        Returns the session with the given name as the current session
        """
        if name not in self.sessions: 
            raise ValueError(f'Invalid session name: `{name}`. Initialize the session first using `session` or `init_session`')
        yield self.sessions[name]

    """
    Session Wrap Methods
    """
    def _session_function(self, *args, _function: Optional[str] = None, session_ctx: Optional[str] = None, **kwargs) -> Union[ResponseT, Awaitable[ResponseT]]:
        """
        Wraps the session function
        """
        if session_ctx is None: session_ctx = self.current
        with self.with_session(session_ctx) as session:
            return getattr(session, _function)(*args, **kwargs)
    
    """
    Copy / Clone Methods
    """

    


KVDBClient: KVDBSessionManager = ProxyObject(obj_cls = KVDBSessionManager)