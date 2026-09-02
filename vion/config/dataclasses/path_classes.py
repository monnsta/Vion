"""
Data models defining directory layouts, file path abstractions, and entity resolution helper methods.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass()
class DirectoryPaths:
	"""
	Core application folder locations and path mapping helpers.
	"""
	root: Path
	data: Path
	logs: Path
	cogs: Path
	trash: Path
	shared: Path
	guilds: Path
	users: Path
	custom_cog_dir_name: str

	def custom_cogs(self, entity_id: str) -> Path:
		"""
		Resolve base custom cog directory for a specific guild ID.

		Args:
			entity_id: String ID representation of the guild.

		Returns:
			Target path pointing to the custom cog directory.
		"""
		return self.guilds / entity_id / self.custom_cog_dir_name


@dataclass()
class Shared:
	"""
	Global shared JSON file locations.
	"""
	blacklist: Path
	activity: Path
	notif: Path
	runtime: Path
	ai_data: Path


@dataclass()
class BaseEntity:
	"""
	Base class defining common file resolution methods for guilds and users.
	"""
	dirs: DirectoryPaths
	base_dir: Path
	settings_filename: str
	ai_data_filename: str
	delete_time_filename: str

	def settings(self, entity_id: str) -> Path:
		"""
		Resolve settings file location for an entity.

		Args:
			entity_id: String ID representation of the entity.

		Returns:
			Target path to settings JSON file.
		"""
		return self.base_dir / entity_id / self.settings_filename

	def ai_data(self, entity_id: str) -> Path:
		"""
		Resolve AI memory/data storage file location for an entity.

		Args:
			entity_id: String ID representation of the entity.

		Returns:
			Target path to AI data JSON file.
		"""
		return self.base_dir / entity_id / self.ai_data_filename

	def delete_time(self, entity_id: str) -> Path:
		"""
		Resolve soft-deletion timestamp file location inside trash storage.

		Args:
			entity_id: String ID representation of the entity.

		Returns:
			Target path to deletion timestamp file inside trash folder.
		"""
		return self.dirs.trash / entity_id / self.delete_time_filename


@dataclass()
class User(BaseEntity):
	"""
	User storage layout mapping inheriting file resolution methods from BaseEntity.
	"""
	pass


@dataclass()
class Guild(BaseEntity):
	"""
	Guild storage layout mapping including custom cog path resolution methods.
	"""
	custom_cog_filename: str
	custom_cog_data_filename: str

	def custom_cog(self, guild_id: str) -> Path:
		"""
		Resolve custom cog entry script file path for a guild.

		Args:
			guild_id: String ID representation of the target guild.

		Returns:
			Target path to custom cog script (__init__.py).
		"""
		return self.dirs.custom_cogs(guild_id) / self.custom_cog_filename

	def custom_cog_data(self, guild_id: str) -> Path:
		"""
		Resolve custom cog persistent data file path for a guild.

		Args:
			guild_id: String ID representation of the target guild.

		Returns:
			Target path to custom cog JSON data store.
		"""
		return self.dirs.custom_cogs(guild_id) / self.custom_cog_data_filename


@dataclass()
class Storage:
	"""
	Master storage configuration container aggregating root paths, shared files, and entities.
	"""
	dirs: DirectoryPaths
	env: Path
	config: Path
	shared: Shared
	guilds: Guild
	users: User
