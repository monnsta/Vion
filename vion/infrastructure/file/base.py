"""
Core file I/O abstract bases and concurrency utilities.

Provides an in-memory sliding TTL/LRU cache, reference-counted locking, and
base file operations with atomic writes, compression, and verification.
"""

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
from typing import AsyncIterator, Generic, TypeVar, Any


log = logging.getLogger("file")

T = TypeVar("T")


@dataclass
class LoadOptions:
	"""
	Configuration options for file loading operations.

	Attributes:
		use_cache: Whether to inspect the in-memory cache before reading from disk.
		trust_cache: Whether to bypass disk modification time (mtime) checks when retrieving cached items.
		read_only: Return cached object directly without deep cloning if True.
		update_cache: Store disk read results back into the cache if True.
	"""

	use_cache: bool = True
	trust_cache: bool = False
	read_only: bool = False
	update_cache: bool = True


@dataclass
class SaveOptions:
	"""
	Configuration options for file saving operations.

	Attributes:
		update_cache: Save updated payload to in-memory cache if True.
		atomic: Write to a temporary file before replacing target file if True.
		verify: Read written bytes back to verify integrity if True.
		compress: Compress file payload using gzip if True.
		compress_level: Compression level used when gzip compression is enabled.
		mode: Optional file permission bitmask (e.g. 0o600).
		background: Dispatch save execution as a background asyncio task if True.
		skip_if_unchanged: Skip disk write if payload matches current cached data.
		fsync: Perform physical disk flush via os.fsync if True.
		trust_cache: Skip mtime check when comparing against cache.
		skip_clone: Skip payload deep cloning when storing to cache.
	"""

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
	"""
	Configuration options for read-modify-write transactional context manager.

	Attributes:
		use_cache: Inspect cache before reading initial payload from disk.
		trust_cache: Bypass mtime verification on cached entry if True.
		auto_save: Save modifications automatically upon exiting context if True.
		atomic: Use atomic file replacement when saving edits.
		verify: Verify disk contents after writing edited data.
		compress: Compress written data with gzip.
		compress_level: Gzip compression level.
		mode: Optional file permission bitmask.
		skip_if_unchanged: Skip disk write if modified object equals initial state.
		fsync: Perform physical disk flush via os.fsync.
	"""

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
	In-memory sliding TTL cache with maxsize capacity eviction.

	Attributes:
		_ttl: Time to live in seconds.
		_maxsize: Maximum allowed cached keys.
	"""

	def __init__(self, ttl_seconds: int = 60, maxsize: int = 1000) -> None:
		"""
		Initialize SlidingTTLCache instance.

		Args:
			ttl_seconds: Inactivity period in seconds before entry expiration.
			maxsize: Maximum number of stored items.
		"""
		self._ttl = ttl_seconds
		self._maxsize = maxsize
		self._cache: dict[str, list[Any]] = {}

		self._gc_thread: threading.Thread | None = None
		self._gc_stop_event: threading.Event | None = None

	def get(self, key: str) -> T | None:
		"""
		Retrieve an item and refresh its TTL window.

		Args:
			key: Unique target key.

		Returns:
			Cached payload if found and unexpired, otherwise None.
		"""
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
		"""
		Insert or replace an item in the cache, enforcing maxsize bounds.

		Args:
			key: Unique target key.
			data: Payload object to cache.
		"""
		self._cache.pop(key, None)

		if len(self._cache) >= self._maxsize:
			self._cleanup()
			if len(self._cache) >= self._maxsize:
				oldest_key = next(iter(self._cache))
				del self._cache[oldest_key]

		self._cache[key] = [data, time.monotonic() + self._ttl]

	def invalidate(self, key: str) -> None:
		"""
		Remove a key manually from the cache.

		Args:
			key: Target key string to invalidate.
		"""
		self._cache.pop(key, None)

	def _cleanup(self) -> None:
		"""Prune all expired keys from internal store."""
		now = time.monotonic()
		keys_to_remove = [k for k, v in self._cache.items() if now >= v[1]]
		for k in keys_to_remove:
			del self._cache[k]

	def _gc_loop_sync(self, interval: float, stop_event: threading.Event) -> None:
		"""
		Background garbage collection thread execution loop.

		Args:
			interval: Sleep interval in seconds between cleanup checks.
			stop_event: Threading stop flag instance.
		"""
		log.debug(
			f"SlidingTTLCache _gc_loop_sync started in thread {threading.current_thread().name}"
		)
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
		Start a background daemon thread for active expired key eviction.

		Args:
			interval_seconds: Optional execution interval override in seconds.
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
			name="SlidingTTLCache_GC_Thread",
		)
		self._gc_thread.start()
		log.info("SlidingTTLCache background GC thread started.")

	def stop_gc(self) -> None:
		"""Stop and join active background garbage collection thread."""
		if self._gc_thread is not None and self._gc_thread.is_alive():
			log.debug("Signaling SlidingTTLCache background GC thread to stop...")
			if self._gc_stop_event:
				self._gc_stop_event.set()
			self._gc_thread.join(timeout=5)
			if self._gc_thread.is_alive():
				log.warning(
					"SlidingTTLCache background GC thread did not terminate gracefully within 5 seconds."
				)
			self._gc_thread = None
			self._gc_stop_event = None
			log.info("SlidingTTLCache background GC thread stopped.")
		else:
			log.debug("SlidingTTLCache background GC thread is not running.")


class RefCountedLock:
	"""
	Wrapper around asyncio.Lock tracking active acquirers for memory cleanup.

	Attributes:
		lock: Internal asyncio lock object instance.
		count: Active consumer count indicator.
	"""

	__slots__ = ("lock", "count")

	def __init__(self) -> None:
		"""Initialize RefCountedLock instance."""
		self.lock = asyncio.Lock()
		self.count = 0


class BaseFileIO(ABC, Generic[T]):
	"""
	Abstract base class for asynchronous file I/O with caching and locks.

	Attributes:
		cache: Sliding TTL memory cache instance.
		load_defaults: Default LoadOptions values.
		save_defaults: Default SaveOptions values.
		edit_defaults: Default EditOptions values.
	"""

	def __init__(self, cache_ttl_seconds: int = 60, cache_maxsize: int = 1000) -> None:
		"""
		Initialize BaseFileIO with configured caching bounds.

		Args:
			cache_ttl_seconds: Cache item expiration TTL in seconds.
			cache_maxsize: Maximum cached records bound.
		"""
		self.cache = SlidingTTLCache[tuple[T, float]](
			ttl_seconds=cache_ttl_seconds, maxsize=cache_maxsize
		)
		self._locks: dict[str, RefCountedLock] = {}

		self.load_defaults = LoadOptions()
		self.save_defaults = SaveOptions()
		self.edit_defaults = EditOptions()

	def _acquire_lock(self, path: str) -> RefCountedLock:
		"""
		Get or instantiate a reference-counted lock for a path.

		Args:
			path: Normalized file path string.

		Returns:
			RefCountedLock object for lock acquisition.
		"""
		if path not in self._locks:
			self._locks[path] = RefCountedLock()
		lock_obj = self._locks[path]
		lock_obj.count += 1
		return lock_obj

	def _release_lock(self, path: str, lock_obj: RefCountedLock) -> None:
		"""
		Decrement lock reference count and prune from dict if unreferenced.

		Args:
			path: Normalized file path string.
			lock_obj: RefCountedLock reference.
		"""
		lock_obj.count -= 1
		if lock_obj.count <= 0:
			self._locks.pop(path, None)

	async def _get_valid_cache(
		self, path: str, trust_cache: bool = False
	) -> tuple[T, float] | None:
		"""
		Verify cache entry freshness against disk mtime.

		Args:
			path: Target file path string.
			trust_cache: Skip disk mtime check if True.

		Returns:
			Tuple of (cached_data, mtime) if valid, otherwise None.
		"""
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
		"""
		Synchronous blocking disk read with gzip auto-decompression.

		Args:
			path: Target file path string.

		Returns:
			Tuple of (deserialized_data, disk_mtime).
		"""
		with open(path, "rb") as f:
			mtime = os.fstat(f.fileno()).st_mtime
			content = f.read()
		if content.startswith(b"\x1f\x8b"):
			content = gzip.decompress(content)
		return self.deserialize(content), mtime

	def _sync_write(
		self,
		path: str,
		data: bytes,
		atomic: bool,
		mode: int | None,
		verify: bool,
		compress: bool,
		compress_level: int,
		fsync: bool,
	) -> float:
		"""
		Synchronous disk write implementation supporting atomic replacement and fsync.

		Args:
			path: Output target file path string.
			data: Serialized byte payload.
			atomic: Write to temp file first if True.
			mode: Optional file permissions bitmask.
			verify: Read back written payload for equality check if True.
			compress: Compress bytes with gzip if True.
			compress_level: Gzip compression level.
			fsync: Flush OS file descriptor buffers to disk if True.

		Returns:
			Final file modification timestamp float.

		Raises:
			IOError: Verification failure if verify=True and written bytes mismatch.
		"""
		if compress:
			data = gzip.compress(data, compresslevel=compress_level)

		target_path = Path(f"{path}.{os.getpid()}.tmp") if atomic else Path(path)
		final_path = Path(path)

		if final_path.parent:
			final_path.parent.mkdir(parents=True, exist_ok=True)

		flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
		fd = os.open(str(target_path), flags, mode or 0o666)
		try:
			with os.fdopen(fd, "wb") as f:
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
			with open(target_path, "rb") as f:
				if f.read() != data:
					if atomic:
						target_path.unlink(missing_ok=True)
					raise IOError(
						"Verification failed: Disk content does not match intended data."
					)

		if atomic:
			target_path.replace(final_path)

		return os.path.getmtime(final_path)

	async def _save_internal(
		self,
		path: str,
		data: T,
		update_cache: bool,
		atomic: bool,
		verify: bool,
		compress: bool,
		compress_level: int,
		mode: int | None,
		skip_if_unchanged: bool,
		fsync: bool,
		trust_cache: bool,
		skip_clone: bool,
	) -> bool:
		"""
		Internal async lock-managed file save routine.

		Args:
			path: Absolute path string.
			data: Object payload to serialize.
			update_cache: Save result to cache if True.
			atomic: Perform atomic file move if True.
			verify: Run write verification if True.
			compress: Compress written output with gzip if True.
			compress_level: Gzip compression ratio level.
			mode: Permission bits.
			skip_if_unchanged: Avoid write if payload equals cache.
			fsync: Flush output streams to disk.
			trust_cache: Bypass mtime checks.
			skip_clone: Avoid deep copy of cache entry if True.

		Returns:
			True if execution completed without errors, False otherwise.
		"""
		lock_obj = self._acquire_lock(path)
		try:
			async with lock_obj.lock:
				if skip_if_unchanged:
					valid_cache = await self._get_valid_cache(
						path, trust_cache=trust_cache
					)
					if valid_cache is not None and valid_cache[0] == data:
						return True

				serialized_data = self.serialize(data)
				new_mtime = await asyncio.to_thread(
					self._sync_write,
					path,
					serialized_data,
					atomic,
					mode,
					verify,
					compress,
					compress_level,
					fsync,
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

	@abstractmethod
	def serialize(self, data: T) -> bytes:
		"""
		Convert python object into bytes.

		Args:
			data: Source object instance.

		Returns:
			Serialized output bytes.
		"""
		...

	@abstractmethod
	def deserialize(self, content: bytes) -> T:
		"""
		Parse raw byte payload into object instance.

		Args:
			content: Raw input bytes.

		Returns:
			Deserialized Python object.
		"""
		...

	@abstractmethod
	def clone(self, data: T) -> T:
		"""
		Deep copy payload object instance.

		Args:
			data: Source object instance.

		Returns:
			Independent deep copy of input data.
		"""
		...

	@property
	@abstractmethod
	def default_empty(self) -> T:
		"""The fallback default payload returned when a target file is unreadable."""
		...

	async def load(
		self,
		path: str | Path,
		*,
		use_cache: bool | None = None,
		trust_cache: bool | None = None,
		read_only: bool | None = None,
		update_cache: bool | None = None,
	) -> tuple[bool, T]:
		"""
		Read payload from cache or disk storage safely.

		Args:
			path: File path reference.
			use_cache: Read from cache if available.
			trust_cache: Skip mtime check during cache lookup.
			read_only: Return cache reference directly without deep cloning.
			update_cache: Store disk load result in cache.

		Returns:
			Tuple of (success_boolean, loaded_data_payload).
		"""
		_use_cache = (
			use_cache if use_cache is not None else self.load_defaults.use_cache
		)
		_trust_cache = (
			trust_cache if trust_cache is not None else self.load_defaults.trust_cache
		)
		_read_only = (
			read_only if read_only is not None else self.load_defaults.read_only
		)
		_update_cache = (
			update_cache
			if update_cache is not None
			else self.load_defaults.update_cache
		)

		path = os.path.abspath(os.fspath(path))
		if _use_cache:
			valid_cache = await self._get_valid_cache(path, trust_cache=_trust_cache)
			if valid_cache is not None:
				return True, (
					valid_cache[0] if _read_only else self.clone(valid_cache[0])
				)

		lock_obj = self._acquire_lock(path)
		try:
			async with lock_obj.lock:
				if _use_cache:
					valid_cache = await self._get_valid_cache(
						path, trust_cache=_trust_cache
					)
					if valid_cache is not None:
						return True, (
							valid_cache[0] if _read_only else self.clone(valid_cache[0])
						)

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
		skip_clone: bool | None = None,
	) -> bool:
		"""
		Save object data payload to disk storage.

		Args:
			path: Output target file path.
			data: Object data payload to save.
			update_cache: Update cache with payload after saving.
			atomic: Write via temporary file replacement.
			verify: Verify written file against payload.
			compress: Compress written file with gzip.
			compress_level: Gzip compression level.
			mode: Optional file permissions bitmask.
			background: Execute save operation in background task.
			skip_if_unchanged: Skip write if data equals cached state.
			fsync: Flush OS file stream buffers to physical media.
			trust_cache: Skip mtime verification during cache validation.
			skip_clone: Skip payload deep cloning when caching.

		Returns:
			True if save succeeded or dispatched to background task, False on failure.
		"""
		_update_cache = (
			update_cache
			if update_cache is not None
			else self.save_defaults.update_cache
		)
		_atomic = atomic if atomic is not None else self.save_defaults.atomic
		_verify = verify if verify is not None else self.save_defaults.verify
		_compress = compress if compress is not None else self.save_defaults.compress
		_compress_level = (
			compress_level
			if compress_level is not None
			else self.save_defaults.compress_level
		)
		_mode = mode if mode is not None else self.save_defaults.mode
		_background = (
			background if background is not None else self.save_defaults.background
		)
		_skip_if_unchanged = (
			skip_if_unchanged
			if skip_if_unchanged is not None
			else self.save_defaults.skip_if_unchanged
		)
		_fsync = fsync if fsync is not None else self.save_defaults.fsync
		_trust_cache = (
			trust_cache if trust_cache is not None else self.save_defaults.trust_cache
		)
		_skip_clone = (
			skip_clone if skip_clone is not None else self.save_defaults.skip_clone
		)

		path = os.path.abspath(os.fspath(path))

		bg_data = data if _skip_clone else self.clone(data)

		if _background:
			asyncio.create_task(
				self._save_internal(
					path,
					bg_data,
					_update_cache,
					_atomic,
					_verify,
					_compress,
					_compress_level,
					_mode,
					_skip_if_unchanged,
					_fsync,
					_trust_cache,
					skip_clone=True,
				)
			)
			return True

		return await self._save_internal(
			path,
			bg_data,
			_update_cache,
			_atomic,
			_verify,
			_compress,
			_compress_level,
			_mode,
			_skip_if_unchanged,
			_fsync,
			_trust_cache,
			skip_clone=True,
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
		fsync: bool | None = None,
	) -> AsyncIterator[T]:
		"""
		Async context manager for atomic read-modify-write transactional editing.

		Args:
			path: File path string or Path instance.
			use_cache: Read initial state from cache if available.
			trust_cache: Bypass mtime validation.
			auto_save: Automatically persist context state changes on exit.
			atomic: Write context results using atomic file move.
			verify: Run post-write verification checks.
			compress: Compress written output using gzip.
			compress_level: Gzip compression level.
			mode: Optional file permissions bitmask.
			skip_if_unchanged: Omit disk write if payload context was un-mutated.
			fsync: Flush OS file descriptor buffers.

		Yields:
			Mutable payload instance yielding from read operation.
		"""
		_use_cache = (
			use_cache if use_cache is not None else self.edit_defaults.use_cache
		)
		_trust_cache = (
			trust_cache if trust_cache is not None else self.edit_defaults.trust_cache
		)
		_auto_save = (
			auto_save if auto_save is not None else self.edit_defaults.auto_save
		)
		_atomic = atomic if atomic is not None else self.edit_defaults.atomic
		_verify = verify if verify is not None else self.edit_defaults.verify
		_compress = compress if compress is not None else self.edit_defaults.compress
		_compress_level = (
			compress_level
			if compress_level is not None
			else self.edit_defaults.compress_level
		)
		_mode = mode if mode is not None else self.edit_defaults.mode
		_skip_if_unchanged = (
			skip_if_unchanged
			if skip_if_unchanged is not None
			else self.edit_defaults.skip_if_unchanged
		)
		_fsync = fsync if fsync is not None else self.edit_defaults.fsync

		path = os.path.abspath(os.fspath(path))
		lock_obj = self._acquire_lock(path)
		try:
			async with lock_obj.lock:
				data = None
				original_data = None
				if _use_cache:
					valid_cache = await self._get_valid_cache(
						path, trust_cache=_trust_cache
					)
					if valid_cache is not None:
						data = self.clone(valid_cache[0])

				if not data:
					try:
						data, _ = await asyncio.to_thread(self._sync_read, path)
					except FileNotFoundError:
						data = self.clone(self.default_empty)
					except Exception as e:
						log.error(
							f"Critical error reading {path} during edit. Falling back to default.",
							exc_info=e,
						)
						raise

				if _auto_save and _skip_if_unchanged:
					original_data = self.clone(data)

				yield data

				if _auto_save:
					if _skip_if_unchanged and original_data == data:
						return

					serialized = self.serialize(data)
					new_mtime = await asyncio.to_thread(
						self._sync_write,
						path,
						serialized,
						_atomic,
						_mode,
						_verify,
						_compress,
						_compress_level,
						_fsync,
					)
					self.cache.set(path, (self.clone(data), new_mtime))
		finally:
			self._release_lock(path, lock_obj)


class CreatePath:
	"""
	Asynchronous directory and empty file creation utility helper.
	"""

	async def process_path(self, path: str | Path, is_dir: bool = False) -> None:
		"""
		Create directory tree and touch target file asynchronously.

		Args:
			path: File or directory path string or Path object.
			is_dir: Treat path purely as a directory target if True.
		"""
		path_obj = Path(path)
		dir_to_create = path_obj if is_dir else path_obj.parent

		try:
			if dir_to_create and not dir_to_create.exists():
				log.debug(f"Creating directory: {dir_to_create}")
				await asyncio.to_thread(
					dir_to_create.mkdir, parents=True, exist_ok=True
				)

			if not is_dir:
				log.debug(f"Touching file: {path_obj}")
				await asyncio.to_thread(path_obj.touch, exist_ok=True)
		except Exception:
			log.error(
				f"An unexpected error occurred while processing {path}", exc_info=True
			)

	async def __call__(self, *paths: tuple[str | Path, bool] | str | Path) -> None:
		"""
		Process multiple file/directory target creations concurrently.

		Args:
			*paths: Variadic path inputs or (path, is_dir_boolean) tuples.
		"""
		log.debug(f"Starting path processing for {len(paths)} paths.")
		tasks = []
		for path in paths:
			if isinstance(path, tuple):
				tasks.append(self.process_path(*path))
			else:
				tasks.append(self.process_path(path))
		await asyncio.gather(*tasks)
		log.debug("Path processing batch complete.")
