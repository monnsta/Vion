import asyncio
import datetime
import io
import logging
import shutil
import zipfile
import hmac
import hashlib
from pathlib import Path
from typing import Any

import discord

from core.lib.converter import convert_guild, convert_user
from core.lib.file import json_file, text_file, create_path
from meta import config, file, sub


log = logging.getLogger(__name__)


class BaseProfileManager:
	def __init__(self, entity_type: str, active_dir: Path, file_routes: Any, default_settings: dict, default_ai_data: dict):
		self.entity_type = entity_type
		self.active_dir = active_dir
		self.file_routes = file_routes
		self.default_settings = default_settings
		self.default_ai_data = default_ai_data

		self.data = self.Data(self)
		self.settings = self.Settings(self)
		self.info = self.Info(self)
		self.cog_data = self.CogData(self)

	async def is_setup(self, entity_id: int) -> bool:
		return await self.data.exists(entity_id)

	async def _setup(self, entity_id: int, entity_name: str, extra_paths: list[str | tuple[str, bool]] = []) -> bool:
		eid = str(entity_id)
		log.info(f"Setting up new {self.entity_type} profile: {entity_name} ({eid})")
		try:
			settings_path = self.file_routes.settings(eid)
			ai_data_path = self.file_routes.ai_data(eid)

			paths_to_create = [settings_path, ai_data_path]
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

	class CogData:
		def __init__(self, parent: "BaseProfileManager"):
			self.parent = parent

		async def load(self, entity_id: int) -> tuple[bool, dict[str, Any]]:
			log.debug(f"Loading cog data for {self.parent.entity_type} {entity_id}")
			if not hasattr(self.parent.file_routes, "data"):
				return False, {}

			path = self.parent.file_routes.data(str(entity_id))
			if not await asyncio.to_thread(path.exists):
				return True, {}

			success, data = await json_file.load(path)
			return success, data

		async def save(self, entity_id: int, data: dict[str, Any]) -> bool:
			log.debug(f"Saving cog data for {self.parent.entity_type} {entity_id}")
			if not hasattr(self.parent.file_routes, "data"):
				return False

			path = self.parent.file_routes.data(str(entity_id))
			return await json_file.save(path, data)

	class Data:
		def __init__(self, parent: "BaseProfileManager"):
			self.parent = parent

		async def exists(self, entity_id: int) -> bool:
			eid = str(entity_id)
			path = Path(self.parent.active_dir) / eid

			return await asyncio.to_thread(path.exists)

		async def delete(self, entity_id: int) -> bool:
			eid = str(entity_id)
			source = Path(self.parent.active_dir) / eid
			dest = Path(sub.trash) / eid

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
			eid = str(entity_id)
			binned = Path(sub.trash) / eid
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
			eid = str(entity_id)
			source = Path(self.parent.active_dir) / eid
			binned = Path(sub.trash) / eid

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
		def __init__(self, parent: "BaseProfileManager"):
			self.parent = parent

		async def load(self, entity_id: int) -> tuple[bool, dict[str, Any]]:
			log.debug(f"Loading settings for {self.parent.entity_type} {entity_id}")
			path = self.parent.file_routes.settings(str(entity_id))
			success, data = await json_file.load(path)
			return success, data

		async def save(self, entity_id: int, data: dict[str, Any]) -> bool:
			log.debug(f"Saving settings for {self.parent.entity_type} {entity_id}")
			path = self.parent.file_routes.settings(str(entity_id))
			return await json_file.save(path, data)

	class Info:
		def __init__(self, parent: "BaseProfileManager"):
			self.parent = parent

		async def load(self, entity_id: int) -> tuple[bool, dict[str, Any]]:
			log.debug(f"Loading AI info for {self.parent.entity_type} {entity_id}")
			path = self.parent.file_routes.ai_data(str(entity_id))
			success, data = await json_file.load(path)
			return (success, data.get(self.parent.entity_type, {})) if success else (False, {})

		async def save(self, entity: discord.Guild | discord.User | discord.Member) -> bool:
			log.debug(f"Updating cached info for {self.parent.entity_type} {entity.id}")
			path = self.parent.file_routes.ai_data(str(entity.id))
			success, data = await json_file.load(path)

			if not success:
				return False

			convert = convert_guild if self.parent.entity_type == "guild" else convert_user

			data[self.parent.entity_type] = await convert(entity)
			return await json_file.save(path, data)


class Server(BaseProfileManager):
	def __init__(self):
		super().__init__(
			entity_type="guild",
			active_dir=sub.servers,
			file_routes=file.server,
			default_settings=config.settings.server,
			default_ai_data=config.ai_data.server
		)

	async def setup(self, guild: discord.Guild) -> bool:
		eid = str(guild.id)
		cog = self.file_routes.cog(eid)

		success = await super()._setup(
			entity_id=guild.id,
			entity_name=guild.name,
			extra_paths=[cog]
		)

		if success:
			await text_file.save(cog, "")

		return success

class User(BaseProfileManager):
	def __init__(self):
		super().__init__(
			entity_type="user",
			active_dir=sub.users,
			file_routes=file.user,
			default_settings=config.settings.user,
			default_ai_data=config.ai_data.user
		)

	async def setup(self, user: discord.User | discord.Member) -> bool:
		return await super()._setup(
			entity_id=user.id,
			entity_name=user.name
		)


server = Server()
user = User()


__all__ = ('server', 'user')
