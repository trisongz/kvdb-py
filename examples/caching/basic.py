"""
A Very basic demonstration of how to use cachify

Without any arguments, cachify will use the default settings and initialize
a default session.
"""

import time
import asyncio
from lazyops.utils.times import Timer
from kvdb.io import cachify
from kvdb.utils.logs import logger

DEBUG_ENABLED = False

@cachify.register(ttl = 10, verbosity = 2 if DEBUG_ENABLED else None, cache_max_size = 15)
async def async_fibonacci(number: int):
    if number == 0: return 0
    elif number == 1: return 1
    return await async_fibonacci(number - 1) + await async_fibonacci(number - 2)

@cachify.register(ttl = 10, verbosity = 2 if DEBUG_ENABLED else None)
def fibonacci(number: int):
    if number == 0: return 0
    elif number == 1: return 1
    return fibonacci(number - 1) + fibonacci(number - 2)

# No Cache Versions
async def async_fibonacci_nc(number: int):
    if number == 0: return 0
    elif number == 1: return 1
    return await async_fibonacci_nc(number - 1) + await async_fibonacci_nc(number - 2)

def fibonacci_nc(number: int):
    if number == 0: return 0
    elif number == 1: return 1
    return fibonacci_nc(number - 1) + fibonacci_nc(number - 2)


async def run_tests(
    start_n: int = 1,
    runs: int = 10,
    print_every: int = 5,
):
    
    """
    Test that both results are the same.
    """

    t = Timer(format_ms=True)

    # Test Sync
    st = Timer(format_ms=True)
    for i in range(runs):
        r = fibonacci(start_n+i)
        d = st.duration_s
        if i % print_every == 0:
            logger.info(f'[Sync - {i}/{runs}] Result: {r} | Time: {d}')
    logger.info(f'[Sync] Cache Average Time: {st.total_average_s(runs)} | Total Time: {st.total_s}')
    logger.info(fibonacci.cache_info(), prefix = '[Sync] Cache Info')

    # Test Async
    at = Timer(format_ms=True)
    for i in range(runs):
        r = await async_fibonacci(start_n+i)
        d = at.duration_s
        if i % print_every == 0:
            logger.info(f'[Async - {i}/{runs}] Result: {r} | Time: {d}')
    logger.info(f'[Async] Cache Average Time: {at.total_average_s(runs)} | Total Time: {at.total_s}')
    logger.info(await async_fibonacci.cache_info(), prefix = '[Async] Cache Info')
    logger.info(t.total_s, prefix = 'Total Time')

    # Clear the Cache
    fibonacci.clear()
    logger.info(fibonacci.cache_info(), prefix = '[Sync] Cache Info')

    await async_fibonacci.clear()
    logger.info(await async_fibonacci.cache_info(), prefix = '[Async] Cache Info')

    logger.info('Testing Non-Cached Functions')
    t = Timer(format_ms=True)

    # Test Sync
    st = Timer(format_ms=True)
    for i in range(runs):
        r = fibonacci_nc(start_n+i)
        d = st.duration_s
        if i % print_every == 0:
            logger.info(f'[Sync - {i}/{runs}] Result: {r} | Time: {d}')
    logger.info(f'[Sync] Cache Average Time: {st.total_average_s(runs)} | Total Time: {st.total_s}')

    # Test Async
    at = Timer(format_ms=True)
    for i in range(runs):
        r = await async_fibonacci_nc(start_n+i)
        d = at.duration_s
        if i % print_every == 0:
            logger.info(f'[Async - {i}/{runs}] Result: {r} | Time: {d}')
    logger.info(f'[Async] Cache Average Time: {at.total_average_s(runs)} | Total Time: {at.total_s}')
    logger.info(t.total_s, prefix = 'Total Time')



if __name__ == '__main__':
    asyncio.run(run_tests(
        start_n = 5,
        runs = 10,
        print_every = 5,
    ))