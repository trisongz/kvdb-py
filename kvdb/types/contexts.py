from __future__ import annotations

"""
Context Components
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
from lazyops.libs.proxyobj import ProxyObject
from kvdb.types.base import BaseModel, KVDBUrl
from kvdb.types.generic import Number, KeyT, ExpiryT, AbsExpiryT, PatternT, ENOVAL
from kvdb.configs import settings
from kvdb.utils.helpers import full_name, create_cache_key_from_kwargs
from typing import Union, Callable, Literal, Optional, Type, Any,  Dict, Iterable, Mapping, overload, TYPE_CHECKING

if TYPE_CHECKING:
    from kvdb.components.connection_pool import (
        ConnectionPool,
        AsyncConnectionPool,
    )
    
    from kvdb.components.lock import Lock, AsyncLock
    from kvdb.components.pubsub import PubSub, AsyncPubSub, PubSubT, AsyncPubSubT
    from kvdb.components.client import KVDB, AsyncKVDB, ClientT
    from kvdb.components.pipeline import Pipeline, AsyncPipeline, PipelineT, AsyncPipelineT
    from kvdb.components.session import KVDBSession


class SessionPools(BaseModel):
    """
    Holds the reference for connection pools
    """
    name: str
    if TYPE_CHECKING:
        pool: ConnectionPool
        apool: AsyncConnectionPool
    
    else:
        pool: Any
        apool: Any


    def with_db_id(
        self,
        db_id: int,
    ) -> 'SessionPools':
        """
        Returns a new SessionPools instance with the given db id
        """
        return self.__class__(
            name=self.name,
            pool=self.pool.with_db_id(db_id),
            apool=self.apool.with_db_id(db_id),
        )

    async def arecreate_pools(
        self,
        inuse_connections: bool = True,
        raise_exceptions: bool = False,
        with_lock: bool = False,
        **recreate_kwargs
    ):
        """
        Resets the connection pools
        """
        self.pool = self.pool.recreate(
            inuse_connections = inuse_connections,
            raise_exceptions = raise_exceptions,
            with_lock = with_lock,
            **recreate_kwargs
        )
        self.apool = await self.apool.recreate(
            inuse_connections = inuse_connections,
            raise_exceptions = raise_exceptions,
            with_lock = with_lock,
            **recreate_kwargs
        )

    @property
    def pool_serialization_enabled(self) -> bool:
        """
        Returns True if serialization is enabled for the pool's encoder
        which requires both serialization and decode_responses to be enabled
        """
        return self.pool.encoder_serialization_enabled or \
            self.apool.encoder_serialization_enabled


class SessionState(BaseModel):
    """
    Holds the reference for session context
    """

    active: bool = False
    # We'll use this to keep track of the number of times we've tried to
    # connect to the database. This is used to determine if we should
    # attempt to reconnect to the database.
    # if the max_attempts have been reached, we'll stop trying to reconnect
    cache_max_attempts: int = 20
    cache_failed_attempts: int = 0

    if TYPE_CHECKING:

        client: Optional['KVDB'] = None
        aclient: Optional['AsyncKVDB'] = None

        lock: Optional['Lock'] = None
        alock: Optional['AsyncLock'] = None
        
        pipeline: Optional['Pipeline'] = None
        apipeline: Optional['AsyncPipeline'] = None

        locks: Dict[str, 'Lock'] = {}
        alocks: Dict[str, 'AsyncLock'] = {}

        pubsub: Optional['PubSub'] = None
        apubsub: Optional['AsyncPubSub'] = None

        pipeline: Optional['Pipeline'] = None
        apipeline: Optional['AsyncPipeline'] = None

    else:
        
        client: Optional[Any] = None
        aclient: Optional[Any] = None
        lock: Optional[Any] = None
        alock: Optional[Any] = None
        pipeline: Optional[Any] = None
        apipeline: Optional[Any] = None
        locks: Dict[str, Any] = {}
        alocks: Dict[str, Any] = {}
        pubsub: Optional[Any] = None
        apubsub: Optional[Any] = None
        pipeline: Optional[Any] = None
        apipeline: Optional[Any] = None

    dict_prefix: Optional[str] = None
    dict_method: Optional[Literal['hset', 'set']] = None
    dict_serialize: Optional[bool] = None
    dict_expiration: Optional[ExpiryT] = None


    # dict_hash_key: Optional[str] = None
    # dict_async_enabled: Optional[bool] = None
    # dict_method: Optional[str] = None


class GlobalKVDBContext(abc.ABC):
    """
    The KVDB Context for the Global KVDB Instance
    """

    ctx: Optional['KVDBSession'] = None
    sessions: Dict[str, 'KVDBSession'] = {}
    pools: Dict[str, SessionPools] = {}

    def set_ctx(
        self,
        name: Optional[str] = None,
        session: Optional['KVDBSession'] = None,
    ):
        """
        Sets the context
        """
        if not name and not session: raise ValueError('Either name or session must be provided')
        if name:
            if name not in self.sessions: raise ValueError(f'Invalid session name: {name}')
            session = self.sessions[name]
        self.ctx = session

    @property
    def current(self) -> Optional[str]:
        """
        Returns the current session
        """
        return self.ctx.name if self.ctx else None