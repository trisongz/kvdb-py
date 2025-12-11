from __future__ import annotations

"""
Some Base Components for KVDB
"""
import os
import sys
import copy
import inspect

import socket
import weakref
import asyncio
import contextlib

# from itertools import chain
from urllib.parse import parse_qs, unquote
from redis.connection import (
    URL_QUERY_ARGUMENT_PARSERS,
    AbstractConnection as _AbstractConnection,
    Connection as _Connection,
    UnixDomainSocketConnection as _UnixDomainSocketConnection,
    SSLConnection as _SSLConnection,
    ConnectionPool as _ConnectionPool,
    BlockingConnectionPool as _BlockingConnectionPool,
    Retry,
    DefaultParser,
)


from redis.asyncio.connection import (
    AbstractConnection as _AsyncAbstractConnection,
    Connection as _AsyncConnection,
    UnixDomainSocketConnection as _AsyncUnixDomainSocketConnection,
    SSLConnection as _AsyncSSLConnection,
    ConnectionPool as _AsyncConnectionPool,
    BlockingConnectionPool as _AsyncBlockingConnectionPool,
    ConnectCallbackT,
    _Sentinel,
    SENTINEL,
    BaseParser as AsyncBaseParser, 
    DefaultParser as AsyncDefaultParser,
    CredentialProvider,
    NoBackoff,
    # DEFAULT_RESP_VERSION,
)

try:
    from redis.asyncio.connection import DEFAULT_RESP_VERSION, EventDispatcher
    DEPRECATED_SUPPORT = False
except ImportError:
    DEFAULT_RESP_VERSION = 2
    DEPRECATED_SUPPORT = True
    # EventDispatcher not available in older versions
    EventDispatcher = None


import kvdb.errors as errors
from kvdb.io.encoder import Encoder
from kvdb.types.base import supported_schemas, KVDBUrl
from kvdb.utils.logs import logger
from kvdb.version import VERSION
from .parser import _AsyncHiredisParser, HIREDIS_AVAILABLE
if HIREDIS_AVAILABLE:
    AsyncDefaultParser = _AsyncHiredisParser

from typing import Union, Optional, Any, Dict, List, Iterable, Tuple, Type, Set, TypeVar, Callable, Awaitable, TYPE_CHECKING

try:
    import trio
    TRIO_ENABLED = True
except ImportError:
    TRIO_ENABLED = False

# the functionality is available in 3.11.x but has a major issue before
# 3.11.3. See https://github.com/redis/redis-py/issues/2633
if sys.version_info >= (3, 11, 3):
    from asyncio import timeout as async_timeout
else:
    from async_timeout import timeout as async_timeout

# from redis._parsers import hiredis
if TYPE_CHECKING:
    from kvdb.configs import KVDBSettings
    from kvdb.io.serializers import SerializerT

# :TODO - add a loadbalancer connection class 

class AbstractConnection(_AbstractConnection):
    """
    A mixin for Connection classes
    This mixin adds the following functionality:
    - overrides the init method to accept an encoder
    """

    def __init__(
        self,
        *args,
        db: int = 0,
        password: Optional[str] = None,
        socket_timeout: Optional[float] = None,
        socket_connect_timeout: Optional[float] = None,
        retry_on_timeout: bool = False,
        retry_on_error = SENTINEL,
        encoding: str = "utf-8",
        encoding_errors: str = "strict",
        decode_responses: bool = False,
        encoder: Optional[Encoder] = None,
        parser_class = DefaultParser,
        socket_read_size: int = 65536,
        health_check_interval: int = 0,
        client_name: Optional[str] = None,
        lib_name: Optional[str] = "kvdb",
        lib_version: Optional[str] = VERSION,
        username: Optional[str] = None,
        retry: Union[Any, None] = None,
        redis_connect_func: Optional[Callable[[], None]] = None,
        credential_provider: Optional[CredentialProvider] = None,
        protocol: Optional[int] = 2,
        event_dispatcher: Optional[Any] = None,
        command_packer: Optional[Callable[[], None]] = None,
        serializer: Optional['SerializerT'] = None,
        **kwargs,
    ):  # sourcery skip: low-code-quality
        """
        Initialize a new Connection.
        To specify a retry policy for specific errors, first set
        `retry_on_error` to a list of the error/s to retry on, then set
        `retry` to a valid `Retry` object.
        To retry on TimeoutError, `retry_on_timeout` can also be set to `True`.
        """
        if (username or password) and credential_provider is not None:
            raise errors.DataError(
                "'username' and 'password' cannot be passed along with 'credential_"
                "provider'. Please provide only one of the following arguments: \n"
                "1. 'password' and (optional) 'username'\n"
                "2. 'credential_provider'"
            )
        # logger.info(f"Using Mixin: {args}, {kwargs}, {self.__dict__}", prefix = self.__class__.__name__)
        self.pid = os.getpid()
        self.db = db
        self.client_name = client_name
        self.lib_name = lib_name
        self.lib_version = lib_version
        self.reset_should_reconnect()
        self.credential_provider = credential_provider
        self.password = password
        self.username = username
        self.socket_timeout = socket_timeout
        if socket_connect_timeout is None:
            socket_connect_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.retry_on_timeout = retry_on_timeout
        if retry_on_error is SENTINEL:
            retry_on_error = []
        if retry_on_timeout:
            # Add TimeoutError to the errors list to retry on
            retry_on_error.append(TimeoutError)
        self.retry_on_error = retry_on_error
        if retry or retry_on_error:
            self.retry = Retry(NoBackoff(), 1) if retry is None else copy.deepcopy(retry)
            # Update the retry's supported errors with the specified errors
            self.retry.update_supported_errors(retry_on_error)
        else:
            self.retry = Retry(NoBackoff(), 0)
        self.health_check_interval = health_check_interval
        self.next_health_check = 0
        self.redis_connect_func = redis_connect_func
        if encoder is not None:
            self.encoder = encoder
        else:
            self.encoder = Encoder(encoding, encoding_errors, decode_responses, serializer = serializer)
        self._sock = None
        self._socket_read_size = socket_read_size
        self.set_parser(parser_class)
        self._re_auth_token = None
        self._connect_callbacks = []
        self._buffer_cutoff = 6000
        try:
            p = int(protocol)
        except TypeError:
            p = DEFAULT_RESP_VERSION
        except ValueError as e:
            raise ConnectionError("protocol must be an integer") from e
        finally:
            if p < 2 or p > 3:
                raise ConnectionError("protocol must be either 2 or 3")
                # p = DEFAULT_RESP_VERSION
            self.protocol = p
        self._command_packer = self._construct_command_packer(command_packer)
        
        # Filter kwargs for super().__init__
        sig = inspect.signature(super().__init__)
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
            # If parent accepts **kwargs, we can't rely on signature filtering alone if the parent's parent is strict.
            # But redis.Connection accepts **kwargs and passes to redis.AbstractConnection (strict).
            # We must inspect the MRO or just filter known bad keys?
            # Or inspect super(redis.Connection, self).__init__? No, we don't know the exact class structure easily.
            # Best effort: if parent accepts kwargs, we pass everything EXCEPT common KVDB internal keys
            # or better: we use filter_kwargs_for_connection logic if possible?
            # User suggestion: "inspect the underlying kwargs ... and only pass through expected".
            # For now, let's assume we remove keys we KNOW are ours and not redis'.
            # 'encoder_class' caused the error.
            kwargs.pop('encoder_class', None)
            kwargs.pop('serializer', None) # serializer is already handled/popped?
            # If we want to be generic:
            init_kwargs = kwargs
        else:
            valid_params = sig.parameters.keys()
            init_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}

        super().__init__(**init_kwargs)

class Connection(AbstractConnection, _Connection): pass
class UnixDomainSocketConnection(AbstractConnection, _UnixDomainSocketConnection): pass
class SSLConnection(AbstractConnection, _SSLConnection): pass

class AsyncAbstractConnection(_AsyncAbstractConnection):
    """
    A mixin for AsyncConnection classes
    This mixin adds the following functionality:
    - overrides the init method to accept an encoder
    """
    def __init__(
        self,
        *args,
        db: Union[str, int] = 0,
        password: Optional[str] = None,
        socket_timeout: Optional[float] = None,
        socket_connect_timeout: Optional[float] = None,
        retry_on_timeout: bool = False,
        retry_on_error: Union[list, _Sentinel] = SENTINEL,
        encoder: Optional[Encoder] = None,
        encoding: str = "utf-8",
        encoding_errors: str = "strict",
        decode_responses: bool = False,
        parser_class: Type[AsyncBaseParser] = AsyncDefaultParser,
        socket_read_size: int = 65536,
        health_check_interval: float = 0,
        client_name: Optional[str] = None,
        lib_name: Optional[str] = "kvdb",
        lib_version: Optional[str] = VERSION,
        username: Optional[str] = None,
        retry: Optional[Retry] = None,
        redis_connect_func: Optional[ConnectCallbackT] = None,
        encoder_class: Type[Encoder] = Encoder,
        credential_provider: Optional[CredentialProvider] = None,
        protocol: Optional[int] = 2,
        event_dispatcher: Optional[Any] = None,
        serializer: Optional['SerializerT'] = None,
        **kwargs,
    ):  # sourcery skip: low-code-quality
        if (username or password) and credential_provider is not None:
            raise errors.DataError(
                "'username' and 'password' cannot be passed along with 'credential_"
                "provider'. Please provide only one of the following arguments: \n"
                "1. 'password' and (optional) 'username'\n"
                "2. 'credential_provider'"
            )
        # logger.info(f"Using Mixin: {args}, {kwargs}, {self.__dict__}", prefix = self.__class__.__name__)
        # Initialize event dispatcher for redis-py 7.x support
        if event_dispatcher is None and not DEPRECATED_SUPPORT and EventDispatcher is not None:
            self._event_dispatcher = EventDispatcher()
        elif event_dispatcher is not None:
            self._event_dispatcher = event_dispatcher
        else:
            self._event_dispatcher = None
        self.db = db
        self.client_name = client_name
        self.lib_name = lib_name
        self.lib_version = lib_version
        self.reset_should_reconnect()
        self.credential_provider = credential_provider
        self.password = password
        self.username = username
        self.socket_timeout = socket_timeout
        if socket_connect_timeout is None:
            socket_connect_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.retry_on_timeout = retry_on_timeout
        if retry_on_error is SENTINEL:
            retry_on_error = []
        if retry_on_timeout:
            retry_on_error.append(TimeoutError)
            retry_on_error.append(asyncio.TimeoutError)
        self.retry_on_error = retry_on_error
        self._init_retry(
            retry=retry, 
            retry_on_error=retry_on_error,
            health_check_interval=health_check_interval,
            encoder=encoder,
            encoder_class=encoder_class,
            encoding=encoding,
            encoding_errors=encoding_errors,
            decode_responses=decode_responses,
            redis_connect_func=redis_connect_func,
            socket_read_size=socket_read_size,
            parser_class=parser_class,
            protocol=protocol,
            serializer=serializer,
        )
        # logger.info(f"AsyncAbstractConnection Initialized: {self}")
        # Call super init to ensure Mixin behavior works, but pass filtered kwargs
        # The parent classes might need specific args, but we should be careful about what we pass
        # Since AsyncAbstractConnection is a Mixin, and we use it with AsyncConnection which inherits from redis.asyncio.connection.Connection
        # We need to make sure we don't pass arguments that are already handled or not expected by the MRO next class if it's not designed to handle **kwargs
        
        # However, redis.asyncio.connection.Connection.__init__ takes **kwargs but passes them to super().__init__
        # And AsyncConnection (our class) inherits from _AsyncConnection (redis) and AsyncAbstractConnection (kvdb)
        # We need to ensure that when we call super().__init__ here, it goes to the right place or we manually handle what's needed.
        
        # Actually, since we are overriding __init__ completely in this Mixin/Base class, we are responsible for setting up current class state.
        # But if we want to support properly what Connection expects (like host/port), we must ensure those are set or passed.
        # In this implementation, we are setting attributes directly.

        # Fix: We need to call super().__init__ to propagate kwargs if there are other Mixins or Base classes.
        # But wait, AsyncConnection inherits from (_AsyncConnection, AsyncAbstractConnection).
        # _AsyncConnection is redis.asyncio.connection.Connection.
        # So AsyncConnection MRO is: AsyncConnection, _AsyncConnection, AsyncAbstractConnection, AbstractConnection, object (roughly)
        # WARNING: If AsyncConnection inherits from _AsyncConnection FIRST, then _AsyncConnection.__init__ is called.
        # But we are REDEFINING AsyncConnection in connection.py as:
        # class AsyncConnection(_AsyncConnection, AsyncAbstractConnection): pass
        # This means _AsyncConnection.__init__ is called first unless AsyncConnection defines __init__. It doesn't.
        # So _AsyncConnection.__init__ is called.
        
        # _AsyncConnection (redis.asyncio.connection.Connection) calls super().__init__(**kwargs).
        # super() from _AsyncConnection refers to AsyncAbstractConnection (because of MRO!).
        # So AsyncAbstractConnection.__init__ IS called by _AsyncConnection.__init__.
        
        # So we just need to ensure we accept **kwargs and handle them or pass them up if needed.
        # And crucially, we must NOT call super().__init__ if we are the last one in chain that matters, OR we call object.__init__
        # But AbstractConnection is also in there.
        
        # Let's check AbstractConnection.
        
        
        # Filter kwargs for super().__init__
        sig = inspect.signature(super().__init__)
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
             kwargs.pop('encoder_class', None)
             kwargs.pop('serializer', None)
             init_kwargs = kwargs
        else:
            valid_params = sig.parameters.keys()
            init_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}

        super().__init__(**init_kwargs)
    
    def reset_should_reconnect(self):
        """
        Reset the flag to True so that the connection tries to reconnect
        """
        self._should_reconnect = False

    def _init_retry(
        self, 
        retry, 
        retry_on_error,
        health_check_interval,
        encoder,
        encoder_class,
        encoding,
        encoding_errors,
        decode_responses,
        redis_connect_func,
        socket_read_size,
        parser_class,
        protocol,
        serializer,
    ):
        if retry:
            # deep-copy the Retry object as it is mutable
            self.retry = copy.deepcopy(retry)
            # Update the retry's supported errors with the specified errors
            self.retry.update_supported_errors(retry_on_error)
        elif retry_on_error:
            self.retry = Retry(NoBackoff(), 1)
            # Update the retry's supported errors with the specified errors
            self.retry.update_supported_errors(retry_on_error)
        else:
            self.retry = Retry(NoBackoff(), 0)

        self.health_check_interval = health_check_interval
        self.next_health_check: float = -1
        if encoder is not None:
            self.encoder = encoder
        else:
            self.encoder = encoder_class(encoding, encoding_errors, decode_responses, serializer = serializer)
        self.redis_connect_func = redis_connect_func
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._socket_read_size = socket_read_size
        self.set_parser(parser_class)
        self._re_auth_token = None
        self._connect_callbacks: List[weakref.WeakMethod[ConnectCallbackT]] = []
        self._buffer_cutoff = 6000
        if DEPRECATED_SUPPORT:
            self.pid = os.getpid()
        try:
            p = int(protocol)
        except TypeError:
            p = DEFAULT_RESP_VERSION
        except ValueError as e:
            raise errors.ConnectionError("protocol must be an integer") from e
        finally:
            if p < 2 or p > 3:
                raise errors.ConnectionError("protocol must be either 2 or 3")
            self.protocol = protocol

        with contextlib.suppress(Exception):
            from lzo.utils import aioexit
            aioexit.register(self.disconnect)
        
        


class AsyncConnection(AsyncAbstractConnection, _AsyncConnection): pass
class AsyncUnixDomainSocketConnection(AsyncAbstractConnection, _AsyncUnixDomainSocketConnection): pass
class AsyncSSLConnection(AsyncAbstractConnection, _AsyncSSLConnection): pass

# TODO: Implement AsyncConnection with trio backend
class TrioAsyncAbstractConnection(AsyncAbstractConnection):
    def __init__(
        self,
        *args,
        db: Union[str, int] = 0,
        password: Optional[str] = None,
        socket_timeout: Optional[float] = None,
        socket_connect_timeout: Optional[float] = None,
        retry_on_timeout: bool = False,
        retry_on_error: Union[list, _Sentinel] = SENTINEL,
        encoder: Optional[Encoder] = None,
        encoding: str = "utf-8",
        encoding_errors: str = "strict",
        decode_responses: bool = False,
        parser_class: Type[AsyncBaseParser] = AsyncDefaultParser,
        socket_read_size: int = 65536,
        health_check_interval: float = 0,
        client_name: Optional[str] = None,
        lib_name: Optional[str] = "kvdb",
        lib_version: Optional[str] = VERSION,
        username: Optional[str] = None,
        retry: Optional[Retry] = None,
        redis_connect_func: Optional[ConnectCallbackT] = None,
        encoder_class: Type[Encoder] = Encoder,
        credential_provider: Optional[CredentialProvider] = None,
        protocol: Optional[int] = 2,
        **kwargs,
    ):  # sourcery skip: low-code-quality
        super().__init__(
            *args,
            db = db,
            password = password,
            socket_timeout = socket_timeout,
            socket_connect_timeout = socket_connect_timeout,
            retry_on_timeout = retry_on_timeout,
            retry_on_error = retry_on_error,
            encoder = encoder,
            encoding = encoding,
            encoding_errors = encoding_errors,
            decode_responses = decode_responses,
            parser_class = parser_class,
            socket_read_size = socket_read_size,
            health_check_interval = health_check_interval,
            client_name = client_name,
            lib_name = lib_name,
            lib_version = lib_version,
            username = username,
            retry = retry,
            redis_connect_func = redis_connect_func,
            encoder_class = encoder_class,
            credential_provider = credential_provider,
            protocol = protocol,
            **kwargs,
        )
        self._sock: Optional[trio.SocketStream] = None

    async def _send_packed_command(self, command: Iterable[bytes]) -> None:
        """
        Send an already packed command to the Redis server.
        """
        for item in command:
            await self._sock.send_all(item)


    async def send_packed_command(
        self, 
        command: Union[bytes, str, Iterable[bytes]], 
        check_health: bool = True
    ) -> None:
        """
        Send an already packed command to the Redis server.
        """
        if not self.is_connected:
            await self.connect()
        elif check_health:
            await self.check_health()

        try:
            if isinstance(command, str):
                command = command.encode()
            if isinstance(command, bytes):
                command = [command]
            for item in command:
                await self._sock.send_all(item)
        except asyncio.TimeoutError:
            await self.disconnect(nowait=True)
            raise TimeoutError("Timeout writing to socket") from None
        except OSError as e:
            await self.disconnect(nowait=True)
            if len(e.args) == 1:
                err_no, errmsg = "UNKNOWN", e.args[0]
            else:
                err_no = e.args[0]
                errmsg = e.args[1]
            raise errors.ConnectionError(
                f"Error {err_no} while writing to socket. {errmsg}."
            ) from e
        except BaseException:
            # BaseExceptions can be raised when a socket send operation is not
            # finished, e.g. due to a timeout.  Ideally, a caller could then re-try
            # to send un-sent data. However, the send_packed_command() API
            # does not support it so there is no point in keeping the connection open.
            await self.disconnect(nowait=True)
            raise
    
    @property
    def is_connected(self):
        """
        Get the connection status
        """
        return self._sock is not None

    async def _connect(self):
        "Create a TCP socket connection"
        # we want to mimic what socket.create_connection does to support
        # ipv4/ipv6, but we want to set options prior to calling
        # socket.connect()
        err = None
        async for res in trio.socket.getaddrinfo(
            self.host, self.port, self.socket_type, trio.socket.SOCK_STREAM
        ):
            family, socktype, proto, canonname, socket_address = res
            sock = None
            try:
                sock = trio.socket.socket(family, socktype, proto)
                # TCP_NODELAY
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                # TCP_KEEPALIVE
                if self.socket_keepalive:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    for k, v in self.socket_keepalive_options.items():
                        sock.setsockopt(socket.IPPROTO_TCP, k, v)

                # set the socket_connect_timeout before we connect
                # sock.settimeout(self.socket_connect_timeout)

                # connect
                with trio.move_on_after(self.socket_connect_timeout):
                    await sock.connect(socket_address)
                    self._sock = trio.SocketStream(sock)

                # set the socket_timeout now that we're connected
                # sock.settimeout(self.socket_timeout)
                # return 
            

            except OSError as _:
                err = _
                if sock is not None:
                    sock.close()

        if err is not None:
            raise err
        raise OSError("socket.getaddrinfo returned an empty list")
    

    async def disconnect(self, nowait: bool = False) -> None:
        """
        Disconnects from the Redis server
        """
        try:
            async with async_timeout(self.socket_connect_timeout):
                self._parser.on_disconnect()
                if not self.is_connected: return
                try:
                    await self._sock.aclose()
                    # self._writer.close()  # type: ignore[union-attr]
                    # wait for close to finish, except when handling errors and
                    # forcefully disconnecting.
                except OSError: pass
                finally: self._sock = None
        except asyncio.TimeoutError:
            raise TimeoutError(f"Timed out closing connection after {self.socket_connect_timeout}") from None


# if TRIO_ENABLED:

#     class TrioAsyncAbstractConnection(_AsyncAbstractConnection):
#         """
#         A mixin for Connection classes
#         This mixin adds the following functionality:
#         - overrides the init method to accept an encoder
#         """

#         def __init__(
#             self,
#             *args,
#             db: int = 0,
#             password: Optional[str] = None,
#             socket_timeout: Optional[float] = None,
#             socket_connect_timeout: Optional[float] = None,
#             retry_on_timeout: bool = False,
#             retry_on_error = SENTINEL,
#             encoding: str = "utf-8",
#             encoding_errors: str = "strict",
#             decode_responses: bool = False,
#             encoder: Optional[Encoder] = None,
#             parser_class = AsyncDefaultParser,
#             socket_read_size: int = 65536,
#             health_check_interval: int = 0,
#             client_name: Optional[str] = None,
#             lib_name: Optional[str] = "kvdb",
#             lib_version: Optional[str] = VERSION,
#             username: Optional[str] = None,
#             retry: Union[Any, None] = None,
#             redis_connect_func: Optional[Callable[[], None]] = None,
#             credential_provider: Optional[CredentialProvider] = None,
#             protocol: Optional[int] = 2,
#             command_packer: Optional[Callable[[], None]] = None,
#             **kwargs,
#         ):  # sourcery skip: low-code-quality
#             """
#             Initialize a new Connection.
#             To specify a retry policy for specific errors, first set
#             `retry_on_error` to a list of the error/s to retry on, then set
#             `retry` to a valid `Retry` object.
#             To retry on TimeoutError, `retry_on_timeout` can also be set to `True`.
#             """
#             if (username or password) and credential_provider is not None:
#                 raise errors.DataError(
#                     "'username' and 'password' cannot be passed along with 'credential_"
#                     "provider'. Please provide only one of the following arguments: \n"
#                     "1. 'password' and (optional) 'username'\n"
#                     "2. 'credential_provider'"
#                 )
#             # logger.info(f"Using Mixin: {args}, {kwargs}, {self.__dict__}", prefix = self.__class__.__name__)
#             self.pid = os.getpid()
#             self.db = db
#             self.client_name = client_name
#             self.lib_name = lib_name
#             self.lib_version = lib_version
#             self.credential_provider = credential_provider
#             self.password = password
#             self.username = username
#             self.socket_timeout = socket_timeout
#             if socket_connect_timeout is None:
#                 socket_connect_timeout = socket_timeout
#             self.socket_connect_timeout = socket_connect_timeout
#             self.retry_on_timeout = retry_on_timeout
#             if retry_on_error is SENTINEL:
#                 retry_on_error = []
#             if retry_on_timeout:
#                 # Add TimeoutError to the errors list to retry on
#                 retry_on_error.append(TimeoutError)
#             self.retry_on_error = retry_on_error
#             if retry or retry_on_error:
#                 self.retry = Retry(NoBackoff(), 1) if retry is None else copy.deepcopy(retry)
#                 # Update the retry's supported errors with the specified errors
#                 self.retry.update_supported_errors(retry_on_error)
#             else:
#                 self.retry = Retry(NoBackoff(), 0)
#             self.health_check_interval = health_check_interval
#             self.next_health_check = 0
#             self.redis_connect_func = redis_connect_func
#             if encoder is not None:
#                 self.encoder = encoder
#             else:
#                 self.encoder = Encoder(encoding, encoding_errors, decode_responses)
#             self._sock = None
#             self._socket_read_size = socket_read_size
#             self.set_parser(parser_class)
#             self._connect_callbacks = []
#             self._buffer_cutoff = 6000
#             try:
#                 p = int(protocol)
#             except TypeError:
#                 p = DEFAULT_RESP_VERSION
#             except ValueError as e:
#                 raise ConnectionError("protocol must be an integer") from e
#             finally:
#                 if p < 2 or p > 3:
#                     raise ConnectionError("protocol must be either 2 or 3")
#                     # p = DEFAULT_RESP_VERSION
#                 self.protocol = p
#             self._command_packer = self._construct_command_packer(command_packer)


# class TrioAsyncConnection(_AsyncConnection, TrioAsyncAbstractConnection):

#     async def _connect(self):
#         "Create a TCP socket connection"
#         # we want to mimic what socket.create_connection does to support
#         # ipv4/ipv6, but we want to set options prior to calling
#         # socket.connect()
#         err = None
#         async for res in trio.socket.getaddrinfo(
#             self.host, self.port, self.socket_type, trio.socket.SOCK_STREAM
#         ):
#             family, socktype, proto, canonname, socket_address = res
#             sock = None
#             try:
#                 sock = trio.socket.socket(family, socktype, proto)
#                 # TCP_NODELAY
#                 sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

#                 # TCP_KEEPALIVE
#                 if self.socket_keepalive:
#                     sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
#                     for k, v in self.socket_keepalive_options.items():
#                         sock.setsockopt(socket.IPPROTO_TCP, k, v)

#                 # set the socket_connect_timeout before we connect
#                 # sock.settimeout(self.socket_connect_timeout)

#                 # connect
#                 with trio.move_on_after(self.socket_connect_timeout):
#                     await sock.connect(socket_address)

#                 # set the socket_timeout now that we're connected
#                 # sock.settimeout(self.socket_timeout)
#                 return sock

#             except OSError as _:
#                 err = _
#                 if sock is not None:
#                     sock.close()

#         if err is not None:
#             raise err
#         raise OSError("socket.getaddrinfo returned an empty list")


#     async def _connect(self):
#         """
#         Create a TCP socket connection
#         """
#         async with async_timeout(self.socket_connect_timeout):
#             self._sock = await trio.open_tcp_stream(self.host, self.port)
#             reader, writer = await asyncio.open_connection(
#                 **self._connection_arguments()
#             )
#         self._reader = reader
#         self._writer = writer
#         sock = writer.transport.get_extra_info("socket")
#         if sock:
#             sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
#             try:
#                 # TCP_KEEPALIVE
#                 if self.socket_keepalive:
#                     sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
#                     for k, v in self.socket_keepalive_options.items():
#                         sock.setsockopt(socket.SOL_TCP, k, v)

#             except (OSError, TypeError):
#                 # `socket_keepalive_options` might contain invalid options
#                 # causing an error. Do not leave the connection open.
#                 writer.close()
#                 raise
class TrioAsyncConnection(TrioAsyncAbstractConnection, _AsyncConnection):
    pass



def parse_url(url: Union[str, KVDBUrl], _is_async: bool = False):
    """
    Parse a URL string into a dictionary of connection parameters.
    """
    if isinstance(url, str) and not any(
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

