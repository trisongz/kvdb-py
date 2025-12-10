# Benchmark Results (Averaged over 3 runs)

| Service | Mode | Pool | SET (ops/s) | GET (ops/s) | DEL (ops/s) | PIPE (ops/s) |
|---------|------|------|-------------|-------------|-------------|--------------|
| Standard Redis | ASYNC | AsyncConnectionPool | 3805 | 4119 | 3986 | 111751 |
| Standard Redis | ASYNC | AsyncBlockingConnectionPool | 3733 | 3705 | 3879 | 115459 |
| Standard Redis | ASYNC | OptimizedAsyncConnectionPool | 3842 | 3985 | 3824 | 113648 |
| Standard Redis | SYNC | ConnectionPool | 6000 | 5926 | 6718 | 150865 |
| Standard Redis | SYNC | BlockingConnectionPool | 5985 | 6169 | 6126 | 126682 |
| KeyDB | ASYNC | AsyncConnectionPool | 3943 | 4163 | 4491 | 108933 |
| KeyDB | ASYNC | AsyncBlockingConnectionPool | 3704 | 4244 | 4018 | 118320 |
| KeyDB | ASYNC | OptimizedAsyncConnectionPool | 4364 | 4453 | 4260 | 113621 |
| KeyDB | SYNC | ConnectionPool | 5118 | 5808 | 6129 | 133929 |
| KeyDB | SYNC | BlockingConnectionPool | 5629 | 5792 | 4544 | 127300 |
| Dragonfly | ASYNC | AsyncConnectionPool | 3770 | 4113 | 3887 | 85827 |
| Dragonfly | ASYNC | AsyncBlockingConnectionPool | 3675 | 3942 | 3973 | 83501 |
| Dragonfly | ASYNC | OptimizedAsyncConnectionPool | 3921 | 4155 | 3975 | 93033 |
| Dragonfly | SYNC | ConnectionPool | 4085 | 4683 | 4586 | 96591 |
| Dragonfly | SYNC | BlockingConnectionPool | 4851 | 4702 | 4701 | 66267 |
| Valkey | ASYNC | AsyncConnectionPool | 5169 | 5321 | 5313 | 127546 |
| Valkey | ASYNC | AsyncBlockingConnectionPool | 4926 | 5422 | 5283 | 126038 |
| Valkey | ASYNC | OptimizedAsyncConnectionPool | 5266 | 5833 | 5554 | 135025 |
| Valkey | SYNC | ConnectionPool | 9161 | 8663 | 8140 | 169847 |
| Valkey | SYNC | BlockingConnectionPool | 8558 | 9452 | 8857 | 156023 |
| Redis Sentinel | ASYNC | Default | 5520 | 6597 | 5734 | 89515 |
| Redis Sentinel | SYNC | Default | 10304 | 11415 | 11073 | 161890 |

## PersistentDict Benchmarks (Optimized with Lua)

| Variant | Set (ops/s) | Get (ops/s) | Del (ops/s) | Iter (ops/s) |
|---------|-------------|-------------|-------------|--------------|
| Sync (HSET)          | 4520 | 4640 | 4830 | ~4.4M |
| Sync (No HSET)       | 4654 | 4695 | 4854 | ~2.7M |
| Async (HSET)         | 3332 | 3099 | 2635 | ~1.7M |
| Async (No HSET)      | 3138 | 3240 | 3033 | ~2.7M |

**Conclusion:**
- **Optimization Successful**: Implemented Lua scripts for atomic `HGET/HSET/HDEL` operations.
- **Performance**: `HSET` performance is now **comparable** to `No HSET` (direct keys) for Read/Write operations.
  - **Get**: ~2x improvement (2318 -> 4640 ops/s).
  - **Del**: ~2x improvement (2467 -> 4830 ops/s).
- **Recommendation**: Users can now safely use `hset_enabled=True` (default) without significant performance penalties compared to direct key usage.
