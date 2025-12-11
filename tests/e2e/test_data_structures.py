
import pytest
from kvdb import KVDBClient

TEST_URL = "redis://localhost:6379/10"

@pytest.fixture
async def async_session():
    # used to use e2e_data_structs but that causes conflict
    session = KVDBClient.get_session(name="e2e_data_structs_unique", url=TEST_URL)
    await session.aclear()
    yield session
    await session.aclear()

@pytest.mark.asyncio
async def test_lists(async_session):
    key = "test:list"
    # Push
    await async_session.alpush(key, "a", "b", "c") # c, b, a
    
    # Len
    assert await async_session.allen(key) == 3
    
    # Range
    items = await async_session.alrange(key, 0, -1)
    assert items == [b'c', b'b', b'a']
    
    # Pop
    val = await async_session.alpop(key)
    assert val == b'c'
    assert await async_session.allen(key) == 2

@pytest.mark.asyncio
async def test_sets(async_session):
    key = "test:set"
    # Add
    await async_session.asadd(key, "a", "b", "c", "a")
    
    # Card (size)
    assert await async_session.ascard(key) == 3
    
    # Members
    members = await async_session.asmembers(key)
    assert set(members) == {b'a', b'b', b'c'}
    
    # Is Member
    # Redis returns 1 for True, 0 for False
    assert await async_session.asismember(key, "a") == 1
    assert await async_session.asismember(key, "z") == 0
    
    # Rem
    await async_session.asrem(key, "b")
    assert await async_session.ascard(key) == 2

@pytest.mark.asyncio
async def test_hashes(async_session):
    key = "test:hash"
    # Hset
    await async_session.ahset(key, mapping={"f1": "v1", "f2": "v2"})
    
    # Hget
    val = await async_session.ahget(key, "f1")
    assert val == b'v1'
    
    # Hgetall
    data = await async_session.ahgetall(key)
    assert data == {b'f1': b'v1', b'f2': b'v2'}
    
    # Hlen
    assert await async_session.ahlen(key) == 2
    
    # Hdel
    await async_session.ahdel(key, "f1")
    assert await async_session.ahget(key, "f1") is None
