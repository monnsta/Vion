from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DirectoryPaths:
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
		return self.guilds / entity_id / self.custom_cog_dir_name


@dataclass(frozen=True)
class Shared:
	blacklist: Path
	activity: Path
	notif: Path
	runtime: Path
	ai_data: Path


@dataclass(frozen=True)
class BaseEntity:
	dirs: DirectoryPaths
	base_dir: Path
	settings_filename: str
	ai_data_filename: str
	delete_time_filename: str

	def settings(self, entity_id: str) -> Path:
		return self.base_dir / entity_id / self.settings_filename

	def ai_data(self, entity_id: str) -> Path:
		return self.base_dir / entity_id / self.ai_data_filename

	def delete_time(self, entity_id: str) -> Path:
		return self.dirs.trash / entity_id / self.delete_time_filename


@dataclass(frozen=True)
class User(BaseEntity):
	pass


@dataclass(frozen=True)
class Guild(BaseEntity):
	custom_cog_filename: str
	custom_cog_data_filename: str

	def custom_cog(self, guild_id: str) -> Path:
		return self.dirs.custom_cogs(guild_id) / self.custom_cog_filename

	def custom_cog_data(self, guild_id: str) -> Path:
		return self.dirs.custom_cogs(guild_id) / self.custom_cog_data_filename


@dataclass(frozen=True)
class Storage:
	dirs: DirectoryPaths
	env: Path
	config: Path
	shared: Shared
	guilds: Guild
	users: User
