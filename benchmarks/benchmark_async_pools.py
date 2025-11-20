"""
Async Connection Pool Performance Benchmark

Benchmarks async connection pool performance against:
- Redis
- Valkey (Redis fork)
- Dragonfly

Measures:
- Connection acquisition time
- Command throughput
- Concurrent request handling
- Connection pool overhead
"""

import asyncio
import time
import statistics
from typing import List, Dict, Any
from dataclasses import dataclass, field
import sys

# Add parent directory to path
sys.path.insert(0, '/home/runner/work/kvdb-py/kvdb-py')

from kvdb.components.connection_pool import AsyncConnectionPool
from kvdb.components.client import AsyncKVDB


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
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'server_type': self.server_type,
            'operations': self.operations,
            'duration': f'{self.duration:.4f}s',
            'throughput': f'{self.throughput:.2f} ops/s',
            'avg_latency': f'{self.avg_latency*1000:.2f}ms',
            'p50_latency': f'{self.p50_latency*1000:.2f}ms',
            'p95_latency': f'{self.p95_latency*1000:.2f}ms',
            'p99_latency': f'{self.p99_latency*1000:.2f}ms',
            'errors': self.errors,
        }


class AsyncPoolBenchmark:
    """Benchmark async connection pools"""
    
    def __init__(self, url: str, server_type: str = "redis", pool_size: int = 10):
        self.url = url
        self.server_type = server_type
        self.pool_size = pool_size
        self.pool = None
        self.client = None
    
    async def setup(self):
        """Initialize connection pool"""
        self.pool = AsyncConnectionPool.from_url(
            self.url,
            max_connections=self.pool_size,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        self.client = AsyncKVDB(connection_pool=self.pool)
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
            operations=num_ops * 2,  # set + get
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
        total_ops = ops_per_worker * concurrency * 2  # set + get
        
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
            operations=num_ops * 2,  # set + get
            duration=duration,
            throughput=(num_ops * 2) / duration,
            avg_latency=statistics.mean(latencies) if latencies else 0,
            p50_latency=statistics.median(latencies) if latencies else 0,
            p95_latency=statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else 0,
            p99_latency=statistics.quantiles(latencies, n=100)[98] if len(latencies) > 100 else 0,
            errors=errors,
            latencies=latencies,
        )
    
    async def benchmark_connection_acquisition(self, num_acquisitions: int = 1000) -> BenchmarkResult:
        """Benchmark connection acquisition time"""
        latencies = []
        errors = 0
        
        start = time.time()
        for i in range(num_acquisitions):
            op_start = time.time()
            try:
                conn = await self.pool.get_connection("PING")
                latencies.append(time.time() - op_start)
                await self.pool.release(conn)
            except Exception as e:
                errors += 1
                print(f"Error in connection_acquisition: {e}")
        
        duration = time.time() - start
        
        return BenchmarkResult(
            name="Connection Acquisition",
            server_type=self.server_type,
            operations=num_acquisitions,
            duration=duration,
            throughput=num_acquisitions / duration,
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
    print("KVDB Async Connection Pool Benchmark")
    print("=" * 80)
    print()
    
    all_results = []
    
    for server_name, url in servers.items():
        print(f"\n{'=' * 80}")
        print(f"Benchmarking: {server_name}")
        print(f"URL: {url}")
        print(f"{'=' * 80}\n")
        
        benchmark = AsyncPoolBenchmark(url, server_type=server_name, pool_size=20)
        
        try:
            await benchmark.setup()
            print("✓ Connection established\n")
            
            # Run different benchmark scenarios
            benchmarks = [
                ("Single Sequential Operations", lambda: benchmark.benchmark_single_ops(1000)),
                ("Concurrent Operations (10 workers)", lambda: benchmark.benchmark_concurrent_ops(1000, 10)),
                ("Concurrent Operations (50 workers)", lambda: benchmark.benchmark_concurrent_ops(1000, 50)),
                ("Pipeline Operations (batch=50)", lambda: benchmark.benchmark_pipeline(1000, 50)),
                ("Pipeline Operations (batch=100)", lambda: benchmark.benchmark_pipeline(1000, 100)),
                ("Connection Acquisition", lambda: benchmark.benchmark_connection_acquisition(1000)),
            ]
            
            for bench_name, bench_func in benchmarks:
                print(f"Running: {bench_name}...")
                result = await bench_func()
                all_results.append(result)
                
                # Print results
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
    
    # Group by benchmark type
    by_benchmark = {}
    for result in results:
        if result.name not in by_benchmark:
            by_benchmark[result.name] = []
        by_benchmark[result.name].append(result)
    
    for bench_name, bench_results in by_benchmark.items():
        print(f"\n{bench_name}:")
        print("-" * 80)
        
        # Sort by throughput
        bench_results.sort(key=lambda x: x.throughput, reverse=True)
        
        for i, result in enumerate(bench_results, 1):
            rank = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"  {i}"
            print(f"{rank} {result.server_type:15} | "
                  f"Throughput: {result.throughput:10.2f} ops/s | "
                  f"P95: {result.p95_latency*1000:6.2f}ms | "
                  f"P99: {result.p99_latency*1000:6.2f}ms")


async def main():
    """Main entry point"""
    # Define servers to benchmark
    servers = {
        "Redis (6379)": "redis://localhost:6379/0",
        "Redis (6380)": "redis://localhost:6380/0",
    }
    
    # Check for Valkey and Dragonfly
    # These would need to be started separately
    # servers["Valkey"] = "redis://localhost:6381/0"
    # servers["Dragonfly"] = "redis://localhost:6382/0"
    
    results = await run_benchmarks(servers)
    generate_comparison_report(results)
    
    print("\n" + "=" * 80)
    print("Benchmark complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
