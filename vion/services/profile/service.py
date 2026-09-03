"""
Profile service implementations.

Provides concrete profile managers for Server (Guild) and User entities.
"""

import discord

from vion.infrastructure.file import text_file
from vion.config import config, storage
from vion.config.dataclasses import Guild, User as UserC

from .base import BaseProfileManager, CogData


class Server(BaseProfileManager[Guild]):
	"""
	Profile manager for Discord server (guild) entities.
	"""

	def __init__(self):
		"""Initialize Server profile manager with guild configurations."""
		super().__init__(
			entity_type="guild",
			active_dir=storage.dirs.guilds,
			file_routes=storage.guilds,
			default_settings=config.settings.server,
			default_ai_data=config.ai_data.server
		)
		self.cog_data = CogData(self)

	async def setup(self, guild: discord.Guild) -> bool:
		"""
		Initialize a new server profile directory, custom cog entrypoint, and default state files.

		Args:
			guild: Discord Guild object to set up.

		Returns:
			True if setup succeeded, False otherwise.
		"""
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
	"""
	Profile manager for Discord user entities.
	"""

	def __init__(self):
		"""Initialize User profile manager with user configurations."""
		super().__init__(
			entity_type="user",
			active_dir=storage.dirs.users,
			file_routes=storage.users,
			default_settings=config.settings.user,
			default_ai_data=config.ai_data.user
		)

	async def setup(self, user: discord.User | discord.Member) -> bool:
		"""
		Initialize a new user profile directory and default state files.

		Args:
			user: Discord User or Member object to set up.

		Returns:
			True if setup succeeded, False otherwise.
		"""
		return await super()._setup(
			entity_id=user.id,
			entity_name=user.name
		)
