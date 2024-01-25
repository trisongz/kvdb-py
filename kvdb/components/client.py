from __future__ import annotations

"""
The KVDB Client
"""

from kvdb.configs import settings
from redis.client import Redis
from redis.asyncio.client import Redis as AsyncRedis

from kvdb.types.base import KVDBUrl
from typing import Union, Callable, Literal, Optional, Type, Any, Iterable, Mapping, overload, TYPE_CHECKING

if TYPE_CHECKING:
    from .connection_pool import (
        ConnectionPoolT,
        AsyncConnectionPoolT
    )
    from .pubsub import (
        PubSubT,
        AsyncPubSubT,
    )
    from .pipeline import (
        PipelineT,
        AsyncPipelineT,
    )
    


class KVDB(Redis):
    """
    Implementation of the Redis protocol that supports multiple protocols

    This abstract class provides a Python interface to all Redis commands
    and an implementation of the Redis protocol.

    Pipelines derive from this, implementing how
    the commands are sent and received to the Redis server. Based on
    configuration, an instance will either use a ConnectionPool, or
    Connection object to talk to keydb.

    It is not safe to pass PubSub or Pipeline objects between threads.
    """

    is_async: bool = False

    if TYPE_CHECKING:
        connection_pool: ConnectionPoolT
        response_callbacks: Mapping[str, Callable[..., Any]]
    
    @classmethod
    def from_url(
        cls, 
        url: Union[str, KVDBUrl], 
        pool_class: Optional[Type['ConnectionPoolT']] = None,
        **kwargs
    ):
        """
        Return a KVDB client object configured from the given URL

        For example::
            redis://[[username]:[password]]@localhost:6379/0
            rediss://[[username]:[password]]@localhost:6379/0
            unix://[[username]:[password]]@/path/to/socket.sock?db=0

        Seven URL schemes are supported:
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
        pool_class = settings.pool.get_pool_class(pool_class = pool_class, is_async = cls.is_async)
        connection_pool = pool_class.from_url(url, **kwargs)
        return cls(connection_pool=connection_pool)


    def pubsub(
        self, 
        retryable: Optional[bool] = False,
        **kwargs,
    ) -> 'PubSubT':
        """
        Return a Publish/Subscribe object. With this object, you can
        subscribe to channels and listen for messages that get published to
        them.
        """
        from .pubsub import (
            PubSub,
            RetryablePubSub
        )
        pubsub_class = RetryablePubSub if retryable else PubSub
        return pubsub_class(connection_pool = self.connection_pool, **kwargs)
    

    def pipeline(
        self, 
        transaction: bool = True, 
        shard_hint: Optional[str] = None,
        retryable: Optional[bool] = False,
    ) -> 'PipelineT':
        """
        Return a new pipeline object that can queue multiple commands for
        later execution. ``transaction`` indicates whether all commands
        should be executed atomically. Apart from making a group of operations
        atomic, pipelines are useful for reducing the back-and-forth overhead
        between the client and server.
        """
        from .pipeline import (
            Pipeline,
            RetryablePipeline
        )
        pipeline_class = RetryablePipeline if retryable else Pipeline
        return pipeline_class(
            connection_pool = self.connection_pool, 
            response_callbacks = self.response_callbacks, 
            transaction = transaction, 
            shard_hint = shard_hint
        )


class AsyncKVDB(AsyncRedis):
    """
    Implementation of the KVDB protocol.

    This abstract class provides a Python interface to all KVDB commands
    and an implementation of the KVDB protocol.

    Pipelines derive from this, implementing how
    the commands are sent and received to the Redis server. Based on
    configuration, an instance will either use a AsyncConnectionPool, or
    AsyncConnection object to talk to redis.
    """
    is_async: bool = True


    if TYPE_CHECKING:
        connection_pool: AsyncConnectionPoolT
        response_callbacks: Mapping[str, Callable[..., Any]]

    @classmethod
    def from_url(
        cls, 
        url: Union[str, KVDBUrl], 
        pool_class: Optional[Type['AsyncConnectionPoolT']] = None,
        single_connection_client: Optional[bool] = False,
        **kwargs
    ):
        """
        Return a KVDB client object configured from the given URL

        For example::
            redis://[[username]:[password]]@localhost:6379/0
            rediss://[[username]:[password]]@localhost:6379/0
            unix://[[username]:[password]]@/path/to/socket.sock?db=0

        Seven URL schemes are supported:
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
        pool_class = settings.pool.get_pool_class(pool_class = pool_class, is_async = cls.is_async)
        connection_pool = pool_class.from_url(url, **kwargs)
        return cls(connection_pool = connection_pool, single_connection_client = single_connection_client)
    

    def pubsub(
        self, 
        retryable: Optional[bool] = False,
        **kwargs,
    ) -> 'AsyncPubSubT':
        """
        Return a Publish/Subscribe object. With this object, you can
        subscribe to channels and listen for messages that get published to
        them.
        """
        from .pubsub import (
            AsyncPubSub,
            AsyncRetryablePubSub
        )
        pubsub_class = AsyncRetryablePubSub if retryable else AsyncPubSub
        return pubsub_class(connection_pool = self.connection_pool, **kwargs)
    

    def pipeline(
        self, 
        transaction: bool = True, 
        shard_hint: Optional[str] = None,
        retryable: Optional[bool] = False,
    ) -> 'AsyncPipelineT':
        """
        Return a new pipeline object that can queue multiple commands for
        later execution. ``transaction`` indicates whether all commands
        should be executed atomically. Apart from making a group of operations
        atomic, pipelines are useful for reducing the back-and-forth overhead
        between the client and server.
        """
        from .pipeline import (
            AsyncPipeline,
            AsyncRetryablePipeline
        )
        pipeline_class = AsyncRetryablePipeline if retryable else AsyncPipeline
        return pipeline_class(
            connection_pool = self.connection_pool, 
            response_callbacks = self.response_callbacks, 
            transaction = transaction, 
            shard_hint = shard_hint
        )


ClientT = Union[KVDB, AsyncKVDB]
