from __future__ import annotations

# Lazy Initialization
import os
from .helpers import lazy_import, extract_obj_init_kwargs
from typing import Dict, Any, Optional, Type, Union, Callable, List, TYPE_CHECKING
# from lazyops.libs.proxyobj import ProxyObject
from lzl.proxied import ProxyObject
if TYPE_CHECKING:
    from kvdb.configs.main import KVDBSettings
    from kvdb.types.common import AppEnv
    from lzl.io.persistence import TemporaryData
    # from lazyops.libs.fastapi_utils.types.persistence import TemporaryData
    from kvdb.components.connection import Connection

_temp_data: Optional['TemporaryData'] = None
_kvdb_settings: Optional['KVDBSettings'] = None
_valid_connection_kwarg_keys: Dict[str, List[str]] = {}


def get_settings() -> 'KVDBSettings':
    """
    Gets the settings object
    """
    global _kvdb_settings
    if _kvdb_settings is None:
        from kvdb.configs.main import KVDBSettings
        _kvdb_settings = KVDBSettings()
    return _kvdb_settings


def get_temp_data() -> 'TemporaryData':
    """
    Retrieves the temporary data
    """
    global _temp_data
    if _temp_data is None:
        from lzl.io.persistence import TemporaryData
        # from lazyops.libs.fastapi_utils.types.persistence import TemporaryData
        _temp_data = TemporaryData.from_module('kvdb')
    return _temp_data


def get_app_env() -> 'AppEnv':
    """
    Retrieves the app environment
    """
    from kvdb.types.common import AppEnv
    for key in {
        "SERVER_ENV",
        "KVDB_ENV",
        "APP_ENV",
        "ENVIRONMENT",
    }:
        if env_value := os.getenv(key):
            return AppEnv.from_env(env_value)
    
    # from lazyops.utils.system import is_in_kubernetes, get_host_name
    from lzo.utils.system import is_in_kubernetes, get_host_name
    if is_in_kubernetes():
        hn = get_host_name()
        try:
            parts = hn.split("-")
            return AppEnv.from_env(parts[2]) if len(parts) > 3 else AppEnv.PRODUCTION
        except Exception as e:
            return AppEnv.from_hostname(hn)
    return AppEnv.LOCAL

temp_data: 'TemporaryData' = ProxyObject(obj_getter = get_temp_data)
app_env: 'AppEnv' = ProxyObject(obj_getter = get_app_env)


def filter_kwargs_for_connection(conn_cls: Type['Connection'], kwargs: Dict[str, Any]) -> Dict[str, Any]:
    # sourcery skip: dict-comprehension
    """
    Filter out kwargs that aren't valid for a connection class
    """
    global _valid_connection_kwarg_keys
    if conn_cls.__name__ not in _valid_connection_kwarg_keys:
        _valid_connection_kwarg_keys[conn_cls.__name__] = extract_obj_init_kwargs(conn_cls)
    return {k: v for k, v in kwargs.items() if k in _valid_connection_kwarg_keys[conn_cls.__name__]}

