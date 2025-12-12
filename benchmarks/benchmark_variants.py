import asyncio
import time
import yaml
import statistics
import logging
from pathlib import Path
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

from kvdb import KVDBClient
from kvdb.components.cluster import AsyncKVDBCluster
from redis.asyncio.sentinel import Sentinel as AsyncSentinel
from redis.sentinel import Sentinel as SyncSentinel
from redis.asyncio.cluster import RedisCluster as AsyncRedisCluster
from redis.cluster import RedisCluster as SyncRedisCluster

# Import KVDB Connection Pools
from kvdb.components.connection_pool import (
    ConnectionPool as KVDBConnectionPool,
    BlockingConnectionPool as KVDBBlockingConnectionPool,
    AsyncConnectionPool as KVDBAsyncConnectionPool,
    AsyncBlockingConnectionPool as KVDBAsyncBlockingConnectionPool,
)
from kvdb.components.connection_pool_optimized import OptimizedAsyncConnectionPool

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BenchmarkVariants")

class BenchmarkRunner:
    def __init__(self, config_path: str, results_dir: str):
        self.config_path = Path(config_path)
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.config = self._load_config()
        self.results = {}
        self.num_runs = 3

    def _load_config(self) -> List[Dict[str, Any]]:
        with open(self.config_path, 'r') as f:
            data = yaml.safe_load(f)
            return data.get('benchmarks', [])

    async def run_benchmarks(self):
        # KVDBClient is a singleton instance
        # _ = KVDBClient() # Removed as it causes TypeError if KVDBClient is already the instance
        
        # We need to run benchmarks for both Async and Sync modes, and for different Pool types.
        
        # Define Pool Variants
        # Mode -> List of (PoolClassName, PoolClass)
        pool_variants = {
            'sync': [
                ('ConnectionPool', KVDBConnectionPool),
                ('BlockingConnectionPool', KVDBBlockingConnectionPool),
            ],
            'async': [
                ('AsyncConnectionPool', KVDBAsyncConnectionPool),
                ('AsyncBlockingConnectionPool', KVDBAsyncBlockingConnectionPool),
                ('OptimizedAsyncConnectionPool', OptimizedAsyncConnectionPool),
            ]
        }

        for entry in self.config:
            name = entry['name']
            base_url = entry['url']
            client_type = entry.get('type', 'standalone')
            
            # Structure: name -> mode -> pool_name -> runs
            self.results[name] = {'async': {}, 'sync': {}}
            
            for mode, pools in pool_variants.items():
                
                if client_type != 'standalone':
                    current_pools = [('Default', None)]
                else:
                    current_pools = pools

                for pool_name, pool_class in current_pools:
                    self.results[name][mode][pool_name] = []
                    
                    logger.info(f"Starting: {name} ({client_type}) | Mode: {mode} | Pool: {pool_name}")
                    
                    for run_idx in range(self.num_runs):
                        # Clear KVDBClient Pool Cache to ensure new pools are created with correct params
                        try:
                            # Access internal context to clear pools. 
                            client_instance = KVDBClient
                            if hasattr(client_instance, 'pools') and hasattr(client_instance.pools, 'clear'):
                                client_instance.pools.clear()
                            elif hasattr(client_instance, 'c') and hasattr(client_instance.c, 'pools'):
                                client_instance.c.pools.clear()
                        except Exception as e:
                            logger.warning(f"Failed to clear KVDBClient pool cache: {e}")

                        logger.info(f"  Run {run_idx + 1}/{self.num_runs}...")
                        try:
                            stats = await self._execute_benchmark(
                                name, base_url, client_type, mode, pool_class, run_idx
                            )
                            self.results[name][mode][pool_name].append(stats)
                        except Exception as e:
                            import traceback
                            logger.error(f"Failed run {run_idx}: {e}")
                            self.results[name][mode][pool_name].append({"error": str(e)})

        self._save_results()

    async def _execute_benchmark(self, name: str, url: str, client_type: str, mode: str, pool_class: Any, run_idx: int) -> Dict[str, float]:
        client = None
        session = None
        
        try:
            if client_type == 'cluster':
                if mode == 'async':
                    client = AsyncKVDBCluster.from_url(url)
                    await client.initialize()
                else:
                    client = SyncRedisCluster.from_url(url)
            
            elif client_type == 'sentinel':
                clean_url = url.replace("redis+sentinel://", "")
                host_port, path = clean_url.split("/", 1)
                host, port = host_port.split(":")
                port = int(port)
                service_name, db = path.split("/")
                db = int(db)

                if mode == 'async':
                    sentinel = AsyncSentinel([(host, port)], socket_timeout=0.1)
                    client = await sentinel.master_for(service_name, socket_timeout=0.1, db=db)
                else:
                    sentinel = SyncSentinel([(host, port)], socket_timeout=0.1)
                    client = sentinel.master_for(service_name, socket_timeout=0.1, db=db)

            else:
                # Standalone: We can inject the pool class
                session_name = f"bench_{name}_{mode}_{pool_class.__name__ if pool_class else 'Default'}_{run_idx}_{time.time()}"
                
                # Prepare kwargs
                kwargs = {
                    'pool_max_connections': 50,
                    'apool_max_connections': 50
                }
                if pool_class:
                    if mode == 'async':
                        kwargs['apool_class'] = pool_class
                    else:
                        kwargs['pool_class'] = pool_class
                
                # KVDBClient should use pool_max_connections from kwargs to limit pool size (preventing BlockingConnectionPool hang)
                session = KVDBClient.get_session(name=session_name, url=url, **kwargs)
                
                if mode == 'async':
                    client = session.aclient
                else:
                    client = session.client
            
            # Warming
                if mode == 'async' and hasattr(client.connection_pool, 'warm_pool'):
                     await client.connection_pool.warm_pool()

            # Ping
            if mode == 'async':
                await client.ping()
                return await self._run_async_operations(client, name)
            else:
                client.ping()
                return self._run_sync_operations(client, name)

        finally:
            if client:
                if mode == 'async':
                    if hasattr(client, 'aclose'):
                        await client.aclose()
                    elif hasattr(client, 'close'):
                        client.close()
                else:
                    if hasattr(client, 'close'):
                        client.close()

    async def _run_async_operations(self, client, name: str) -> Dict[str, float]:
        ops_count = 10000
        key_prefix = f"bench:{name}:async:"
        
        # SET Benchmark
        start_time = time.time()
        for i in range(ops_count):
            await client.set(f"{key_prefix}{i}", f"value_{i}")
        set_duration = time.time() - start_time
        set_ops = ops_count / set_duration

        # GET Benchmark
        start_time = time.time()
        for i in range(ops_count):
            await client.get(f"{key_prefix}{i}")
        get_duration = time.time() - start_time
        get_ops = ops_count / get_duration
        
        # DEL Benchmark
        start_time = time.time()
        for i in range(ops_count):
            await client.delete(f"{key_prefix}{i}")
        del_duration = time.time() - start_time
        del_ops = ops_count / del_duration

        # Pipeline Benchmark (Async)
        pipeline_ops_count = ops_count
        pipeline_batch_size = 100
        start_time = time.time()
        async with client.pipeline() as pipe:
             for i in range(0, pipeline_ops_count, pipeline_batch_size):
                 for j in range(pipeline_batch_size):
                     pipe.set(f"{key_prefix}pipe:{i+j}", f"val_{i+j}")
                 await pipe.execute()
        pipe_duration = time.time() - start_time
        pipe_ops = pipeline_ops_count / pipe_duration

        return {
            "set_ops_per_sec": set_ops,
            "get_ops_per_sec": get_ops,
            "del_ops_per_sec": del_ops,
            "pipe_ops_per_sec": pipe_ops
        }

    def _run_sync_operations(self, client, name: str) -> Dict[str, float]:
        ops_count = 10000
        key_prefix = f"bench:{name}:sync:"
        
        # SET Benchmark
        start_time = time.time()
        for i in range(ops_count):
            client.set(f"{key_prefix}{i}", f"value_{i}")
        set_duration = time.time() - start_time
        set_ops = ops_count / set_duration

        # GET Benchmark
        start_time = time.time()
        for i in range(ops_count):
            client.get(f"{key_prefix}{i}")
        get_duration = time.time() - start_time
        get_ops = ops_count / get_duration
        
        # DEL Benchmark
        start_time = time.time()
        for i in range(ops_count):
            client.delete(f"{key_prefix}{i}")
        del_duration = time.time() - start_time
        del_ops = ops_count / del_duration

        # Pipeline Benchmark (Sync)
        pipeline_ops_count = ops_count
        pipeline_batch_size = 100
        start_time = time.time()
        with client.pipeline() as pipe:
             for i in range(0, pipeline_ops_count, pipeline_batch_size):
                 for j in range(pipeline_batch_size):
                     pipe.set(f"{key_prefix}pipe:{i+j}", f"val_{i+j}")
                 pipe.execute()
        pipe_duration = time.time() - start_time
        pipe_ops = pipeline_ops_count / pipe_duration

        return {
            "set_ops_per_sec": set_ops,
            "get_ops_per_sec": get_ops,
            "del_ops_per_sec": del_ops,
            "pipe_ops_per_sec": pipe_ops
        }

    def _save_results(self):
        output_file = self.results_dir / "results_detailed.txt"
        md_file = self.results_dir / "BENCHMARK_REPORT.md"
        
        with open(output_file, 'w') as f:
            for name, modes in self.results.items():
                f.write(f"=== {name} ===\n")
                for mode, pools in modes.items():
                    f.write(f"  [{mode.upper()}]\n")
                    for pool_name, runs in pools.items():
                        f.write(f"    Pool: {pool_name}\n")
                        for i, run in enumerate(runs):
                            f.write(f"      Run {i+1}: {run}\n")
                f.write("\n")
                
        with open(md_file, 'w') as f:
            f.write("# Benchmark Results (Averaged over 3 runs)\n\n")
            f.write("| Service | Mode | Pool | SET (ops/s) | GET (ops/s) | DEL (ops/s) | PIPE (ops/s) |\n")
            f.write("|---------|------|------|-------------|-------------|-------------|--------------|\n")
            
            for name, modes in self.results.items():
                for mode, pools in modes.items():
                    for pool_name, runs in pools.items():
                        valid_runs = [r for r in runs if "error" not in r]
                        
                        if not valid_runs:
                            f.write(f"| {name} | {mode.upper()} | {pool_name} | Error | Error | Error |\n")
                            continue
                            
                        avg_set = statistics.mean([r['set_ops_per_sec'] for r in valid_runs])
                        avg_get = statistics.mean([r['get_ops_per_sec'] for r in valid_runs])
                        avg_del = statistics.mean([r['del_ops_per_sec'] for r in valid_runs])
                        avg_pipe = statistics.mean([r.get('pipe_ops_per_sec', 0) for r in valid_runs])
                        
                        f.write(f"| {name} | {mode.upper()} | {pool_name} | {avg_set:.0f} | {avg_get:.0f} | {avg_del:.0f} | {avg_pipe:.0f} |\n")

if __name__ == "__main__":
    runner = BenchmarkRunner(
        config_path="benchmarks/benchmark_setup_config.yaml",
        results_dir="benchmarks/results"
    )
    asyncio.run(runner.run_benchmarks())
