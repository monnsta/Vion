import discord

from infrastructure.file import text_file
from config import config, storage
from config.dataclasses import Guild, User as UserC

from .base import BaseProfileManager, CogData


class Server(BaseProfileManager[Guild]):
	def __init__(self):
		super().__init__(
			entity_type="guild",
			active_dir=storage.dirs.guilds,
			file_routes=storage.guilds,
			default_settings=config.settings.server,
			default_ai_data=config.ai_data.server
		)
		self.cog_data = CogData(self)

	async def setup(self, guild: discord.Guild) -> bool:
		eid = str(guild.id)
		cog = self.file_routes.custom_cog(eid)

		success = await super()._setup(
			entity_id=guild.id,
			entity_name=guild.name,
			extra_paths=[cog]
		)

		if success:
			await text_file.save(cog, "")

		return success

class User(BaseProfileManager[UserC]):
	def __init__(self):
		super().__init__(
			entity_type="user",
			active_dir=storage.dirs.users,
			file_routes=storage.users,
			default_settings=config.settings.user,
			default_ai_data=config.ai_data.user
		)

	async def setup(self, user: discord.User | discord.Member) -> bool:
		return await super()._setup(
			entity_id=user.id,
			entity_name=user.name
		)
