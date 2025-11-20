"""
Optimized Async Connection Pool Implementation

This module provides optimized connection pool implementations with:
- Reduced lock contention
- Connection health check caching
- Pool warming
- Better error handling
- Performance metrics
"""

from __future__ import annotations

import time
import asyncio
import contextlib
from typing import Optional, Set, List, Dict, Any
from dataclasses import dataclass, field

from .connection_pool import (
    AsyncConnectionPool as BaseAsyncConnectionPool,
    AsyncConnection,
)

# Handle logger import gracefully
try:
    from kvdb.utils.logs import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


@dataclass
class PoolMetrics:
    """Connection pool performance metrics"""
    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    connection_acquisitions: int = 0
    connection_creation_time: float = 0.0
    connection_acquisition_time: float = 0.0
    lock_wait_time: float = 0.0
    health_check_time: float = 0.0
    errors: int = 0
    
    def reset(self):
        """Reset counters (keep connection counts)"""
        self.connection_acquisitions = 0
        self.connection_creation_time = 0.0
        self.connection_acquisition_time = 0.0
        self.lock_wait_time = 0.0
        self.health_check_time = 0.0
        self.errors = 0


class HealthCachedConnection:
    """Wrapper for connection with cached health status"""
    def __init__(self, connection: AsyncConnection, check_interval: float = 1.0):
        self.connection = connection
        self.check_interval = check_interval
        self._last_health_check = 0.0
        self._is_healthy = True
    
    async def is_healthy(self) -> bool:
        """Check if connection is healthy (with caching)"""
        current_time = time.time()
        
        # Fast path: use cached result if recent
        if current_time - self._last_health_check < self.check_interval:
            return self._is_healthy
        
        # Perform actual health check
        try:
            if await self.connection.can_read_destructive():
                self._is_healthy = False
            else:
                self._is_healthy = True
            self._last_health_check = current_time
            return self._is_healthy
        except Exception:
            self._is_healthy = False
            return False
    
    def mark_used(self):
        """Mark connection as recently used (reset health check timer)"""
        self._last_health_check = time.time()
        self._is_healthy = True


class OptimizedAsyncConnectionPool(BaseAsyncConnectionPool):
    """
    Optimized async connection pool with:
    - Reduced lock contention
    - Health check caching
    - Connection pool warming
    - Performance metrics
    """
    
    def __init__(self, *args, enable_metrics: bool = False, 
                 health_check_interval: float = 1.0,
                 min_idle_connections: int = 5,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.enable_metrics = enable_metrics
        self.health_check_interval = health_check_interval
        self.min_idle_connections = min(min_idle_connections, self.max_connections // 2)
        self.metrics = PoolMetrics() if enable_metrics else None
        self._connection_cache: Dict[AsyncConnection, HealthCachedConnection] = {}
        self._warmed = False
    
    async def warm_pool(self, target_connections: Optional[int] = None):
        """
        Pre-create connections to reduce cold-start latency
        
        Args:
            target_connections: Number of connections to pre-create.
                               Defaults to min_idle_connections.
        """
        if target_connections is None:
            target_connections = self.min_idle_connections
        
        target_connections = min(target_connections, self.max_connections)
        
        logger.info(f"Warming connection pool to {target_connections} connections...")
        
        async with self._lock:
            created = 0
            while self._created_connections < target_connections:
                try:
                    connection = self.make_connection()
                    await connection.connect()
                    self._available_connections.append(connection)
                    self._created_connections += 1
                    self._connection_cache[connection] = HealthCachedConnection(
                        connection, self.health_check_interval
                    )
                    created += 1
                except Exception as e:
                    logger.warning(f"Failed to create connection during warming: {e}")
                    if self.metrics:
                        self.metrics.errors += 1
                    break
        
        self._warmed = True
        logger.info(f"Pool warmed with {created} connections")
        return created
    
    async def get_connection_optimized(self, command_name, *keys, **options):
        """
        Optimized connection acquisition with reduced lock contention
        
        Uses a fast-path approach:
        1. Try to get connection without full lock
        2. Only acquire lock for critical operations
        3. Cache health status to reduce checks
        """
        start_time = time.time() if self.metrics else None
        connection = None
        
        # Fast path: try lock-free pop
        try:
            # Note: list.pop() is atomic in CPython, but we still need
            # to check for race conditions
            potential_conn = self._available_connections.pop()
            
            # Quick check: is this connection actually available?
            async with self._lock:
                if potential_conn not in self._in_use_connections:
                    connection = potential_conn
                    self._in_use_connections.add(connection)
                else:
                    # Race condition: put it back
                    self._available_connections.append(potential_conn)
                    connection = None
                    
        except IndexError:
            # No connections available, need to create or wait
            pass
        
        # Slow path: acquire lock and handle connection creation
        if connection is None:
            lock_start = time.time() if self.metrics else None
            
            async with self._lock:
                if self.metrics and lock_start:
                    self.metrics.lock_wait_time += time.time() - lock_start
                
                try:
                    connection = self._available_connections.pop()
                    self._in_use_connections.add(connection)
                except IndexError:
                    # Need to create new connection
                    if self._created_connections >= self.max_connections:
                        # Pool exhausted - could implement waiting here
                        raise Exception("Connection pool exhausted")
                    
                    create_start = time.time() if self.metrics else None
                    connection = self.make_connection()
                    self._created_connections += 1
                    self._in_use_connections.add(connection)
                    self._connection_cache[connection] = HealthCachedConnection(
                        connection, self.health_check_interval
                    )
                    
                    if self.metrics and create_start:
                        self.metrics.connection_creation_time += time.time() - create_start
        
        # Use cached health check
        cached_conn = self._connection_cache.get(connection)
        if cached_conn:
            health_start = time.time() if self.metrics else None
            
            try:
                if not await cached_conn.is_healthy():
                    # Connection unhealthy, reconnect
                    await connection.disconnect()
                    await connection.connect()
                    cached_conn.mark_used()
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                if self.metrics:
                    self.metrics.errors += 1
                raise
            
            if self.metrics and health_start:
                self.metrics.health_check_time += time.time() - health_start
        
        # Mark as used (for health check caching)
        if cached_conn:
            cached_conn.mark_used()
        
        if self.metrics:
            self.metrics.connection_acquisitions += 1
            self.metrics.connection_acquisition_time += time.time() - start_time
            self.metrics.active_connections = len(self._in_use_connections)
            self.metrics.idle_connections = len(self._available_connections)
            self.metrics.total_connections = self._created_connections
        
        # Use standard ensure_connection for final validation
        async with self.ensure_connection(connection) as conn:
            return conn
    
    async def get_connection(self, command_name, *keys, **options):
        """
        Get a connection from the pool (delegates to optimized version if enabled)
        """
        # For now, use the optimized version by default
        # Could make this configurable
        return await self.get_connection_optimized(command_name, *keys, **options)
    
    def get_metrics(self) -> Optional[Dict[str, Any]]:
        """Get current pool metrics"""
        if not self.metrics:
            return None
        
        return {
            'total_connections': self.metrics.total_connections,
            'active_connections': self.metrics.active_connections,
            'idle_connections': self.metrics.idle_connections,
            'connection_acquisitions': self.metrics.connection_acquisitions,
            'avg_acquisition_time_ms': (
                (self.metrics.connection_acquisition_time / self.metrics.connection_acquisitions * 1000)
                if self.metrics.connection_acquisitions > 0 else 0
            ),
            'avg_creation_time_ms': (
                (self.metrics.connection_creation_time / max(1, self.metrics.total_connections) * 1000)
            ),
            'total_lock_wait_time_ms': self.metrics.lock_wait_time * 1000,
            'total_health_check_time_ms': self.metrics.health_check_time * 1000,
            'errors': self.metrics.errors,
        }
    
    def reset_metrics(self):
        """Reset metrics counters"""
        if self.metrics:
            self.metrics.reset()
