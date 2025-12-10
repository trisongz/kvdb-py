import asyncio
import time
import statistics
import logging
from typing import Dict, Any, List
from kvdb.components.persistence import KVDBStatefulBackend

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BenchmarkPersistence")

class PersistenceBenchmark:
    def __init__(self, url: str):
        self.url = url
        self.num_runs = 3
        self.ops_count = 5000
        self.results = {}

    async def run_benchmarks(self):
        # Variants to test
        variants = [
            ("Sync (HSET)", {"async_enabled": False, "hset_disabled": False, "base_key": "bench:pdict:sync:hset"}),
            ("Sync (No HSET)", {"async_enabled": False, "hset_disabled": True, "base_key": "bench:pdict:sync:keys"}),
            ("Async (HSET)", {"async_enabled": True, "hset_disabled": False, "base_key": "bench:pdict:async:hset"}),
            ("Async (No HSET)", {"async_enabled": True, "hset_disabled": True, "base_key": "bench:pdict:async:keys"}),
        ]

        print(f"{'Variant':<20} | {'Set (ops/s)':<12} | {'Get (ops/s)':<12} | {'Del (ops/s)':<12} | {'Iter (ops/s)':<12}")
        print("-" * 80)

        for name, kwargs in variants:
            await self._run_variant(name, kwargs)

    async def _run_variant(self, name: str, kwargs: Dict[str, Any]):
        set_samples = []
        get_samples = []
        del_samples = []
        iter_samples = []

        is_async = kwargs.get("async_enabled", False)
        
        # Initialize pdict
        # We need to ensure we clear it first
        # Temporary pdict for clearing
        temp_pdict = KVDBStatefulBackend.as_persistent_dict(url=self.url, **kwargs)
        if is_async:
            await temp_pdict.aclear()
        else:
            temp_pdict.clear()

        for i in range(self.num_runs):
            # Create fresh instance each run? Or reuse? Reuse is fine, but maybe clear between runs.
            pdict = KVDBStatefulBackend.as_persistent_dict(url=self.url, **kwargs)
            
            # Clear before run
            if is_async:
                await pdict.aclear()
            else:
                pdict.clear()

            # SET
            start = time.perf_counter()
            if is_async:
                for j in range(self.ops_count):
                    await pdict.aset(f"k{j}", f"val_{j}")
            else:
                for j in range(self.ops_count):
                    pdict[f"k{j}"] = f"val_{j}"
            set_ops = self.ops_count / (time.perf_counter() - start)
            set_samples.append(set_ops)

            # GET
            start = time.perf_counter()
            if is_async:
                for j in range(self.ops_count):
                    await pdict.aget(f"k{j}")
            else:
                for j in range(self.ops_count):
                    _ = pdict.get(f"k{j}")
            get_ops = self.ops_count / (time.perf_counter() - start)
            get_samples.append(get_ops)

            # ITER (Simulate getting all keys or iterating)
            # Iteration might be slow for individual fetches, so we measure iterating keys
            start = time.perf_counter()
            if is_async:
                # PersistentDict doesn't have native async iter yet? Wrapper has iterate(). 
                # Let's check backend implementation.
                # Backend has iterate() which returns iter(keys).
                # But PersistentDict might wrapp it.
                # Let's use get_keys or similar if available, or just iterate keys
                # The backend 'iterate' is synchronous usually mainly returning keys.
                # Let's check aget_keys for async.
                keys = await pdict.base.aget_keys(pattern="*")
                # Just counting fetching all keys as "iteration" op for now, or lightweight loop
                for k in keys: pass
            else:
                for k in pdict: pass
            iter_count = self.ops_count # Approx, actually it matches keys set
            iter_ops = iter_count / (time.perf_counter() - start)
            iter_samples.append(iter_ops)

            # DELETE
            start = time.perf_counter()
            if is_async:
                for j in range(self.ops_count):
                    await pdict.adelete(f"k{j}")
            else:
                for j in range(self.ops_count):
                    del pdict[f"k{j}"]
            del_ops = self.ops_count / (time.perf_counter() - start)
            del_samples.append(del_ops)

        avg_set = statistics.mean(set_samples)
        avg_get = statistics.mean(get_samples)
        avg_del = statistics.mean(del_samples)
        avg_iter = statistics.mean(iter_samples)

        print(f"{name:<20} | {avg_set:<12.0f} | {avg_get:<12.0f} | {avg_del:<12.0f} | {avg_iter:<12.0f}")

if __name__ == "__main__":
    runner = PersistenceBenchmark(url="redis://localhost:6379/1") # Use DB 1 for benchmarks
    asyncio.run(runner.run_benchmarks())
