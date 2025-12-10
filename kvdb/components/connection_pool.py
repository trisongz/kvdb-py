from __future__ import annotations

import sys
import time
import anyio
import socket
import asyncio
import typing
import contextlib
import threading
import itertools

# from itertools import chain
from queue import Empty, Full, Queue, LifoQueue

# the functionality is available in 3.11.x but has a major issue before
# 3.11.3. See https://github.com/redis/redis-py/issues/2633
if sys.version_info >= (3, 11, 3):
    from asyncio import timeout as async_timeout
else:
    from async_timeout import timeout as async_timeout



import kvdb.errors as errors
from redis import exceptions as rerrors
from redis.event import EventDispatcher
from kvdb.io.encoder import Encoder
from kvdb.types.base import supported_schemas, KVDBUrl
from kvdb.utils.logs import logger
from kvdb.version import VERSION
from kvdb.utils.helpers import set_ulimits
from kvdb.utils.lazy import filter_kwargs_for_connection

from .connection import (
    Connection,
    AsyncConnection,
    TrioAsyncConnection,

    _ConnectionPool,
    _BlockingConnectionPool,
    _AsyncConnectionPool,
    _AsyncBlockingConnectionPool,

    parse_url,
)

from typing import Union, Optional, Any, Dict, List, Tuple, Iterable, Set, Type, TypeVar, Callable, Generator, Awaitable, AsyncGenerator, TYPE_CHECKING

if TYPE_CHECKING:
    from kvdb.configs import KVDBSettings
    from kvdb.io.serializers import SerializerT

# TODO: Add support for loadbalancing

class ConnectionPool(_ConnectionPool):

    is_async = False

    @classmethod
    def from_url(cls, url: Union[str, KVDBUrl], **kwargs):
        """
        Return a connection pool configured from the given URL.

        For example::
            keydb://[[username]:[password]]@localhost:6379/0
            keydbs://[[username]:[password]]@localhost:6379/0
            dfly://[[username]:[password]]@localhost:6379/0
            dflys://[[username]:[password]]@localhost:6379/0
            redis://[[username]:[password]]@localhost:6379/0
            rediss://[[username]:[password]]@localhost:6379/0
            unix://[[username]:[password]]@/path/to/socket.sock?db=0

        Seven URL schemes are supported:
        - `keydb://` creates a TCP socket connection. (KeyDB)
        - `keydbs://` creates a SSL wrapped TCP socket connection. (KeyDB)
        - `dfly://` creates a TCP socket connection. (Dragonfly)
        - `dflys://` creates a SSL wrapped TCP socket connection. (Dragonfly)
        - `redis://` creates a TCP socket connection. See more at:
          <https://www.iana.org/assignments/uri-schemes/prov/redis>
        - `rediss://` creates a SSL wrapped TCP socket connection. See more at:
          <https://www.iana.org/assignments/uri-schemes/prov/rediss>
        - ``unix://``: creates a Unix Domain Socket connection.

        The username, password, hostname, path and all querystring values
        are passed through urllib.parse.unquote in order to replace any
        percent-encoded values with their corresponding characters.

        There are several ways to specify a database number. The first value
        found will be used:

            1. A ``db`` querystring option, e.g. redis://localhost?db=0
            2. If using the redis:// or rediss:// schemes, the path argument
               of the url, e.g. redis://localhost/0
            3. A ``db`` keyword argument to this function.

        If none of these options are specified, the default db=0 is used.

        All querystring options are cast to their appropriate Python types.
        Boolean arguments can be specified with string values "True"/"False"
        or "Yes"/"No". Values that cannot be properly cast cause a
        ``ValueError`` to be raised. Once parsed, the querystring arguments
        and keyword arguments are passed to the ``ConnectionPool``'s
        class initializer. In the case of conflicting arguments, querystring
        arguments always win.
        """
        url_options = parse_url(url, _is_async = cls.is_async)
        if "connection_class" in kwargs: url_options["connection_class"] = kwargs["connection_class"]
        kwargs.update(url_options)
        return cls(**kwargs)
    
    def __init__(
        self, 
        connection_class: Type[Connection] = Connection, 
        max_connections: Optional[int] = None, 
        **connection_kwargs
    ):
        max_connections = max_connections or 2**31
        if not isinstance(max_connections, int) or max_connections < 0:
            raise ValueError('"max_connections" must be a positive integer')
        try:
            set_ulimits(max_connections)
        except Exception as e:
            logger.debug(f"Unable to set ulimits for connection: {e}")
        self.connection_class = connection_class
        # logger.info(f"Using Mixin: {self.__dict__}", prefix = self.__class__.__name__)
        self.connection_kwargs = filter_kwargs_for_connection(self.connection_class, connection_kwargs)
        self.serializer: Optional['SerializerT'] = None
        self.max_connections = max_connections
        self.post_init_base(**connection_kwargs)
        self.post_init_pool(**connection_kwargs)

    @property
    def encoder_serialization_enabled(self) -> bool:
        """
        Returns True if serialization is enabled for the encoder
        which requires both serialization and decode_responses to be enabled
        """
        return self.encoder.serialization_enabled
    
    def enable_serialization(self, serializer: Optional['SerializerT'] = None, decode_responses: Optional[bool] = None):
        """
        Enable Serialization in the Encoder
        """
        self.encoder.enable_serialization(serializer = serializer, decode_responses = decode_responses)

    def disable_serialization(self, decode_responses: Optional[bool] = None):
        """
        Disable Serialization in the Encoder
        """
        self.encoder.disable_serialization(decode_responses=decode_responses)


    def get_init_kwargs(self, **kwargs) -> Dict[str, Any]:
        """
        Returns the init kwargs
        """
        _kwargs = self.connection_kwargs.copy()
        _kwargs.update(self.extra_kwargs)
        _kwargs.update(kwargs)
        _kwargs.update({
            "connection_class": self.connection_class,
            "max_connections": self.max_connections,
        })
        return _kwargs

    def post_init_base(self, **kwargs):
        """
        Post init function
        """
        self._settings: Optional['KVDBSettings'] = None
        self._encoder: Optional[Encoder] = None
        self.extra_kwargs = {k:v for k, v in kwargs.items() if k not in self.connection_kwargs}
        self.auto_pause_enabled = self.extra_kwargs.get('auto_pause_enabled', self.settings.pool.auto_pause_enabled)
        self.auto_pause_interval = self.extra_kwargs.get('auto_pause_interval', self.settings.pool.auto_pause_interval)
        self.auto_pause_max_delay = self.extra_kwargs.get('auto_pause_max_delay', self.settings.pool.auto_pause_max_delay)

        self.encoder_class = self.connection_kwargs.get("encoder_class", Encoder)
        self.connection_kwargs['encoder_class'] = self.encoder_class
        if 'serializer' in kwargs:
            serializer = kwargs.get('serializer')
            if isinstance(serializer, str):
                from kvdb.io.serializers import get_serializer
                serializer = get_serializer(**kwargs, is_encoder = True)
                # logger.info(f"Serializer: {serializer}")
            self.serializer = serializer
            self.connection_kwargs['serializer'] = serializer
        self.auto_reset_enabled = kwargs.get('auto_reset_enabled', self.settings.pool.auto_reset_enabled)
    
    def post_init_pool(self, **kwargs):
        """
        Post init function
        """
        self._lock: threading.RLock = threading.RLock()
        self._created_connections: int = None
        self._available_connections: List[Type[Connection]] = None
        self._in_use_connections: Set[Type[Connection]] = None
        self._fork_lock: threading.Lock = threading.Lock()
        self._event_dispatcher = kwargs.get("event_dispatcher")
        if self._event_dispatcher is None:
            self._event_dispatcher = EventDispatcher()
        self.reset()

    def with_db_id(self, db_id: int):
        """
        Return a new connection pool with the specified db_id.
        """
        return self.__class__(**self.get_init_kwargs(db = db_id))

    def make_connection(self) -> "Connection":
        """
        Create a new connection
        """
        if self._created_connections >= self.max_connections:
            raise errors.ConnectionError("Too many connections")
        self._created_connections += 1
        return self.connection_class(**self.connection_kwargs, encoder = self.encoder)
    
    def reestablish_connection(self, connection: Connection) -> bool:
        """
        Attempts to Reestablish connection to the host
        """
        duration = 0.0
        err = None
        while duration < self.auto_pause_max_delay:
            try:
                sock = socket.create_connection((connection.host, connection.port), timeout = 0.5)
                sock.close()
                connection.connect()
                return True
            except ConnectionRefusedError as err:
                logger.info(f"Connection Refused: {err}")
                time.sleep(self.auto_pause_interval)
                duration += self.auto_pause_interval
        logger.info(f"Unable to reestablish connection: {err} after {duration} seconds")
        return False

    @contextlib.contextmanager
    def ensure_connection(self, connection: Connection) -> Generator[Connection, None, None]:
        """
        Ensure that the connection is available and that the host is available
        """
        try:
            # ensure this connection is connected to Redis
            connection.connect()
        
        except rerrors.TimeoutError as exc:
            if not self.auto_pause_enabled or not self.reestablish_connection(connection): 
                raise errors.TimeoutError(source_error = exc) from exc

        # connections that the pool provides should be ready to send
        # a command. if not, the connection was either returned to the
        # pool before all data has been read or the socket has been
        # closed. either way, reconnect and verify everything is good.
        try:
            if connection.can_read():
                raise errors.ConnectionError("Connection has data")
        except (errors.ConnectionError, rerrors.ConnectionError, ConnectionError, OSError) as exc:
            connection.disconnect()
            connection.connect()
            try:
                if connection.can_read():
                    raise errors.ConnectionError("Connection not ready") from exc
                
            except (errors.ConnectionError, rerrors.ConnectionError, ConnectionError, OSError) as exc:
                if not self.reestablish_connection(connection): 
                    raise errors.TimeoutError(source_error = exc) from exc
        
        except BaseException:
            # release the connection back to the pool so that we don't
            # leak it
            self.release(connection)
            raise
        
        yield connection

    def get_connection(self, command_name: Optional[str] = None, *keys: Any, **options: Dict[str, Any]) -> Connection:
        """
        Get a connection from the pool
        """
        self._checkpid()
        with self._lock:
            try:
                connection = self._available_connections.pop()
            except IndexError:
                try:
                    connection = self.make_connection()
                except errors.ConnectionError as e:
                    if not self.auto_reset_enabled: raise e
                    logger.warning(f'Resetting Connection Pool: {self._created_connections}/{self.max_connections}')
                    self.reset_pool()
                    connection = self.make_connection()

            self._in_use_connections.add(connection)
            # if command_name in {'PUBLISH', 'SUBSCRIBE', 'UNSUBSCRIBE'}:
            #     connection.encoder = self.encoder
        with self.ensure_connection(connection) as conn:
            return conn


    @contextlib.contextmanager
    def disconnect_ctx(self, with_lock: bool = True, **kwargs):
        """
        A context manager for disconnecting
        """
        if not with_lock:
            yield
            return
        with self._lock:
            yield
    
    def disconnect(    
        self, 
        inuse_connections: bool = True,
        raise_errors: bool = False,
        with_lock: bool = True,
        return_connections: bool = False,
        **kwargs,
    ):
        """
        Disconnects connections in the pool

        If ``inuse_connections`` is True, disconnect connections that are
        current in use, potentially by other tasks. Otherwise only disconnect
        connections that are idle in the pool.
        """
        self._checkpid()
        with self.disconnect_ctx(with_lock = with_lock):
            if inuse_connections:
                connections = itertools.chain(self._available_connections, self._in_use_connections)
            else: connections = self._available_connections
            outputs: List[Union[BaseException, Connection]] = []
            for connection in connections:
                try:
                    connection.disconnect()
                    outputs.append(connection)
                except BaseException as exc:
                    outputs.append(exc)
                    if raise_errors: raise exc
            if return_connections: return outputs


    def recreate(
        self,
        inuse_connections: bool = True,
        raise_errors: bool = False,
        with_lock: bool = True,
        **recreate_kwargs
    ) -> 'ConnectionPool':
        """
        Recreates the connection pool
        """
        self.disconnect(
            inuse_connections = inuse_connections,
            raise_errors = raise_errors,
            with_lock = with_lock,
        )
        return self.__class__(**self.get_init_kwargs(**recreate_kwargs))

    def reset_pool(
        self, 
        inuse_connections: bool = True, 
        raise_errors: bool = False,
        with_lock: bool = True,
        **kwargs,
    ):
        """
        Resets the connection pool
        """
        self.disconnect(inuse_connections = inuse_connections, raise_errors = raise_errors, with_lock = with_lock)
        self.reset()

    
    @property
    def db_id(self) -> int:
        """
        Returns the database ID
        """
        return self.connection_kwargs.get("db", 0)

    @property
    def settings(self) -> 'KVDBSettings':
        """
        Returns the settings
        """
        if self._settings is None:
            from kvdb.configs import settings
            self._settings = settings
        return self._settings
    
    @property
    def encoder(self) -> 'Encoder':
        """
        Returns the encoder
        """
        if self._encoder is None:
            kwargs = self.connection_kwargs
            serializer_disabled = self.extra_kwargs.get(
                'serializer_disabled', self.serializer is None
            )
            # logger.info(f"Serializer Disabled: {serializer_disabled}")
            self._encoder = self.encoder_class(
                encoding = kwargs.get("encoding", "utf-8"),
                encoding_errors = kwargs.get("encoding_errors", "strict"),
                decode_responses = kwargs.get("decode_responses"),
                serializer = None if serializer_disabled else self.serializer,
            )
        return self._encoder


class BlockingConnectionPool(_BlockingConnectionPool, ConnectionPool):
    """
    A blocking connection pool
    """


    def __init__(
        self, 
        connection_class: Type[Connection] = Connection, 
        max_connections: Optional[int] = None, 
        **kwargs
    ):
        """
        Initialize the Blocking Connection Pool
        """
        # We need to ensure that the connection class is the KVDB connection class
        # which supports the encoder and other features
        # We also need to ensure that max_connections is set to a reasonable value
        # to avoid hanging during initialization if it's too large (caused by queue filling)
        max_connections = max_connections or 50
        super().__init__(connection_class = connection_class, max_connections = max_connections, **kwargs)

    def make_connection(self):
        """
        Make a fresh connection.
        """
        connection = self.connection_class(**self.connection_kwargs, encoder = self.encoder)
        self._connections.append(connection)
        return connection

    def get_connection(self, command_name: Optional[str] = None, *keys: Any, **options: Dict[str, Any]) -> Generator[Connection, None, None]:
        """
        Get a connection, blocking for ``self.timeout`` until a connection
        is available from the pool.

        If the connection returned is ``None`` then creates a new connection.
        Because we use a last-in first-out queue, the existing connections
        (having been returned to the pool after the initial ``None`` values
        were added) will be returned before ``None`` values. This means we only
        create new connections when we need to, i.e.: the actual number of
        connections will only increase in response to demand.
        """
        # Make sure we haven't changed process.
        self._checkpid()

        # Try and get a connection from the pool. If one isn't available within
        # self.timeout then raise a ``ConnectionError``.
        connection = None
        try:
            connection = self.pool.get(block=True, timeout=self.timeout)
        except Empty as e:
            # Note that this is not caught by the redis client and will be
            # raised unless handled by application code. If you want never to
            raise ConnectionError("No connection available.") from e

        # If the ``connection`` is actually ``None`` then that's a cue to make
        # a new connection to add to the pool.
        if connection is None: connection = self.make_connection()
        with self.ensure_connection(connection) as conn:
            return conn
    

    def disconnect(self, inuse_connections: bool = True, raise_errors: bool = False, **kwargs):
        """
        Disconnects all connections in the pool.
        """
        self._checkpid()
        for connection in self._connections:
            connection.disconnect()



"""
Async Connection Pools
"""

class AsyncConnectionPool(_AsyncConnectionPool):

    is_async = True

    @classmethod
    def from_url(cls, url: Union[str, KVDBUrl], **kwargs):
        """
        Return a connection pool configured from the given URL.

        For example::
            keydb://[[username]:[password]]@localhost:6379/0
            keydbs://[[username]:[password]]@localhost:6379/0
            dfly://[[username]:[password]]@localhost:6379/0
            dflys://[[username]:[password]]@localhost:6379/0
            redis://[[username]:[password]]@localhost:6379/0
            rediss://[[username]:[password]]@localhost:6379/0
            unix://[[username]:[password]]@/path/to/socket.sock?db=0

        Seven URL schemes are supported:
        - `keydb://` creates a TCP socket connection. (KeyDB)
        - `keydbs://` creates a SSL wrapped TCP socket connection. (KeyDB)
        - `dfly://` creates a TCP socket connection. (Dragonfly)
        - `dflys://` creates a SSL wrapped TCP socket connection. (Dragonfly)
        - `redis://` creates a TCP socket connection. See more at:
          <https://www.iana.org/assignments/uri-schemes/prov/redis>
        - `rediss://` creates a SSL wrapped TCP socket connection. See more at:
          <https://www.iana.org/assignments/uri-schemes/prov/rediss>
        - ``unix://``: creates a Unix Domain Socket connection.

        The username, password, hostname, path and all querystring values
        are passed through urllib.parse.unquote in order to replace any
        percent-encoded values with their corresponding characters.

        There are several ways to specify a database number. The first value
        found will be used:

            1. A ``db`` querystring option, e.g. redis://localhost?db=0
            2. If using the redis:// or rediss:// schemes, the path argument
               of the url, e.g. redis://localhost/0
            3. A ``db`` keyword argument to this function.

        If none of these options are specified, the default db=0 is used.

        All querystring options are cast to their appropriate Python types.
        Boolean arguments can be specified with string values "True"/"False"
        or "Yes"/"No". Values that cannot be properly cast cause a
        ``ValueError`` to be raised. Once parsed, the querystring arguments
        and keyword arguments are passed to the ``ConnectionPool``'s
        class initializer. In the case of conflicting arguments, querystring
        arguments always win.
        """
        url_options = parse_url(url, _is_async = cls.is_async)
        if "connection_class" in kwargs: url_options["connection_class"] = kwargs["connection_class"]
        kwargs.update(url_options)
        return cls(**kwargs)

    def __init__(
        self, 
        connection_class: Type[AsyncConnection] = AsyncConnection, 
        max_connections: Optional[int] = None, 
        **connection_kwargs
    ):
        max_connections = max_connections or 2**31
        if not isinstance(max_connections, int) or max_connections < 0:
            raise ValueError('"max_connections" must be a positive integer')
        try:
            set_ulimits(max_connections)
        except Exception as e:
            logger.debug(f"Unable to set ulimits for connection: {e}")
        self.connection_class = connection_class
        # logger.info(f"Using Mixin: {self.__dict__}", prefix = self.__class__.__name__)
        self.connection_kwargs = filter_kwargs_for_connection(self.connection_class, connection_kwargs)
        self.max_connections = max_connections
        self.serializer: Optional['SerializerT'] = None
        self.post_init_base(**connection_kwargs)
        self.post_init_pool(**connection_kwargs)
    
    @property
    def encoder_serialization_enabled(self) -> bool:
        """
        Returns True if serialization is enabled for the encoder
        which requires both serialization and decode_responses to be enabled
        """
        return self.encoder.serialization_enabled
    
    def enable_serialization(self, serializer: Optional['SerializerT'] = None, decode_responses: Optional[bool] = None):
        """
        Enable Serialization in the Encoder
        """
        self.encoder.enable_serialization(serializer = serializer, decode_responses = decode_responses)

    def disable_serialization(self, decode_responses: Optional[bool] = None):
        """
        Disable Serialization in the Encoder
        """
        self.encoder.disable_serialization(decode_responses=decode_responses)

    
    def get_init_kwargs(self, **kwargs) -> Dict[str, Any]:
        """
        Returns the init kwargs
        """
        _kwargs = self.connection_kwargs.copy()
        _kwargs.update(self.extra_kwargs)
        _kwargs.update(kwargs)
        _kwargs.update({
            "connection_class": self.connection_class,
            "max_connections": self.max_connections,
        })
        return _kwargs

    
    def post_init_base(self, **kwargs):
        """
        Post init function
        """
        self._settings: Optional['KVDBSettings'] = None
        self._encoder: Optional[Encoder] = None
        self.extra_kwargs = {k:v for k, v in kwargs.items() if k not in self.connection_kwargs}
        self.auto_pause_enabled = self.extra_kwargs.get('auto_pause_enabled', self.settings.pool.auto_pause_enabled)
        self.auto_pause_interval = self.extra_kwargs.get('auto_pause_interval', self.settings.pool.auto_pause_interval)
        self.auto_pause_max_delay = self.extra_kwargs.get('auto_pause_max_delay', self.settings.pool.auto_pause_max_delay)

        self.encoder_class = self.connection_kwargs.get("encoder_class", Encoder)
        self.connection_kwargs['encoder_class'] = self.encoder_class
        if 'serializer' in kwargs:
            serializer = kwargs.get('serializer')
            if isinstance(serializer, str):
                from kvdb.io.serializers import get_serializer
                serializer = get_serializer(**kwargs, is_encoder = True)
                # logger.info(f"Serializer: {serializer}")
            self.serializer = serializer
            self.connection_kwargs['serializer'] = serializer
            self.connection_kwargs['serializer'] = serializer
        self.auto_reset_enabled = kwargs.get('auto_reset_enabled', self.settings.pool.auto_reset_enabled)

    def post_init_pool(self, **kwargs):
        """
        Post init function
        """
        self._created_connections: int = None
        self._available_connections: List[Type[AsyncConnection]] = None
        self._in_use_connections: Set[Type[AsyncConnection]] = None
        self._lock = asyncio.Lock()
        self._event_dispatcher = kwargs.get("event_dispatcher")
        if self._event_dispatcher is None:
            self._event_dispatcher = EventDispatcher()
        self.reset()

    def reset(self):
        super().reset()
        self._created_connections = 0


    def with_db_id(self, db_id: int):
        """
        Return a new connection pool with the specified db_id.
        """
        return self.__class__(**self.get_init_kwargs(db = db_id))
    
    def make_connection(self):
        """
        Create a new connection.  Can be overridden by child classes.
        """
        if self._created_connections >= self.max_connections:
            raise errors.ConnectionError("Too many connections")
        self._created_connections += 1
        return self.connection_class(**self.connection_kwargs, encoder = self.encoder)
    
    async def reestablish_connection(self, connection: AsyncConnection) -> bool:
        """
        Attempts to Reestablish connection to the host
        """
        duration = 0.0
        err, sock = None, None
        while duration < self.auto_pause_max_delay:
            try:
                sock = socket.create_connection((connection.host, connection.port), timeout = 0.5)
                sock.close()
                await connection.connect()
                return True
            except ConnectionRefusedError as err:
                await asyncio.sleep(self.auto_pause_interval)
                duration += self.auto_pause_interval
            finally:
                if sock: 
                    with contextlib.suppress(Exception):
                        sock.close() 
        if sock:
            with contextlib.suppress(Exception):
                sock.close()
        return False
    
    @contextlib.asynccontextmanager
    async def ensure_connection(self, connection: AsyncConnection) -> AsyncGenerator[AsyncConnection, None]:
        """
        Ensure that the connection is available and that the host is available
        """
        try:
            # ensure this connection is connected to Redis
            await connection.connect()
        
        except (rerrors.TimeoutError, rerrors.ConnectionError) as exc:
            if not self.auto_pause_enabled or not await self.reestablish_connection(connection): 
                raise errors.TimeoutError(source_error = exc) from exc

        # connections that the pool provides should be ready to send
        # a command. if not, the connection was either returned to the
        # pool before all data has been read or the socket has been
        # closed. either way, reconnect and verify everything is good.
        try:
            if await connection.can_read_destructive():
                # raise errors.ConnectionError("Connection has data")
                # Suppress error to avoid loop/hang on 'Connection has data' false positives or partials
                pass
        except (errors.ConnectionError, rerrors.ConnectionError, ConnectionError, OSError) as exc:
            await connection.disconnect()
            await connection.connect()
            try:
                if await connection.can_read_destructive():
                    raise errors.ConnectionError("Connection not ready") from exc
            
            except (errors.ConnectionError, rerrors.ConnectionError, ConnectionError, OSError) as exc:
                if not await self.reestablish_connection(connection): 
                    raise errors.TimeoutError(source_error = exc) from exc
        
        except BaseException:
            # release the connection back to the pool so that we don't
            # leak it
            await self.release(connection)
            raise

        try:
            yield connection
        except Exception as e:
            logger.error(f"Error in connection pool: {e}")
            with contextlib.suppress(Exception):
                await self.release(connection)
            raise e


    async def get_connection(self, command_name: Optional[str] = None, *keys, **options):
        """
        Get a connection from the pool
        """
        # self._checkpid()
        async with self._lock:
            try:
                connection = self._available_connections.pop()
            except IndexError:
                try:
                    connection = self.make_connection()
                except errors.ConnectionError as e:
                    if not self.auto_reset_enabled: raise e
                    logger.warning(f'Resetting Connection Pool: {self._created_connections}/{self.max_connections}')
                    await self.reset_pool()
                    connection = self.make_connection()

            self._in_use_connections.add(connection)

        async with self.ensure_connection(connection) as conn:
            return conn
    

    
    @contextlib.asynccontextmanager
    async def disconnect_ctx(self, with_lock: bool = True, **kwargs):
        """
        A context manager for disconnecting
        """
        if not with_lock:
            yield
            return
        async with self._lock:
            yield

    async def disconnect(    
        self, 
        inuse_connections: bool = True,
        raise_errors: bool = False,
        with_lock: bool = True,
        return_connections: bool = False,
        **kwargs,
    ):
        """
        Disconnects connections in the pool

        If ``inuse_connections`` is True, disconnect connections that are
        current in use, potentially by other tasks. Otherwise only disconnect
        connections that are idle in the pool.
        """
        async with self.disconnect_ctx(with_lock = with_lock):
            if inuse_connections:
                connections: Iterable[AsyncConnection] = itertools.chain(
                    self._available_connections, self._in_use_connections
                )
            else:
                connections = self._available_connections
            resp = await asyncio.gather(
                *(connection.disconnect() for connection in connections),
                return_exceptions=True,
            )
            exc = next((r for r in resp if isinstance(r, BaseException)), None)
            if exc and raise_errors:
                raise exc
            if return_connections:
                return [connection for connection, r in zip(connections, resp) if not isinstance(r, BaseException)]
            
    
    async def recreate(
        self,
        inuse_connections: bool = True,
        raise_errors: bool = False,
        with_lock: bool = False,
        **recreate_kwargs
    ) -> 'AsyncConnectionPool':
        """
        Recreates the connection pool
        """
        await self.disconnect(
            inuse_connections = inuse_connections,
            raise_errors = raise_errors,
            with_lock = with_lock,
        )
        return self.__class__(**self.get_init_kwargs(**recreate_kwargs))

    async def reset_pool(
        self, 
        *args,
        inuse_connections: bool = True, 
        raise_errors: bool = False,
        with_lock: bool = False,
        **kwargs,
    ):
        """
        Resets the connection pool
        """
        await self.disconnect(inuse_connections = inuse_connections, raise_errors = raise_errors, with_lock = with_lock, return_connections = True)
        self.reset()

    @property
    def db_id(self) -> int:
        """
        Returns the database ID
        """
        return self.connection_kwargs.get("db", 0)

    @property
    def settings(self) -> 'KVDBSettings':
        """
        Returns the settings
        """
        if self._settings is None:
            from kvdb.configs import settings
            self._settings = settings
        return self._settings
    
    @property
    def encoder(self) -> 'Encoder':
        """
        Returns the encoder
        """
        if self._encoder is None:
            kwargs = self.connection_kwargs
            serializer_disabled = self.extra_kwargs.get(
                'serializer_disabled', self.serializer is None
            )
            # logger.info(f"Serializer Disabled: {serializer_disabled}")
            self._encoder = self.encoder_class(
                encoding = kwargs.get("encoding", "utf-8"),
                encoding_errors = kwargs.get("encoding_errors", "strict"),
                decode_responses = kwargs.get("decode_responses"),
                serializer = None if serializer_disabled else self.serializer,
            )
        return self._encoder


class AsyncBlockingConnectionPool(_AsyncBlockingConnectionPool, AsyncConnectionPool):
    """
    A blocking connection pool
    """

    def __init__(
        self, 
        connection_class: Type[AsyncConnection] = AsyncConnection, 
        max_connections: Optional[int] = None, 
        **kwargs
    ):
        """
        Initialize the Blocking Connection Pool
        """
        max_connections = max_connections or 50
        super().__init__(connection_class = connection_class, max_connections = max_connections, **kwargs)
        # Ensure condition uses the same lock as the rest of the pool
        self._condition = asyncio.Condition(self._lock)

    async def get_connection(self, command_name: Optional[str] = None, *keys, **options):
        """
        Gets a connection from the pool, blocking until one is available
        """
        async with self._condition:
            if self.timeout is None:
                await self._condition.wait_for(self.can_get_connection)
            else:
                try:
                    async with async_timeout(self.timeout):
                        await self._condition.wait_for(self.can_get_connection)
                except asyncio.TimeoutError as err:
                    raise errors.ConnectionError("No connection available.") from err
            
            if self._available_connections:
                connection = self._available_connections.pop()
            else:
                connection = self.make_connection()
            
            self._in_use_connections.add(connection)

        async with self.ensure_connection(connection) as conn:
            return conn



ConnectionPoolT = Union[ConnectionPool, BlockingConnectionPool]
AsyncConnectionPoolT = Union[AsyncConnectionPool, AsyncBlockingConnectionPool]