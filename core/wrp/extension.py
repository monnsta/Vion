import logging
from pathlib import Path
from typing import Dict, List, Tuple, Iterable

import discord
from discord.ext import commands

from core.lib.file import text_file
from core.lib.dataclass import Data, Repr
from meta import config, sub, file


log = logging.getLogger(__name__)


def map_command_mentions(synced_commands: List[discord.app_commands.AppCommand], bot: commands.Bot):
	def walk(command, prefix="", root_id=None):
		root_id = root_id or getattr(command, "id", None)
		name = f"{prefix} {command.name}".strip()
		var_name = name.replace(" ", ".")
		mention_name = f"</{name}:{root_id}>" if root_id else name

		options = getattr(command, "options", [])
		has_subcommands = False

		for opt in options:
			if opt.type in (discord.AppCommandOptionType.subcommand, discord.AppCommandOptionType.subcommand_group):
				has_subcommands = True
				walk(opt, prefix=name, root_id=root_id)

		if not has_subcommands:
			bot_cmd = bot.get_command(name)
			aliases = list(getattr(bot_cmd, "aliases", [])) if bot_cmd else []

			if hasattr(command, "name_localizations") and command.name_localizations:
				aliases.extend(command.name_localizations.values())

			command_data = Data(
				id=getattr(command, "id", root_id),
				root_id=root_id,
				name=name,
				aliases=list(set(aliases)),
				mention=mention_name,
				description=getattr(command, "description", "No description."),
				parameters=options
			)

			repr_obj = Repr(mention_name, command_data)
			config.cmd.set(var_name, repr_obj)

	for cmd in synced_commands:
		walk(cmd)


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
		cog_path = file.server.cog(str(guild_id))
		rel_path = Path(cog_path).relative_to(Path.cwd())
		return str(rel_path.with_suffix('')).replace('/', '.').replace('\\', '.')

	async def edit(self, guild_id: int, bot: commands.Bot, code: str) -> Tuple[bool, str]:
		path = file.server.cog(str(guild_id))

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
		path = file.server.cog(str(guild_id))
		return await text_file.load(path)

	async def delete(self, guild_id: int, bot: commands.Bot) -> Tuple[bool, str]:
		await self.unload(guild_id, bot)
		path = file.server.cog(str(guild_id))
		success = await text_file.save(path, "")
		if success:
			return True, "Cog deleted and cleared successfully."
		return False, "Failed to clear cog code."

	async def load(self, guild_id: int, bot: commands.Bot) -> Tuple[bool, str]:
		module = self._get_module_name(guild_id)
		try:
			await bot.load_extension(module)
			return True, "Cog loaded successfully."
		except commands.ExtensionAlreadyLoaded:
			try:
				await bot.reload_extension(module)
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
				cog_file = Path(file.server.cog(server_dir.name))
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


server_cog = ServerCogManager()
extension = Extension()


__all__ = ('extension', 'server_cog', 'GuildCog')
