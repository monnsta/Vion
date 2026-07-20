import logging
import sys
import types
from pathlib import Path
from typing import Dict, List, Tuple, Iterable, Any, cast

import discord
from discord.ext import commands

from core.lib.file import text_file, create_path
from core.lib.dataclass import Data, Repr
from meta import config, sub, file


log = logging.getLogger(__name__)


def map_command_mentions(synced_commands):
	def walk(command, prefix="", root_id=None):
		root_id = root_id or command.id
		name = f"{prefix} {command.name}".strip()
		var_name = name.replace(" ", ".")
		mention_name = f"</{name}:{root_id}>"

		options = getattr(command, "options", [])
		has_subcommands = False

		for opt in options:
			if opt.type in (discord.AppCommandOptionType.subcommand, discord.AppCommandOptionType.subcommand_group):
				has_subcommands = True
				walk(opt, prefix=name, root_id=root_id)

		if not has_subcommands:
			command_data = Data(
				name=name,
				mention=mention_name,
				description=command.description or "No description.",
				root_id=root_id,
				parameters=options
			)
			config.cmd.set(var_name, Repr(mention_name, command_data))

	for cmd in synced_commands:
		walk(cmd)


class Extension:
	async def _handle_dev_guilds(self, bot: commands.Bot, extension: str, dev_guilds: Iterable | None = None) -> None:
		if not dev_guilds:
			return

		for _, cog in bot.cogs.items():
			if getattr(cog, '__module__', '').startswith(extension) and getattr(cog, 'dev_only', False):

				for app_cmd in cog.get_app_commands():
					for guild_id in dev_guilds:
						bot.tree.add_command(app_cmd, guild=discord.Object(id=int(guild_id)), override=True)
					bot.tree.remove_command(app_cmd.name)

				for cmd in cog.get_commands():
					if isinstance(cmd, (commands.HybridCommand, commands.HybridGroup)):
						app_cmd = cmd.app_command
						if app_cmd:
							for guild_id in dev_guilds:
								bot.tree.add_command(app_cmd, guild=discord.Object(id=int(guild_id)), override=True)
							bot.tree.remove_command(app_cmd.name)

				log.info(f"Registered app commands for {extension} in dev guilds.")

	async def get_all(self) -> List[str]:
		extensions = []

		cog_dir = Path(sub.cog).resolve()
		cwd = Path.cwd().resolve()

		for init_path in cog_dir.rglob('__init__.py'):
			try:
				rel_to_cog = init_path.relative_to(cog_dir)
			except ValueError:
				continue

			if any(part.startswith('_') for part in rel_to_cog.parts[:-1]):
				continue

			package_dir = init_path.parent.resolve()

			try:
				relative_path = package_dir.relative_to(cwd)
				extension_path = ".".join(relative_path.parts)
			except ValueError:
				extension_path = ".".join(package_dir.parts)

			extensions.append(extension_path)

		log.debug("Valid extensions found:\n" + "\n".join(f" * {ext}" for ext in extensions))
		return extensions

	async def load(self, bot: commands.Bot, extension: str) -> Tuple[bool, str]:
		try:
			await bot.load_extension(extension)
			await self._handle_dev_guilds(bot, extension, config.dev_server_ids)
			log.info(f"Loaded extension: '{extension}'")
			return True, f"Successfully loaded `{extension}`."
		except commands.ExtensionAlreadyLoaded:
			return False, f"`{extension}` is already loaded."
		except commands.NoEntryPointError:
			log.error(f"Extension '{extension}' has no setup()")
			return False, f"`{extension}` is missing a `setup` function."
		except commands.ExtensionFailed as e:
			log.error(f"Extension '{extension}' failed", exc_info=e.original)
			return False, f"Extension failed to initialize:\n```py\n{e.original}\n```"
		except Exception as e:
			log.error(f"Failed to load {extension}", exc_info=True)
			return False, f"Failed to load:\n```py\n{e}\n```"

	async def unload(self, bot: commands.Bot, extension: str) -> Tuple[bool, str]:
		if "dev" in extension:
			return False, "This cog cannot be unloaded."

		try:
			await bot.unload_extension(extension)
			log.info(f"Unloaded extension: '{extension}'")
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
			log.info(f"Reloaded extension: '{extension}'")
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
		loaded_exts = list(bot.extensions)

		for ext in loaded_exts:
			results[ext] = await self.unload(bot, ext)
		return results

	async def reload_all(self, bot: commands.Bot) -> Dict[str, Tuple[bool, str]]:
		results = {}
		loaded_exts = list(bot.extensions)

		for ext in loaded_exts:
			results[ext] = await self.reload(bot, ext)
		return results


extension = Extension()


__all__ = ('extension',)
