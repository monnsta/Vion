import asyncio
import builtins
import gzip
import logging
import os
import time
import threading
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import cast, AsyncIterator, Generic, TypeVar, Any

orjson: Any = None
yaml: Any = None
SafeLoader: Any = None
SafeDumper: Any = None

try:
	import orjson

	try:
		import yaml
		try:
			from yaml import CSafeLoader as SafeLoader, CSafeDumper as SafeDumper
		except ImportError:
			from yaml import SafeLoader, SafeDumper
	except ImportError:
		pass
except ImportError:
	pass


log = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class LoadOptions:
	"""Default options for the load method."""
	use_cache: bool = True
	trust_cache: bool = False
	read_only: bool = False
	update_cache: bool = True

@dataclass
class SaveOptions:
	"""Default options for the save method."""
	update_cache: bool = True
	atomic: bool = True
	verify: bool = False
	compress: bool = False
	compress_level: int = 3
	mode: int | None = None
	background: bool = False
	skip_if_unchanged: bool = False
	fsync: bool = True
	trust_cache: bool = False
	skip_clone: bool = False

@dataclass
class EditOptions:
	"""Default options for the edit method."""
	use_cache: bool = True
	trust_cache: bool = False
	auto_save: bool = True
	atomic: bool = True
	verify: bool = False
	compress: bool = False
	compress_level: int = 3
	mode: int | None = None
	skip_if_unchanged: bool = False
	fsync: bool = True


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
		self._cache: dict[str, list[Any]] = {}

		self._gc_thread: threading.Thread | None = None
		self._gc_stop_event: threading.Event | None = None

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
		"""
		Internal method to prune all expired keys at once.
		Iterates through all items to find expired ones, as expiration times are not
		guaranteed to be in insertion order due to 'get' refreshing TTL.
		"""
		now = time.monotonic()
		keys_to_remove = [k for k, v in self._cache.items() if now >= v[1]]
		for k in keys_to_remove:
			del self._cache[k]

	def _gc_loop_sync(self, interval: float, stop_event: threading.Event) -> None:
		"""
		The actual loop that sleeps and triggers cleanup in a separate system thread.
		Uses `time.sleep` and a `threading.Event` for control.
		"""
		log.debug(f"SlidingTTLCache _gc_loop_sync started in thread {threading.current_thread().name}")
		try:
			while not stop_event.is_set():
				stop_event.wait(interval)
				if stop_event.is_set():
					break
				self._cleanup()
		except Exception as e:
			log.error("Error in SlidingTTLCache _gc_loop_sync", exc_info=e)
		finally:
			log.debug("SlidingTTLCache _gc_loop_sync stopped.")

	def start_gc(self, interval_seconds: int | None = None) -> None:
		"""
		Starts a background *system thread* to periodically clear expired items.
		"""
		interval = interval_seconds or (self._ttl / 2.0)

		if self._gc_thread is not None and self._gc_thread.is_alive():
			log.warning("SlidingTTLCache background GC thread is already running.")
			return

		self._gc_stop_event = threading.Event()

		self._gc_thread = threading.Thread(
			target=self._gc_loop_sync,
			args=(interval, self._gc_stop_event),
			daemon=True,
			name="SlidingTTLCache_GC_Thread"
		)
		self._gc_thread.start()
		log.info("SlidingTTLCache background GC thread started.")

	def stop_gc(self) -> None:
		"""Cancels the running background garbage collection thread."""
		if self._gc_thread is not None and self._gc_thread.is_alive():
			log.debug("Signaling SlidingTTLCache background GC thread to stop...")
			if self._gc_stop_event:
				self._gc_stop_event.set()
			self._gc_thread.join(timeout=5)
			if self._gc_thread.is_alive():
				log.warning("SlidingTTLCache background GC thread did not terminate gracefully within 5 seconds.")
			self._gc_thread = None
			self._gc_stop_event = None
			log.info("SlidingTTLCache background GC thread stopped.")
		else:
			log.debug("SlidingTTLCache background GC thread is not running.")


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
		self.cache = SlidingTTLCache[tuple[T, float]](ttl_seconds=cache_ttl_seconds, maxsize=cache_maxsize)
		self._locks: dict[str, RefCountedLock] = {}

		self.load_defaults = LoadOptions()
		self.save_defaults = SaveOptions()
		self.edit_defaults = EditOptions()


	# Internals
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

	async def _get_valid_cache(self, path: str, trust_cache: bool = False) -> tuple[T, float] | None:
		cached_entry = self.cache.get(path)
		if cached_entry is None:
			return None

		if trust_cache:
			return cached_entry

		try:
			disk_mtime = await asyncio.to_thread(os.path.getmtime, path)
			if disk_mtime == cached_entry[1]:
				return cached_entry
		except FileNotFoundError:
			pass

		return None

	def _sync_read(self, path: str) -> tuple[T, float]:
		with open(path, "rb") as f:
			mtime = os.fstat(f.fileno()).st_mtime
			content = f.read()
		if content.startswith(b'\x1f\x8b'):
			content = gzip.decompress(content)
		return self.deserialize(content), mtime

	def _sync_write(self, path: str, data: bytes, atomic: bool, mode: int | None, verify: bool, compress: bool, compress_level: int, fsync: bool) -> float:
		if compress:
			data = gzip.compress(data, compresslevel=compress_level)

		target_path = Path(f"{path}.{os.getpid()}.tmp") if atomic else Path(path)
		final_path = Path(path)

		if final_path.parent:
			final_path.parent.mkdir(parents=True, exist_ok=True)

		flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
		fd = os.open(str(target_path), flags, mode or 0o666)
		try:
			with os.fdopen(fd, 'wb') as f:
				f.write(data)
				if fsync:
					f.flush()
					os.fsync(f.fileno())

			if mode is not None:
				target_path.chmod(mode)

		except Exception:
			if atomic:
				target_path.unlink(missing_ok=True)
			raise

		if verify:
			with open(target_path, 'rb') as f:
				if f.read() != data:
					if atomic:
						target_path.unlink(missing_ok=True)
					raise IOError("Verification failed: Disk content does not match intended data.")

		if atomic:
			target_path.replace(final_path)

		return os.path.getmtime(final_path)

	async def _save_internal(self, path: str, data: T, update_cache: bool, atomic: bool, verify: bool, compress: bool, compress_level: int, mode: int | None, skip_if_unchanged: bool, fsync: bool, trust_cache: bool, skip_clone: bool) -> bool:
		lock_obj = self._acquire_lock(path)
		try:
			async with lock_obj.lock:
				if skip_if_unchanged:
					valid_cache = await self._get_valid_cache(path, trust_cache=trust_cache)
					if valid_cache is not None and valid_cache[0] == data:
						return True

				serialized_data = self.serialize(data)
				new_mtime = await asyncio.to_thread(
					self._sync_write, path, serialized_data, atomic, mode, verify, compress, compress_level, fsync
				)
				if update_cache:
					cache_data = data if skip_clone else self.clone(data)
					self.cache.set(path, (cache_data, new_mtime))
				return True
		except Exception:
			log.error(f"Save failed for {path}", exc_info=True)
			return False
		finally:
			self._release_lock(path, lock_obj)


	# implementation
	@abstractmethod
	def serialize(self, data: T) -> bytes:
		"""Convert data to bytes for disk storage."""
		...

	@abstractmethod
	def deserialize(self, content: bytes) -> T:
		"""Convert bytes from disk back into Python objects."""
		...

	@abstractmethod
	def clone(self, data: T) -> T:
		"""Return a deep copy of the data to prevent accidental mutation of cache."""
		...

	@property
	@abstractmethod
	def default_empty(self) -> T:
		"""The default value to return if a file is missing or corrupted."""
		...


	# Public Methods
	async def load(
		self,
		path: str | Path,
		*,
		use_cache: bool | None = None,
		trust_cache: bool | None = None,
		read_only: bool | None = None,
		update_cache: bool | None = None
	) -> tuple[bool, T]:
		"""
		Load data from cache or disk.

		:param path: The file path to read.
		:param use_cache: If False, ignores existing cache and reads from disk.
		:param trust_cache: If True, skips disk mtime check and trusts in-memory cache directly.
		:param read_only: If True, returns the cached object directly (no cloning).
		                  FASTER, but you MUST NOT modify the returned object.
		:param update_cache: If True, disk-read results will be stored in cache.
		:return: Tuple of (Success Boolean, Data)
		"""
		_use_cache = use_cache if use_cache is not None else self.load_defaults.use_cache
		_trust_cache = trust_cache if trust_cache is not None else self.load_defaults.trust_cache
		_read_only = read_only if read_only is not None else self.load_defaults.read_only
		_update_cache = update_cache if update_cache is not None else self.load_defaults.update_cache

		path = os.path.abspath(os.fspath(path))
		if _use_cache:
			valid_cache = await self._get_valid_cache(path, trust_cache=_trust_cache)
			if valid_cache is not None:
				return True, (valid_cache[0] if _read_only else self.clone(valid_cache[0]))

		lock_obj = self._acquire_lock(path)
		try:
			async with lock_obj.lock:
				if _use_cache:
					valid_cache = await self._get_valid_cache(path, trust_cache=_trust_cache)
					if valid_cache is not None:
						return True, (valid_cache[0] if _read_only else self.clone(valid_cache[0]))

				try:
					data, mtime = await asyncio.to_thread(self._sync_read, path)
					if _update_cache:
						self.cache.set(path, (self.clone(data), mtime))
					return True, data
				except (FileNotFoundError, Exception) as e:
					if type(e) not in builtins.__dict__.values():
						raise
					if not isinstance(e, FileNotFoundError):
						log.error(f"Failed to load {path}", exc_info=True)
					return False, self.default_empty
		finally:
			self._release_lock(path, lock_obj)

	async def save(
		self,
		path: str | Path,
		data: T,
		*,
		update_cache: bool | None = None,
		atomic: bool | None = None,
		verify: bool | None = None,
		compress: bool | None = None,
		compress_level: int | None = None,
		mode: int | None = None,
		background: bool | None = None,
		skip_if_unchanged: bool | None = None,
		fsync: bool | None = None,
		trust_cache: bool | None = None,
		skip_clone: bool | None = None
	) -> bool:
		"""
		Save data to disk and update cache.

		:param path: The file path to write to.
		:param data: The Python object to save.
		:param update_cache: If True, the data is added to the sliding cache.
		:param atomic: If True, uses a temporary file and os.replace to prevent corruption.
		:param verify: If True, reads the file back to guarantee integrity before returning.
		:param compress: If True, compresses the file with gzip.
		:param compress_level: Compression level used when gzip compression is enabled.
		:param mode: Optional file permissions (e.g., 0o600).
		:param background: If True, executes the save as a fire-and-forget asyncio task.
		:param skip_if_unchanged: If True, ignores the save if the data equals the cache.
		:param fsync: If False, skips physical disk flush for higher performance.
		:param trust_cache: If True, skips disk mtime check during cache validation.
		:param skip_clone: If True, skips cloning data before storing in cache.
		:return: True if successful (or successfully dispatched to background), False otherwise.
		"""
		_update_cache = update_cache if update_cache is not None else self.save_defaults.update_cache
		_atomic = atomic if atomic is not None else self.save_defaults.atomic
		_verify = verify if verify is not None else self.save_defaults.verify
		_compress = compress if compress is not None else self.save_defaults.compress
		_compress_level = compress_level if compress_level is not None else self.save_defaults.compress_level
		_mode = mode if mode is not None else self.save_defaults.mode
		_background = background if background is not None else self.save_defaults.background
		_skip_if_unchanged = skip_if_unchanged if skip_if_unchanged is not None else self.save_defaults.skip_if_unchanged
		_fsync = fsync if fsync is not None else self.save_defaults.fsync
		_trust_cache = trust_cache if trust_cache is not None else self.save_defaults.trust_cache
		_skip_clone = skip_clone if skip_clone is not None else self.save_defaults.skip_clone

		path = os.path.abspath(os.fspath(path))

		bg_data = data if _skip_clone else self.clone(data)

		if _background:
			asyncio.create_task(
				self._save_internal(
					path, bg_data, _update_cache, _atomic,
					_verify, _compress, _compress_level, _mode,
					_skip_if_unchanged, _fsync, _trust_cache, skip_clone=True
				)
			)
			return True

		return await self._save_internal(
			path, bg_data, _update_cache, _atomic, _verify, _compress, _compress_level, _mode, _skip_if_unchanged, _fsync, _trust_cache, skip_clone=True
		)

	@asynccontextmanager
	async def edit(
		self,
		path: str | Path,
		*,
		use_cache: bool | None = None,
		trust_cache: bool | None = None,
		auto_save: bool | None = None,
		atomic: bool | None = None,
		verify: bool | None = None,
		compress: bool | None = None,
		compress_level: int | None = None,
		mode: int | None = None,
		skip_if_unchanged: bool | None = None,
		fsync: bool | None = None
	) -> AsyncIterator[T]:
		"""
		Context manager to read, modify, and automatically save data.
		The per-file lock is held for the duration of the 'with' block to ensure
		atomicity and prevent race conditions during the read-modify-write cycle.
		"""
		_use_cache = use_cache if use_cache is not None else self.edit_defaults.use_cache
		_trust_cache = trust_cache if trust_cache is not None else self.edit_defaults.trust_cache
		_auto_save = auto_save if auto_save is not None else self.edit_defaults.auto_save
		_atomic = atomic if atomic is not None else self.edit_defaults.atomic
		_verify = verify if verify is not None else self.edit_defaults.verify
		_compress = compress if compress is not None else self.edit_defaults.compress
		_compress_level = compress_level if compress_level is not None else self.edit_defaults.compress_level
		_mode = mode if mode is not None else self.edit_defaults.mode
		_skip_if_unchanged = skip_if_unchanged if skip_if_unchanged is not None else self.edit_defaults.skip_if_unchanged
		_fsync = fsync if fsync is not None else self.edit_defaults.fsync

		path = os.path.abspath(os.fspath(path))
		lock_obj = self._acquire_lock(path)
		try:
			async with lock_obj.lock:
				data = None
				original_data = None
				if _use_cache:
					valid_cache = await self._get_valid_cache(path, trust_cache=_trust_cache)
					if valid_cache is not None:
						data = self.clone(valid_cache[0])

				if not data:
					try:
						data, _ = await asyncio.to_thread(self._sync_read, path)
					except FileNotFoundError:
						data = self.clone(self.default_empty)
					except Exception as e:
						log.error(f"Critical error reading {path} during edit. Falling back to default.", exc_info=e)
						raise

				if _auto_save and _skip_if_unchanged:
					original_data = self.clone(data)

				yield data

				if _auto_save:
					if _skip_if_unchanged and original_data == data:
						return

					serialized = self.serialize(data)
					new_mtime = await asyncio.to_thread(
						self._sync_write, path, serialized, _atomic, _mode, _verify, _compress, _compress_level, _fsync
					)
					self.cache.set(path, (self.clone(data), new_mtime))
		finally:
			self._release_lock(path, lock_obj)


class CreatePath:
	async def process_path(self, path: str | Path, is_dir: bool = False) -> None:
		path_obj = Path(path)
		dir_to_create = path_obj if is_dir else path_obj.parent

		try:
			if dir_to_create and not dir_to_create.exists():
				log.debug(f"Creating directory: {dir_to_create}")
				await asyncio.to_thread(dir_to_create.mkdir, parents=True, exist_ok=True)

			if not is_dir:
				log.debug(f"Touching file: {path_obj}")
				await asyncio.to_thread(path_obj.touch, exist_ok=True)
		except Exception:
			log.error(f"An unexpected error occurred while processing {path}", exc_info=True)

	async def __call__(self, *paths: tuple[str | Path, bool] | str | Path) -> None:
		log.debug(f"Starting path processing for {len(paths)} paths.")
		tasks = []
		for path in paths:
			if isinstance(path, tuple):
				tasks.append(self.process_path(*path))
			else:
				tasks.append(self.process_path(path))
		await asyncio.gather(*tasks)
		log.debug("Path processing batch complete.")


class TEXT(BaseFileIO[str]):
	"""Plain text implementation."""
	def serialize(self, data: str) -> bytes:
		return (data or "").encode("utf-8")

	def deserialize(self, content: bytes) -> str:
		return content.decode("utf-8") if content else ""

	def clone(self, data: str) -> str:
		return data or ""

	@property
	def default_empty(self) -> str:
		return ""

class JSON(BaseFileIO[dict[str, Any]]):
	"""JSON implementation."""
	def serialize(self, data: dict[str, Any]) -> bytes:
		return orjson.dumps(data if data is not None else {}, option=orjson.OPT_INDENT_2)

	def deserialize(self, content: bytes) -> dict[str, Any]:
		if not content or content.strip() == b"":
			return self.default_empty
		return cast(dict[str, Any], orjson.loads(content))

	def clone(self, data: dict[str, Any]) -> dict[str, Any]:
		if not data: return {}
		return cast(dict[str, Any], orjson.loads(orjson.dumps(data)))

	@property
	def default_empty(self) -> dict[str, Any]:
		return {}

class YAML(BaseFileIO[dict[str, Any]]):
	"""YAML implementation."""
	def serialize(self, data: dict[str, Any]) -> bytes:
		return yaml.dump(data if data is not None else {}, Dumper=SafeDumper, sort_keys=False).encode("utf-8")

	def deserialize(self, content: bytes) -> dict[str, Any]:
		if not content or content.strip() == b"":
			return self.default_empty
		return cast(dict[str, Any], yaml.load(content.decode("utf-8"), Loader=SafeLoader) or {})

	def clone(self, data: dict[str, Any]) -> dict[str, Any]:
		if not data: return {}
		return cast(dict[str, Any], orjson.loads(orjson.dumps(data)))

	@property
	def default_empty(self) -> dict[str, Any]:
		return {}


_default = (
	1800, # cache_ttl_seconds
	500   # cache_maxsize
)

text_file = TEXT(*_default)
json_file = cast(JSON, JSON(*_default) if orjson else None)
yaml_file = cast(YAML, YAML(*_default) if yaml and orjson else None)

create_path = CreatePath()


__all__ = (
	'text_file', 'json_file', 'yaml_file',
	'TEXT',      'JSON',      'YAML',
	'create_path'
)
