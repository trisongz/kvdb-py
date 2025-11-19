from __future__ import annotations

"""
KVDB Multi-Database (Active-Active) Support

Provides integration with redis-py's multidb module for Active-Active
Redis Enterprise database setups with automatic failover and health checks.
"""

import typing
from typing import Union, Optional, List, Type, Any, Dict

try:
    from redis.multidb.client import MultiDBClient as _MultiDBClient
    from redis.multidb.config import MultiDbConfig, DatabaseConfig
    from redis.multidb.database import Database, SyncDatabase
    from redis.multidb.failover import FailoverStrategy
    from redis.multidb.failure_detector import FailureDetector
    from redis.multidb.healthcheck import HealthCheck
    from redis.event import EventDispatcherInterface
    MULTIDB_AVAILABLE = True
except ImportError:
    MULTIDB_AVAILABLE = False
    _MultiDBClient = None
    MultiDbConfig = None
    DatabaseConfig = None
    Database = None
    SyncDatabase = None
    FailoverStrategy = None
    FailureDetector = None
    HealthCheck = None
    EventDispatcherInterface = None

from kvdb.types.base import KVDBUrl
from kvdb.utils.logs import logger

if typing.TYPE_CHECKING:
    from redis import Redis, RedisCluster


class KVDBMultiDBClient:
    """
    KVDB wrapper for redis-py MultiDBClient.
    
    Provides Active-Active database support with automatic failover, 
    health checks, and circuit breakers for Redis Enterprise setups.
    
    Example usage:
        from kvdb.components.multidb import KVDBMultiDBClient, DatabaseConfig, MultiDbConfig
        
        config = MultiDbConfig(
            databases_config=[
                DatabaseConfig(
                    from_url="redis://db1.example.com:6379/0",
                    weight=1.0,
                ),
                DatabaseConfig(
                    from_url="redis://db2.example.com:6379/0",
                    weight=0.5,
                ),
            ]
        )
        
        client = KVDBMultiDBClient(config)
        client.initialize()
        
        # Use like a normal Redis client
        client.set("key", "value")
        value = client.get("key")
    """
    
    def __init__(self, config: 'MultiDbConfig'):
        """
        Initialize a MultiDB client.
        
        Args:
            config: MultiDbConfig instance with database configurations
        
        Raises:
            ImportError: If redis-py multidb support is not available (< 7.0)
        """
        if not MULTIDB_AVAILABLE:
            raise ImportError(
                "redis-py multidb support is not available. "
                "Please upgrade to redis-py >= 7.0 to use Active-Active features."
            )
        self._client = _MultiDBClient(config)
        self._config = config
    
    def initialize(self):
        """
        Perform initialization of databases to define their initial state.
        Starts recurring health checks in the background.
        """
        self._client.initialize()
    
    def __getattr__(self, name: str) -> Any:
        """
        Proxy all other method calls to the underlying MultiDBClient.
        """
        return getattr(self._client, name)
    
    @classmethod
    def from_urls(
        cls,
        urls: List[Union[str, KVDBUrl]],
        weights: Optional[List[float]] = None,
        client_class: Type[Union['Redis', 'RedisCluster']] = None,
        **config_kwargs
    ) -> 'KVDBMultiDBClient':
        """
        Create a MultiDB client from a list of URLs.
        
        Args:
            urls: List of Redis connection URLs
            weights: Optional list of weights for each database (default: all 1.0)
            client_class: Redis client class to use (default: Redis)
            **config_kwargs: Additional MultiDbConfig parameters
        
        Returns:
            Initialized KVDBMultiDBClient instance
        """
        if not MULTIDB_AVAILABLE:
            raise ImportError(
                "redis-py multidb support is not available. "
                "Please upgrade to redis-py >= 7.0 to use Active-Active features."
            )
        
        from redis import Redis
        
        if client_class is None:
            client_class = Redis
        
        if weights is None:
            weights = [1.0] * len(urls)
        elif len(weights) != len(urls):
            raise ValueError("Number of weights must match number of URLs")
        
        databases_config = []
        for url, weight in zip(urls, weights):
            url_str = url.value if isinstance(url, KVDBUrl) else str(url)
            databases_config.append(
                DatabaseConfig(
                    from_url=url_str,
                    weight=weight,
                )
            )
        
        config = MultiDbConfig(
            databases_config=databases_config,
            client_class=client_class,
            **config_kwargs
        )
        
        return cls(config)


# Re-export key classes for convenience
__all__ = [
    'KVDBMultiDBClient',
    'MULTIDB_AVAILABLE',
]

# Conditionally export multidb classes if available
if MULTIDB_AVAILABLE:
    __all__.extend([
        'MultiDbConfig',
        'DatabaseConfig',
        'Database',
        'SyncDatabase',
        'FailoverStrategy',
        'FailureDetector',
        'HealthCheck',
        'EventDispatcherInterface',
    ])
