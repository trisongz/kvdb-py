from __future__ import annotations

"""
This module controls the default configurations for certain parameters and provides
the ability to override them.

:TODO - Add Compression Configs
"""

from typing import Optional, Dict, Literal

KindOptions = Literal['session', 'task', 'cache', 'persistence']

DEFAULT_SERIALIZER = "json"
DEFAULT_SERIALIZERS: Dict[str, Optional[str]] = {
    "session": DEFAULT_SERIALIZER,
    "task": "pickle",
    "cache": DEFAULT_SERIALIZER,
    "persistence": DEFAULT_SERIALIZER,
}

DEFAULT_SERIALIZER_ENABLED = False
DEFAULT_SERIALIZERS_ENABLED: Dict[str, bool] = {
    "session": False,
    "task": True,
    "cache": True,
    "persistence": True,
}

DEFAULT_DB_IDS: Dict[str, Optional[int]] = {
    "session": None,
    "task": 3,
    "cache": None,
    "persistence": None,
}

DEFAULT_KVDB_URL = "redis://localhost:6379/0"

DEFAULT_PREFIXES: Dict[str, str] = {
    "cache": "_kvc_",
    "task": "_kvq_",
}

"""
These Affect `kvdb.io.serializers`
"""

def get_default_serializer() -> str:
    """
    Returns the default serializer
    """
    return DEFAULT_SERIALIZER

def set_default_serializer(
    serializer: str,
    propogate: Optional[bool] = False,
) -> None:
    """
    Sets the default serializer

    :param serializer: The serializer to use
    :param propogate: Whether to propogate the change to all serializers
    """
    global DEFAULT_SERIALIZER, DEFAULT_SERIALIZERS
    DEFAULT_SERIALIZER = serializer
    if propogate:
        for kind in DEFAULT_SERIALIZERS:
            DEFAULT_SERIALIZERS[kind] = serializer


"""
These Affect `kvdb.configs.base.SerializerConfig`
"""

def enable_default_serializer() -> None:
    """
    Enables the default serializer
    """
    global DEFAULT_SERIALIZER_ENABLED
    DEFAULT_SERIALIZER_ENABLED = True

def disable_default_serializer() -> None:
    """
    Disables the default serializer
    """
    global DEFAULT_SERIALIZER_ENABLED
    DEFAULT_SERIALIZER_ENABLED = False

def get_default_serializer_for_config() -> Optional[str]:
    """
    Returns the default serializer for the config

    - If the default serializer is enabled, then it returns the default serializer
    - Else, it returns None
    """
    return DEFAULT_SERIALIZER if DEFAULT_SERIALIZER_ENABLED else None

"""
These affect subclasses that inherit from `kvdb.configs.base.SerializerConfig`
"""

def set_default_serializer_for(
    serializer: str,
    *kinds: KindOptions,
    # kind: KindOptions = 'session'
):
    """
    Sets the default serializer for the given kind
    """
    global DEFAULT_SERIALIZERS
    for kind in kinds:
        DEFAULT_SERIALIZERS[kind] = serializer

def get_default_serializer_for(
    kind: KindOptions = 'session'
) -> str:
    """
    Returns the default serializer for the given kind
    """
    return DEFAULT_SERIALIZERS[kind] if DEFAULT_SERIALIZERS_ENABLED[kind] else None

def enable_default_serializer_for(
    *kinds: KindOptions,
    # kind: KindOptions = 'session'
) -> None:
    """
    Enables the default serializer for the given kind
    """
    global DEFAULT_SERIALIZERS_ENABLED
    for kind in kinds:
        DEFAULT_SERIALIZERS_ENABLED[kind] = True

def disable_default_serializer_for(
    kind: KindOptions = 'session'
) -> None:
    """
    Disables the default serializer for the given kind
    """
    global DEFAULT_SERIALIZERS_ENABLED
    DEFAULT_SERIALIZERS_ENABLED[kind] = False

def get_default_db_id_for(
    kind: KindOptions = 'session'
) -> Optional[int]:
    """
    Returns the default db id for the given kind
    """
    return DEFAULT_DB_IDS[kind]

def set_default_db_id_for(
    db_id: int,
    kind: KindOptions = 'session'
) -> None:
    """
    Sets the default db id for the given kind
    """
    global DEFAULT_DB_IDS
    DEFAULT_DB_IDS[kind] = db_id

def get_default_prefix_for(
    kind: KindOptions = 'cache'
) -> str:
    """
    Returns the default prefix for the given kind
    """
    return DEFAULT_PREFIXES[kind]

def set_default_prefix_for(
    prefix: str,
    kind: KindOptions = 'cache'
) -> None:
    """
    Sets the default prefix for the given kind
    """
    global DEFAULT_PREFIXES
    DEFAULT_PREFIXES[kind] = prefix


"""
These Affect `kvdb.configs.base.TaskQueueConfig`
"""

def enable_default_task_serializer() -> None:
    """
    Enables the default task serializer
    """
    enable_default_serializer_for('task')

def disable_default_task_serializer() -> None:
    """
    Disables the default task serializer
    """
    disable_default_serializer_for('task')

def set_default_task_serializer(serializer: str) -> None:
    """
    Sets the default task serializer
    """
    set_default_serializer_for(serializer, 'task')

def get_default_task_serializer() -> Optional[str]:
    """
    Returns the default task serializer for the config

    - If the default task serializer is enabled, then it returns the default task serializer
    - Else, it returns None
    """
    return get_default_serializer_for('task')

def set_default_task_db_id(db_id: int) -> None:
    """
    Sets the default task db id
    """
    set_default_db_id_for(db_id, 'task')


def get_default_task_db_id() -> int:
    """
    Returns the default task db id
    """
    return get_default_db_id_for('task')

def set_default_task_prefix(prefix: str) -> None:
    """
    Sets the default task prefix
    """
    set_default_prefix_for(prefix, 'task')

def get_default_task_prefix() -> str:
    """
    Returns the default task prefix
    """
    return get_default_prefix_for('task')



"""
These Affect `kvdb.configs.caching.KVDBCachifyConfig`
"""

def enable_default_cache_serializer() -> None:
    """
    Enables the default cache serializer
    """
    enable_default_serializer_for('cache')

def disable_default_cache_serializer() -> None:
    """
    Disables the default cache serializer
    """
    disable_default_serializer_for('cache')

def set_default_cache_serializer(serializer: str) -> None:
    """
    Sets the default cache serializer
    """
    set_default_serializer_for(serializer, 'cache')

def get_default_cache_serializer() -> Optional[str]:
    """
    Returns the default cache serializer for the config

    - If the default cache serializer is enabled, then it returns the default cache serializer
    - Else, it returns None
    """
    return get_default_serializer_for('cache')

def set_default_cache_db_id(db_id: int) -> None:
    """
    Sets the default cache db id
    """
    set_default_db_id_for(db_id, 'cache')

def get_default_cache_db_id() -> int:
    """
    Returns the default cache db id
    """
    return get_default_db_id_for('cache')

def set_default_cache_prefix(prefix: str) -> None:
    """
    Sets the default cache prefix
    """
    set_default_prefix_for(prefix, 'cache')

def get_default_cache_prefix() -> str:
    """
    Returns the default cache prefix
    """
    return get_default_prefix_for('cache')

"""
These Affect `kvdb.configs.main.KVDBSettings`
"""

def set_default_kvdb_url(url: str) -> None:
    """
    Sets the default kvdb url
    """
    global DEFAULT_KVDB_URL
    DEFAULT_KVDB_URL = url

def get_default_kvdb_url() -> str:
    """
    Returns the default kvdb url
    """
    return DEFAULT_KVDB_URL

def set_default_session_db_id(db_id: int) -> None:
    """
    Sets the default session db id
    """
    set_default_db_id_for(db_id, 'session')

def get_default_session_db_id() -> int:
    """
    Returns the default session db id
    """
    return get_default_db_id_for('session')

"""
These Affect `kvdb.configs.core.KVDBSerializationConfig`
"""

def set_default_session_serializer(serializer: str) -> None:
    """
    Sets the default session serializer
    """
    set_default_serializer_for(serializer, 'session')

def get_default_session_serializer() -> str:
    """
    Returns the default session serializer
    """
    return get_default_serializer_for('session')

def enable_default_session_serializer() -> None:
    """
    Enables the default session serializer
    """
    enable_default_serializer_for('session')

def disable_default_session_serializer() -> None:
    """
    Disables the default session serializer
    """
    disable_default_serializer_for('session')


"""
These Affect `kvdb.configs.persistence.KVDBPersistenceConfig`
"""

def enable_default_persistence_serializer() -> None:
    """
    Enables the default persistence serializer
    """
    enable_default_serializer_for('persistence')

def disable_default_persistence_serializer() -> None:
    """
    Disables the default persistence serializer
    """
    disable_default_serializer_for('persistence')

def set_default_persistence_serializer(serializer: str) -> None:
    """
    Sets the default persistence serializer
    """
    set_default_serializer_for(serializer, 'persistence')

def get_default_persistence_serializer() -> Optional[str]:
    """
    Returns the default persistence serializer for the config

    - If the default persistence serializer is enabled, then it returns the default persistence serializer
    - Else, it returns None
    """
    return get_default_serializer_for('persistence')


