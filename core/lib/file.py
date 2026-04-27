import asyncio
import copy
import logging
import os
import time
from abc         import ABC, abstractmethod
from contextlib  import asynccontextmanager
from typing      import Any, AsyncIterator, Generic, TypeVar

import orjson
import tomli
import tomli_w
import yaml


log = logging.getLogger(__name__)

T = TypeVar("T")


class SlidingTTLCache(Generic[T]):
	"""
	An in-memory cache using a Sliding Window TTL (Time To Live) and LRU eviction.
	
	Optimized for asyncio by utilizing synchronous dictionary operations which are 
	atomic within the context of the single-threaded event loop. Includes an 
	optional background garbage collection task to prevent memory bloat.
	"""
	def __init__(self, ttl_seconds: int = 60, maxsize: int = 1000) -> None:
		"""
		Initialize the cache.
		
		:param ttl_seconds: Seconds of inactivity before an item is considered expired.
		:param maxsize: Maximum number of items to keep in memory.
		"""
		self._ttl = ttl_seconds
		self._maxsize = maxsize
		self._cache: dict[str, list] = {}
		self._gc_task: asyncio.Task | None = None

	def get(self, key: str) -> T | None:
		"""Retrieve an item and refresh its expiration timer."""
		entry = self._cache.pop(key, None)
		if not entry:
			return None

		now = time.monotonic()
		if now >= entry[1]:
			return None

		entry[1] = now + self._ttl
		self._cache[key] = entry
		return entry[0]

	def set(self, key: str, data: T) -> None:
		"""Add an item to cache, enforcing maxsize and TTL."""
		self._cache.pop(key, None)

		if len(self._cache) >= self._maxsize:
			self._cleanup()
			if len(self._cache) >= self._maxsize:
				oldest_key = next(iter(self._cache))
				del self._cache[oldest_key]

		self._cache[key] = [data, time.monotonic() + self._ttl]

	def invalidate(self, key: str) -> None:
		"""Manually remove a specific key from the cache."""
		self._cache.pop(key, None)

	def _cleanup(self) -> None:
		"""Internal method to prune all expired keys at once. Optimized for O(expired)."""
		now = time.monotonic()
		expired = []
		for k, v in self._cache.items():
			if now >= v[1]:
				expired.append(k)
			else:
				break
		for k in expired:
			del self._cache[k]

	def start_background_gc(self, interval_seconds: int | None = None) -> None:
		"""
		Starts a background asyncio task to periodically clear expired items.
		Should be called after the asyncio event loop is running.
		"""
		interval = interval_seconds or (self._ttl / 2.0)
		
		if self._gc_task is not None and not self._gc_task.done():
			log.warning("Garbage collection task is already running.")
			return

		self._gc_task = asyncio.create_task(self._gc_loop(interval))

	def stop_background_gc(self) -> None:
		"""Cancels the running background garbage collection task."""
		if self._gc_task is not None and not self._gc_task.done():
			self._gc_task.cancel()
			self._gc_task = None

	async def _gc_loop(self, interval: float) -> None:
		"""The actual loop that sleeps and triggers cleanup."""
		try:
			while True:
				await asyncio.sleep(interval)
				self._cleanup()
		except asyncio.CancelledError:
			log.debug("SlidingTTLCache background GC cancelled.")
		except Exception as e:
			log.error("Error in SlidingTTLCache GC loop", exc_info=e)

class RefCountedLock:
	"""A wrapper for asyncio.Lock that tracks active users to allow safe deletion from memory."""
	__slots__ = ('lock', 'count')
	def __init__(self) -> None:
		self.lock = asyncio.Lock()
		self.count = 0

class BaseFileIO(ABC, Generic[T]):
	"""
	Abstract Base Class for high-performance, thread-safe File I/O with caching.
	Supports atomic writes and concurrent-safe modifications via context managers.
	"""
	def __init__(self, cache_ttl_seconds: int = 60, cache_maxsize: int = 1000) -> None:
		self._cache = SlidingTTLCache[T](ttl_seconds=cache_ttl_seconds, maxsize=cache_maxsize)
		self._locks: dict[str, RefCountedLock] = {}

	@abstractmethod
	def _serialize(self, data: T) -> bytes:
		"""Convert data to bytes for disk storage."""
		...

	@abstractmethod
	def _deserialize(self, content: bytes) -> T:
		"""Convert bytes from disk back into Python objects."""
		...

	@abstractmethod
	def _clone(self, data: T) -> T:
		"""Return a deep copy of the data to prevent accidental mutation of cache."""
		...

	@property
	@abstractmethod
	def _default_empty(self) -> T:
		"""The default value to return if a file is missing or corrupted."""
		...

	def _acquire_lock(self, path: str) -> RefCountedLock:
		if path not in self._locks:
			self._locks[path] = RefCountedLock()
		lock_obj = self._locks[path]
		lock_obj.count += 1
		return lock_obj

	def _release_lock(self, path: str, lock_obj: RefCountedLock) -> None:
		lock_obj.count -= 1
		if lock_obj.count <= 0:
			self._locks.pop(path, None)

	def _sync_read(self, path: str) -> T:
		with open(path, "rb") as f:
			return self._deserialize(f.read())

	def _sync_write(self, path: str, data: bytes, atomic: bool) -> None:
		dir_name = os.path.dirname(path)
		if dir_name:
			os.makedirs(dir_name, exist_ok=True)

		if not atomic:
			with open(path, 'wb') as f:
				f.write(data)
			return

		tmp_path = f"{path}.{os.getpid()}.tmp"
		try:
			with open(tmp_path, 'wb') as f:
				f.write(data)
				f.flush()
				os.fsync(f.fileno())
			os.replace(tmp_path, path)
		except Exception:
			if os.path.exists(tmp_path):
				os.remove(tmp_path)
			raise

	async def load(
		self, 
		path: str, 
		*,
		use_cache: bool = True, 
		read_only: bool = False,
		update_cache: bool = True
	) -> tuple[bool, T]:
		"""
		Load data from cache or disk.

		:param path: The file path to read.
		:param use_cache: If False, ignores existing cache and reads from disk.
		:param read_only: If True, returns the cached object directly (no cloning). 
		                  FASTER, but you MUST NOT modify the returned object.
		:param update_cache: If True, disk-read results will be stored in cache.
		:return: Tuple of (Success Boolean, Data)
		"""
		if use_cache:
			cached = self._cache.get(path)
			if cached is not None:
				return True, (cached if read_only else self._clone(cached))

		lock_obj = self._acquire_lock(path)
		try:
			async with lock_obj.lock:
				if use_cache:
					cached = self._cache.get(path)
					if cached is not None:
						return True, (cached if read_only else self._clone(cached))

				try:
					data = await asyncio.to_thread(self._sync_read, path)
					if update_cache:
						self._cache.set(path, self._clone(data))
					return True, data
				except (FileNotFoundError, Exception) as e:
					if not isinstance(e, FileNotFoundError):
						log.error(f"Failed to load {path}", exc_info=True)
					return False, self._default_empty
		finally:
			self._release_lock(path, lock_obj)

	async def save(
		self,
		path: str,
		data: T,
		*,
		update_cache: bool = True,
		atomic: bool = True
	) -> bool:
		"""
		Save data to disk and update cache.

		:param path: The file path to write to.
		:param data: The Python object to save.
		:param update_cache: If True, the data is added to the sliding cache.
		:param atomic: If True, uses a temporary file and os.replace to prevent corruption.
		:return: True if successful, False otherwise.
		"""
		lock_obj = self._acquire_lock(path)
		try:
			async with lock_obj.lock:
				serialized_data = self._serialize(data)
				await asyncio.to_thread(self._sync_write, path, serialized_data, atomic)
				if update_cache:
					self._cache.set(path, self._clone(data))
				return True
		except Exception:
			log.error(f"Save failed for {path}", exc_info=True)
			return False
		finally:
			self._release_lock(path, lock_obj)

	@asynccontextmanager
	async def edit(
		self,
		path: str,
		*,
		use_cache: bool = True,
		auto_save: bool = True,
		atomic: bool = True
	) -> AsyncIterator[T]:
		"""
		Context manager to read, modify, and automatically save data.
		The per-file lock is held for the duration of the 'with' block to ensure 
		atomicity and prevent race conditions during the read-modify-write cycle.

		:param path: The file path to edit.
		:param auto_save: If True, writes the modified object back to disk after the block exits.
		:param atomic: If True, uses temporary files during saving to prevent data corruption.
		:yield: The Python object (T) retrieved from cache or disk for modification.
		"""
		lock_obj = self._acquire_lock(path)
		try:
			async with lock_obj.lock:
				data = None
				if use_cache:
					cached = self._cache.get(path)
					if cached is not None:
						data = self._clone(cached)

				if not data:
					try:
						data = await asyncio.to_thread(self._sync_read, path)
					except FileNotFoundError:
						data = self._clone(self._default_empty)
					except Exception as e:
						log.error(f"Critical error reading {path} during edit. Falling back to default.", exc_info=e)
						raise

				yield data

				if auto_save:
					serialized = self._serialize(data)
					await asyncio.to_thread(self._sync_write, path, serialized, atomic)
					self._cache.set(path, self._clone(data))
		finally:
			self._release_lock(path, lock_obj)


class JSON(BaseFileIO[dict]):
	"""JSON implementation using orjson for maximum serialization speed."""
	def _serialize(self, data: dict) -> bytes:
		return orjson.dumps(data)

	def _deserialize(self, content: bytes) -> dict:
		return orjson.loads(content)

	def _clone(self, data: dict) -> dict:
		if not data: return {}
		return orjson.loads(orjson.dumps(data))

	@property
	def _default_empty(self) -> dict:
		return {}

class TOML(BaseFileIO[dict]):
	"""TOML implementation."""
	def _serialize(self, data: dict) -> bytes:
		return tomli_w.dumps(data).encode("utf-8")

	def _deserialize(self, content: bytes) -> dict:
		return tomli.loads(content.decode("utf-8"))

	def _clone(self, data: dict) -> dict:
		if not data: return {}
		return orjson.loads(orjson.dumps(data))

	@property
	def _default_empty(self) -> dict:
		return {}

class YAML(BaseFileIO[dict]):
	"""YAML implementation."""
	def _serialize(self, data: dict) -> bytes:
		return yaml.safe_dump(data, sort_keys=False).encode("utf-8")

	def _deserialize(self, content: bytes) -> dict:
		return yaml.safe_load(content.decode("utf-8")) or {}

	def _clone(self, data: dict) -> dict:
		if not data: return {}
		return orjson.loads(orjson.dumps(data))

	@property
	def _default_empty(self) -> dict:
		return {}

class TEXT(BaseFileIO[str]):
	"""Plain text implementation with UTF-8 encoding."""
	def _serialize(self, data: str) -> bytes:
		return data.encode("utf-8")

	def _deserialize(self, content: bytes) -> str:
		return content.decode("utf-8")

	def _clone(self, data: str) -> str:
		return data

	@property
	def _default_empty(self) -> str:
		return ""


_default = {
	"cache_ttl_seconds": 1800,
	"cache_maxsize": 500
}

json_file = JSON(**_default)
toml_file = TOML(**_default)
yaml_file = YAML(**_default)
text_file = TEXT(**_default)

__all__ = (
	'json_file', 'toml_file', 'yaml_file', 'text_file',
	'JSON',      'TOML',      'YAML',      'TEXT'
)
