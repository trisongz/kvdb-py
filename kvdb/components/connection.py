from __future__ import annotations

import os
import sys
import abc
import copy
import logging
import asyncio
import typing
import contextlib
import threading
import inspect


from itertools import chain
from queue import Empty, Full, Queue, LifoQueue
from urllib.parse import parse_qs, unquote, urlparse, ParseResult

from redis.connection import (
    URL_QUERY_ARGUMENT_PARSERS,
    Connection,
    UnixDomainSocketConnection,
    SSLConnection,
    ConnectionPool as _ConnectionPool,
    BlockingConnectionPool as _BlockingConnectionPool,
    Retry,
)

from redis.asyncio.connection import (
    Connection as AsyncConnection,
    UnixDomainSocketConnection as AsyncUnixDomainSocketConnection,
    SSLConnection as AsyncSSLConnection,
    ConnectionPool as _AsyncConnectionPool,
    BlockingConnectionPool as _AsyncBlockingConnectionPool,
)


# the functionality is available in 3.11.x but has a major issue before
# 3.11.3. See https://github.com/redis/redis-py/issues/2633
if sys.version_info >= (3, 11, 3):
    from asyncio import timeout as async_timeout
else:
    from async_timeout import timeout as async_timeout

from kvdb import errors
from kvdb.types.base import supported_schemas, KVDBUrl
from kvdb.utils.logs import logger
from kvdb.utils.helpers import extract_obj_init_kwargs
from kvdb.io.encoder import Encoder
from typing import Union, Optional, Any, Dict, List, Tuple, Type, TypeVar, Callable, Awaitable, TYPE_CHECKING

if TYPE_CHECKING:
    from kvdb.configs.base import KVDBSettings
    from kvdb.io.serializers import SerializerT

def parse_url(url: Union[str, KVDBUrl], _is_async: bool = False):
    """
    Parse a URL string into a dictionary of connection parameters.
    """
    if not any(
        url.startswith(scheme) for scheme in supported_schemas
    ):
        raise ValueError(f"Invalid URL scheme (valid schemes are:  {', '.join(supported_schemas)})")
    url: KVDBUrl = KVDBUrl(url = url) if isinstance(url, str) else url
    kwargs = {}
    for name, value in parse_qs(url.query).items():
        if value and len(value) > 0:
            value = unquote(value[0])
            parser = URL_QUERY_ARGUMENT_PARSERS.get(name)
            if parser:
                try:
                    kwargs[name] = parser(value)
                except (TypeError, ValueError) as e:
                    raise ValueError(f"Invalid value for `{name}` in connection URL.") from e
            else:
                kwargs[name] = value
    
    if url.username: kwargs["username"] = unquote(url.username)
    if url.password: kwargs["password"] = unquote(url.password)
    if url.is_unix: 
        if url.path: kwargs["path"] = unquote(url.path)
        kwargs["connection_class"] = AsyncUnixDomainSocketConnection if _is_async else UnixDomainSocketConnection
    else:
        if url.host: kwargs["host"] = unquote(url.host)
        if url.port: kwargs["port"] = int(url.port)
        kwargs["db"] = url.db_id
        if url.is_tls:
            kwargs["connection_class"] = AsyncSSLConnection if _is_async else SSLConnection
    return kwargs


_conn_valid_kwarg_keys: Dict[str, List[str]] = {}

def filter_kwargs_for_connection(conn_cls: Type[Connection], kwargs: Dict[str, typing.Any]) -> typing.Dict[str, typing.Any]:
    # sourcery skip: dict-comprehension
    """
    Filter out kwargs that aren't valid for a connection class
    """
    global _conn_valid_kwarg_keys
    if conn_cls.__name__ not in _conn_valid_kwarg_keys:
        _conn_valid_kwarg_keys[conn_cls.__name__] = extract_obj_init_kwargs(conn_cls)
    return {k: v for k, v in kwargs.items() if k in _conn_valid_kwarg_keys[conn_cls.__name__]}

class ConnectionPoolMixin(abc.ABC):
    """
    Connection Pool Mixin Functions
    """

    _settings: Optional['KVDBSettings'] = None
    _encoder: Optional['Encoder'] = None

    serializer: Optional['SerializerT'] = None
    auto_reset_enabled: Optional[bool] = None
    is_async: bool = False

    if TYPE_CHECKING:
        is_async: bool
        connection_kwargs: Dict[str, Any]
        connection_class: typing.Type[Connection]
        max_connections: typing.Optional[int]
        extra_kwargs: typing.Dict[str, Any]
        pid: int
        _lock: Union[threading.Lock, asyncio.Lock]
        _available_connections: typing.Union[typing.List[typing.Type[Connection]], typing.List[typing.Type[AsyncConnection]]]
        _in_use_connections: typing.Union[typing.Set[typing.Type[Connection]], typing.Set[typing.Type[AsyncConnection]]]
        _created_connections: int
        
        
    @property
    def settings(self) -> 'KVDBSettings':
        """
        Returns the settings
        """
        if self._settings is None:
            from kvdb.configs import settings
            self._settings = settings
        return self._settings

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

    def post_init_base(self, **kwargs):
        """
        Post init function
        """
        self.extra_kwargs = {k:v for k, v in kwargs.items() if k not in self.connection_kwargs}
        self.encoder_class = self.connection_kwargs.get("encoder_class", Encoder)
        if 'serializer' in kwargs:
            serializer = kwargs.get('serializer')
            if isinstance(serializer, str):
                from kvdb.io.serializers import get_serializer
                serializer = get_serializer(serializer, **kwargs)
            self.serializer = serializer
        self.auto_reset_enabled = kwargs.get('auto_reset_enabled', self.settings.pool.auto_reset_enabled)
        # a lock to protect the critical section in _checkpid().
        # this lock is acquired when the process id changes, such as
        # after a fork. during this time, multiple threads in the child
        # process could attempt to acquire this lock. the first thread
        # to acquire the lock will reset the data structures and lock
        # object of this pool. subsequent threads acquiring this lock
        # will notice the first thread already did the work and simply
        # release the lock.
        
        self._fork_lock: threading.Lock = threading.Lock()


    def _checkpid(self):
        # _checkpid() attempts to keep ConnectionPool fork-safe on modern
        # systems. this is called by all ConnectionPool methods that
        # manipulate the pool's state such as get_connection() and release().
        #
        # _checkpid() determines whether the process has forked by comparing
        # the current process id to the process id saved on the ConnectionPool
        # instance. if these values are the same, _checkpid() simply returns.
        #
        # when the process ids differ, _checkpid() assumes that the process
        # has forked and that we're now running in the child process. the child
        # process cannot use the parent's file descriptors (e.g., sockets).
        # therefore, when _checkpid() sees the process id change, it calls
        # reset() in order to reinitialize the child's ConnectionPool. this
        # will cause the child to make all new connection objects.
        #
        # _checkpid() is protected by self._fork_lock to ensure that multiple
        # threads in the child process do not call reset() multiple times.
        #
        # there is an extremely small chance this could fail in the following
        # scenario:
        #   1. process A calls _checkpid() for the first time and acquires
        #      self._fork_lock.
        #   2. while holding self._fork_lock, process A forks (the fork()
        #      could happen in a different thread owned by process A)
        #   3. process B (the forked child process) inherits the
        #      ConnectionPool's state from the parent. that state includes
        #      a locked _fork_lock. process B will not be notified when
        #      process A releases the _fork_lock and will thus never be
        #      able to acquire the _fork_lock.
        #
        # to mitigate this possible deadlock, _checkpid() will only wait 5
        # seconds to acquire _fork_lock. if _fork_lock cannot be acquired in
        # that time it is assumed that the child is deadlocked and a
        # redis.ChildDeadlockedError error is raised.
        if self.pid != os.getpid():
            acquired = self._fork_lock.acquire(timeout=5)
            if not acquired:
                raise errors.ChildDeadlockedError
            # reset() the instance for the new process if another thread
            # hasn't already done so
            try:
                if self.pid != os.getpid(): self.reset()
            finally: self._fork_lock.release()
    

    def post_init_pool(self, **kwargs):
        """
        Post init function
        """
        pass

    def get_encoder(self) -> 'Encoder':
        """
        Returns the encoder
        """
        return self.encoder

    @property
    def encoder(self) -> 'Encoder':
        """
        Returns the encoder
        """
        if self._encoder is None:
            kwargs = self.connection_kwargs
            self._encoder = self.encoder_class(
                encoding = kwargs.get("encoding", "utf-8"),
                encoding_errors = kwargs.get("encoding_errors", "strict"),
                decode_responses = kwargs.get("decode_responses", True),
            )
        return self._encoder

    @property
    def db_id(self) -> int:
        """
        Returns the database ID
        """
        return self.connection_kwargs.get("db", 0)
    
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
    
    def with_db_id(self, db_id: int):
        """
        Return a new connection pool with the specified db_id.
        """
        return self.__class__(**self.get_init_kwargs(db = db_id))
    
    def validate_connection_limit(self):
        """
        Validate the connection limit
        """
        pass

    def make_connection(self) -> Connection:
        """
        Create a new connection
        """
        self.validate_connection_limit()
        new_cls = self.connection_class(**self.connection_kwargs)
        new_cls.encoder = self.encoder
        return new_cls

    def owns_connection(self, connection: Connection) -> bool:
        """
        Check if the connection belongs to this pool
        """
        return connection.pid == self.pid
    
    def set_retry(self, retry: "Retry") -> None:
        """
        Set the retry instance for the pool and all its connections.
        """
        self.connection_kwargs.update({"retry": retry})
        for conn in self._available_connections:
            conn.retry = retry
        for conn in self._in_use_connections:
            conn.retry = retry

    def disconnect(
        self, 
        inuse_connections: bool = True,
        raise_exceptions: bool = True,
        with_lock: bool = True,
    ):
        """
        Disconnects connections in the pool

        If ``inuse_connections`` is True, disconnect connections that are
        current in use, potentially by other threads. Otherwise only disconnect
        connections that are idle in the pool.
        """
        self._checkpid()
        if with_lock: self._lock.acquire()
        if inuse_connections: connections = chain(self._available_connections, self._in_use_connections)
        else: connections = self._available_connections
        for connection in connections:
            try: connection.disconnect()
            except Exception as e:
                if raise_exceptions: raise errors.transpose_error(
                    e, msg = f'Error disconnecting connection: {connection}'
                ) from e
        if with_lock: self._lock.release()
        
    def reset_pool(
        self, 
        inuse_connections: bool = True, 
        raise_exceptions: bool = False,
    ):
        """
        Resets the connection pool
        """
        self.disconnect(inuse_connections = inuse_connections, raise_exceptions = raise_exceptions, with_lock = False)
        self.reset()

    def recreate(
        self,
        inuse_connections: bool = True,
        raise_exceptions: bool = False,
        with_lock: bool = False,
        **recreate_kwargs
    ) -> 'ConnectionPool':
        """
        Recreates the connection pool
        """
        self.disconnect(
            inuse_connections = inuse_connections,
            raise_exceptions = raise_exceptions,
            with_lock = with_lock,
        )
        return self.__class__(**self.get_init_kwargs(**recreate_kwargs))

class AsyncConnectionPoolMixin(ConnectionPoolMixin):
    """
    Async Connection Pool Mixin Functions
    """
    is_async: bool = True

    async def disconnect(    
        self, 
        inuse_connections: bool = True,
        raise_exceptions: bool = False,
        with_lock: bool = True,
        return_connections: bool = False,
    ):
        """
        Disconnects connections in the pool

        If ``inuse_connections`` is True, disconnect connections that are
        current in use, potentially by other tasks. Otherwise only disconnect
        connections that are idle in the pool.
        """
        self._checkpid()
        if with_lock:
            await self._lock.acquire()
        if inuse_connections:
            connections: typing.Iterable[Connection] = chain(
                self._available_connections, self._in_use_connections
            )
        else:
            connections = self._available_connections
        resp = await asyncio.gather(
            *(connection.disconnect() for connection in connections),
            return_exceptions=True,
        )
        exc = next((r for r in resp if isinstance(r, BaseException)), None)
        if exc and raise_exceptions:
            raise exc
        if with_lock:
            self._lock.release()
        if return_connections:
            return [connection for connection, r in zip(connections, resp) if not isinstance(r, BaseException)]
        
    async def reset_pool(
        self, 
        inuse_connections: bool = True, 
        raise_exceptions: bool = False,
        with_lock: bool = False,
    ):
        """
        Resets the connection pool
        """
        await self.disconnect(inuse_connections = inuse_connections, raise_exceptions = raise_exceptions, with_lock = with_lock, return_connections = True)
        self.reset()

    async def recreate(
        self,
        inuse_connections: bool = True,
        raise_exceptions: bool = False,
        with_lock: bool = False,
        **recreate_kwargs
    ) -> 'AsyncConnectionPool':
        """
        Recreates the connection pool
        """
        await self.disconnect(
            inuse_connections = inuse_connections,
            raise_exceptions = raise_exceptions,
            with_lock = with_lock,
        )
        return self.__class__(**self.get_init_kwargs(**recreate_kwargs))



class ConnectionPool(_ConnectionPool, ConnectionPoolMixin):
    """
    Create a connection pool. ``If max_connections`` is set, then this
    object raises :py:class:`~redis.exceptions.ConnectionError` when the pool's
    limit is reached.

    By default, TCP connections are created unless ``connection_class``
    is specified. Use class:`.UnixDomainSocketConnection` for
    unix sockets.

    Any additional keyword arguments are passed to the constructor of
    ``connection_class``.
    """

    

    def __init__(
        self, 
        connection_class: typing.Type[Connection] = Connection, 
        max_connections: typing.Optional[int] = None, 
        **connection_kwargs
    ):
        max_connections = max_connections or 2**31
        if not isinstance(max_connections, int) or max_connections < 0:
            raise ValueError('"max_connections" must be a positive integer')
        # try:
        #     set_ulimits(max_connections)
        # except Exception as e:
        #     logger.debug(f"Unable to set ulimits for connection: {e}")
        
        self.connection_class = connection_class
        self.connection_kwargs = filter_kwargs_for_connection(self.connection_class, connection_kwargs)
        self.max_connections = max_connections
        self.post_init_base(**connection_kwargs)
        self.post_init_pool(**connection_kwargs)

    def post_init_pool(self, **kwargs):
        """
        Post init function
        """
        self._lock: threading.Lock = None
        self._created_connections: int = None
        self._available_connections: typing.List[typing.Type[Connection]] = None
        self._in_use_connections: typing.Set[typing.Type[Connection]] = None
        self.reset()

    def validate_connection_limit(self):
        """
        Validate the connection limit
        """
        if self._created_connections >= self.max_connections:
            raise errors.ConnectionError("Too many connections")
        self._created_connections += 1

    def get_connection(self, command_name, *keys, **options):
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

        try:
            # ensure this connection is connected to Redis
            connection.connect()
            # connections that the pool provides should be ready to send
            # a command. if not, the connection was either returned to the
            # pool before all data has been read or the socket has been
            # closed. either way, reconnect and verify everything is good.
            try:
                if connection.can_read():
                    raise ConnectionError("Connection has data")
            except (errors.ConnectionError, ConnectionError, OSError) as exc:
                connection.disconnect()
                connection.connect()
                if connection.can_read():
                    raise errors.ConnectionError("Connection not ready") from exc
        except BaseException:
            # release the connection back to the pool so that we don't
            # leak it
            self.release(connection)
            raise
        return connection



class BlockingConnectionPool(_BlockingConnectionPool, ConnectionPoolMixin):
    """
    Thread-safe blocking connection pool::

        >>> from kvdb.client import KVDB
        >>> client = KVDB(connection_pool=BlockingConnectionPool())

    It performs the same function as the default
    :py:class:`~redis.ConnectionPool` implementation, in that,
    it maintains a pool of reusable connections that can be shared by
    multiple redis clients (safely across threads if required).

    The difference is that, in the event that a client tries to get a
    connection from the pool when all of connections are in use, rather than
    raising a :py:class:`~redis.ConnectionError` (as the default
    :py:class:`~redis.ConnectionPool` implementation does), it
    makes the client wait ("blocks") for a specified number of seconds until
    a connection becomes available.

    Use ``max_connections`` to increase / decrease the pool size::

        >>> pool = BlockingConnectionPool(max_connections=10)

    Use ``timeout`` to tell it either how many seconds to wait for a connection
    to become available, or to block forever:

        >>> # Block forever.
        >>> pool = BlockingConnectionPool(timeout=None)

        >>> # Raise a ``ConnectionError`` after five seconds if a connection is
        >>> # not available.
        >>> pool = BlockingConnectionPool(timeout=5)
    """


    def __init__(
        self,
        max_connections: int = 50,
        timeout: int = 20,
        connection_class: Type[Connection] = Connection,
        queue_class: Type[Queue] = LifoQueue,
        **connection_kwargs,
    ):

        self.queue_class = queue_class
        self.timeout = timeout
        self._connections: typing.List[Connection] = []
        self.connection_class = connection_class
        self.connection_kwargs = filter_kwargs_for_connection(self.connection_class, connection_kwargs)
        self.max_connections = max_connections
        self.post_init_base(**connection_kwargs)
        self.post_init_pool(**connection_kwargs)

    def make_connection(self) -> Connection:
        """
        Create a new connection
        """
        self.validate_connection_limit()
        new_cls = self.connection_class(**self.connection_kwargs)
        new_cls.encoder = self.encoder
        self._connections.append(new_cls)
        return new_cls

    def post_init_pool(self, **kwargs):
        """
        Post init function
        """
        self.reset()

    def disconnect(
        self, 
        **kwargs
    ):
        """
        Disconnects connections in the pool

        If ``inuse_connections`` is True, disconnect connections that are
        current in use, potentially by other threads. Otherwise only disconnect
        connections that are idle in the pool.
        """
        self._checkpid()
        for connection in self._connections:
            connection.disconnect()


class AsyncConnectionPool(_AsyncConnectionPool, AsyncConnectionPoolMixin):


    def __init__(
        self, 
        connection_class: typing.Type[AsyncConnection] = AsyncConnection, 
        max_connections: typing.Optional[int] = None, 
        **connection_kwargs
    ):
        max_connections = max_connections or 2**31
        if not isinstance(max_connections, int) or max_connections < 0:
            raise ValueError('"max_connections" must be a positive integer')
        # try:
        #     set_ulimits(max_connections)
        # except Exception as e:
        #     logger.debug(f"Unable to set ulimits for connection: {e}")
        
        self.connection_class = connection_class
        self.connection_kwargs = filter_kwargs_for_connection(self.connection_class, connection_kwargs)
        self.max_connections = max_connections
        self.post_init_base(**connection_kwargs)
        self.post_init_pool(**connection_kwargs)    

    def post_init_pool(self, **kwargs):
        """
        Post init function
        """
        self._lock: asyncio.Lock = None
        self._created_connections: int = None
        self._available_connections: typing.List[typing.Type[AsyncConnection]] = None
        self._in_use_connections: typing.Set[typing.Type[AsyncConnection]] = None
        self.reset()

    def validate_connection_limit(self):
        """
        Validate the connection limit
        """
        if self._created_connections >= self.max_connections:
            raise errors.ConnectionError("Too many connections")
        self._created_connections += 1

    async def get_connection(self, command_name, *keys, **options):
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
                    await self.reset_pool()
                    connection = self.make_connection()

            self._in_use_connections.add(connection)

        try:
            # ensure this connection is connected to Redis
            await connection.connect()
            # connections that the pool provides should be ready to send
            # a command. if not, the connection was either returned to the
            # pool before all data has been read or the socket has been
            # closed. either way, reconnect and verify everything is good.
            try:
                if await connection.can_read_destructive():
                    raise errors.ConnectionError("Connection has data")
            except (errors.ConnectionError, ConnectionError, OSError) as exc:
                await connection.disconnect()
                await connection.connect()
                if await connection.can_read_destructive():
                    raise errors.ConnectionError("Connection not ready") from exc
        except BaseException:
            # release the connection back to the pool so that we don't
            # leak it
            await self.release(connection)
            raise
        return connection
    

class AsyncBlockingConnectionPool(_AsyncBlockingConnectionPool, AsyncConnectionPoolMixin):


    def __init__(
        self,
        max_connections: int = 50,
        timeout: int = 20,
        connection_class: Type[AsyncConnection] = AsyncConnection,
        queue_class: Type[asyncio.Queue] = asyncio.LifoQueue,
        **connection_kwargs,
    ):

        self.queue_class = queue_class
        self.timeout = timeout
        self._connections: typing.List[AsyncConnection] = []
        self.connection_class = connection_class
        self.connection_kwargs = filter_kwargs_for_connection(self.connection_class, connection_kwargs)
        self.max_connections = max_connections
        self.post_init_base(**connection_kwargs)
        self.post_init_pool(**connection_kwargs)


    def make_connection(self) -> AsyncConnection:
        """
        Create a new connection
        """
        self.validate_connection_limit()
        new_cls = self.connection_class(**self.connection_kwargs)
        new_cls.encoder = self.encoder
        self._connections.append(new_cls)
        return new_cls

    def post_init_pool(self, **kwargs):
        """
        Post init function
        """
        self.reset()


    async def disconnect(
        self, 
        **kwargs
    ):
        """
        Disconnects connections in the pool

        If ``inuse_connections`` is True, disconnect connections that are
        current in use, potentially by other threads. Otherwise only disconnect
        connections that are idle in the pool.
        """
        self._checkpid()
        async with self._lock:
            resp = await asyncio.gather(
                *(connection.disconnect() for connection in self._connections),
                return_exceptions=True,
            )
            exc = next((r for r in resp if isinstance(r, BaseException)), None)
            if exc:
                raise exc
