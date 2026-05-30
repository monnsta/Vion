import bootstrap

import asyncio
import logging
import signal
import sys

import discord
from discord.ext         import commands

from core.lib.bttrdict   import BD, Repr
from core.wrp.profile    import server, user
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
			intents=intents,
			help_command=None
		)
		log.info("Bot initialized")

	@staticmethod
	def _map_command_mentions(synced_commands):
		def walk(command, prefix="", root_id=None):
			root_id = root_id or command.id
			name = f"{prefix} {command.name}".strip()
			var_name = name.replace(" ", ".")
			mention_name = f"</{name}:{root_id}>"

			if isinstance(command, discord.app_commands.Command):
				command_data = BD(
					name=name,
					mention=mention_name,
					description=command.description or "No description.",
					root_id=root_id,
					parameters=command.parameters
				)
				config.cmd.set(var_name, Repr(mention_name, command_data))

			elif isinstance(command, discord.app_commands.Group):
				for sub_item in command.commands:
					walk(sub_item, prefix=name, root_id=root_id)

		for cmd in synced_commands:
			walk(cmd)

	async def setup_hook(self):
		log.info("Starting Setup...")

		loop = asyncio.get_running_loop()
		for sig in (signal.SIGINT, signal.SIGTERM):
			try:
				loop.add_signal_handler(sig, lambda: asyncio.create_task(self.close()))
			except NotImplementedError:
				pass

		dev_guilds = [discord.Object(id=g_id) for g_id in config.dev_server_ids]

		await extension.load_all(self)

		log.info("Syncing application commands...")
		synced_global = await self.tree.sync()

		total_dev_synced = 0
		for guild in dev_guilds:
			try:
				dev_synced = await self.tree.sync(guild=guild)
				total_dev_synced += len(dev_synced)
			except discord.HTTPException as e:
				log.error(f"Failed to sync dev guild {guild.id}: {e}")

		log.info(f"Sync Complete: {len(synced_global)} Global, {total_dev_synced} Dev")
		self._map_command_mentions(synced_global)

	async def determine_prefix(self, _, message):
		guild_settings = {}
		user_settings = {}

		if message.guild:
			_, guild_settings = await server.settings.load(message.guild.id)
		_, user_settings = await user.settings.load(message.author.id) 

		return [
			*config.default_prefix,
			*guild_settings.get("prefix", []),
			*user_settings.get("prefix", [])
		]


if __name__ == "__main__":
	bot = Bot()

	try:
		log.info("Starting bot...")
		bot.run(config.secrets.discord_api_key, log_handler=None)
	except (KeyboardInterrupt, SystemExit):
		log.info("Process terminated by user")
	except Exception:
		log.critical("Fatal error during bot startup", exc_info=True)
