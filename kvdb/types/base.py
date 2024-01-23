from __future__ import annotations

import xxhash
from typing_extensions import Literal
from typing import Dict, Optional, Tuple
"""
Base Types
"""

# Support for v1 and v2 of pydantic
try:
    from pydantic import BaseModel as _BaseModel, ConfigDict, computed_field

    PYDANTIC_VERSION = 2

    class BaseModel(_BaseModel):
        """
        Base Model
        """

        def update_config(self, **kwargs):
            """
            Update the config for the other settings
            """
            for k, v in kwargs.items():
                if not hasattr(self, k): continue
                if isinstance(getattr(self, k), BaseModel):
                    val: 'BaseModel' = getattr(self, k)
                    if hasattr(val, 'update_config'):
                        val.update_config(**v)
                    else: val = val.__class__(**v)
                    setattr(self, k, val)
                else: setattr(self, k, v)

        @classmethod
        def extract_kwargs(
            cls, 
            _prefix: Optional[str] = None,
            _include_prefix: Optional[bool] = None,
            _include: Optional[set[str]] = None,
            _exclude: Optional[set[str]] = None,
            _exclude_none: Optional[bool] = True,
            **kwargs
        ) -> Dict[str, Any]:
            """
            Extract the kwargs that are valid for this model
            """
            if _prefix:
                _kwargs = {(k if _include_prefix else k.replace(_prefix, '')): v for k, v in kwargs.items() if k.startswith(_prefix) and k.replace(_prefix, '') in cls.model_fields}
            else:
                _kwargs = {k: v for k, v in kwargs.items() if k in cls.model_fields}
            
            if _exclude_none: _kwargs = {k: v for k, v in _kwargs.items() if v is not None}
            if _include is not None: 
                _extra_kwargs = {k: v for k, v in _kwargs.items() if k in _include}
                _kwargs.update(_extra_kwargs)
            if _exclude is not None: _kwargs = {k: v for k, v in _kwargs.items() if k not in _exclude}
            return _kwargs
        

        @classmethod
        def extract_config_and_kwargs(
            cls,
            _prefix: Optional[str] = None,
            _include_prefix: Optional[bool] = None,
            _include: Optional[set[str]] = None,
            _exclude: Optional[set[str]] = None,
            _exclude_none: Optional[bool] = True,
            **kwargs
        ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
            """
            Extract the config that are valid for this model and returns
            the config and kwargs

            Returns:
                Tuple[Dict[str, Any], Dict[str, Any]]: The config and deduplicated kwargs
            """
            config = cls.extract_kwargs(
                _prefix = _prefix,
                _include_prefix = _include_prefix,
                _include = _include,
                _exclude = _exclude,
                _exclude_none = _exclude_none,
                **kwargs
            )
            kwargs = {k: v for k, v in kwargs.items() if k not in config}
            if _prefix: kwargs = {k: v for k, v in kwargs.items() if f'{_prefix}{k}' not in config}
            return config, kwargs
        
        model_config = ConfigDict(
            extra = 'allow',
            arbitrary_types_allowed = True,
        )



except ImportError:
    from pydantic import BaseModel as _BaseModel

    PYDANTIC_VERSION = 1

    class BaseModel(_BaseModel):
        """
        [v1] Base Model
        """

        class Config:
            extra = 'allow'
            arbitrary_types_allowed = True
        
        def update_config(self, **kwargs):
            """
            Update the config for the other settings
            """
            for k, v in kwargs.items():
                if not hasattr(self, k): continue
                if isinstance(getattr(self, k), BaseModel):
                    val: 'BaseModel' = getattr(self, k)
                    if hasattr(val, 'update_config'):
                        val.update_config(**v)
                    else: val = val.__class__(**v)
                    setattr(self, k, val)
                else:  setattr(self, k, v)

        @classmethod
        def model_validate(cls: type['BaseModel'], value: Any, *args, **kwargs) -> 'BaseModel':
            """
            [v1] Support for model_validate
            """
            return cls.parse_obj(value)
        
        @classmethod
        def model_validate_json(cls: type['BaseModel'], value: Any, *args, **kwargs) -> 'BaseModel':
            """
            [v1] Support for model_validate_json
            """
            return cls.parse_raw(value)

        def model_dump(self, *, mode: str = 'python', include: set[int] | set[str] | dict[int, Any] | dict[str, Any] | None = None, exclude: set[int] | set[str] | dict[int, Any] | dict[str, Any] | None = None, by_alias: bool = False, exclude_unset: bool = False, exclude_defaults: bool = False, exclude_none: bool = False, round_trip: bool = False, warnings: bool = True) -> Dict[str, Any]:
            """
            [v1] Support for model_dump
            """
            return self.dict(
                include = include,
                exclude = exclude,
                by_alias = by_alias,
                exclude_unset = exclude_unset,
                exclude_defaults = exclude_defaults,
                exclude_none = exclude_none,

            )
        

        @classmethod
        def extract_kwargs(
            cls, 
            _prefix: Optional[str] = None,
            _include_prefix: Optional[bool] = None,
            _include: Optional[set[str]] = None,
            _exclude: Optional[set[str]] = None,
            _exclude_none: Optional[bool] = True,
            **kwargs
        ) -> Dict[str, Any]:
            """
            Extract the kwargs that are valid for this model
            """
            if _prefix:
                _kwargs = {(k if _include_prefix else k.replace(_prefix, '')): v for k, v in kwargs.items() if k.startswith(_prefix) and k.replace(_prefix, '') in cls.__fields__}
            else:
                _kwargs = {k: v for k, v in kwargs.items() if k in cls.__fields__}
            if _exclude_none: _kwargs = {k: v for k, v in _kwargs.items() if v is not None}
            if _include is not None: 
                _extra_kwargs = {k: v for k, v in _kwargs.items() if k in _include}
                _kwargs.update(_extra_kwargs)
            if _exclude is not None: _kwargs = {k: v for k, v in _kwargs.items() if k not in _exclude}
            return _kwargs
        
        @classmethod
        def extract_config_and_kwargs(
            cls,
            _prefix: Optional[str] = None,
            _include_prefix: Optional[bool] = None,
            _include: Optional[set[str]] = None,
            _exclude: Optional[set[str]] = None,
            _exclude_none: Optional[bool] = True,
            **kwargs
        ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
            """
            Extract the config that are valid for this model and returns
            the config and kwargs

            Returns:
                Tuple[Dict[str, Any], Dict[str, Any]]: The config and deduplicated kwargs
            """
            config = cls.extract_kwargs(
                _prefix = _prefix,
                _include_prefix = _include_prefix,
                _include = _include,
                _exclude = _exclude,
                _exclude_none = _exclude_none,
                **kwargs
            )
            kwargs = {k: v for k, v in kwargs.items() if k not in config}
            if _prefix: kwargs = {k: v for k, v in kwargs.items() if f'{_prefix}{k}' not in config}
            return config, kwargs

    def computed_field(*args, **kwargs):
        # Return a fake wrapper
        def wrapper(func):
            return func
        
        return wrapper


from pydantic.networks import Url
from typing import Any, Callable, Set, Annotated, Optional, Dict, Union

kv_db_schemas: Dict[str, str] = {
    "redis": "redis",
    "redis+unix": "redis",
    "redis+socket": "redis",
    "redis+tls": "redis",
    "rediss": "redis",

    "dfly": "dragonfly",
    "dfly+unix": "dragonfly",
    "dfly+socket": "dragonfly",
    "dfly+tls": "dragonfly",

    "dflys": "dragonfly",


    "dragonfly": "dragonfly",
    "dragonflys": "dragonfly",

    "keydb": "keydb",
    "keydb+unix": "keydb",
    "keydb+socket": "keydb",
    "keydb+tls": "keydb",
    "keydbs": "keydb",

    "kdb": "keydb",
    "kdbs": "keydb",

    "memc": "memcached",
    "memcs": "memcached",

    "memcached": "memcached",
    "memcacheds": "memcached",

    "tkv": "tikv",
    "tkvs": "tikv",

    "tikv": "tikv",
    "tikvs": "tikv",
}

supported_schemas = list(set(kv_db_schemas.keys()))

class KVDBUrl(Url):
    """
    Abstraction that allows for Pydantic to validate and parse KVDB URLs
    """
    _key: Optional[str] = None

    @property
    def backend(self) -> str:
        """
        Returns the backend
        """
        return kv_db_schemas.get(self.scheme, "redis")

    @property
    def db_id(self) -> int:
        """
        Returns the database ID
        """
        return 0 if self.path is None else int(self.path[1:])
    
    @property
    def auth_str(self) -> Optional[str]:
        """
        Returns the auth string
        """
        if self.username is None and self.password is None:
            return None        
        a = ""
        if self.username is not None: a += self.username
        if self.password is not None: a += f":{self.password}"
        return a

    @property
    def db_url(self) -> str:
        """
        Returns the database URL
        """
        url = f"{self.scheme}://"
        if self.auth_str is not None: url += f"{self.auth_str}@"
        url += f"{self.host}"
        if self.port is not None: url += f":{self.port}"
        if self.path is not None: url += f"{self.path}"
        return url


    @property
    def safe_url(self) -> str:
        """
        Returns the URL with the password removed
        """
        url = self.db_url
        if self.password is not None: url = url.replace(self.password, "***")
        return url

    @property
    def is_tls(self) -> bool:
        """
        Returns True if the URL is using TLS
        """
        return (self.scheme.endswith("s") and self.scheme != "redis") or self.scheme.endswith("tls")
    
    @property
    def is_unix(self) -> bool:
        """
        Returns True if the URL is using a unix socket
        """
        return self.scheme.endswith("unix") or self.scheme.endswith("socket")
    
    @property
    def value(self) -> str:
        """
        Returns the URL as a string
        """
        url = self.db_url
        if self.query is not None: url += f"?{self.query}"
        if self.fragment is not None: url += f"#{self.fragment}"
        return url
    
    @property
    def key(self) -> str:
        """
        Returns the key
        """
        if self._key is None: self.set_key()
        return self._key
    
    def set_key(self, *args, **kwargs):
        """
        Sets the key
        """
        from kvdb.utils.helpers import create_cache_key_from_kwargs
        kwargs['url'] = self.value
        self._key = create_cache_key_from_kwargs('kvdburl', args = args, kwargs = kwargs, exclude_null = True)

    def with_db_id(
        self,
        db_id: int,
    ) -> KVDBUrl:
        """
        Returns a new KVDBUrl with the specified database ID
        """
        new_path = self.path.replace(f"{self.db_id}", f"{db_id}").lstrip("/")
        return self.build(
            scheme = self.scheme,
            username = self.username,
            password = self.password,
            host = self.host,
            port = self.port,
            path = new_path,
            query = self.query,
            fragment = self.fragment,
        )

    def __repr__(self) -> str:
        """
        Returns the URL as a string
        """
        return f"'{self.db_url}'"
    
    def __str__(self) -> str:
        """
        Returns the URL as a string
        """
        return self.safe_url
    

