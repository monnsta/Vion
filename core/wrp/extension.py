import logging
from pathlib        import Path
from typing         import Dict, List, Tuple, Iterable

from discord.ext    import commands

from meta           import config, sub, file, create_path
from core.lib.file  import text_file


log = logging.getLogger(__name__)


class Extension:
	@staticmethod
	def _get_cog_name(extension: str) -> str:
		return extension.split('.')[-1].capitalize()

	async def _handle_dev_guilds(self, bot: commands.Bot, extension: str, dev_guilds: Iterable | None = None) -> None:
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

	async def get_all(self) -> List[str]:
		extensions = []
		cog_dir = Path(sub.cog)

		for path in cog_dir.rglob('*.py'):
			if any(part.startswith('_') for part in path.parts):
				continue

			extension_path = str(path.with_suffix('')).replace('\\', '.').replace('/', '.')
			extensions.append(extension_path)

		return extensions

	async def add(self, bot: commands.Bot, guild_id: int | str, code: str) -> Tuple[bool, str]:
		guild_id = str(guild_id)
		cog_path = file.server.commands(guild_id)

		module_path = str(cog_path.with_suffix('')).replace('\\', '.').replace('/', '.')

		try:
			await create_path((cog_path, False))

			await text_file.save(str(cog_path), code)

			if module_path in bot.extensions:
				return await self.reload(bot, module_path)
			return await self.load(bot, module_path)

		except SyntaxError as e:
			log.error(f"Syntax error in custom cog for guild {guild_id}: {e}")
			return False, f"Failed to load due to Syntax Error:\n```py\n{e}\n```"
		except Exception as e:
			log.error(f"Failed to create/load custom cog for {guild_id}", exc_info=True)
			return False, f"Critical error during custom cog deployment:\n```py\n{e}\n```"

	async def load(self, bot: commands.Bot, extension: str) -> Tuple[bool, str]:
		try:
			await bot.load_extension(extension)
			await self._handle_dev_guilds(bot, extension, config.dev_server_ids)
			log.info(f"Loaded cog: '{extension}'")
			return True, f"Successfully loaded `{extension}`."
		except commands.ExtensionAlreadyLoaded:
			return False, f"`{extension}` is already loaded."
		except commands.NoEntryPointError:
			return False, f"`{extension}` is missing a `setup` function."
		except commands.ExtensionFailed as e:
			return False, f"Extension failed to initialize:\n```py\n{e.original}\n```"
		except Exception as e:
			log.error(f"Failed to load {extension}", exc_info=True)
			return False, f"Failed to load:\n```py\n{e}\n```"

	async def unload(self, bot: commands.Bot, extension: str) -> Tuple[bool, str]:
		if "dev" in extension:
			return False, "This cog cannot be unloaded."

		try:
			await bot.unload_extension(extension)
			log.info(f"Unloaded cog: '{extension}'")
			return True, f"Successfully unloaded `{extension}`."
		except commands.ExtensionNotLoaded:
			return False, f"`{extension}` is not loaded."
		except Exception as e:
			log.error(f"Failed to unload {extension}", exc_info=True)
			return False, f"Failed to unload:\n```py\n{e}\n```"

	async def reload(self, bot: commands.Bot, extension: str) -> Tuple[bool, str]:
		try:
			await bot.reload_extension(extension)
			await self._handle_dev_guilds(bot, extension, config.dev_server_ids)
			log.info(f"Reloaded cog: '{extension}'")
			return True, f"Successfully reloaded `{extension}`."
		except commands.ExtensionNotLoaded:
			return await self.load(bot, extension)
		except Exception as e:
			log.error(f"Failed to reload {extension}", exc_info=True)
			return False, f"Failed to reload:\n```py\n{e}\n```"

	async def load_all(self, bot: commands.Bot) -> Dict[str, Tuple[bool, str]]:
		results = {}
		for ext in await self.get_all():
			results[ext] = await self.load(bot, ext)
		return results

	async def unload_all(self, bot: commands.Bot) -> Dict[str, Tuple[bool, str]]:
		results = {}
		loaded_exts = list(bot.extensions.keys())

		for ext in loaded_exts:
			if "cog_manager" not in ext:
				results[ext] = await self.unload(bot, ext)
		return results

	async def reload_all(self, bot: commands.Bot) -> Dict[str, Tuple[bool, str]]:
		results = {}
		loaded_exts = list(bot.extensions.keys())

		for ext in loaded_exts:
			results[ext] = await self.reload(bot, ext)
		return results


extension = Extension()


__all__ = ('extension')
