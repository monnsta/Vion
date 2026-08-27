import bootstrap as _

import asyncio
import logging
import sys

import aiohttp
import discord
from discord.ext import commands

from core.wrp.extension import extension, server_cog, map_command_mentions
from core.wrp.trackers import runtime
from meta import config


log = logging.getLogger(__name__)


class Bot(commands.Bot):
	def __init__(self):
		intents = discord.Intents.default()
		intents.members = True
		intents.presences = True
		intents.message_content = True

		super().__init__(
			command_prefix=[],
			intents=intents,
			help_command=None
		)

		self.name = config.bot.name
		self.id = config.bot.id
		self.invite = config.bot.invite
		config.set('bot', self)

		log.info("Bot initialized")

	async def setup_hook(self):
		log.info("Starting Setup...")

		await extension.load_all(self)
		await server_cog.load_all(self)

		await runtime.mark_event('startup')

		try:
			global_cmds = await self.tree.fetch_commands()
			map_command_mentions(global_cmds, bot)

			try:
				guild = discord.Object(id=int(config.dev_server_ids[0]))
				guild_cmds = await self.tree.fetch_commands(guild=guild)
				map_command_mentions(guild_cmds, bot)
			except discord.HTTPException:
				pass
		except discord.HTTPException:
			log.error("Failed to fetch commands during startup", exc_info=True)

	async def on_disconnect(self):
		await runtime.mark_event('disconnect')

	async def on_resumed(self):
		await runtime.mark_event('resume')

	async def close(self):
		await runtime.mark_event('shutdown')
		await super().close()


if __name__ == "__main__":
	bot = Bot()

	try:
		log.info("Starting bot...")
		key = config.get("secrets.discord", None)
		if key:
			bot.run(key, log_handler=None)
		else:
			log.critical("Could not find the bot token.")
			sys.exit(10)

	except discord.LoginFailure:
		log.critical("Invalid bot token. Check config.secrets.discord")
	except discord.PrivilegedIntentsRequired:
		log.critical("Privileged intents not enabled in Developer Portal")
	except discord.HTTPException as e:
		log.critical(f"Discord HTTP error {e.status}: {e.text}")
	except aiohttp.ClientConnectorError:
		log.critical("Could not connect to Discord. Check internet/DNS")
	except asyncio.TimeoutError:
		log.critical("Connection to Discord timed out")
	except (KeyboardInterrupt, SystemExit):
		log.info("Process terminated by user")

	except Exception:
		log.critical("An unexpected error occured", exc_info=True)
