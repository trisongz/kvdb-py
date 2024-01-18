from __future__ import annotations

"""
Base Config Types
"""

import os
import pathlib
from kvdb.types.base import BaseModel, KVDBUrl
from typing import Dict, Any, Optional, Type, Union, Callable

# Support for v1 and v2 of pydantic
try:
    from pydantic_settings import BaseSettings as _BaseSettings, SettingsConfigDict

    PYDANTIC_VERSION = 2

    class BaseSettings(_BaseSettings):
        """
        Base Settings
        """

        def update_config(self, **kwargs):
            """
            Update the config for the other settings
            """
            for k, v in kwargs.items():
                if not hasattr(self, k): continue
                if isinstance(getattr(self, k), pathlib.Path):
                    setattr(self, k, pathlib.Path(v))
                elif isinstance(getattr(self, k), KVDBUrl):
                    setattr(self, k, KVDBUrl(url = v))
                elif isinstance(getattr(self, k), (BaseSettings, BaseModel)):
                    val: Union['BaseSettings', BaseModel] = getattr(self, k)
                    if hasattr(val, 'update_config'):
                        val.update_config(**v)
                    else: val = val.__class__(**v)
                    setattr(self, k, val)
                else: setattr(self, k, v)
        

        def set_environ(self):
            """
            Update the Env variables for the current session
            """
            data: Dict[str, Any] = self.model_dump(exclude_none=True)
            for k, v in data.items():
                if isinstance(v, (dict, list, BaseModel)): continue
                if isinstance(v, BaseSettings): v.set_environ()
                else: os.environ[self.model_config.env_prefix + k.upper()] = str(v)


        model_config = SettingsConfigDict(
            env_prefix = '',
            case_sensitive = False,
        )


except ImportError:
    from pydantic import BaseSettings as _BaseSettings

    PYDANTIC_VERSION = 1

    class BaseSettings(_BaseSettings):
        """
        Base Settings
        """

        def update_config(self, **kwargs):
            """
            Update the config for the other settings
            """
            for k, v in kwargs.items():
                if not hasattr(self, k): continue
                if isinstance(getattr(self, k), pathlib.Path):
                    setattr(self, k, pathlib.Path(v))
                elif isinstance(getattr(self, k), KVDBUrl):
                    setattr(self, k, KVDBUrl(url = v))
                elif isinstance(getattr(self, k), (BaseSettings, BaseModel)):
                    val: Union['BaseSettings', BaseModel] = getattr(self, k)
                    if hasattr(val, 'update_config'):
                        val.update_config(**v)
                    else: val = val.__class__(**v)
                    setattr(self, k, val)
                else:  setattr(self, k, v)
        

        def set_environ(self):
            """
            Update the Env variables for the current session
            """
            data: Dict[str, Any] = self.dict(exclude_none=True)
            for k, v in data.items():
                if isinstance(v, (dict, list, BaseModel)): continue
                if isinstance(v, BaseSettings): v.set_environ()
                else: os.environ[self.Config.env_prefix + k.upper()] = str(v)

        class Config:
            env_prefix = ''
            case_sensitive = False


"""
Proxy Settings
"""


class ProxySettings:
    def __init__(
        self,
        settings_cls: Optional[Type[BaseSettings]] = None,
        settings_getter: Optional[Union[Callable, str]] = None,
        debug_enabled: Optional[bool] = False,
    ):
        """
        Proxy settings object
        """
        # Intentionally underscore on the end to avoid conflicts with the settings
        assert settings_cls or settings_getter, "Either settings_cls or settings_getter must be provided"
        self.__settings_cls_ = settings_cls
        self.__settings_getter_ = settings_getter
        if self.__settings_getter_ and isinstance(self.__settings_getter_, str):
            from kvdb.utils.helpers import lazy_import
            self.__settings_getter_ = lazy_import(self.__settings_getter_)
        self.__settings_ = None
        self.__debug_enabled_ = debug_enabled
        self.__last_attrs_: Dict[str, int] = {}

    @property
    def _settings_(self):
        """
        Returns the settings object
        """
        if self.__settings_ is None:
            if self.__settings_getter_:
                self.__settings_ = self.__settings_getter_()
            elif self.__settings_cls_:
                self.__settings_ = self.__settings_cls_()
        return self.__settings_

    def __getattr__(self, name):
        """
        Forward all unknown attributes to the settings object
        """
        if not self.__debug_enabled_:
            return getattr(self._settings_, name)
        
        # Try to debug the attribute
        if name not in self.__last_attrs_:
            self.__last_attrs_[name] = 0
        self.__last_attrs_[name] += 1
        if self.__last_attrs_[name] > 5:
            raise AttributeError(f"Settings object has no attribute {name}")

        if hasattr(self._settings_, name):
            self.__last_attrs_[name] = 0
            return getattr(self._settings_, name)
        raise AttributeError(f"Settings object has no attribute {name}")
