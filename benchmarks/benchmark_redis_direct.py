"""
Direct redis-py Async Performance Benchmark

Benchmarks redis-py async performance directly to establish baselines.
"""

import asyncio
import time
import statistics
from typing import List, Dict, Any
from dataclasses import dataclass, field

try:
    from redis.asyncio import Redis
    from redis.asyncio.connection import ConnectionPool
except ImportError:
    from redis import asyncio as redis_asyncio
    Redis = redis_asyncio.Redis
    ConnectionPool = redis_asyncio.ConnectionPool


@dataclass
class BenchmarkResult:
    """Store benchmark results"""
    name: str
    server_type: str
    operations: int
    duration: float
    throughput: float
    avg_latency: float
    p50_latency: float
    p95_latency: float
    p99_latency: float
    errors: int = 0
    latencies: List[float] = field(default_factory=list)


class RedisBenchmark:
    """Benchmark redis-py directly"""
    
    def __init__(self, url: str, server_type: str = "redis", pool_size: int = 10):
        self.url = url
        self.server_type = server_type
        self.pool_size = pool_size
        self.client = None
    
    async def setup(self):
        """Initialize connection pool"""
        self.client = Redis.from_url(
            self.url,
            max_connections=self.pool_size,
            socket_connect_timeout=5,
            socket_timeout=5,
            decode_responses=False,
        )
        # Warm up connection
        await self.client.ping()
    
    async def cleanup(self):
        """Clean up resources"""
        if self.client:
            await self.client.aclose()
    
    async def benchmark_single_ops(self, num_ops: int = 1000) -> BenchmarkResult:
        """Benchmark sequential single operations"""
        latencies = []
        errors = 0
        
        start = time.time()
        for i in range(num_ops):
            op_start = time.time()
            try:
                await self.client.set(f"bench_key_{i}", f"value_{i}")
                await self.client.get(f"bench_key_{i}")
                latencies.append(time.time() - op_start)
            except Exception as e:
                errors += 1
                print(f"Error in single_ops: {e}")
        
        duration = time.time() - start
        
        return BenchmarkResult(
            name="Single Sequential Operations",
            server_type=self.server_type,
            operations=num_ops * 2,
            duration=duration,
            throughput=(num_ops * 2) / duration,
            avg_latency=statistics.mean(latencies) if latencies else 0,
            p50_latency=statistics.median(latencies) if latencies else 0,
            p95_latency=statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else 0,
            p99_latency=statistics.quantiles(latencies, n=100)[98] if len(latencies) > 100 else 0,
            errors=errors,
            latencies=latencies,
        )
    
    async def benchmark_concurrent_ops(self, num_ops: int = 1000, concurrency: int = 10) -> BenchmarkResult:
        """Benchmark concurrent operations"""
        latencies = []
        errors = 0
        
        async def worker(worker_id: int, ops_per_worker: int):
            nonlocal errors
            for i in range(ops_per_worker):
                op_start = time.time()
                try:
                    key = f"bench_concurrent_{worker_id}_{i}"
                    await self.client.set(key, f"value_{i}")
                    await self.client.get(key)
                    latencies.append(time.time() - op_start)
                except Exception as e:
                    errors += 1
                    print(f"Error in concurrent_ops worker {worker_id}: {e}")
        
        ops_per_worker = num_ops // concurrency
        start = time.time()
        
        tasks = [worker(i, ops_per_worker) for i in range(concurrency)]
        await asyncio.gather(*tasks)
        
        duration = time.time() - start
        total_ops = ops_per_worker * concurrency * 2
        
        return BenchmarkResult(
            name=f"Concurrent Operations ({concurrency} workers)",
            server_type=self.server_type,
            operations=total_ops,
            duration=duration,
            throughput=total_ops / duration,
            avg_latency=statistics.mean(latencies) if latencies else 0,
            p50_latency=statistics.median(latencies) if latencies else 0,
            p95_latency=statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else 0,
            p99_latency=statistics.quantiles(latencies, n=100)[98] if len(latencies) > 100 else 0,
            errors=errors,
            latencies=latencies,
        )
    
    async def benchmark_pipeline(self, num_ops: int = 1000, batch_size: int = 100) -> BenchmarkResult:
        """Benchmark pipeline operations"""
        latencies = []
        errors = 0
        
        start = time.time()
        for batch_start in range(0, num_ops, batch_size):
            op_start = time.time()
            try:
                pipe = self.client.pipeline()
                for i in range(batch_start, min(batch_start + batch_size, num_ops)):
                    pipe.set(f"bench_pipe_{i}", f"value_{i}")
                    pipe.get(f"bench_pipe_{i}")
                await pipe.execute()
                latencies.append(time.time() - op_start)
            except Exception as e:
                errors += 1
                print(f"Error in pipeline: {e}")
        
        duration = time.time() - start
        
        return BenchmarkResult(
            name=f"Pipeline Operations (batch_size={batch_size})",
            server_type=self.server_type,
            operations=num_ops * 2,
            duration=duration,
            throughput=(num_ops * 2) / duration,
            avg_latency=statistics.mean(latencies) if latencies else 0,
            p50_latency=statistics.median(latencies) if latencies else 0,
            p95_latency=statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else 0,
            p99_latency=statistics.quantiles(latencies, n=100)[98] if len(latencies) > 100 else 0,
            errors=errors,
            latencies=latencies,
        )


async def run_benchmarks(servers: Dict[str, str]):
    """Run benchmarks against multiple servers"""
    print("=" * 80)
    print("Redis-py Async Performance Benchmark")
    print("=" * 80)
    print()
    
    all_results = []
    
    for server_name, url in servers.items():
        print(f"\n{'=' * 80}")
        print(f"Benchmarking: {server_name}")
        print(f"URL: {url}")
        print(f"{'=' * 80}\n")
        
        benchmark = RedisBenchmark(url, server_type=server_name, pool_size=20)
        
        try:
            await benchmark.setup()
            print("✓ Connection established\n")
            
            benchmarks = [
                ("Single Sequential Operations", lambda: benchmark.benchmark_single_ops(1000)),
                ("Concurrent Operations (10 workers)", lambda: benchmark.benchmark_concurrent_ops(1000, 10)),
                ("Concurrent Operations (50 workers)", lambda: benchmark.benchmark_concurrent_ops(1000, 50)),
                ("Pipeline Operations (batch=50)", lambda: benchmark.benchmark_pipeline(1000, 50)),
                ("Pipeline Operations (batch=100)", lambda: benchmark.benchmark_pipeline(1000, 100)),
            ]
            
            for bench_name, bench_func in benchmarks:
                print(f"Running: {bench_name}...")
                result = await bench_func()
                all_results.append(result)
                
                print(f"  Operations: {result.operations}")
                print(f"  Duration: {result.duration:.4f}s")
                print(f"  Throughput: {result.throughput:.2f} ops/s")
                print(f"  Avg Latency: {result.avg_latency*1000:.2f}ms")
                print(f"  P95 Latency: {result.p95_latency*1000:.2f}ms")
                print(f"  P99 Latency: {result.p99_latency*1000:.2f}ms")
                if result.errors > 0:
                    print(f"  ⚠ Errors: {result.errors}")
                print()
            
        except Exception as e:
            print(f"✗ Failed to benchmark {server_name}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await benchmark.cleanup()
    
    return all_results


def generate_comparison_report(results: List[BenchmarkResult]):
    """Generate comparison report"""
    print("\n" + "=" * 80)
    print("COMPARISON REPORT")
    print("=" * 80 + "\n")
    
    by_benchmark = {}
    for result in results:
        if result.name not in by_benchmark:
            by_benchmark[result.name] = []
        by_benchmark[result.name].append(result)
    
    for bench_name, bench_results in by_benchmark.items():
        print(f"\n{bench_name}:")
        print("-" * 80)
        
        bench_results.sort(key=lambda x: x.throughput, reverse=True)
        
        for i, result in enumerate(bench_results, 1):
            rank = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"  {i}"
            print(f"{rank} {result.server_type:20} | "
                  f"Throughput: {result.throughput:10.2f} ops/s | "
                  f"P95: {result.p95_latency*1000:6.2f}ms | "
                  f"P99: {result.p99_latency*1000:6.2f}ms")


async def main():
    """Main entry point"""
    servers = {
        "Redis (6379)": "redis://localhost:6379/0",
        "Redis (6380)": "redis://localhost:6380/0",
    }
    
    results = await run_benchmarks(servers)
    generate_comparison_report(results)
    
    print("\n" + "=" * 80)
    print("Benchmark complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
