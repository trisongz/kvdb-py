from __future__ import annotations

"""
The Main KVDB Client that Manages the Various KVDB Components
"""


import abc
import sys
import functools

from lazyops.libs.pooler import ThreadPooler
from lazyops.libs.proxyobj import ProxyObject
from kvdb.types.base import BaseModel, KVDBUrl
from kvdb.types.contexts import SessionPools, SessionState, GlobalKVDBContext
from kvdb.components.client import KVDB, AsyncKVDB, ClientT
from kvdb.components.session import KVDBSession
from kvdb.configs import settings
from kvdb.configs.base import SerializerConfig


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


ResponseT = TypeVar('ResponseT')

class KVDBSessionManager(abc.ABC):
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
        self.c = GlobalKVDBContext()
        self.pools = self.c.pools
        self.sessions = self.c.sessions
        self.settings = settings
        self.logger = self.settings.logger
        self.autologger = self.settings.autologger
        self.settings.configure(**kwargs)
    

    def configure(
        self,
        overwrite: Optional[bool] = None,
        **kwargs,
    ):
        """
        Configures the global settings
        """
        self.settings.configure(**kwargs)

    def get_pool(
        self,
        name: str,
        url: Optional[Union[str, KVDBUrl]] = None,
        serializer_config: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> SessionPools:
        """
        Configures the session pools
        """
        if url is None: url = self.settings.url
        if isinstance(url, str): url = KVDBUrl(url)
        url.set_key(name)
        if url.key in self.pools: 
            self.autologger.info(f'Using existing pool with name {name} and url {url}: {url.key}')
            return self.pools[url.key]

        # Get the serializer config
        serializer_config = SerializerConfig.extract_kwargs(_exclude_none = True, **kwargs) \
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

        pool = SessionPools(
            name = name,
            pool = pool_class.from_url(
                url,
                max_connections = pool_max_connections,
                **pool_config,
            ),
            apool = apool_class.from_url(
                url,
                max_connections = apool_max_connections,
                **pool_config,
            ),
        )
        self.pools[url.key] = pool
        return pool

    """
    Session Management
    """

    def create_session(
        self,
        name: Optional[str] = 'default',
        url: Optional[Union[str, KVDBUrl]] = None,
        db_id: Optional[int] = None,
        **kwargs,
    ) -> KVDBSession:
        """
        Returns a new KVDB Session

        - Does not perform validation with the current contexts
        """

        if url is None: url = self.settings.url
        if isinstance(url, str): url = KVDBUrl(url)
        if db_id is not None and url.db_id != db_id: url = url.with_db_id(db_id)

        # Get the serializer config
        serializer_config = SerializerConfig.extract_kwargs(_exclude_none = True, **kwargs)
        kwargs = {k : v for k, v in kwargs.items() if k not in serializer_config}

        # Get the Client Config
        client_config = self.settings.client_config.model_dump(exclude_none = True)
        client_kwargs = self.settings.client_config.extract_kwargs(_exclude_none = True, **kwargs)
        if client_kwargs: client_config.update(client_kwargs)
        kwargs = {k : v for k, v in kwargs.items() if k not in client_config}

        # Get the pool
        pool = self.get_pool(name, url, serializer_config = serializer_config, **kwargs)
        if serializer_config: client_config.update(serializer_config)
        # self.autologger.info(f'Creating new KVDB Session with name {name} and url {url}, with client config {client_config} and kwargs {kwargs}')
        return KVDBSession(
            name = name,
            url = url,
            pool = pool,
            **client_config,
            **kwargs,
        )

    def session(
        self,
        name: Optional[str] = 'default',
        url: Optional[Union[str, KVDBUrl]] = None,
        db_id: Optional[int] = None,
        set_as_ctx: Optional[bool] = None,
        overwrite: Optional[bool] = None,
        **kwargs,
    ) -> KVDBSession:
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
    

    def init_session(
        self,
        name: Optional[str] = 'default',
        url: Optional[Union[str, KVDBUrl]] = None,
        db_id: Optional[int] = None,
        set_as_ctx: Optional[bool] = None,
        overwrite: Optional[bool] = None,
        **kwargs,
    ) -> KVDBSession:
        """
        Initializes a KVDB Session that is managed by the KVDB Session Manager

        - Raises an error if the session already exists
        """
        if name in self.sessions and overwrite is not True:
            raise ValueError(f'The session with name {name} already exists. Use overwrite = True to overwrite the session')
        return self.session(name = name, url = url, db_id = db_id, set_as_ctx = set_as_ctx, overwrite = overwrite, **kwargs)
    
    def get_session(
        self,
        name: Optional[str] = None,
        **kwargs,
    ) -> KVDBSession:
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
        session: KVDBSession,
        overwrite: Optional[bool] = None,
        set_as_ctx: Optional[bool] = None,
        **kwargs,
    ):
        """
        Adds a KVDB Session to the KVDB Session Manager
        """
        if not isinstance(session, KVDBSession): raise ValueError(f'Invalid session type: {type(session)}')
        if session.name in self.sessions and overwrite is not True:
            raise ValueError(f'The session with name {session.name} already exists. Use overwrite = True to overwrite the session')
        if set_as_ctx is None: set_as_ctx = not len(self.sessions)
        self.sessions[session.name] = session
        if set_as_ctx is True: self.c.set_ctx(name = session.name)

    """
    Properties
    """

    @property
    def ctx(self) -> KVDBSession:
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
        return self.c.current
    
    @property
    def kvdb(self) -> KVDB:
        """
        Returns the current session
        """
        return self.ctx.client
    
    @property
    def akvdb(self) -> AsyncKVDB:
        """
        Returns the current session
        """
        return self.ctx.aclient
    


        
        


KVDBClient: KVDBSessionManager = ProxyObject(obj_cls = KVDBSessionManager)