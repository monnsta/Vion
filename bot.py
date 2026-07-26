import bootstrap as _

import asyncio
import logging
import sys

import aiohttp
import discord
from discord.ext import commands

from core.wrp.profile import server, user
from core.wrp.extension import extension, server_cog, map_command_mentions
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
		await server_cog.load_all(self)

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

	async def process_commands(self, message):
		if message.author.bot:
			return

		ctx = await self.get_context(message)

		if ctx.command is None and ctx.prefix:
			unprefixed = message.content[len(ctx.prefix):]
			first_word = unprefixed.split()[0] if unprefixed else ""

			if len(first_word) > 1:
				node = config.cmd
				resolved = []

				for char in first_word:
					if not hasattr(node, "keys"):
						resolved.clear()
						break

					match = next((k for k in node.keys() if k.startswith(char)), None)
					if match:
						resolved.append(match)
						node = getattr(node, match)
					else:
						resolved.clear()
						break

				if resolved and len(resolved) == len(first_word) and hasattr(node, "mention"):
					spaced = " ".join(resolved)

					old_prefix_len = len(f"{ctx.prefix}{first_word}")
					new_prefix_str = f"{ctx.prefix}{spaced}"
					message.content = new_prefix_str + message.content[old_prefix_len:]

					ctx = await self.get_context(message)

		await self.invoke(ctx)


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

	except discord.LoginFailure:
		log.critical("Invalid bot token. Check config.secrets.discord_api_key")
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
