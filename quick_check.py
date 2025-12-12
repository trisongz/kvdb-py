
import asyncio
from kvdb import KVDBClient

async def run():
    session = KVDBClient.get_session(name="test", url="redis://localhost:6380/0")
    client = session.client
    print("PING:", client.ping())
    client.set("foo", "bar")
    print("GET:", client.get("foo"))
    client.delete("foo")
    print("DEL ok")
    # client.close()

if __name__ == "__main__":
    asyncio.run(run())
