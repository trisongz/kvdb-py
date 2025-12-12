

import pytest
import asyncio
from kvdb import KVDBClient

TEST_URL = "redis://localhost:6379/10"

@pytest.fixture
async def async_session():
    session = KVDBClient.get_session(name="e2e_async", url=TEST_URL, serializer="json")
    session.enable_serialization("json")
    await session.aclear()
    yield session
    await session.aclear()

@pytest.mark.asyncio
async def test_async_lock(async_session):
    # Test acquiring lock
    lock = async_session.alock("test_lock", timeout=5, blocking_timeout=1)
    
    assert await lock.acquire() is True
    
    # Try to acquire same lock (should fail)
    lock2 = async_session.alock("test_lock", timeout=5, blocking_timeout=0.1)
    assert await lock2.acquire() is False
    
    # Release
    await lock.release()
    
    # Now lock2 should be acquirable
    assert await lock2.acquire() is True
    await lock2.release()

@pytest.mark.asyncio
async def test_async_pubsub(async_session):
    channel = "test_channel"
    received_messages = []

    async def listener():
        pubsub = async_session.apubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    received_messages.append(message['data'])
                    if message['data'] == b'STOP' or message['data'] == 'STOP':
                        await pubsub.unsubscribe(channel)
                        break
        finally:
            await pubsub.close()

    # Start listener task
    task = asyncio.create_task(listener())
    
    # Wait a bit for subscription
    await asyncio.sleep(0.5)
    
    # Publish messages
    await async_session.apublish(channel, "Hello")
    await async_session.apublish(channel, "World")
    await async_session.apublish(channel, "STOP")
    
    try:
        await asyncio.wait_for(task, timeout=5.0)
    except asyncio.TimeoutError:
        task.cancel()
        raise Exception("PubSub timed out - message not received or loop stuck")
    
    assert b'Hello' in received_messages or 'Hello' in received_messages
    assert b'World' in received_messages or 'World' in received_messages
