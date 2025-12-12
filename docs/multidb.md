# Multi-Database (Active-Active) Support

Starting with redis-py 7.0, kvdb-py supports Active-Active database configurations through the `KVDBMultiDBClient`. This feature is designed for production environments using Redis Enterprise with Active-Active geo-distributed databases.

## Overview

The multi-database client provides:

- **Automatic Failover**: Seamlessly switches to backup databases when the active database becomes unhealthy
- **Circuit Breakers**: Prevents cascading failures by temporarily stopping requests to unhealthy databases
- **Health Monitoring**: Continuously checks database health with configurable intervals and policies
- **Weighted Selection**: Prioritizes databases by weight for intelligent failover decisions
- **Command Retries**: Automatically retries failed commands with exponential backoff
- **Auto-Fallback**: Returns to higher-priority databases when they recover

## Requirements

```bash
pip install 'redis>=7.0' pybreaker
```

The multidb features require:
- redis-py >= 7.0
- pybreaker (for circuit breaker functionality)
- Redis Enterprise with Active-Active databases or multiple Redis instances

## Basic Usage

### Simple Configuration

```python
from kvdb.components.multidb import KVDBMultiDBClient

# Create client from URLs with weights
client = KVDBMultiDBClient.from_urls(
    urls=[
        "redis://primary.example.com:6379/0",
        "redis://secondary.example.com:6379/0",
    ],
    weights=[1.0, 0.5],  # Primary has higher weight
)

# Initialize (performs health checks and sets up monitoring)
client.initialize()

# Use like a normal Redis client
client.set("key", "value")
value = client.get("key")
```

### Advanced Configuration

```python
from kvdb.components.multidb import (
    KVDBMultiDBClient,
    MultiDbConfig,
    DatabaseConfig,
)

config = MultiDbConfig(
    databases_config=[
        DatabaseConfig(
            from_url="redis://db1.example.com:6379/0",
            weight=1.0,
            health_check_url="redis://db1.example.com:6379/0",
            grace_period=30.0,  # Circuit breaker grace period
        ),
        DatabaseConfig(
            from_url="redis://db2.example.com:6379/0",
            weight=0.8,
            health_check_url="redis://db2.example.com:6379/0",
        ),
        DatabaseConfig(
            from_url="redis://db3.example.com:6379/0",
            weight=0.5,
            health_check_url="redis://db3.example.com:6379/0",
        ),
    ],
    # Health check configuration
    health_check_interval=10.0,      # Check every 10 seconds
    health_check_probes=3,           # Number of probes for health determination
    health_check_probes_delay=1.0,   # Delay between probes
    
    # Failover configuration
    failover_attempts=3,             # Number of failover attempts
    failover_delay=1.0,              # Delay between attempts
    auto_fallback_interval=120.0,    # Auto-fallback to primary after 2 minutes
    
    # Failure detection
    min_num_failures=5,              # Minimum failures before triggering failover
    failure_rate_threshold=0.5,      # 50% failure rate threshold
    failures_detection_window=60.0,  # Track failures in 60-second window
)

client = KVDBMultiDBClient(config)
client.initialize()
```

### Using Connection Pools

```python
from redis import ConnectionPool
from kvdb.components.multidb import MultiDbConfig, DatabaseConfig, KVDBMultiDBClient

# Create connection pools for better connection management
pool1 = ConnectionPool.from_url("redis://db1.example.com:6379/0", max_connections=50)
pool2 = ConnectionPool.from_url("redis://db2.example.com:6379/0", max_connections=50)

config = MultiDbConfig(
    databases_config=[
        DatabaseConfig(from_pool=pool1, weight=1.0),
        DatabaseConfig(from_pool=pool2, weight=0.5),
    ]
)

client = KVDBMultiDBClient(config)
client.initialize()
```

### Using with Redis Cluster

```python
from redis import RedisCluster
from kvdb.components.multidb import KVDBMultiDBClient

client = KVDBMultiDBClient.from_urls(
    urls=[
        "redis://cluster1.example.com:6379/0",
        "redis://cluster2.example.com:6379/0",
    ],
    weights=[1.0, 0.5],
    client_class=RedisCluster,  # Use Redis Cluster
)

client.initialize()
```

## Key Concepts

### Database Weights

Weights determine database priority for active selection:
- Higher weight = higher priority for becoming active
- Used during failover to select the next best database
- Typical pattern: Primary (1.0), Secondary (0.5-0.8), Tertiary (0.3-0.5)

### Circuit Breakers

Circuit breakers prevent cascading failures:
- **CLOSED**: Database is healthy, requests flow normally
- **OPEN**: Database is unhealthy, requests are blocked
- **HALF_OPEN**: Testing if database has recovered

The `grace_period` defines how long to wait before testing recovery.

### Health Checks

Continuous health monitoring with configurable policies:
- **Probes**: Number of health check attempts
- **Delay**: Time between probe attempts
- **Policy**: Logic for determining overall health from probe results

### Failover Strategy

When active database fails:
1. Circuit breaker opens for the failed database
2. Failure detector triggers failover
3. Next highest-weighted healthy database becomes active
4. Commands are retried on new active database
5. Original database is monitored for recovery

### Auto-Fallback

After a configured interval, the system checks if higher-weighted databases have recovered and automatically fails back to them.

## Manual Database Management

```python
# Get all databases
databases = client.get_databases()

# Manually set active database
for db, weight in databases:
    if weight == 1.0:  # Highest weighted
        client.set_active_database(db)
        break

# Add a new database dynamically
from kvdb.components.multidb import Database
from redis import Redis

new_db = Database(
    client=Redis.from_url("redis://new-db.example.com:6379/0"),
    circuit=...,  # Circuit breaker instance
    weight=0.6,
)
client.add_database(new_db)
```

## Event Handling

The multidb client dispatches events for monitoring:

```python
from redis.event import EventDispatcher

def on_database_failover(event):
    print(f"Failover occurred: {event}")

dispatcher = EventDispatcher()
# Register event handlers as needed

config = MultiDbConfig(
    databases_config=[...],
    event_dispatcher=dispatcher,
)
```

## Best Practices

1. **Use Health Check URLs**: For Redis Enterprise, use the FQDN endpoint for accurate health checks
2. **Set Appropriate Weights**: Reflect geographic or infrastructure preferences
3. **Configure Timeouts**: Set reasonable socket timeouts to detect failures quickly
4. **Monitor Events**: Track failover events for operational awareness
5. **Test Failover**: Regularly test failover scenarios in staging
6. **Connection Pools**: Use connection pools for better resource management

## Troubleshooting

### Import Error: No module named 'pybreaker'

```bash
pip install pybreaker
```

### Import Error: Cannot import MultiDBClient

Upgrade redis-py:
```bash
pip install --upgrade 'redis>=7.0'
```

### NoValidDatabaseException on Initialize

- Ensure at least one Redis instance is running and accessible
- Check connection URLs are correct
- Verify network connectivity to Redis instances
- Check Redis authentication credentials if using password

### Failover Not Working

- Verify health check URLs are configured correctly
- Check failure detection thresholds are appropriate
- Ensure health check interval is reasonable for your use case
- Monitor circuit breaker states

## Limitations

- The multidb client is marked as experimental in redis-py
- Not all Redis commands may work identically across databases
- Active-Active configurations have eventual consistency characteristics
- Transaction support may be limited across failovers

## See Also

- [redis-py Multi-Database Documentation](https://redis.readthedocs.io/en/stable/multi_database.html)
- [Redis Enterprise Active-Active](https://redis.com/redis-enterprise/technology/active-active-geo-distribution/)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
