"""
Core Discord client initialization and runtime execution module.

Defines client extension loading hooks, lifecycle state tracking,
slash command mention mapping, and runtime setup exceptions.
"""

import vion.bootstrap as _

import asyncio
import logging
import sys

import aiohttp
import discord
from discord.ext import commands

from vion.services.extensions import (
	extension,
	server_cog,
	map_command_mentions
)
from vion.services.trackers import runtime
from vion.config import config


log = logging.getLogger("startup")


class Bot(commands.Bot):
	"""
	Customized Discord Client instance with dynamic command mapping and extension lifecycle management.
	"""

	def __init__(self) -> None:
		"""
		Initialize Discord client instance with configured intent flags.
		"""
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

	async def setup_hook(self) -> None:
		"""
		Asynchronous setup hook invoked prior to gateway websocket connection.

		Loads cogs, registers extensions, tracks startup state, and caches command references.
		"""
		log.info("Starting Setup...")

		await extension.load_all(self)
		await server_cog.load_all(self)

		await runtime.mark_event('startup')

		try:
			global_cmds = await self.tree.fetch_commands()
			map_command_mentions(global_cmds, self)

			try:
				guild = discord.Object(id=int(config.dev_server_ids[0]))
				guild_cmds = await self.tree.fetch_commands(guild=guild)
				map_command_mentions(guild_cmds, self)
			except discord.HTTPException:
				pass
		except discord.HTTPException:
			log.error("Failed to fetch commands during startup", exc_info=True)

	async def on_disconnect(self) -> None:
		"""
		Event handler triggered when client disconnects from the Discord gateway.
		"""
		await runtime.mark_event('disconnect')

	async def on_resumed(self) -> None:
		"""
		Event handler triggered when client connection resumes after disconnection.
		"""
		await runtime.mark_event('resume')

	async def close(self) -> None:
		"""
		Gracefully shut down gateway connections and record shutdown runtime metrics.
		"""
		await runtime.mark_event('shutdown')
		await super().close()


def run() -> None:
	"""
	Instantiate the bot client and initiate login sequence using configured secrets.
	"""
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


if __name__ == "__main__":
	run()
