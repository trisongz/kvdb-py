"""
Example: Using KVDB with Multi-Database (Active-Active) Support

This example demonstrates how to use kvdb-py with redis-py 7.x multi-database
features for Active-Active Redis Enterprise setups. This provides automatic
failover, health checks, and circuit breakers across multiple Redis databases.

Requirements:
- redis-py >= 7.0
- pybreaker (for circuit breakers)
- Redis Enterprise with Active-Active databases or multiple Redis instances

Note: This is an advanced feature primarily for production environments with
Redis Enterprise Active-Active configurations.
"""

from kvdb.components.multidb import (
    KVDBMultiDBClient,
    MultiDbConfig,
    DatabaseConfig,
    MULTIDB_AVAILABLE,
)

def main():
    """
    Main example function demonstrating Active-Active database setup.
    """
    
    # Check if multidb support is available
    if not MULTIDB_AVAILABLE:
        print("Multi-database support is not available.")
        print("Please install redis-py >= 7.0 and pybreaker:")
        print("  pip install 'redis>=7.0' pybreaker")
        return
    
    print("✓ Multi-database support is available")
    
    # Configure multiple databases with weights
    # Higher weight = preferred for active connections
    config = MultiDbConfig(
        databases_config=[
            DatabaseConfig(
                from_url="redis://localhost:6379/0",
                weight=1.0,  # Primary database
                health_check_url="redis://localhost:6379/0",  # Optional: for health checks
            ),
            DatabaseConfig(
                from_url="redis://localhost:6380/0",
                weight=0.5,  # Secondary database (lower priority)
                health_check_url="redis://localhost:6380/0",
            ),
        ],
        # Optional: Configure health check interval (in seconds)
        health_check_interval=10.0,
        
        # Optional: Configure failover behavior
        failover_attempts=3,
        failover_delay=1.0,
        
        # Optional: Auto-fallback to higher-weighted database after recovery
        auto_fallback_interval=120.0,
    )
    
    # Alternative: Create from URLs directly
    # client = KVDBMultiDBClient.from_urls(
    #     urls=[
    #         "redis://localhost:6379/0",
    #         "redis://localhost:6380/0",
    #     ],
    #     weights=[1.0, 0.5],
    # )
    
    print("✓ Configuration created")
    
    # Create the multi-database client
    client = KVDBMultiDBClient(config)
    print("✓ Multi-database client created")
    
    # Initialize the client (performs health checks and sets up failover)
    try:
        client.initialize()
        print("✓ Client initialized - databases are healthy")
    except Exception as e:
        print(f"✗ Failed to initialize: {e}")
        print("  Make sure Redis instances are running on configured URLs")
        return
    
    # Use the client like a normal Redis client
    # All commands are automatically routed to the active database
    # with automatic failover if the active database becomes unhealthy
    
    try:
        # Set a key
        client.set("example_key", "example_value")
        print("✓ Set key successfully")
        
        # Get a key
        value = client.get("example_key")
        print(f"✓ Got value: {value}")
        
        # The client automatically handles:
        # - Circuit breakers to prevent cascading failures
        # - Health checks to detect unhealthy databases
        # - Automatic failover to backup databases
        # - Command retries with exponential backoff
        # - Auto-fallback to higher-weighted databases when they recover
        
        # Get information about databases
        databases = client.get_databases()
        print(f"✓ Number of databases: {len(databases)}")
        
        # You can also manually set the active database if needed
        # (though this is usually handled automatically)
        # client.set_active_database(some_database)
        
    except Exception as e:
        print(f"✗ Error during operations: {e}")
    
    print("\n✅ Example completed successfully!")
    print("\nKey features of Multi-Database support:")
    print("  • Automatic failover between databases")
    print("  • Circuit breakers to prevent cascading failures")
    print("  • Continuous health monitoring")
    print("  • Weighted database selection")
    print("  • Command retries with exponential backoff")
    print("  • Auto-fallback to primary database after recovery")


if __name__ == "__main__":
    main()
