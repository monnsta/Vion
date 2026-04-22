import asyncio
import os
import time
import shutil
import orjson
from typing import Dict
from dataclasses import dataclass

from core.lib.file import JSON, SlidingTTLCache, json_file


@dataclass
class TestResult:
	name: str
	passed: bool
	duration: float
	metadata: str = ""


class UtilityTester:
	def __init__(self):
		self.test_dir = "test_data"
		if not os.path.exists(self.test_dir):
			os.makedirs(self.test_dir)

	def cleanup(self):
		if os.path.exists(self.test_dir):
			shutil.rmtree(self.test_dir)

	async def test_cache_sliding_and_eviction(self):
		cache = SlidingTTLCache[int](ttl_seconds=1, maxsize=2)

		cache.set("a", 1)
		cache.set("b", 2)

		await asyncio.sleep(0.6)
		cache.get("a") 

		await asyncio.sleep(0.6)
		assert cache.get("a") == 1, "Sliding TTL failed to refresh expiration"
		assert cache.get("b") is None, "Item should have expired"

		cache.set("c", 3)
		cache.set("d", 4)
		assert cache.get("a") is None, "LRU eviction failed to remove oldest item"

		return "Cache logic verified (Sliding TTL & Maxsize)"

	async def test_cache_mutation_protection(self):
		path = os.path.join(self.test_dir, "mutation.json")
		original_data = {"list": [1, 2, 3]}
		await json_file.save(path, original_data)

		success, data = await json_file.load(path, read_only=False)
		data["list"].append(4)

		_, second_load = await json_file.load(path)
		assert second_load["list"] == [1, 2, 3], "Internal cache was poisoned by external mutation"

		return "Cache isolation verified (Deep Cloning)"

	async def test_concurrency_and_lock_cleanup(self):
		path = os.path.join(self.test_dir, "race_test.json")
		await json_file.save(path, {"count": 0})

		async def increment():
			async with json_file.edit(path) as data:
				current = data["count"]
				await asyncio.sleep(0.01)
				data["count"] = current + 1

		await asyncio.gather(*(increment() for _ in range(100)))

		_, final_data = await json_file.load(path, use_cache=False)
		assert final_data["count"] == 100, f"Race condition: Expected 100, got {final_data['count']}"

		assert path not in json_file._locks, "Memory leak: Lock object not removed from _locks dict"

		return "Concurrency verified (100 atomic updates + Lock cleanup)"

	async def test_recovery_from_corruption(self):
		path = os.path.join(self.test_dir, "corrupt.json")

		with open(path, "wb") as f:
			f.write(b"NOT_VALID_JSON{}}}")

		success, data = await json_file.load(path, use_cache=False)
		assert success is False
		assert data == {}, "Failed to return default empty dict on file corruption"
		
		return "Corruption recovery verified"

	async def benchmark_io_vs_cache(self):
		path = os.path.join(self.test_dir, "bench.json")
		payload = {"data": "x" * 5000}
		await json_file.save(path, payload)

		iterations = 1000

		start = time.perf_counter()
		for _ in range(iterations):
			await json_file.load(path, use_cache=False)
		disk_time = time.perf_counter() - start

		start = time.perf_counter()
		for _ in range(iterations):
			await json_file.load(path, use_cache=True)
		cache_time = time.perf_counter() - start

		speedup = disk_time / cache_time
		return f"Disk: {disk_time:.4f}s | Cache: {cache_time:.4f}s ({speedup:.1f}x speedup)"

	async def run_all(self):
		tests = [
			("Cache Logic", self.test_cache_sliding_and_eviction),
			("Cache Isolation", self.test_cache_mutation_protection),
			("Concurrency & Locks", self.test_concurrency_and_lock_cleanup),
			("Corruption Recovery", self.test_recovery_from_corruption),
			("I/O Performance", self.benchmark_io_vs_cache),
		]

		print(f"{'TEST NAME':<25} | {'STATUS':<10} | {'INFO'}")
		print("-" * 80)

		for name, func in tests:
			start = time.perf_counter()
			try:
				info = await func()
				status = "+ PASS"
			except Exception as e:
				info = f"{type(e).__name__}: {str(e)}"
				status = "- FAIL"
			duration = time.perf_counter() - start
			print(f"{name:<25} | {status:<10} | {info} ({duration:.3f}s)")


if __name__ == "__main__":
	tester = UtilityTester()
	try:
		asyncio.run(tester.run_all())
	finally:
		tester.cleanup()
