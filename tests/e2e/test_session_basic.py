
import pytest
import asyncio
from kvdb import KVDBClient
from pydantic import BaseModel

class User(BaseModel):
    name: str
    age: int

# Configuration for local testing or CI
# In CI, service is usually at localhost:6379/0
TEST_URL = "redis://localhost:6379/10" # Use DB 10 for tests

@pytest.fixture
def sync_session():
    session = KVDBClient.get_session(name="e2e_sync", url=TEST_URL, serializer="json", decode_responses=True)
    session.enable_serialization("json", decode_responses=True)
    session.clear()
    yield session
    session.clear()

@pytest.fixture
async def async_session():
    session = KVDBClient.get_session(name="e2e_async", url=TEST_URL, serializer="json", decode_responses=True)
    session.enable_serialization("json", decode_responses=True)
    await session.aclear()
    yield session
    await session.aclear()

def test_sync_basic_ops(sync_session):
    # Set
    sync_session.set("foo", "bar")
    assert sync_session.get("foo") == "bar"
    
    # Delete
    sync_session.delete("foo")
    assert sync_session.get("foo") is None

    # Serialization
    user = User(name="Alice", age=30)
    sync_session.set("user:1", user)
    retrieved = sync_session.get("user:1")
    assert retrieved == user
    assert isinstance(retrieved, User)

@pytest.mark.asyncio
async def test_async_basic_ops(async_session):
    # Set
    await async_session.aset("foo", "bar")
    val = await async_session.aget("foo")
    assert val == "bar"

    # Delete
    await async_session.adelete("foo")
    val = await async_session.aget("foo")
    assert val is None

    # Serialization
    user = User(name="Bob", age=25)
    await async_session.aset("user:2", user)
    retrieved = await async_session.aget("user:2")
    assert retrieved == user
    assert isinstance(retrieved, User)
