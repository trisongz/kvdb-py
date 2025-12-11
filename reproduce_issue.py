
import asyncio
from kvdb.components.connection import AsyncConnection
from redis.asyncio.connection import Connection as RedisAsyncConnection

async def main():
    print("Testing AsyncConnection instantiation...")
    try:
        # Initialize AsyncConnection, which should set host via super().__init__ or similar
        conn = AsyncConnection(host='localhost', port=6379, db=0)
        print(f"Connection created: {conn}")
        
        # Try to access host
        print(f"Host: {conn.host}")
        
        # Try to access _connection_arguments if it exists (redis 5.x) or just mimic the error
        try:
            args = conn._connection_arguments()
            print(f"Connection args: {args}")
        except AttributeError as e:
            print(f"Failed to get connection args: {e}")
            
    except AttributeError as e:
        print(f"Caught expected error: {e}")
    except Exception as e:
        print(f"Caught unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
