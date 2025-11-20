"""
Simple Benchmark - Direct redis-py Only

This avoids kvdb imports and just benchmarks redis-py baseline performance
"""

import asyncio
import time
import statistics
from typing import List
from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass
class Result:
    name: str
    throughput: float
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float


async def benchmark(name: str, client, num_ops: int, concurrency: int):
    """Run benchmark"""
    latencies = []
    
    async def worker(wid: int, ops: int):
        for i in range(ops):
            start = time.time()
            try:
                key = f"b_{wid}_{i}"
                await client.set(key, f"v_{i}")
                await client.get(key)
                latencies.append(time.time() - start)
            except Exception as e:
                print(f"Error: {e}")
    
    ops_per = num_ops // concurrency
    start = time.time()
    await asyncio.gather(*[worker(i, ops_per) for i in range(concurrency)])
    duration = time.time() - start
    
    total_ops = ops_per * concurrency * 2
    return Result(
        name=name,
        throughput=total_ops / duration,
        avg_latency_ms=statistics.mean(latencies) * 1000 if latencies else 0,
        p95_latency_ms=statistics.quantiles(latencies, n=20)[18] * 1000 if len(latencies) > 20 else 0,
        p99_latency_ms=statistics.quantiles(latencies, n=100)[98] * 1000 if len(latencies) > 100 else 0,
    )


async def main():
    print("=" * 80)
    print("Redis Performance Benchmark")
    print("=" * 80)
    
    url = "redis://localhost:6379/0"
    results = []
    
    for concurrency in [1, 10, 50, 100]:
        print(f"\nConcurrency: {concurrency}")
        print("-" * 80)
        
        client = Redis.from_url(url, max_connections=200)
        await client.ping()
        
        result = await benchmark(f"C={concurrency}", client, 1000, concurrency)
        results.append(result)
        
        print(f"Throughput: {result.throughput:.2f} ops/s")
        print(f"Avg Latency: {result.avg_latency_ms:.2f}ms")
        print(f"P95 Latency: {result.p95_latency_ms:.2f}ms")
        print(f"P99 Latency: {result.p99_latency_ms:.2f}ms")
        
        await client.aclose()
    
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    for r in results:
        print(f"{r.name:15} | {r.throughput:10.2f} ops/s | P95: {r.p95_latency_ms:6.2f}ms")


if __name__ == "__main__":
    asyncio.run(main())
