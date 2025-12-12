
import pytest
from kvdb import KVDBClient
from kvdb.types.contexts import GlobalKVDBContext

@pytest.fixture(autouse=True)
async def clear_kvdb_client_state():
    """
    Clears the KVDBClient global state (sessions and pools) before and after each test.
    This prevents RuntimeError caused by reusing clients bound to closed event loops
    when pytest-asyncio creates new loops for each test.
    """
    ctx = GlobalKVDBContext()
    
    # Pre-test cleanup
    await _cleanup_ctx(ctx)

    yield

    # Post-test cleanup
    await _cleanup_ctx(ctx)

async def _cleanup_ctx(ctx):
    # Close and clear sessions
    if ctx.sessions:
        for name, session in list(ctx.sessions.items()):
            try:
                await session.aclose(close_pool=True)
            except Exception:
                pass
        ctx.sessions.clear()

    # Clear pools (disconnecting them first is ideal but aclose(close_pool=True) might have handled it for used pools)
    # To be safe, let's try to disconnect any lingering pools in 'pools' dict
    if ctx.pools:
        for key, pool in list(ctx.pools.items()):
            if hasattr(pool, 'apool'):
                 try:
                     await pool.apool.disconnect()
                 except Exception:
                     pass
        ctx.pools.clear()
