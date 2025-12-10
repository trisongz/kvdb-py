
import pytest
import asyncio
from kvdb.components.persistence import KVDBStatefulBackend

TEST_URL = "redis://localhost:6379/10"

@pytest.fixture
def clean_db():
    # Setup
    yield
    # Teardown logic if needed, tests handle their own cleanup mostly

@pytest.mark.asyncio
async def test_persistence_hset_enabled():
    # Test HSET mode (Default)
    # HSET mode stores keys in a hash `bench:hset`
    pdict = KVDBStatefulBackend.as_persistent_dict(
        url=TEST_URL, 
        base_key="test:pdict:hset", 
        hset_disabled=False, 
        async_enabled=True
    )
    await pdict.aclear()

    # Set
    await pdict.aset("key1", "value1")
    assert await pdict.aget("key1") == "value1"

    # Set with Expiration
    await pdict.aset("key2", "value2", ex=1)
    assert await pdict.aget("key2") == "value2"
    await asyncio.sleep(1.2)
    assert await pdict.aget("key2") is None

    # Delete
    await pdict.adelete("key1")
    assert await pdict.aget("key1") is None

@pytest.mark.asyncio
async def test_persistence_no_hset():
    # Test No-HSET mode (Direct keys)
    # No-HSET mode stores keys as `test:pdict:nohset:key`
    pdict = KVDBStatefulBackend.as_persistent_dict(
        url=TEST_URL, 
        base_key="test:pdict:nohset", 
        hset_disabled=True, 
        async_enabled=True
    )
    await pdict.aclear() # Should clear keys matching pattern

    # Set
    await pdict.aset("key1", "value1")
    assert await pdict.aget("key1") == "value1"

    # Set with Expiration
    await pdict.aset("key2", "value2", ex=1)
    assert await pdict.aget("key2") == "value2"
    await asyncio.sleep(1.2)
    assert await pdict.aget("key2") is None

    # Delete
    await pdict.adelete("key1")
    assert await pdict.aget("key1") is None
