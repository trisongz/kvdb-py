from __future__ import annotations

"""
Implementation of the KVDB Session protocol.
"""

import abc
import sys
import time
import anyio
import typing
import logging
import asyncio
import functools
import contextlib

from pydantic.types import ByteSize
from lazyops.libs.pooler import ThreadPooler
from redis.compat import Literal
from kvdb.types.base import BaseModel, KVDBUrl
from kvdb.types.generic import Number, KeyT, ExpiryT, AbsExpiryT, PatternT, ENOVAL
from kvdb.types.contexts import SessionPools, SessionState

from kvdb.configs import settings
from kvdb.configs.base import SerializerConfig
from kvdb.utils.retry import get_retry, create_retryable_client
from kvdb.utils.helpers import full_name, create_cache_key_from_kwargs

from .connection import (
    ConnectionPool,
    AsyncConnectionPool,
)
from .lock import Lock, AsyncLock
from .pubsub import PubSub, AsyncPubSub, PubSubT, AsyncPubSubT
from .client import KVDB, AsyncKVDB, ClientT
from .pipeline import Pipeline, AsyncPipeline, PipelineT, AsyncPipelineT

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
)


if sys.version_info >= (3, 11, 3):
    from asyncio import timeout as async_timeout
else:
    from async_timeout import timeout as async_timeout

if TYPE_CHECKING:
    from kvdb.io.encoder import Encoder
    from kvdb.io.serializers import SerializerT

ResponseT = TypeVar('ResponseT')

class KVDBSession(abc.ABC):
    """
    The KVDB Session protocol
    """

    def __init__(
        self,
        name: str,
        url: Union[str, KVDBUrl],
        *,
        pools: SessionPools,
        db_id: Optional[int] = None,
        serializer: Optional[Union['SerializerT', str]] = None,
        encoder: Optional['Encoder'] = None,
        **kwargs: Any,
    ) -> None:
        """
        Initializes the KVDB Session
        """
        if isinstance(url, str): url = KVDBUrl(url)
        self.name = name
        self.url = url
        self.pools = pools
        if db_id is not None and db_id != self.url.db_id:
            self.url = self.url.with_db_id(db_id)
        self.init_serializer(serializer, **kwargs)
        self.init_encoder(encoder, **kwargs)
        self.init_cache_config(**kwargs)
        self.init_state(**kwargs)
        self.settings = settings
        self._kwargs = kwargs


    """
    Initialization
    """

    def init_serializer(
        self, 
        serializer: Optional[Union['SerializerT', str]] = None, 
        **kwargs: Any
    ) -> None:
        """
        Initializes the serializer
        """
        if serializer is None or isinstance(serializer, str):
            _serializer_kwargs = SerializerConfig.extract_kwargs(
                _include = ('raise_errors'), 
                **kwargs
            )
            serializer = settings.client_config.get_serializer(
                serializer = serializer,
                **_serializer_kwargs,
            )
        self.serializer = serializer

    def init_encoder(
        self, 
        encoder: Optional['Encoder'] = None, 
        **kwargs: Any
    ) -> None:
        """
        Initializes the encoder
        """
        if encoder is None:
            from kvdb.io.encoder import Encoder
            serializer_disabled = kwargs.get(
                'serializer_disabled', self.serializer is None
            )
            encoder = Encoder(
                encoding = kwargs.get('encoding', 'utf-8'),
                encoding_errors = kwargs.get('encoding_errors', 'strict'),
                decode_responses = kwargs.get('decode_responses'),
                serializer = None if serializer_disabled else self.serializer,
            )
        self.encoder = encoder

    def init_cache_config(self, **kwargs: Any) -> None:
        """
        Initializes the cache config
        """
        _cache_config = settings.cache.extract_kwargs(_prefix = 'cache_', _exclude_none = True, **kwargs)
        self.cache_config = settings.cache.model_copy(update = _cache_config, deep = True)

    def init_state(self, **kwargs: Any) -> None:
        """
        Initializes the session state
        """
        self.state = SessionState(
            cache_max_attempts = self.cache_config.max_attempts,
            dict_method = kwargs.get('dict_method', 'hset'),
            dict_prefix = kwargs.get('dict_prefix', f'{self.name}.dict'),
            dict_serialize = kwargs.get('dict_serialize', True),
            dict_expiration = kwargs.get('dict_expiration'),
        )


    @classmethod
    def _get_client_class(
        cls, 
        retry_client_enabled: Optional[bool] = None,
        retry_client_max_attempts: Optional[int] = None,
        retry_client_max_delay: Optional[int] = None,
        retry_client_logging_level: Optional[Union[int, str]] = None,
        is_async: Optional[bool] = False,
        **kwargs
    ) -> Type['ClientT']:
        """
        Returns the client class
        """
        base_class = AsyncKVDB if is_async else KVDB
        if retry_client_enabled is None: retry_client_enabled = settings.retry.client_enabled
        if not retry_client_enabled: return base_class
        if retry_client_max_attempts is None: retry_client_max_attempts = settings.retry.client_max_attempts
        if retry_client_max_delay is None: retry_client_max_delay = settings.retry.client_max_delay
        if retry_client_logging_level is None: retry_client_logging_level = settings.retry.client_logging_level
        return create_retryable_client(
            base_class,
            max_attempts = retry_client_max_attempts,
            max_delay = retry_client_max_delay,
            logging_level = retry_client_logging_level,
            **kwargs
        )
    

    """
    Properties
    """
    @property
    def client(self) -> KVDB:
        """
        [Sync] The KVDB client
        """
        if self.state.client is None:
            self.state.client = self._get_client_class(**self._kwargs)(connection_pool=self.pools.pool)
        return self.state.client

    @property
    def aclient(self) -> AsyncKVDB:
        """
        [Async] The KVDB client
        """
        if self.state.aclient is None:
            self.state.aclient = self._get_client_class(is_async = True, **self._kwargs)(connection_pool=self.pools.apool)
        return self.state.aclient

    def execute_command(self, *args: Any, **options: Any) -> Any:
        """
        Execute a command and return a parsed response
        """
        return self.client.execute_command(*args, **options)
    
    async def aexecute_command(self, *args: Any, **options: Any) -> Any:
        """
        Execute a command and return a parsed response
        """
        return await self.aclient.execute_command(*args, **options)

    """
    Component Methods
    """

    def pubsub(
        self, 
        retryable: Optional[bool] = None,
        **kwargs
    ) -> PubSubT:
        """
        Return a Publish/Subscribe object. With this object, you can
        subscribe to channels and listen for messages that get published to
        """
        if retryable is None: retryable = self.settings.retry.pubsub_enabled
        return self.client.pubsub(retryable = retryable, **kwargs)

    def apubsub(
        self, 
        retryable: Optional[bool] = None,
        **kwargs
    ) -> AsyncPubSubT:
        """
        Return a Publish/Subscribe object. With this object, you can
        subscribe to channels and listen for messages that get published to
        """
        if retryable is None: retryable = self.settings.retry.pubsub_enabled
        return self.aclient.pubsub(retryable = retryable, **kwargs)
    
    """
    PubSub Utility Methods
    """
    
    def pipeline(
        self, 
        transaction: Optional[bool] = True, 
        shard_hint: Optional[str] = None, 
        retryable: Optional[bool] = None,
        **kwargs
    ) -> PipelineT:
        """
        Return a new pipeline object that can queue multiple commands for
        later execution. ``transaction`` indicates whether all commands
        should be executed atomically. Apart from making a group of operations
        atomic, pipelines are useful for reducing the back-and-forth overhead
        between the client and server.
        """
        if retryable is None: retryable = self.settings.retry.pipeline_enabled
        return self.client.pipeline(transaction = transaction, shard_hint = shard_hint, retryable = retryable)

    def apipeline(
        self, 
        transaction: Optional[bool] = True, 
        shard_hint: Optional[str] = None, 
        retryable: Optional[bool] = None,
        **kwargs
    ) -> AsyncPipelineT:
        """
        Return a new pipeline object that can queue multiple commands for
        later execution. ``transaction`` indicates whether all commands
        should be executed atomically. Apart from making a group of operations
        atomic, pipelines are useful for reducing the back-and-forth overhead
        between the client and server.
        """
        if retryable is None: retryable = self.settings.retry.pipeline_enabled
        return self.aclient.pipeline(transaction = transaction, shard_hint = shard_hint, retryable = retryable)

    def lock(
        self, 
        name: str, 
        timeout: Optional[Number] = None,
        sleep: Optional[Number] = 0.1,
        blocking: Optional[bool] = True,
        blocking_timeout: Optional[Number] = None,
        thread_local: Optional[bool] = True,
        **kwargs,
    ) -> Lock:
        """
        Create a new Lock instance named ``name`` using the Redis client
        supplied by ``keydb``.

        ``timeout`` indicates a maximum life for the lock in seconds.
        By default, it will remain locked until release() is called.
        ``timeout`` can be specified as a float or integer, both representing
        the number of seconds to wait.

        ``sleep`` indicates the amount of time to sleep in seconds per loop
        iteration when the lock is in blocking mode and another client is
        currently holding the lock.

        ``blocking`` indicates whether calling ``acquire`` should block until
        the lock has been acquired or to fail immediately, causing ``acquire``
        to return False and the lock not being acquired. Defaults to True.
        Note this value can be overridden by passing a ``blocking``
        argument to ``acquire``.

        ``blocking_timeout`` indicates the maximum amount of time in seconds to
        spend trying to acquire the lock. A value of ``None`` indicates
        continue trying forever. ``blocking_timeout`` can be specified as a
        float or integer, both representing the number of seconds to wait.

        ``thread_local`` indicates whether the lock token is placed in
        thread-local storage. By default, the token is placed in thread local
        storage so that a thread only sees its token, not a token set by
        another thread. 
        """
        if name not in self.state.locks:
            self.state.locks[name] = Lock(
                self.client, 
                name = name, 
                timeout = timeout, 
                sleep = sleep, 
                blocking = blocking, 
                blocking_timeout = blocking_timeout, 
                thread_local = thread_local
            )
        if self.state.lock is None: self.state.lock = self.state.locks[name]
        return self.state.locks[name]
    
    def alock(
        self, 
        name: str, 
        timeout: Optional[Number] = None,
        sleep: Number = 0.1,
        blocking: bool = True,
        blocking_timeout: Optional[Number] = None,
        thread_local: bool = True,
        **kwargs,
    ) -> AsyncLock:
        """
        Create a new Lock instance named ``name`` using the Redis client
        supplied by ``keydb``.

        ``timeout`` indicates a maximum life for the lock in seconds.
        By default, it will remain locked until release() is called.
        ``timeout`` can be specified as a float or integer, both representing
        the number of seconds to wait.

        ``sleep`` indicates the amount of time to sleep in seconds per loop
        iteration when the lock is in blocking mode and another client is
        currently holding the lock.

        ``blocking`` indicates whether calling ``acquire`` should block until
        the lock has been acquired or to fail immediately, causing ``acquire``
        to return False and the lock not being acquired. Defaults to True.
        Note this value can be overridden by passing a ``blocking``
        argument to ``acquire``.

        ``blocking_timeout`` indicates the maximum amount of time in seconds to
        spend trying to acquire the lock. A value of ``None`` indicates
        continue trying forever. ``blocking_timeout`` can be specified as a
        float or integer, both representing the number of seconds to wait.

        ``thread_local`` indicates whether the lock token is placed in
        thread-local storage. By default, the token is placed in thread local
        storage so that a thread only sees its token, not a token set by
        another thread. 
        """
        if name not in self.state.alocks:
            self.state.alocks[name] = AsyncLock(
                self.aclient, 
                name = name, 
                timeout = timeout, 
                sleep = sleep, 
                blocking = blocking, 
                blocking_timeout = blocking_timeout, 
                thread_local = thread_local
            )
        if self.state.alock is None: self.state.alock = self.state.alocks[name]
        return self.state.alocks[name]
    
    """
    Lock Utility Methods
    """

    def close_locks(
        self, 
        names: Optional[Union[List[str], str]] = None,
        force: Optional[bool] = False,
        raise_errors: Optional[bool] = False,
    ):
        """
        Closes the locks that are currently managed by the session
        """
        if names is None: names = list(self.state.locks.keys())
        if isinstance(names, str): names = [names]
        for name in names:
            if name in self.state.locks:
                self.state.locks[name].release(force = force, raise_errors = raise_errors)
                del self.state.locks[name]
    
    async def aclose_locks(
        self, 
        names: Optional[Union[List[str], str]] = None,
        force: Optional[bool] = False,
        raise_errors: Optional[bool] = False,
    ):
        """
        Closes the locks that are currently managed by the session
        """
        if names is None: names = list(self.state.alocks.keys())
        if isinstance(names, str): names = [names]
        for name in names:
            if name in self.state.alocks:
                await self.state.alocks[name].release(force = force, raise_errors = raise_errors)
                del self.state.alocks[name]
    
    
    """
    Dict-Like Interface
    """

    def get_dictkey(self, key: KeyT) -> str:
        """
        Returns the dict key
        """
        if self.state.dict_method == 'hset': return key
        return f'{self.state.dict_prefix}:{key}' if self.state.dict_prefix is not None and self.state.dict_prefix not in key else key

    def getitem(
        self,
        key: KeyT,
        default: Optional[Any] = None,
    ) -> ResponseT:
        """
        [Dict] Returns the value for the given key
        """
        if self.state.dict_method == 'hset': value = self.client.hget(self.state.dict_prefix, key)
        else: value = self.client.get(self.get_dictkey(key))
        return default if value is None else \
            self.encoder.decode(value) if self.state.dict_serialize else value
    
    async def agetitem(
        self,
        key: KeyT,
        default: Optional[Any] = None,
    ) -> ResponseT:
        """
        [Dict] Returns the value for the given key
        """
        if self.state.dict_method == 'hset': value = await self.aclient.hget(self.state.dict_prefix, key)
        else: value = await self.aclient.get(self.get_dictkey(key))
        return default if value is None else \
            await self.encoder.adecode(value) if self.state.dict_serialize else value
    
    
    def setitem(
        self,
        key: KeyT,
        value: Any,
        ex: Optional[ExpiryT] = None,
        **kwargs: Any,
    ) -> None:
        """
        [Dict] Sets the value for the given key
        """
        value = self.encoder.encode(value) if self.state.dict_serialize else value
        ex = self.state.dict_expiration if ex is None else ex
        if self.state.dict_method == 'hset':
            self.client.hset(self.state.dict_prefix, key, value)
            if ex is not None: self.client.expire(self.state.dict_prefix, ex, **kwargs)
        else: self.client.set(self.get_dictkey(key), value, ex, **kwargs)

    async def asetitem(
        self,
        key: KeyT,
        value: Any,
        ex: Optional[ExpiryT] = None,
        **kwargs: Any,
    ) -> None:
        """
        [Dict] Sets the value for the given key
        """
        value = await self.encoder.aencode(value) if self.state.dict_serialize else value
        ex = self.state.dict_expiration if ex is None else ex
        if self.state.dict_method == 'hset':
            await self.aclient.hset(self.state.dict_prefix, key, value)
            if ex is not None: await self.aclient.expire(self.state.dict_prefix, ex, **kwargs)
        else:
            await self.aclient.set(self.get_dictkey(key), value, ex, **kwargs)

    def delitem(
        self,
        key: KeyT,
    ) -> None:
        """
        [Dict] Deletes the key
        """
        if self.state.dict_method == 'hset': self.client.hdel(self.state.dict_prefix, key)
        else: self.client.delete(self.get_dictkey(key))
    
    async def adelitem(
        self,
        key: KeyT,
    ) -> None:
        """
        [Dict] Deletes the key
        """
        if self.state.dict_method == 'hset': await self.aclient.hdel(self.state.dict_prefix, key)
        else: await self.aclient.delete(self.get_dictkey(key))



    """
    Class Object Methods
    """

    def close(self, close_pool: bool = False, force: Optional[bool] = None, raise_errors: bool = False):
        """
        Close the session
        """
        self.close_locks(force=force, raise_errors=raise_errors)
        if self.state.pubsub is not None:
            self.state.pubsub.close()
            self.state.pubsub = None
        
        if self.state.client is not None:
            self.state.client.close()
            if close_pool:
                self.state.client.connection_pool.disconnect(raise_errors = raise_errors)
            self.state.client = None

    async def aclose(self, close_pool: bool = False, force: Optional[bool] = None, raise_errors: bool = False):
        """
        Close the session
        """
        await self.aclose_locks(force=force, raise_errors=raise_errors)
        if self.state.apubsub is not None:
            await self.state.apubsub.close()
            self.state.apubsub = None
        
        if self.state.aclient is not None:
            await self.state.aclient.close()
            if close_pool: await self.state.aclient.connection_pool.disconnect(raise_errors = raise_errors)
            self.state.aclient = None
        
        if self.state.client is not None:
            self.state.client.close()
            if close_pool: self.state.client.connection_pool.disconnect(raise_errors = raise_errors)
            self.state.client = None


    def __enter__(self):
        """
        Enter the runtime context related to this object.
        """
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        On exit, close the session
        """
        self.close()
    

    async def __aenter__(self):
        """
        Enter the runtime context related to this object.
        """
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Close the session
        """
        await self.aclose()

    def __setitem__(self, key: KeyT, value: Any) -> None:
        """
        [Dict] Sets the value for the given key
        """
        if settings.is_in_async_loop():
            return ThreadPooler.create_background_task(
                self.asetitem, key, value,
            )
        return self.setitem(key, value)


    def __getitem__(self, key: KeyT) -> ResponseT:
        """
        [Dict] Returns the value for the given key
        """
        return self.getitem(key)


    def __delitem__(self, key: KeyT) -> None:
        """
        [Dict] Deletes the key
        """
        if settings.is_in_async_loop():
            return ThreadPooler.create_background_task(self.adelitem, key)
        return self.delitem(key)
    
    def __contains__(self, key: KeyT) -> bool:
        """
        [Dict] Returns whether the key exists
        """
        if self.state.dict_method == 'hset':
            return self.client.hexists(self.state.dict_prefix, key)
        return self.client.exists(self.get_dictkey(key))
    
    """
    Class Wrap Methods
    """

    def _client_function(self, *args, _function: Optional[str] = None, **kwargs) -> ResponseT:
        """
        [Sync] Wraps the client function
        """
        return getattr(self.client, _function)(*args, **kwargs)
    
    def _aclient_function(self, *args, _function: Optional[str] = None, **kwargs) -> Awaitable[ResponseT]:
        """
        [Async] Wraps the client function
        """
        return getattr(self.aclient, _function)(*args, **kwargs)


    @classmethod
    def initialize_class_functions(cls):
        """
        Initializes the class methods
        and sets them based on both the async and sync methods
        """
        import inspect
        from makefun import create_function
        from redis.commands import (
            CoreCommands,
            # RedisModuleCommands,
            SentinelCommands,

            AsyncCoreCommands, 
            # AsyncRedisModuleCommands,
            AsyncSentinelCommands,
        )

        existing_methods = set(dir(cls))
        added_methods = set()

        # Sync Methods
        for sync_module in {
            CoreCommands,
            # RedisModuleCommands,
            SentinelCommands,
        }:

            for name in dir(sync_module):
                if name.startswith('_'): continue
                if name in existing_methods: continue
                # if name in skip_methods: continue
                existing_func = getattr(sync_module, name)
                existing_sig = inspect.signature(existing_func)
                new_func = create_function(
                    existing_sig,
                    functools.partial(cls._client_function, _function = name),
                    func_name = name,
                    module_name = cls.__module__,
                )
                setattr(cls, name, new_func)
                existing_methods.add(name)
                added_methods.add(name)

        # Async Methods
        for amodule in {
            AsyncCoreCommands,
            # AsyncRedisModuleCommands,
            AsyncSentinelCommands,
        }:
            # Core Commands
            for name in dir(amodule):
                if name.startswith('_'): continue
                aname = f'a{name}'
                # if aname == 'async': aname = 'asyncronize'
                if aname in {
                    'async', 'await'
                }:
                    aname = f'{aname}_'
                if aname in existing_methods: continue
                # if name in skip_methods: continue
                existing_func = getattr(amodule, name)
                existing_sig = inspect.signature(existing_func)
                try:
                    new_func = create_function(
                        existing_sig,
                        functools.partial(cls._aclient_function, _function = name),
                        func_name = aname,
                        module_name = cls.__module__,
                    )
                    setattr(cls, aname, new_func)
                    existing_methods.add(aname)
                    added_methods.add(aname)
                except Exception as e:
                    print(f"Error adding method: {name} -> {aname}")
                    raise e

        # print('Added Methods: ', added_methods)


KVDBSession.initialize_class_functions()