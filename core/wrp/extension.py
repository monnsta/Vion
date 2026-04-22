import logging
import os
from typing       import Dict, List, Optional, Tuple

from discord.ext  import commands

from meta         import sub


log = logging.getLogger(__name__)


class Extension:
	@staticmethod
	def _get_cog_name(extension: str) -> str:
		return extension.split('.')[-1].capitalize()
	
	async def _handle_dev_guilds(self, bot: commands.Bot, extension: str, dev_guilds: Optional[list]) -> None:
		if not dev_guilds:
			return

		cog_name = self._get_cog_name(extension)
		cog = bot.get_cog(cog_name)

		if cog and getattr(cog, 'dev_only', False):
			for command in cog.get_app_commands():
				for guild in dev_guilds:
					bot.tree.add_command(command, guild=guild, override=True)
					bot.tree.remove_command(command.name)
			log.debug(f"Registered app commands for {extension} in dev guilds.")
	
	async def load(self, bot: commands.Bot, extension: str, dev_guilds: Optional[list] = None) -> Tuple[bool, str]:
		try:
			await bot.load_extension(extension)
			await self._handle_dev_guilds(bot, extension, dev_guilds)
			log.info(f"Loaded cog: '{extension}'")
			return True, f"Successfully loaded `{extension}`."
		except commands.ExtensionAlreadyLoaded:
			return False, f"`{extension}` is already loaded."
		except Exception as e:
			log.error(f"Failed to load {extension}", exc_info=True)
			return False, f"Failed to load:\n```py\n{e}\n```"
	
	async def unload(self, bot: commands.Bot, extension: str) -> Tuple[bool, str]:
		if "cog_manager" in extension:
			return False, "This core cog cannot be unloaded."

		try:
			await bot.unload_extension(extension)
			log.info(f"Unloaded cog: '{extension}'")
			return True, f"Successfully unloaded `{extension}`."
		except commands.ExtensionNotLoaded:
			return False, f"`{extension}` is not loaded."
		except Exception as e:
			log.error(f"Failed to unload {extension}", exc_info=True)
			return False, f"Failed to unload:\n```py\n{e}\n```"
	
	async def reload(self, bot: commands.Bot, extension: str, dev_guilds: Optional[list] = None) -> Tuple[bool, str]:
		try:
			await bot.reload_extension(extension)
			await self._handle_dev_guilds(bot, extension, dev_guilds)
			log.info(f"Reloaded cog: '{extension}'")
			return True, f"Successfully reloaded `{extension}`."
		except commands.ExtensionNotLoaded:
			return await self.load(bot, extension, dev_guilds)
		except Exception as e:
			log.error(f"Failed to reload {extension}", exc_info=True)
			return False, f"Failed to reload:\n```py\n{e}\n```"
	
	async def get_all(self) -> List[str]:
		extensions = []
		for directory in (sub.commands, sub.events):
			dir_path = directory()
			dir_module = directory(module=True)

			if not os.path.exists(dir_path):
				continue

			for filename in os.listdir(dir_path):
				if filename.endswith('.py') and not filename.startswith('__'):
					extensions.append(f"{dir_module}.{filename[:-3]}")

		return extensions
	
	async def load_all(self, bot: commands.Bot, dev_guilds: Optional[list] = None) -> Dict[str, Tuple[bool, str]]:
		results = {}
		for ext in await self.get_all():
			results[ext] = await self.load(bot, ext, dev_guilds)
		return results

	async def unload_all(self, bot: commands.Bot) -> Dict[str, Tuple[bool, str]]:
		results = {}
		loaded_exts = list(bot.extensions.keys())

		for ext in loaded_exts:
			if "cog_manager" not in ext:
				results[ext] = await self.unload(bot, ext)
		return results
	
	async def reload_all(self, bot: commands.Bot, dev_guilds: Optional[list] = None) -> Dict[str, Tuple[bool, str]]:
		results = {}
		loaded_exts = list(bot.extensions.keys())

		for ext in loaded_exts:
			results[ext] = await self.reload(bot, ext, dev_guilds)
		return results
extension = Extension()

__all__ = ('extension')