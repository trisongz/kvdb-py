from __future__ import annotations

"""
ThreadPool Implementation
"""

# from lazyops.libs.pooler import (
#     ThreadPooler as Pooler,
#     ensure_coro,
#     is_coro_func,
#     amap_iterable,
#     get_concurrency_limit, 
#     set_concurrency_limit
# )


from lzl.pool import (
    ThreadPool as Pooler,
    ensure_coro,
    is_coro_func,
    amap_iterable,
    get_concurrency_limit, 
    set_concurrency_limit
)

