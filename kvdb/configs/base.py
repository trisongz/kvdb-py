from __future__ import annotations

"""
Base Config Class
"""

# TODO - Support v1 later

import socket
import contextlib
from kvdb.types.base import KVDBUrl, BaseModel, supported_schemas, kv_db_schemas, computed_field
from .types import BaseSettings, SettingsConfigDict, ProxySettings, PYDANTIC_VERSION

from pydantic import Field, model_validator, validator
from pydantic import ImportString, AliasChoices # Not available in v1
from typing import Dict, Any, Optional, Type, Union, Callable, List, Mapping, TYPE_CHECKING

# if PYDANTIC_VERSION == 2:
#     from pydantic import ImportString, AliasChoices


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


class KVDBPoolConfig(BaseModel):
    """
    The KVDB Pool Config
    """
    pool_class: Optional[str] = None
    apool_class: Optional[str] = None

    pool_max_connections: Optional[int] = None
    apool_max_connections: Optional[int] = None

    auto_close_connection_pool: Optional[bool] = True
    auto_close_aconnection_pool: Optional[bool] = True

    single_connection_client: Optional[bool] = False
    auto_reset_enabled: Optional[bool] = True


class KVDBClientConfig(BaseModel):
    """
    The KVDB Client Config
    """
    socket_timeout: Optional[float] = None
    socket_connect_timeout: Optional[float] = None
    socket_keepalive: Optional[bool] = None
    socket_keepalive_options: Optional[Mapping[int, Union[int, bytes]]] = None
    unix_socket_path: Optional[str] = None

    ssl: Optional[bool] = None
    ssl_keyfile: Optional[str] = None
    ssl_certfile: Optional[str] = None
    ssl_cert_reqs: str = "required"
    ssl_ca_certs: Optional[str] = None
    ssl_ca_data: Optional[str] = None
    ssl_check_hostname: bool = None


class KVDBSerializationConfig(BaseModel):
    """
    The KVDB Serialization Config
    """
    encoding: Optional[str] = 'utf-8'
    encoding_errors: Optional[str] = 'strict'
    serializer: Optional[str] = 'json'


class KVDBRetryConfig(BaseModel):
    """
    The KVDB Retry Config
    """
    on_timeout: Optional[bool] = True
    on_error: Optional[list] = None
    on_connection_error: Optional[bool] = True
    on_connection_reset_error: Optional[bool] = True
    on_response_error: Optional[bool] = True
    enabled: Optional[bool] = True

    client_enabled: Optional[bool] = True
    client_max_attempts: Optional[int] = 15
    client_max_delay: Optional[int] = 60
    # retry_client_logging_level: Optional[int] = logging.DEBUG

class KVDBCacheConfig(BaseModel):
    """
    The KVDB Cache Config
    """
    enabled: Optional[bool] = False
    ttl: Optional[int] = 60
    maxsize: Optional[int] = 1000
    typed: Optional[bool] = False
    eviction_policy: Optional[str] = 'LRU'
    cache_class: Optional[str] = None

    prefix: Optional[str] = Field('_kvc_', description = 'The prefix for the cache key')


class KVDBQueueConfig(BaseModel):
    """
    The KVDB Queue Config
    """

    prefix: Optional[str] = Field('_kvq_', description = 'The prefix for job keys')
    

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

    # Client Settings
    client_config: Optional[KVDBClientConfig] = Field(default_factory = KVDBClientConfig)

    # Pool Settings
    pool: Optional[KVDBPoolConfig] = Field(default_factory = KVDBPoolConfig)

    # Serialization Settings
    serialization: Optional[KVDBSerializationConfig] = Field(default_factory = KVDBSerializationConfig)

    # Retry Settings
    retry: Optional[KVDBRetryConfig] = Field(default_factory = KVDBRetryConfig)

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



        self.update_config(**kwargs)
        if update_url: self.update_connection_params(force = True)


    model_config = SettingsConfigDict(
        env_prefix = 'KVDB_',
        case_sensitive = False,
    )

settings: 'KVDBSettings' = ProxySettings(
    settings_getter = 'kvdb.utils.lazy.get_settings',
)
