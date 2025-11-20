"""
Benchmark Optimized Connection Pool vs Baseline

Compares performance between:
- Baseline redis-py
- KVDB baseline connection pool
- KVDB optimized connection pool
"""

import asyncio
import time
import statistics
from typing import List, Dict
from dataclasses import dataclass

from redis.asyncio import Redis as BaseRedis
import sys
sys.path.insert(0, '/home/runner/work/kvdb-py/kvdb-py')

# Import after path setup
from kvdb.components.connection_pool import AsyncConnectionPool
from kvdb.components.connection_pool_optimized import OptimizedAsyncConnectionPool
from kvdb.components.client import AsyncKVDB


@dataclass
class ComparisonResult:
    name: str
    impl_type: str
    throughput: float
    avg_latency: float
    p95_latency: float
    p99_latency: float


async def benchmark_implementation(name: str, client, num_ops: int = 1000, concurrency: int = 10):
    """Benchmark a specific implementation"""
    latencies = []
    
    async def worker(worker_id: int, ops_per_worker: int):
        for i in range(ops_per_worker):
            op_start = time.time()
            try:
                key = f"bench_{worker_id}_{i}"
                await client.set(key, f"value_{i}")
                await client.get(key)
                latencies.append(time.time() - op_start)
            except Exception as e:
                print(f"Error in {name}: {e}")
    
    ops_per_worker = num_ops // concurrency
    start = time.time()
    
    tasks = [worker(i, ops_per_worker) for i in range(concurrency)]
    await asyncio.gather(*tasks)
    
    duration = time.time() - start
    total_ops = ops_per_worker * concurrency * 2
    
    return ComparisonResult(
        name=name,
        impl_type=name.split()[0],
        throughput=total_ops / duration,
        avg_latency=statistics.mean(latencies) if latencies else 0,
        p95_latency=statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else 0,
        p99_latency=statistics.quantiles(latencies, n=100)[98] if len(latencies) > 100 else 0,
    )


async def run_comparison(url: str = "redis://localhost:6379/0"):
    """Run comparison benchmarks"""
    print("=" * 80)
    print("Connection Pool Optimization Comparison")
    print("=" * 80)
    print()
    
    results = []
    
    # Test different concurrency levels
    concurrency_levels = [1, 10, 50, 100]
    num_ops = 1000
    
    for concurrency in concurrency_levels:
        print(f"\n{'=' * 80}")
        print(f"Concurrency Level: {concurrency} workers, {num_ops} ops")
        print(f"{'=' * 80}\n")
        
        # 1. Baseline redis-py
        print("Testing: Baseline redis-py...")
        redis_client = BaseRedis.from_url(url, max_connections=50)
        try:
            await redis_client.ping()
            result = await benchmark_implementation(
                f"Redis-py Baseline (C={concurrency})",
                redis_client,
                num_ops,
                concurrency
            )
            results.append(result)
            print(f"  Throughput: {result.throughput:.2f} ops/s")
            print(f"  P95 Latency: {result.p95_latency*1000:.2f}ms")
            print()
        finally:
            await redis_client.aclose()
        
        # 2. KVDB Baseline
        print("Testing: KVDB Baseline Connection Pool...")
        pool = AsyncConnectionPool.from_url(url, max_connections=50)
        kvdb_client = AsyncKVDB(connection_pool=pool)
        try:
            await kvdb_client.ping()
            result = await benchmark_implementation(
                f"KVDB Baseline (C={concurrency})",
                kvdb_client,
                num_ops,
                concurrency
            )
            results.append(result)
            print(f"  Throughput: {result.throughput:.2f} ops/s")
            print(f"  P95 Latency: {result.p95_latency*1000:.2f}ms")
            print()
        finally:
            await kvdb_client.aclose()
        
        # 3. KVDB Optimized
        print("Testing: KVDB Optimized Connection Pool...")
        opt_pool = OptimizedAsyncConnectionPool.from_url(
            url,
            max_connections=50,
            enable_metrics=True,
            health_check_interval=0.5,
            min_idle_connections=10
        )
        opt_client = AsyncKVDB(connection_pool=opt_pool)
        try:
            await opt_client.ping()
            # Warm the pool
            await opt_pool.warm_pool(10)
            
            result = await benchmark_implementation(
                f"KVDB Optimized (C={concurrency})",
                opt_client,
                num_ops,
                concurrency
            )
            results.append(result)
            print(f"  Throughput: {result.throughput:.2f} ops/s")
            print(f"  P95 Latency: {result.p95_latency*1000:.2f}ms")
            
            # Show metrics
            metrics = opt_pool.get_metrics()
            if metrics:
                print(f"\n  Pool Metrics:")
                print(f"    Active/Idle/Total: {metrics['active_connections']}/{metrics['idle_connections']}/{metrics['total_connections']}")
                print(f"    Avg Acquisition Time: {metrics['avg_acquisition_time_ms']:.3f}ms")
                print(f"    Lock Wait Time: {metrics['total_lock_wait_time_ms']:.3f}ms")
            print()
        finally:
            await opt_client.aclose()
    
    # Generate comparison report
    print("\n" + "=" * 80)
    print("PERFORMANCE COMPARISON REPORT")
    print("=" * 80 + "\n")
    
    # Group by concurrency level
    by_concurrency = {}
    for result in results:
        # Extract concurrency from name
        concurrency = result.name.split("C=")[1].split(")")[0]
        if concurrency not in by_concurrency:
            by_concurrency[concurrency] = []
        by_concurrency[concurrency].append(result)
    
    for concurrency, group_results in sorted(by_concurrency.items(), key=lambda x: int(x[0])):
        print(f"\nConcurrency = {concurrency} workers:")
        print("-" * 80)
        
        # Sort by throughput
        group_results.sort(key=lambda x: x.throughput, reverse=True)
        
        baseline = None
        for i, result in enumerate(group_results, 1):
            if "Baseline" in result.impl_type and baseline is None:
                baseline = result.throughput
            
            improvement = ""
            if baseline and "Optimized" in result.impl_type:
                pct = ((result.throughput - baseline) / baseline * 100)
                improvement = f" ({pct:+.1f}% vs baseline)"
            
            rank = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"  {i}"
            print(f"{rank} {result.name:40} | "
                  f"{result.throughput:10.2f} ops/s | "
                  f"P95: {result.p95_latency*1000:6.2f}ms{improvement}")
    
    print("\n" + "=" * 80)
    print("Comparison complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_comparison())
