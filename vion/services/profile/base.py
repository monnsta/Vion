"""
Base profile management functionality.

Provides generic data, settings, AI information, and archive handling classes
backed by persistent storage, HMAC signatures, and file system operations.
"""

import asyncio
import datetime
import io
import logging
import shutil
import zipfile
import hmac
import hashlib
from pathlib import Path
from typing import Any, TypeVar, Generic

from vion.infrastructure.converter import convert_guild, convert_user
from vion.infrastructure.file import json_file, create_path
from vion.config import config, storage
from vion.config.dataclasses import Guild, User


log = logging.getLogger("profile")

TRoute = TypeVar("TRoute", Guild, User)


class CogData:
	"""
	Handles reading and writing custom cog persistent data for an entity profile.
	"""

	def __init__(self, parent: "BaseProfileManager[Guild]"):
		"""
		Initialize CogData manager.

		Args:
			parent: Parent BaseProfileManager instance.
		"""
		self.parent = parent

	async def load(self, entity_id: int) -> tuple[bool, dict[str, Any]]:
		"""
		Load custom cog data for a specific entity.

		Args:
			entity_id: Target entity snowflake ID.

		Returns:
			Tuple of (success_flag, data_dict).
		"""
		log.debug(f"Loading cog data for {self.parent.entity_type} {entity_id}")
		if not hasattr(self.parent.file_routes, "data"):
			return False, {}

		path = self.parent.file_routes.custom_cog_data(str(entity_id))
		if not await asyncio.to_thread(path.exists):
			return True, {}

		success, data = await json_file.load(path)
		return success, data

	async def save(self, entity_id: int, data: dict[str, Any]) -> bool:
		"""
		Save custom cog data for a specific entity.

		Args:
			entity_id: Target entity snowflake ID.
			data: Dictionary object containing cog state data to persist.

		Returns:
			True if saved successfully, False otherwise.
		"""
		log.debug(f"Saving cog data for {self.parent.entity_type} {entity_id}")
		if not hasattr(self.parent.file_routes, "data"):
			return False

		path = self.parent.file_routes.custom_cog_data(str(entity_id))
		return await json_file.save(path, data)


class Data:
	"""
	Manages life-cycle operations for entity data directories, including deletion,
	restoration, permanent purging, and HMAC-verified ZIP exports/imports.
	"""

	def __init__(self, parent: "BaseProfileManager"):
		"""
		Initialize Data manager.

		Args:
			parent: Parent BaseProfileManager instance.
		"""
		self.parent = parent

	async def exists(self, entity_id: int) -> bool:
		"""
		Check if an active profile directory exists for an entity.

		Args:
			entity_id: Target entity snowflake ID.

		Returns:
			True if profile directory exists, False otherwise.
		"""
		eid = str(entity_id)
		path = Path(self.parent.active_dir) / eid

		return await asyncio.to_thread(path.exists)

	async def delete(self, entity_id: int) -> bool:
		"""
		Move active entity profile directory to trash and record timestamp.

		Args:
			entity_id: Target entity snowflake ID.

		Returns:
			True if moved successfully, False otherwise.
		"""
		eid = str(entity_id)
		source = Path(self.parent.active_dir) / eid
		dest = Path(storage.dirs.trash) / eid

		if not source.exists():
			log.warning(f"Delete failed: Source path {source} does not exist")
			return False

		try:
			log.info(f"Moving {self.parent.entity_type} data {eid} to bin")
			def sync_io_ops():
				if dest.exists():
					shutil.rmtree(dest)
				shutil.move(str(source), str(dest))

			await asyncio.to_thread(sync_io_ops)

			info = {"moved_at": datetime.datetime.now(config.timezone).isoformat()}
			await json_file.save(self.parent.file_routes.delete_time(eid), info)
			return True
		except Exception:
			log.error(f"Error moving data for {self.parent.entity_type} '{eid}' to bin", exc_info=True)
			return False

	async def restore(self, entity_id: int) -> bool:
		"""
		Restore binned entity profile back to active directory with automatic rollback on error.

		Args:
			entity_id: Target entity snowflake ID.

		Returns:
			True if restored successfully, False otherwise.
		"""
		eid = str(entity_id)
		binned = Path(storage.dirs.trash) / eid
		active = Path(self.parent.active_dir) / eid

		if not binned.exists():
			log.warning(f"Restore failed: Binned data for {eid} not found")
			return False

		temp_backup = active.with_suffix(".bak")
		log.info(f"Restoring {self.parent.entity_type} data for {eid} from bin")

		try:
			def sync_restore_ops():
				if active.exists():
					active.rename(temp_backup)
				shutil.move(str(binned), str(active))
				if temp_backup.exists():
					shutil.rmtree(temp_backup)

				info_file = Path(self.parent.file_routes.delete_time(eid))
				if info_file.exists():
					info_file.unlink()

			await asyncio.to_thread(sync_restore_ops)
			log.info(f"Successfully restored {self.parent.entity_type} {eid}")
			return True
		except Exception:
			log.error(f"Restore failed for '{eid}'", exc_info=True)
			def rollback():
				if temp_backup.exists():
					log.info(f"Rolling back restoration for {eid}")
					temp_backup.rename(active)
			await asyncio.to_thread(rollback)
			return False

	async def restore_zip(self, entity_id: int, zip_bytes: bytes) -> tuple[bool, str]:
		"""
		Verify HMAC signature and unpack backup ZIP payload into active directory.

		Args:
			entity_id: Target entity snowflake ID.
			zip_bytes: Raw binary content of uploaded ZIP file.

		Returns:
			Tuple of (success_flag, user_facing_message).
		"""
		eid = str(entity_id)
		dest_dir = (Path(self.parent.active_dir) / eid).resolve()

		def process_restore():
			buffer = io.BytesIO(zip_bytes)

			buffer.seek(0)

			try:
				zf = zipfile.ZipFile(buffer, "r")
			except zipfile.BadZipFile:
				log.error("BadZipFile while opening restore archive", exc_info=True)
				return False, "The uploaded file is corrupted or not a valid ZIP archive."

			with zf:
				if '.signature' not in zf.namelist():
					return False, "Restore Failed: Missing security signature (`.signature`). Ensure you are uploading an unmodified backup export."

				try:
					expected_sig = zf.read('.signature').decode('utf-8')
					h = hmac.new(config.secrets.hmac.encode('utf-8'), digestmod=hashlib.sha256)

					files_to_check = [n for n in zf.namelist() if n not in ('.signature', 'README.md')]

					for path in sorted(files_to_check):
						h.update(path.encode('utf-8'))
						h.update(zf.read(path))

					if not hmac.compare_digest(h.hexdigest(), expected_sig):
						return False, "Restore Failed: Signature verification failed. The data inside the backup appears to have been modified or tampered with."
				except Exception:
					return False, "Restore Failed: Could not verify archive integrity or security signatures."

				try:
					if dest_dir.exists():
						shutil.rmtree(dest_dir)
					dest_dir.mkdir(parents=True, exist_ok=True)

					for path in files_to_check:
						extracted_path = (dest_dir / path).resolve()
						if not str(extracted_path).startswith(str(dest_dir)):
							return False, "Restore Failed: Security violation detected (Invalid archive path structure)."

						extracted_path.parent.mkdir(parents=True, exist_ok=True)
						extracted_path.write_bytes(zf.read(path))

					return True, "Data successfully restored."
				except Exception:
					log.error(f"Error writing restored files for {eid}", exc_info=True)
					return False, "Restore Failed: An error occurred while unpacking and writing your backup files."

		log.info(f"Restoring archive for {self.parent.entity_type} {eid}")
		return await asyncio.to_thread(process_restore)

	async def delete_permanent(self, entity_id: int) -> tuple[bool, str]:
		"""
		Permanently remove entity profile directory from active or trash storage.

		Args:
			entity_id: Target entity snowflake ID.

		Returns:
			Tuple of (success_flag, status_message).
		"""
		eid = str(entity_id)
		source = Path(self.parent.active_dir) / eid
		binned = Path(storage.dirs.trash) / eid

		def sync_delete_logic():
			path = binned if binned.exists() else source if source.exists() else None

			if not path:
				log.warning(f"Permanent delete failed: {eid} not found in active or bin")
				return False, "Could not find any data"

			log.info(f"Permanently purging {self.parent.entity_type} {eid}")
			shutil.rmtree(path)
			return True, "Data deleted permanently"

		try:
			return await asyncio.to_thread(sync_delete_logic)
		except Exception:
			log.error(f"Error during permanent delete for {eid}", exc_info=True)
			return False, "There was an error deleting your data, please report this"

	async def get_zip(self, entity_id: int) -> tuple[bool, io.BytesIO | str]:
		"""
		Generate an in-memory ZIP export of entity directory with an HMAC signature.

		Args:
			entity_id: Target entity snowflake ID.

		Returns:
			Tuple of (success_flag, BytesIO_buffer_or_error_string).
		"""
		eid = str(entity_id)
		source_dir = Path(self.parent.active_dir) / eid

		if not source_dir.exists():
			log.warning(f"Zip failed: Source path {source_dir} does not exist")
			return False, "We could not find any data related to you in our storage."

		def create_in_memory_zip():
			buffer = io.BytesIO()
			try:
				with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
					readme_content = (
						f"# {self.parent.entity_type.capitalize()} Data Export\n\n"
						"This archive contains your raw data export in JSON format.\n\n"
						"### File Guide:\n"
						"- `settings.json`: Core preferences and configuration settings.\n"
						"- `ai_data.json`: Cached context and memory data used by the AI.\n"
					)
					if self.parent.entity_type == "guild":
						readme_content += "- `cog/*`: Custom commands & events setup for this server.\n"
						readme_content += "- `cog/data.json`: Persistent storage data for your custom cogs.\n"

					readme_content += (
						"\n\n*Note: JSON files can be opened in any text editor "
						"(like Notepad, VS Code) or viewed nicely online using a JSON viewer.*"
					)

					h = hmac.new(config.secrets.hmac.encode('utf-8'), digestmod=hashlib.sha256)
					files_for_sig = {}

					for file_path in source_dir.rglob('*'):
						if not file_path.is_file():
							continue

						rel_path = str(file_path.relative_to(source_dir)).replace('\\', '/')
						content = file_path.read_bytes()
						files_for_sig[rel_path] = content
						zf.writestr(rel_path, content)

					for path in sorted(files_for_sig.keys()):
						h.update(path.encode('utf-8'))
						h.update(files_for_sig[path])

					zf.writestr('.signature', h.hexdigest())
					zf.writestr("README.md", readme_content)

				buffer.seek(0)
				return True, buffer
			except Exception:
				log.error(f"Error creating zip for {eid}", exc_info=True)
				return False, "There was an error gathering your data. Please report this."

		log.info(f"Generating archive for {self.parent.entity_type} {eid}")
		return await asyncio.to_thread(create_in_memory_zip)


class Settings:
	"""
	Manages reading and writing entity settings configurations.
	"""

	def __init__(self, parent: "BaseProfileManager"):
		"""
		Initialize Settings manager.

		Args:
			parent: Parent BaseProfileManager instance.
		"""
		self.parent = parent

	async def load(self, entity_id: int) -> tuple[bool, dict[str, Any]]:
		"""
		Load configuration settings for an entity.

		Args:
			entity_id: Target entity snowflake ID.

		Returns:
			Tuple of (success_flag, settings_dict).
		"""
		log.debug(f"Loading settings for {self.parent.entity_type} {entity_id}")
		path = self.parent.file_routes.settings(str(entity_id))
		success, data = await json_file.load(path)
		return success, data

	async def save(self, entity_id: int, data: dict[str, Any]) -> bool:
		"""
		Save configuration settings for an entity.

		Args:
			entity_id: Target entity snowflake ID.
			data: Settings dictionary to save.

		Returns:
			True if saved successfully, False otherwise.
		"""
		log.debug(f"Saving settings for {self.parent.entity_type} {entity_id}")
		path = self.parent.file_routes.settings(str(entity_id))
		return await json_file.save(path, data)


class Info:
	"""
	Manages reading and updating cached AI metadata for entities.
	"""

	def __init__(self, parent: "BaseProfileManager"):
		"""
		Initialize Info manager.

		Args:
			parent: Parent BaseProfileManager instance.
		"""
		self.parent = parent

	async def load(self, entity_id: int) -> tuple[bool, dict[str, Any]]:
		"""
		Load cached AI information for an entity.

		Args:
			entity_id: Target entity snowflake ID.

		Returns:
			Tuple of (success_flag, info_dict).
		"""
		log.debug(f"Loading AI info for {self.parent.entity_type} {entity_id}")
		path = self.parent.file_routes.ai_data(str(entity_id))
		success, data = await json_file.load(path)
		return (success, data.get(self.parent.entity_type, {})) if success else (False, {})

	async def save(self, entity) -> bool:
		"""
		Convert entity metadata and write to AI cached data storage.

		Args:
			entity: Discord Guild or User/Member object.

		Returns:
			True if saved successfully, False otherwise.
		"""
		log.debug(f"Updating cached info for {self.parent.entity_type} {entity.id}")
		path = self.parent.file_routes.ai_data(str(entity.id))
		success, data = await json_file.load(path)

		if not success:
			return False

		convert = convert_guild if self.parent.entity_type == "guild" else convert_user

		data[self.parent.entity_type] = await convert(entity)
		return await json_file.save(path, data)


class BaseProfileManager(Generic[TRoute]):
	"""
	Base class for entity profile managers coordinating data, settings, and metadata sub-managers.

	Attributes:
		entity_type: Entity scope string ('guild' or 'user').
		active_dir: Base directory Path for active profiles.
		file_routes: Configured file routing object.
		default_settings: Default settings dictionary template.
		default_ai_data: Default AI data dictionary template.
		data: Data manager instance for storage operations.
		settings: Settings manager instance.
		info: Info manager instance for AI metadata.
	"""

	def __init__(self, entity_type: str, active_dir: Path, file_routes: TRoute, default_settings: dict, default_ai_data: dict):
		"""
		Initialize BaseProfileManager instance.

		Args:
			entity_type: Scope string ('guild' or 'user').
			active_dir: Path to active entity files.
			file_routes: Route provider for relative file locations.
			default_settings: Default settings payload template.
			default_ai_data: Default AI data payload template.
		"""
		self.entity_type = entity_type
		self.active_dir = active_dir
		self.file_routes = file_routes
		self.default_settings = default_settings
		self.default_ai_data = default_ai_data

		self.data = Data(self)
		self.settings = Settings(self)
		self.info = Info(self)

	async def is_setup(self, entity_id: int) -> bool:
		"""
		Check if an entity profile has already been initialized.

		Args:
			entity_id: Target entity snowflake ID.

		Returns:
			True if profile exists, False otherwise.
		"""
		return await self.data.exists(entity_id)

	async def _setup(self, entity_id: int, entity_name: str, extra_paths: list[Path | tuple[Path, bool]] = []) -> bool:
		"""
		Internal setup helper to initialize directory structures and default files.

		Args:
			entity_id: Target entity snowflake ID.
			entity_name: Human-readable entity name for logging.
			extra_paths: Optional list of additional paths/files to create.

		Returns:
			True if setup completed successfully, False otherwise.
		"""
		eid = str(entity_id)
		log.info(f"Setting up new {self.entity_type} profile: {entity_name} ({eid})")
		try:
			settings_path = self.file_routes.settings(eid)
			ai_data_path = self.file_routes.ai_data(eid)

			paths_to_create: list[Path | tuple[Path, bool]] = [settings_path, ai_data_path]
			if extra_paths:
				paths_to_create.extend(extra_paths)

			log.debug(f"Creating directory structure for {eid}")
			await create_path(*paths_to_create)

			await json_file.save(settings_path, self.default_settings)
			await json_file.save(ai_data_path, self.default_ai_data)

			log.info(f"Setup completed successfully for {self.entity_type} {eid}")
			return True
		except Exception:
			log.error(f"Error setting up {self.entity_type} {eid}", exc_info=True)
			return False
