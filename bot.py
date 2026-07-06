import bootstrap as _

import logging
import sys

import discord
from discord.ext import commands

from core.lib.utils import map_command_mentions
from core.wrp.profile import server, user
from core.wrp.extension import extension
from meta import config


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

	async def setup_hook(self):
		log.info("Starting Setup...")

		await extension.load_all(self)

		try:
			global_cmds = await self.tree.fetch_commands()
			map_command_mentions(global_cmds, config)

			try:
				guild = discord.Object(id=int(config.dev_server_ids[0]))
				guild_cmds = await self.tree.fetch_commands(guild=guild)
				map_command_mentions(guild_cmds, config)
			except discord.HTTPException:
				pass
		except discord.HTTPException:
			log.error("Failed to fetch commands during startup", exc_info=True)

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
		key = config.get("secrets.discord_api_key", None)
		if key:
			bot.run(key, log_handler=None)
		else:
			log.critical("Could not find the bot token.")
			sys.exit(10)
	except (KeyboardInterrupt, SystemExit):
		log.info("Process terminated by user")
	except Exception:
		log.critical("Fatal error during bot startup", exc_info=True)
