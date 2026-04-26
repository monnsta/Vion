import bootstrap

import asyncio
import inspect
import logging
import os
import signal
import traceback
import textwrap
import readline

import discord
from discord.ext         import commands

from core.lib.bttrdict   import BD
from core.lib.repl       import AsyncREPL
from core.wrp.profile    import server
from core.wrp.extension  import extension
from meta                import config


log = logging.getLogger(__name__)


class Bot(commands.Bot):
	def __init__(self):
		intents = discord.Intents.default()
		intents.members = True
		intents.presences = True
		intents.message_content = True

		super().__init__(
			command_prefix=self.determine_prefix,
			intents=intents
		)
		self.command_mentions = BD()
		self._repl_task = None
		log.info("Bot initialized")

	def _map_command_mentions(self, synced_commands):
		def walk(command, prefix="", root_id=None):
			if root_id is None:
				root_id = command.id
			full_name = f"{prefix} {command.name}".strip()

			if isinstance(command, discord.app_commands.Command):
				self.command_mentions.set(full_name, f"</{full_name}:{root_id}>")
			elif isinstance(command, discord.app_commands.Group):
				for sub_item in command.commands:
					walk(sub_item, prefix=full_name, root_id=root_id)

		for cmd in synced_commands:
			walk(cmd)

	# Setup & Lifecycle
	async def setup_hook(self):
		log.info("Starting Setup...")

		loop = asyncio.get_running_loop()
		for sig in (signal.SIGINT, signal.SIGTERM):
			try:
				loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))
			except NotImplementedError:
				pass

		dev_guilds = [discord.Object(id=g[0]) for g in config.dev_guilds]

		await extension.load_all(self, dev_guilds)

		log.info("Syncing application commands...")
		synced_global = await self.tree.sync()

		total_dev_synced = 0
		for guild in dev_guilds:
			dev_synced = await self.tree.sync(guild=guild)
			total_dev_synced += len(dev_synced)

		log.info(f"Sync Complete: {len(synced_global)} Global, {total_dev_synced} Dev")

		self._map_command_mentions(synced_global)

		self._repl_task = self.loop.create_task(self.terminal_repl())

	async def shutdown(self):
		log.info("Shutdown signal received. Cleaning up...")
		if self._repl_task:
			self._repl_task.cancel()
		await self.close()
		log.info("Bot closed successfully.")

	# Logic & Utilities
	async def determine_prefix(self, _, message):
		if not message.guild:
			return config.prefix

		_, settings = await server.settings.load(message.guild.id)
		server_prefixes = (
			prefix
			for prefix in settings.get("prefix", [])
			if prefix not in config.prefix
		)
		return [*config.prefix, *server_prefixes]

	async def start_repl(self):
		repl_env = {
			'bot':     self,
			'discord': discord,
			'os':      os,
			'asyncio': asyncio,
			'config':  config
		}

		repl = AsyncREPL(env=repl_env)
		await repl.start()

		if not self.is_closed():
			await self.shutdown()


if __name__ == "__main__":
	bot = Bot()

	try:
		log.info("Starting bot process...")
		bot.run(config.secrets.discord_api_key)
	except (KeyboardInterrupt, SystemExit):
		log.info("Process terminated by user")
	except Exception:
		log.critical("Fatal error during bot startup", exc_info=True)
