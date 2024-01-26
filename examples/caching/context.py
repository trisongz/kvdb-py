"""
A Very basic demonstration of how to use cachify with objects using a context

Similiar to registering tasks, a context can be created to register objects or functions, where
the passed parameters will be used as the default parameters for all registered functions.

Run this example:

    # cwd: examples/caching
    $ python context.py
"""

import time
import abc
import asyncio
from lazyops.utils.times import Timer
from kvdb.io import cachify
from kvdb.utils.logs import logger

DEBUG_ENABLED = False

cache_context = cachify.create_context(
    cache_name='test', # Unique name for the cache. This is used to identify the cache in the cache registry
    prefix = '_kvtest_', # Prefix for the cache key
    ttl = 10,
    verbosity = 2 if DEBUG_ENABLED else None,
    cache_max_size = 15,
)

@cache_context.register_object()
class TestObject(abc.ABC):

    def __init__(self, *args, **kwargs):
        logger.info('running init')

    @cache_context.register()
    async def async_fibonacci(self, number: int):
        if number == 0: return 0
        elif number == 1: return 1
        return await self.async_fibonacci(number - 1) + await self.async_fibonacci(number - 2)

    @cache_context.register()
    def fibonacci(self, number: int):
        if number == 0: return 0
        elif number == 1: return 1
        return self.fibonacci(number - 1) + self.fibonacci(number - 2)

    # No Cache Versions
    async def async_fibonacci_nc(self, number: int):
        if number == 0: return 0
        elif number == 1: return 1
        return await self.async_fibonacci_nc(number - 1) + await self.async_fibonacci_nc(number - 2)

    def fibonacci_nc(self, number: int):
        if number == 0: return 0
        elif number == 1: return 1
        return self.fibonacci_nc(number - 1) + self.fibonacci_nc(number - 2)


async def run_tests(
    start_n: int = 1,
    runs: int = 10,
    print_every: int = 5,
):
    
    """
    Test that both results are the same.
    """

    t = Timer(format_ms=True)
    o = TestObject()

    # Test Sync
    st = Timer(format_ms=True)
    for i in range(runs):
        r = o.fibonacci(start_n+i)
        d = st.duration_s
        if i % print_every == 0:
            logger.info(f'[Sync - {i}/{runs}] Result: {r} | Time: {d}')
    logger.info(f'[Sync] Cache Average Time: {st.total_average_s(runs)} | Total Time: {st.total_s}')
    logger.info(o.fibonacci.cache_info(), prefix = '[Sync] Cache Info')

    # Test Async
    at = Timer(format_ms=True)
    for i in range(runs):
        r = await o.async_fibonacci(start_n+i)
        d = at.duration_s
        if i % print_every == 0:
            logger.info(f'[Async - {i}/{runs}] Result: {r} | Time: {d}')
    logger.info(f'[Async] Cache Average Time: {at.total_average_s(runs)} | Total Time: {at.total_s}')
    logger.info(await o.async_fibonacci.cache_info(), prefix = '[Async] Cache Info')
    logger.info(t.total_s, prefix = 'Total Time')

    # Clear the Cache
    o.fibonacci.clear()
    logger.info(o.fibonacci.cache_info(), prefix = '[Sync] Cache Info')

    await o.async_fibonacci.clear()
    logger.info(await o.async_fibonacci.cache_info(), prefix = '[Async] Cache Info')

    logger.info('Testing Non-Cached Functions')
    t = Timer(format_ms=True)

    # Test Sync
    st = Timer(format_ms=True)
    for i in range(runs):
        r = o.fibonacci_nc(start_n+i)
        d = st.duration_s
        if i % print_every == 0:
            logger.info(f'[Sync - {i}/{runs}] Result: {r} | Time: {d}')
    logger.info(f'[Sync] Cache Average Time: {st.total_average_s(runs)} | Total Time: {st.total_s}')

    # Test Async
    at = Timer(format_ms=True)
    for i in range(runs):
        r = await o.async_fibonacci_nc(start_n+i)
        d = at.duration_s
        if i % print_every == 0:
            logger.info(f'[Async - {i}/{runs}] Result: {r} | Time: {d}')
    logger.info(f'[Async] Cache Average Time: {at.total_average_s(runs)} | Total Time: {at.total_s}')
    logger.info(t.total_s, prefix = 'Total Time')



if __name__ == '__main__':
    asyncio.run(run_tests(
        start_n = 5,
        runs = 40,
        print_every = 5,
    ))