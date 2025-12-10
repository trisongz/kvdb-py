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

## PersistentDict Benchmarks

| Variant | Set (ops/s) | Get (ops/s) | Del (ops/s) | Iter (ops/s) |
|---------|-------------|-------------|-------------|--------------|
| Sync (HSET)          | 4724 | 2318 | 2467 | ~4.0M |
| Sync (No HSET)       | 4701 | 4985 | 4786 | ~2.9M |
| Async (HSET)         | 3637 | 1534 | 1732 | ~2.0M |
| Async (No HSET)      | 2897 | 3339 | 3792 | ~3.5M |

**Conclusion:**
- **No HSET (Direct Keys)** is significantly faster for **Get/Del** operations (~2x faster) compared to HSET, likely due to avoiding the extra expiration check roundtrip required by the HSET implementation.
- **Sync** is generally faster than Async for sequential checks.
- **Iteration** is extremely fast in all cases as it fetches keys in bulk.
