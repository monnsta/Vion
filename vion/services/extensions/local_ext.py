"""
Local bot extensions discoverer, loader, and app command mapper.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Iterable, Optional, Any

import discord
from discord.ext import commands

from config import config, storage


log = logging.getLogger("extensions")


@dataclass
class CommandInfo:
	"""Data model storing metadata and rendered mention formatting for app commands."""

	id: Optional[int]
	root_id: Optional[int]
	name: str
	aliases: List[str] = field(default_factory=list)
	mention: Optional[str] = None
	description: str = "No description."
	parameters: List[Any] = field(default_factory=list)
	doc: Optional[str] = None

	def __str__(self) -> str:
		return self.mention or self.name

	def __repr__(self) -> str:
		return f"<CommandInfo name={self.name!r} mention={self.mention!r}>"


def map_command_mentions(synced_commands: List[discord.app_commands.AppCommand], bot: commands.Bot):
	"""
	Traverse synced app command structures and populate global config references.

	Args:
		synced_commands: List of synced application command objects.
		bot: Active Discord bot instance.
	"""
	def walk(command, prefix="", root_id=None):
		current_root_id = root_id or getattr(command, "id", None)
		name = f"{prefix} {command.name}".strip()
		var_name = name.replace(" ", ".")

		options = getattr(command, "options", [])

		command_types = (
			discord.AppCommandOptionType.subcommand,
			discord.AppCommandOptionType.subcommand_group
		)

		is_group = any(
			opt.type in command_types
			for opt in options
		)

		if is_group:
			mention_name = None
		else:
			mention_name = getattr(command, "mention", f"</{name}:{current_root_id}>")

		bot_cmd = bot.get_command(name)

		doc_string = None
		if hasattr(command, "extras"):
			doc_string = command.extras.get("doc")
		if not doc_string and bot_cmd and hasattr(bot_cmd, "extras"):
			doc_string = bot_cmd.extras.get("doc")

		command_data = CommandInfo(
			id=getattr(command, "id", current_root_id),
			root_id=current_root_id,
			name=name,
			mention=mention_name,
			description=getattr(command, "description", "No description."),
			parameters=options,
			doc=doc_string
		)

		config.cmd.set(var_name, command_data)

		for opt in options:
			if opt.type in command_types:
				walk(opt, prefix=name, root_id=current_root_id)

	for cmd in synced_commands:
		walk(cmd)


class Extension:
	"""Handler for finding, loading, unloading, and reloading core bot extensions."""

	async def _handle_dev_guilds(self, bot: commands.Bot, extension: str, dev_guilds: Iterable | None = None) -> None:
		"""
		Bind developer-only application commands directly to designated development guilds.

		Args:
			bot: Active Discord bot instance.
			extension: Module path string for loaded extension.
			dev_guilds: Iterable of guild ID strings/ints for developer testing.
		"""
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
		"""
		Scan the configured cogs directory recursively for valid extension package paths.

		Returns:
			List of dot-separated extension module paths.
		"""
		extensions = []

		cog_dir = Path(storage.dirs.cogs).resolve()
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
		"""
		Load a single bot extension by module path.

		Args:
			bot: Active Discord bot instance.
			extension: Module path string.

		Returns:
			Tuple of (success_boolean, status_or_error_message).
		"""
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
		"""
		Unload a single bot extension by module path.

		Args:
			bot: Active Discord bot instance.
			extension: Module path string.

		Returns:
			Tuple of (success_boolean, status_or_error_message).
		"""
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
		"""
		Reload an active bot extension or attempt load if not active.

		Args:
			bot: Active Discord bot instance.
			extension: Module path string.

		Returns:
			Tuple of (success_boolean, status_or_error_message).
		"""
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
		"""
		Discover and load all available extensions under the cogs directory.

		Args:
			bot: Active Discord bot instance.

		Returns:
			Dictionary mapping extension path string to result tuple.
		"""
		results = {}
		for ext in await self.get_all():
			results[ext] = await self.load(bot, ext)
		return results

	async def unload_all(self, bot: commands.Bot) -> Dict[str, Tuple[bool, str]]:
		"""
		Unload all currently active extensions.

		Args:
			bot: Active Discord bot instance.

		Returns:
			Dictionary mapping extension path string to result tuple.
		"""
		results = {}
		loaded_exts = list(bot.extensions)

		for ext in loaded_exts:
			results[ext] = await self.unload(bot, ext)
		return results

	async def reload_all(self, bot: commands.Bot) -> Dict[str, Tuple[bool, str]]:
		"""
		Reload all currently active extensions.

		Args:
			bot: Active Discord bot instance.

		Returns:
			Dictionary mapping extension path string to result tuple.
		"""
		results = {}
		loaded_exts = list(bot.extensions)

		for ext in loaded_exts:
			results[ext] = await self.reload(bot, ext)
		return results
