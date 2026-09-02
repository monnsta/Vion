import logging
from pathlib import Path
from typing import Tuple

import discord
from discord.ext import commands

from infrastructure.file import text_file
from config import storage


log = logging.getLogger("extensions")


class GuildCog(commands.Cog):
	def __init__(self, bot: commands.Bot, guild_id: int):
		self.bot = bot
		self.guild_id = guild_id

	def cog_check(self, ctx: commands.Context) -> bool:
		if ctx.guild is None:
			return False
		return ctx.guild.id == self.guild_id

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		return interaction.guild_id == self.guild_id


class ServerCogManager:
	def _get_module_name(self, guild_id: int) -> str:
		cog_path = storage.guilds.custom_cog(str(guild_id))
		rel_path = Path(cog_path).relative_to(Path.cwd())
		return str(rel_path.with_suffix('')).replace('/', '.').replace('\\', '.')

	def _isolate_cog_commands(self, guild_id: int, bot: commands.Bot, module: str) -> None:
		guild_obj = discord.Object(id=guild_id)

		for _, cog in bot.cogs.items():
			if getattr(cog, '__module__', '') == module:
				for app_cmd in cog.get_app_commands():
					bot.tree.add_command(app_cmd, guild=guild_obj, override=True)
					bot.tree.remove_command(app_cmd.name)  # Remove from global tree

				for cmd in cog.get_commands():
					if isinstance(cmd, (commands.HybridCommand, commands.HybridGroup)) and cmd.app_command:
						bot.tree.add_command(cmd.app_command, guild=guild_obj, override=True)
						bot.tree.remove_command(cmd.app_command.name)

	async def edit(self, guild_id: int, bot: commands.Bot, code: str) -> Tuple[bool, str]:
		path = storage.guilds.custom_cog(str(guild_id))

		success, old_code = await self.read(guild_id)
		if not success:
			old_code = ""

		save_success = await text_file.save(path, code)
		if not save_success:
			return False, "Failed to write cog code to file."

		load_success, msg = await self.load(guild_id, bot)

		if not load_success:
			await text_file.save(path, old_code)
			if old_code.strip():
				await self.load(guild_id, bot)
			else:
				await self.unload(guild_id, bot)
			return False, f"Edit reverted due to syntax or load error:\n{msg}"

		return True, "Cog updated and loaded successfully."

	async def read(self, guild_id: int) -> Tuple[bool, str]:
		path = storage.guilds.custom_cog(str(guild_id))
		return await text_file.load(path)

	async def delete(self, guild_id: int, bot: commands.Bot) -> Tuple[bool, str]:
		await self.unload(guild_id, bot)
		path = storage.guilds.custom_cog(str(guild_id))
		success = await text_file.save(path, "")
		if success:
			return True, "Cog deleted and cleared successfully."
		return False, "Failed to clear cog code."

	async def load(self, guild_id: int, bot: commands.Bot) -> Tuple[bool, str]:
		module = self._get_module_name(guild_id)
		try:
			await bot.load_extension(module)
			self._isolate_cog_commands(guild_id, bot, module)
			return True, "Cog loaded successfully."
		except commands.ExtensionAlreadyLoaded:
			try:
				await bot.reload_extension(module)
				self._isolate_cog_commands(guild_id, bot, module)
				return True, "Cog reloaded successfully."
			except commands.ExtensionFailed as e:
				log.error(f"Failed to reload server cog {guild_id}: {e.original}")
				return False, f"Reload setup error: {e.original}"
			except Exception as e:
				log.error(f"Failed to reload server cog {guild_id}: {e}")
				return False, f"Reload error: {e}"
		except commands.NoEntryPointError:
			return False, "Missing `setup` function in cog."
		except commands.ExtensionFailed as e:
			log.error(f"Failed to load server cog {guild_id}: {e.original}")
			return False, f"Setup error: {e.original}"
		except Exception as e:
			log.error(f"Failed to load server cog {guild_id}: {e}")
			return False, f"Error: {e}"

	async def unload(self, guild_id: int, bot: commands.Bot) -> Tuple[bool, str]:
		module = self._get_module_name(guild_id)
		try:
			await bot.unload_extension(module)
			return True, "Cog unloaded successfully."
		except commands.ExtensionNotLoaded:
			return False, "Cog is not currently loaded."
		except Exception as e:
			log.error(f"Failed to unload server cog {guild_id}: {e}")
			return False, f"Error: {e}"

	async def load_all(self, bot: commands.Bot) -> None:
		servers_dir = Path('data/servers')
		if not servers_dir.exists():
			return

		for server_dir in servers_dir.iterdir():
			if server_dir.is_dir() and server_dir.name.isdigit():
				cog_file = Path(storage.guilds.custom_cog(server_dir.name))
				if cog_file.exists() and cog_file.stat().st_size > 0:
					await self.load(int(server_dir.name), bot)

	async def sync(self, guild_id: int, bot: commands.Bot) -> Tuple[bool, str]:
		try:
			guild_obj = discord.Object(id=guild_id)

			module_prefix = self._get_module_name(guild_id)
			for _, cog in bot.cogs.items():
				if getattr(cog, '__module__', '') == module_prefix:
					for app_cmd in cog.get_app_commands():
						bot.tree.add_command(app_cmd, guild=guild_obj, override=True)

					for cmd in cog.get_commands():
						if isinstance(cmd, (commands.HybridCommand, commands.HybridGroup)) and cmd.app_command:
							bot.tree.add_command(cmd.app_command, guild=guild_obj, override=True)

			synced_commands = await bot.tree.sync(guild=guild_obj)

			return True, f"Synced {len(synced_commands)} command(s) successfully."
		except Exception as e:
			log.error(f"Failed to sync commands for {guild_id}: {e}")
			return False, f"Sync error: {e}"
