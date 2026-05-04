import asyncio
import datetime
import io
import json
import logging
import os
import shutil
import zipfile
from typing              import Any, Union

import discord

from core.lib.converter  import convert_guild, convert_user
from core.lib.file       import json_file, text_file
from meta                import config, create_path, file, sub


log = logging.getLogger(__name__)


class BaseProfileManager:
	def __init__(self, entity_type: str, active_dir: str, file_routes: Any, default_settings: dict, default_ai_data: dict):
		self.entity_type = entity_type
		self.active_dir = active_dir
		self.file_routes = file_routes
		self.default_settings = default_settings
		self.default_ai_data = default_ai_data

		self.data = self.Data(self)
		self.settings = self.Settings(self)
		self.info = self.Info(self)

	async def _setup(self, entity_id: int, entity_name: str, extra_paths: list[str] = []) -> bool:
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

	class Data:
		def __init__(self, parent: "BaseProfileManager"):
			self.parent = parent

		async def exists(self, entity_id: int) -> bool:
			eid = str(entity_id)
			path = os.path.join(self.parent.active_dir, eid)

			return await asyncio.to_thread(os.path.exists, path)

		async def delete(self, entity_id: int) -> bool:
			eid = str(entity_id)
			source = os.path.join(self.parent.active_dir, eid)
			dest = os.path.join(sub.bin, eid)

			if not os.path.exists(source):
				log.warning(f"Delete failed: Source path {source} does not exist")
				return False

			try:
				log.info(f"Moving {self.parent.entity_type} data {eid} to bin")
				def sync_io_ops():
					if os.path.exists(dest):
						shutil.rmtree(dest)
					shutil.move(source, dest)

				await asyncio.to_thread(sync_io_ops)

				info = {"moved_at": datetime.datetime.now(config.timezone).isoformat()}
				await json_file.save(self.parent.file_routes.delete_time(eid), info)
				return True
			except Exception:
				log.error(f"Error moving data for {self.parent.entity_type} '{eid}' to bin", exc_info=True)
				return False

		async def restore(self, entity_id: int) -> bool:
			eid = str(entity_id)
			binned = os.path.join(sub.bin, eid)
			active = os.path.join(self.parent.active_dir, eid)

			if not os.path.exists(binned):
				log.warning(f"Restore failed: Binned data for {eid} not found")
				return False

			temp_backup = f"{active}.bak"
			log.info(f"Restoring {self.parent.entity_type} data for {eid} from bin")

			try:
				def sync_restore_ops():
					if os.path.exists(active):
						os.rename(active, temp_backup)
					shutil.move(binned, active)
					if os.path.exists(temp_backup):
						shutil.rmtree(temp_backup)

					info_file = self.parent.file_routes.delete_time(eid)
					if os.path.exists(info_file):
						os.remove(info_file)

				await asyncio.to_thread(sync_restore_ops)
				log.info(f"Successfully restored {self.parent.entity_type} {eid}")
				return True
			except Exception:
				log.error(f"Restore failed for '{eid}'", exc_info=True)
				def rollback():
					if os.path.exists(temp_backup):
						log.info(f"Rolling back restoration for {eid}")
						os.rename(temp_backup, active)
				await asyncio.to_thread(rollback)
				return False

		async def delete_permanent(self, entity_id: int) -> tuple[bool, str]:
			eid = str(entity_id)
			source = os.path.join(self.parent.active_dir, eid)
			binned = os.path.join(sub.bin, eid)

			def sync_delete_logic():
				if os.path.exists(binned): path = binned
				elif os.path.exists(source): path = source
				else: path = None

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

		async def get_zip(self, entity_id: int) -> tuple[bool, Union[io.BytesIO, str]]:
			eid = str(entity_id)
			source_dir = os.path.join(self.parent.active_dir, eid)

			if not os.path.exists(source_dir):
				log.warning(f"Zip failed: Source path {source_dir} does not exist")
				return False, "We could not find any data related to you in our storage."

			def create_in_memory_zip():
				buffer = io.BytesIO()
				try:
					def dict_to_markdown(data_obj, level=0) -> str:
						md = ""
						indent = "\t" * level
						if isinstance(data_obj, dict):
							for key, value in data_obj.items():
								if isinstance(value, (dict, list)) and value:
									md += f"{indent}- **{key}**:\n"
									md += dict_to_markdown(value, level + 1)
								else:
									md += f"{indent}- **{key}**: {value}\n"
						elif isinstance(data_obj, list):
							for item in data_obj:
								if isinstance(item, (dict, list)):
									md += dict_to_markdown(item, level + 1)
								else:
									md += f"{indent}- {item}\n"
						else:
							md += f"{indent}{data_obj}\n"
						return md

					with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
						readme_content = (
							f"# {self.parent.entity_type.capitalize()} Data Export\n\n"
							"This archive contains a readable export of your requested data.\n\n"
							"### File Guide:\n"
							"- **settings.md**: Your core preferences and configuration settings.\n"
							"- **ai_data.md**: Cached information the AI uses for processing.\n"
						)
						if self.parent.entity_type == "guild":
							readme_content += (
								"- **commands.py**: Custom commands setup for this server.\n"
								"- **events.py**: Custom events setup for this server.\n"
							)
						
						readme_content += "\n*Note: Original JSON data files have been formatted as readable Markdown lists for easier viewing.*"
						zf.writestr("README.md", readme_content)

						for root, _, files in os.walk(source_dir):
							for file_name in files:
								full_path = os.path.join(root, file_name)
								rel_path = os.path.relpath(full_path, source_dir)

								if file_name.endswith('.json'):
									try:
										with open(full_path, 'r', encoding='utf-8') as f:
											json_data = json.load(f)

										md_content = f"# {file_name.replace('.json', '').capitalize()} Data\n\n"
										md_content += dict_to_markdown(json_data)

										md_rel_path = rel_path[:-5] + ".md"
										zf.writestr(md_rel_path, md_content)
									except json.JSONDecodeError:
										zf.write(full_path, rel_path)
								else:
									zf.write(full_path, rel_path)

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
			log.info(f"Saving settings for {self.parent.entity_type} {entity_id}")
			path = self.parent.file_routes.settings(str(entity_id))
			return await json_file.save(path, data)

	class Info:
		def __init__(self, parent: "BaseProfileManager"):
			self.parent = parent

		async def load(self, entity_id: int) -> tuple[bool, dict[str, Any]]:
			log.debug(f"Loading AI info for {self.parent.entity_type} {entity_id}")
			path = self.parent.file_routes.ai_data(str(entity_id))
			success, data = await json_file.load(path)
			return success, data.get(self.parent.entity_type, {})

		async def save(self, entity: Union[discord.Guild, discord.User, discord.Member]) -> bool:
			log.info(f"Updating cached info for {self.parent.entity_type} {entity.id}")
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
		commands_path = self.file_routes.commands(eid)
		events_path = self.file_routes.events(eid)

		success = await super()._setup(
			entity_id=guild.id, 
			entity_name=guild.name, 
			extra_paths=[commands_path, events_path]
		)

		if success:
			await text_file.save(commands_path, "")
			await text_file.save(events_path, "")

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

	async def setup(self, user: Union[discord.User, discord.Member]) -> bool:
		return await super()._setup(
			entity_id=user.id,
			entity_name=user.name
		)


server = Server()
user = User()


__all__ = ('server', 'user')
