from __future__ import annotations

"""
Main Config Class
"""

# TODO - Support v1 later
import asyncio
import socket
import contextlib

from pydantic import Field, model_validator, validator
from pydantic import ImportString, AliasChoices # Not available in v1
from lazyops.libs.proxyobj import ProxyObject
from kvdb.types.base import KVDBUrl, BaseModel, supported_schemas, kv_db_schemas, computed_field
from .base import temp_data, app_env
from .types import BaseSettings, SettingsConfigDict, PYDANTIC_VERSION
from .core import (
    KVDBRetryConfig,
    KVDBPoolConfig,
    KVDBClientConfig,
    KVDBSerializationConfig,
)
from .caching import KVDBCacheConfig
from .tasks import KVDBTaskQueueConfig
from typing import Dict, Any, Optional, Type, Literal, Union, Callable, List, Mapping, TYPE_CHECKING

if TYPE_CHECKING:
    from kvdb.utils.logs import Logger
    from kvdb.types.common import AppEnv
    from lazyops.libs.fastapi_utils.types.persistence import TemporaryData

def create_alias_choices(key: str) -> AliasChoices:
    """
    Helper Function to create alias choices
    """
    alias_env_vars = []
    if key == 'database': suffixes = ['database', 'db']
    elif key == 'url': suffixes = ['url', 'uri', 'dsn']
    else: suffixes = [key]
    for schema in supported_schemas:
        alias_env_vars.extend(
            f'{schema.upper()}_{suffix.upper()}' for suffix in suffixes
        )
    return AliasChoices(*alias_env_vars)


class KVDBSettings(BaseSettings):
    """
    KVDB Settings
    """

    # Primary Settings
    url: KVDBUrl = Field('redis://localhost:6379/0', validation_alias = create_alias_choices('url'))

    scheme: Optional[str] = Field(None, validation_alias = create_alias_choices('scheme'))
    host: Optional[str] = Field(None, validation_alias = create_alias_choices('host'))
    port: Optional[int] = Field(None, validation_alias = create_alias_choices('port'))
    username: Optional[str] = Field(None, validation_alias = create_alias_choices('username'))
    password: Optional[str] = Field(None, validation_alias = create_alias_choices('password'))
    database: Optional[int] = Field(None, validation_alias = create_alias_choices('database'))

    debug: Optional[bool] = None

    # Client Settings
    client_config: Optional[KVDBClientConfig] = Field(default_factory = KVDBClientConfig)

    # Pool Settings
    pool: Optional[KVDBPoolConfig] = Field(default_factory = KVDBPoolConfig)

    # Serialization Settings
    serialization: Optional[KVDBSerializationConfig] = Field(default_factory = KVDBSerializationConfig)

    # Retry Settings
    retry: Optional[KVDBRetryConfig] = Field(default_factory = KVDBRetryConfig)

    # Caching Settings
    cache: Optional[KVDBCacheConfig] = Field(default_factory = KVDBCacheConfig)

    # Task Queue Settings
    tasks: Optional[KVDBTaskQueueConfig] = Field(default_factory = KVDBTaskQueueConfig)

    @validator('url', pre = True)
    def validate_url(cls, v: Union[str, KVDBUrl]) -> KVDBUrl:
        """
        Validate the URL
        """
        return v if isinstance(v, KVDBUrl) else KVDBUrl(url = v)
    
    def update_connection_params(self, force: Optional[bool] = False):
        """
        Updates the connection params

        Force will update the params even if they are already set
        """
        if self.scheme is None or force: self.scheme = self.url.scheme
        if self.host is None or force: self.host = self.url.host
        if self.port is None or force: self.port = self.url.port
        if (self.username is None or force) and self.url.username is not None:
            self.username = self.url.username
        if (self.password is None or force) and self.url.password is not None:
            self.password = self.url.password
        if self.database is None or force: self.database = self.url.db_id

        # Update the Client Config
        if self.client_config.ssl is None and self.url.is_tls: self.client_config.ssl = True


    @model_validator(mode = 'after')
    def validate_settings(self):
        """
        Validate the settings
        """
        # Allow the host to override the default URL
        if self.host is not None:
            self.url = KVDBUrl.build(
                scheme = self.scheme,
                host = self.host,
                port = self.port or 6379,
                username = self.username,
                password = self.password,
                path = f"/{self.database or 0}",
            )
        
        # Update the rest of the settings
        self.update_connection_params()
        return self

    @property
    def is_enabled(self) -> bool:
        """
        Checks whether the host is valid
        """
        with contextlib.suppress(socket.gaierror):
            # Try to catch keydb in docker-compose
            socket.gethostbyname(self.host)[0]
            return True
        return False

    @computed_field
    @property
    def version(self) -> str:
        """
        Returns the version of the database
        """
        from kvdb.version import VERSION
        return VERSION
    
    @property
    def app_env(self) -> 'AppEnv':
        """
        Returns the App Env
        """
        return app_env
    
    @property
    def temp_data(self) -> 'TemporaryData':
        """
        Returns the Temp Data
        """
        return temp_data
    
    @property
    def logger(self) -> 'Logger':
        """
        Returns the logger
        """
        from kvdb.utils.logs import logger
        return logger
    
    @property
    def null_logger(self) -> 'Logger':
        """
        Returns a null logger
        """
        from kvdb.utils.logs import null_logger
        return null_logger
    
    @property
    def debug_enabled(self) -> bool:
        """
        Returns whether debug is enabled
        """
        return self.debug is True or self.is_development_env

    @property
    def autologger(self) -> 'Logger':
        """
        Returns the logger
        """
        return self.logger if self.debug_enabled else self.null_logger


    @computed_field
    @property
    def in_k8s(self) -> bool:
        """
        Returns whether the app is running in k8s
        """
        from lazyops.utils.system import is_in_kubernetes
        return is_in_kubernetes()
    
    @computed_field
    @property
    def is_local_env(self) -> bool:
        """
        Returns whether the environment is development
        """
        from kvdb.types.common import AppEnv
        return self.app_env in [AppEnv.DEVELOPMENT, AppEnv.LOCAL] and not self.in_k8s
    
    @computed_field
    @property
    def is_production_env(self) -> bool:
        """
        Returns whether the environment is production
        """
        from kvdb.types.common import AppEnv
        return self.app_env == AppEnv.PRODUCTION and self.in_k8s

    @computed_field
    @property
    def is_development_env(self) -> bool:
        """
        Returns whether the environment is development
        """
        from kvdb.types.common import AppEnv
        return self.app_env in [AppEnv.DEVELOPMENT, AppEnv.LOCAL, AppEnv.CICD]


    def configure(self, **kwargs):
        """
        Update the config for the other settings
        """
        update_url = 'url' in kwargs

        # Extract Kwargs from other configs

        ## Client Config
        if 'client_config' in kwargs: client_config = kwargs.pop('client_config')
        else:
            client_config = {
                field: kwargs.pop(field, None)
                for field in self.client_config.model_fields
                if field in kwargs
            }
        if client_config: self.client_config.update_config(**client_config)
        
        ## Pool Config
        if 'pool_config' in kwargs: pool_config = kwargs.pop('pool_config')
        else:
            pool_config = {
                field: kwargs.pop(field, None)
                for field in self.pool.model_fields
                if field in kwargs
            }
        if pool_config: self.pool.update_config(**pool_config)

        ## Serialization Config
        if 'serialization_config' in kwargs: serialization_config = kwargs.pop('serialization_config')
        else:
            serialization_config = {
                field: kwargs.pop(field, None)
                for field in self.serialization.model_fields
                if field in kwargs
            }
        if serialization_config: self.serialization.update_config(**serialization_config)


        # Retry Config
        if 'retry_config' in kwargs: retry_config = kwargs.pop('retry_config')
        else:
            retry_config = {
                field: kwargs.pop(f'retry_{field}', None)
                for field in self.retry.model_fields
                if f'retry_{field}' in kwargs
            }
        if retry_config: self.retry.update_config(**retry_config)

        # Cache Config
        if 'cache_config' in kwargs: cache_config = kwargs.pop('cache_config')
        else:
            cache_config = {
                field: kwargs.pop(f'cache_{field}', None)
                for field in self.cache.model_fields
                if f'cache_{field}' in kwargs
            }
        if cache_config: self.cache.update_config(**cache_config)

        # Task Config
        if 'task_config' in kwargs: task_config = kwargs.pop('task_config')
        else:
            task_config = {
                field: kwargs.pop(f'task_{field}', None)
                for field in self.tasks.model_fields
                if f'task_{field}' in kwargs
            }

        if task_config: self.tasks.update_config(**task_config)



        self.update_config(**kwargs)
        if update_url: self.update_connection_params(force = True)


    def is_in_async_loop(self) -> bool:
        """
        Returns whether the app is in an async loop
        """
        with contextlib.suppress(RuntimeError):
            asyncio.get_running_loop()
            return True
        return False

    model_config = SettingsConfigDict(
        env_prefix = 'KVDB_',
        case_sensitive = False,
    )

settings: 'KVDBSettings' = ProxyObject(
    obj_getter = 'kvdb.utils.lazy.get_settings',
)
