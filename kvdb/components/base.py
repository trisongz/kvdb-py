from __future__ import annotations

"""
Some Base Components for KVDB
"""
import os
import copy
import socket
import weakref
import asyncio
from itertools import chain
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
    DEFAULT_RESP_VERSION,
)

from kvdb import errors
from kvdb.io.encoder import Encoder
from kvdb.types.base import supported_schemas, KVDBUrl
from kvdb.utils.logs import logger
from kvdb.version import VERSION

from typing import Union, Optional, Any, Dict, List, Iterable, Tuple, Type, Set, TypeVar, Callable, Awaitable, TYPE_CHECKING


if TYPE_CHECKING:
    from kvdb.configs import KVDBSettings
    from kvdb.io.serializers import SerializerT

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
        command_packer: Optional[Callable[[], None]] = None,
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
            self.encoder = Encoder(encoding, encoding_errors, decode_responses)
        self._sock = None
        self._socket_read_size = socket_read_size
        self.set_parser(parser_class)
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

class Connection(_Connection, AbstractConnection): pass
class UnixDomainSocketConnection(_UnixDomainSocketConnection, AbstractConnection): pass
class SSLConnection(_SSLConnection, AbstractConnection): pass


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
        self.db = db
        self.client_name = client_name
        self.lib_name = lib_name
        self.lib_version = lib_version
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
            retry_on_error.append(socket.timeout)
            retry_on_error.append(asyncio.TimeoutError)
        self.retry_on_error = retry_on_error
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
            self.encoder = encoder_class(encoding, encoding_errors, decode_responses)
        self.redis_connect_func = redis_connect_func
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._socket_read_size = socket_read_size
        self.set_parser(parser_class)
        self._connect_callbacks: List[weakref.WeakMethod[ConnectCallbackT]] = []
        self._buffer_cutoff = 6000
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

class AsyncConnection(_AsyncConnection, AsyncAbstractConnection): pass
class AsyncUnixDomainSocketConnection(_AsyncUnixDomainSocketConnection, AsyncAbstractConnection): pass
class AsyncSSLConnection(_AsyncSSLConnection, AsyncAbstractConnection): pass


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

