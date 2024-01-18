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

