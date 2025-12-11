
import pytest
from kvdb import KVDBClient

TEST_URL = "redis://localhost:6379/10"

@pytest.fixture
def session():
    session = KVDBClient.get_session(name="e2e_bulk_sync", url=TEST_URL)
    session.clear()
    yield session
    session.clear()

@pytest.fixture
async def async_session():
    session = KVDBClient.get_session(name="e2e_bulk_async_unique", url=TEST_URL)
    await session.aclear()
    yield session
    await session.aclear()

def test_sync_mset_mget(session):
    data = {"k1": "v1", "k2": "v2", "k3": "v3"}
    
    # MSET
    session.mset(data)
    
    # MGET
    values = session.mget(["k1", "k2", "k3", "k4"])
    # Note: redis-py mget returns list of values. 
    # If using decode_responses=False (default), they are bytes.
    assert values == [b'v1', b'v2', b'v3', None]

@pytest.mark.asyncio
async def test_async_mset_mget(async_session):
    data = {"ak1": "av1", "ak2": "av2", "ak3": "av3"}
    
    # AMSET
    await async_session.amset(data)
    
    # AMGET
    values = await async_session.amget(["ak1", "ak2", "ak3", "ak4"])
    assert values == [b'av1', b'av2', b'av3', None]
