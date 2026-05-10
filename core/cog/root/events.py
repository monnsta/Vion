import asyncio
import difflib
import logging
import random
import shutil
from datetime               import datetime, timedelta
from pathlib                import Path

import discord
from discord.ext            import commands, tasks

from core.lib.file          import json_file
from core.wrp.profile       import server
from core.cog.ui_template   import Fail, Generic
from meta                   import config, file, sub


log = logging.getLogger(__name__)


class Events(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.status_queue = []
		self.random_status_task = self.bot.loop.create_task(self.random_status_change())
		log.debug("General Cog initialized.")

	def cog_unload(self):
		self.cleanup_old_data.cancel()
		if self.random_status_task:
			self.random_status_task.cancel()
		log.info("General Cog unloaded and tasks cancelled.")
		return super().cog_unload()

	async def random_status_change(self):
		await self.bot.wait_until_ready()
		log.debug("Random status task started.")

		while not self.bot.is_closed():
			try:
				if not self.status_queue:
					self.status_queue = config.status.list
					random.shuffle(self.status_queue)

				new_status = self.status_queue.pop()
				log.debug(f"Changing status to: {new_status}")

				await self.bot.change_presence(
					activity=discord.Activity(
						type=config.status.type,
						name=new_status
					),
					status=discord.Status.dnd
				)

				wait_seconds = random.randint(*config.status.range)
				await asyncio.sleep(wait_seconds)
			except asyncio.CancelledError:
				log.debug("Random status task cancelled.")
				return
			except Exception:
				log.error(f"An unexpected error occurred in random_status_change", exc_info=True)
				await asyncio.sleep(10)

	@staticmethod
	async def safe_send(guild: discord.Guild, view):
		if (
			guild.system_channel
			and isinstance(guild.system_channel, discord.TextChannel)
			and guild.system_channel.permissions_for(guild.me).send_messages
		):
			try:
				await guild.system_channel.send(view=view)
				return
			except discord.Forbidden:
				log.warning(f"Forbidden to send in system channel of {guild.id}")
				pass

		for channel in sorted(guild.text_channels, key=lambda c: c.position):
			if channel.permissions_for(guild.me).send_messages:
				if (
					channel == channel.guild.system_channel or
					channel.type == discord.ChannelType.news or
					(channel.guild.rules_channel and channel.id == channel.guild.rules_channel.id)
				):
					continue
				try:
					await channel.send(view=view)
					log.info(f"Sent join message to channel {channel.name} in {guild.id}")
					return
				except discord.Forbidden:
					continue
		log.warning(f"Could not find a suitable channel to send join message in {guild.id}")


	# --- Background Tasks ---
	@tasks.loop(hours=24)
	async def cleanup_old_data(self):
		log.info("Starting scheduled cleanup of old data.")

		servers_path = Path(sub.servers)
		if servers_path.exists():
			guild_ids = {str(guild.id) for guild in self.bot.guilds}
			for folder in servers_path.iterdir():
				if folder.is_dir() and folder.name not in guild_ids:
					log.info(f"Removing data for unknown guild: {folder.name}")
					await server.data.delete(folder.name)

		current_time = datetime.now(config.timezone)
		bin_path = Path(sub.trash)
		if bin_path.exists():
			for folder in bin_path.iterdir():
				if not folder.is_dir():
					continue

				timestamp_file = Path(file.server.delete_time(folder.name))

				if timestamp_file.exists():
					try:
						_, info = await json_file.load(str(timestamp_file))
						moved_at_str = info.get("moved_at")
						if moved_at_str:
							moved_at_time = datetime.fromisoformat(moved_at_str)
							if current_time - moved_at_time > timedelta(days=config.cleanup_days):
								shutil.rmtree(folder)
								log.info(f"Permanently deleted data for guild {folder.name} from bin.")
					except Exception:
						log.error(f"Error processing bin folder {folder.name}", exc_info=True)
				else:
					log.debug(f"No timestamp found for {folder.name}, cleaning up directly.")
					shutil.rmtree(folder)


	@cleanup_old_data.before_loop
	async def before_cleanup(self):
		await self.bot.wait_until_ready()
		log.debug("Cleanup task waiting for bot to be ready.")


	# --- Core Event Listeners ---
	@commands.Cog.listener()
	async def on_ready(self):
		log.info(f"Bot is ready. Logged in as {getattr(self.bot, 'user', 'Unknown')}")
		status = random.choice(config.status.list)
		await self.bot.change_presence(
			activity=discord.Activity(
				type=config.status.type,
				name=status
			),
			status=discord.Status.dnd
		)
		log.info("Updating Guilds...")
		for guild in self.bot.guilds:
			if await blacklist.is_blacklisted(guild.id, "server"):
				log.warning(f"Found blacklisted guild {guild.name} ({guild.id}). Leaving...")
				await guild.leave()
			await server.info.save(guild)
			log.debug(f"Updated guild: '{getattr(guild, 'id', 'Could not retrieve id... somehow')}'")

		self.cleanup_old_data.start()
		log.info("Initialization tasks completed.")


	@commands.Cog.listener()
	async def on_guild_join(self, guild: discord.Guild):
		if await blacklist.is_blacklisted(guild.id, "server"):
			log.warning(f"Joined blacklisted guild: {guild.name} ({guild.id}). Leaving...")
			await guild.leave()
			return

		log.info(f"Joined guild: {guild.name} ({guild.id})")
		data_restored = await server.data.restore(guild.id)

		legal = (
			"-# By adding this bot, you agree to our "
			f"[Terms of Service]( <https://{config.domain}/terms> ) & "
			f"[Privacy Policy]( <https://{config.domain}/privacy> )."
		)
		if data_restored:
			log.info(f"Data restored for guild {guild.id}.")
			view = Generic(
				"Here we go again.",
				None,
				legal
			)
		else:
			await server.setup(guild)
			await server.info.save(guild)
			log.info(f"Setup performed for new guild {guild.id}.")
			view = Generic(
				"## Ding Dong.",
				f"Use {config.cmd.help.manual}, or your server's organic matter might achieve peak frustration with me.",
				None,
				legal
			)

		await self.safe_send(guild, message)


	@commands.Cog.listener()
	async def on_guild_remove(self, guild: discord.Guild):
		log.info(f"Left guild: {guild.name} ({guild.id}). Purging data.")
		await server.data.delete(guild.id)


	@commands.Cog.listener()
	async def on_command_error(self, ctx: commands.Context, error):
		if hasattr(ctx.command, 'on_error'):
			return

		error = getattr(error, 'original', error)

		if isinstance(error, commands.CommandNotFound):
			invoked_with = ctx.invoked_with
			all_commands = list(self.bot.command_mentions.keys())
			matches = difflib.get_close_matches(invoked_with, all_commands, n=1, cutoff=0.6)

			if matches:
				suggestion_name = matches[0]
				suggestion_mention = self.bot.command_mentions.get(suggestion_name)
				description = f"The command `{invoked_with}` does not exist. Did you mean {suggestion_mention}?"
			else:
				description = "The command you entered does not exist."

			await ctx.reply(view=Fail("Invalid Command", description))

		elif isinstance(error, commands.MissingRequiredArgument):
			await ctx.reply(view=Fail(
				"Missing Argument", 
				f"You missed the `{error.param.name}` parameter. Use {config.cmd.help.command} {ctx.command} for details."
			))

		elif isinstance(error, commands.CommandOnCooldown):
			await ctx.reply(view=Fail(
				"On Cooldown", 
				f"You can try this again in **{error.retry_after:.1f}s**."
			))

		elif isinstance(error, commands.MissingPermissions):
			perms = ", ".join([f"`{p.replace('_', ' ').title()}`" for p in error.missing_permissions])
			await ctx.reply(view=Fail(
				"Missing Permissions", 
				f"You need the following permission(s) to do that: {perms}"
			))

		elif isinstance(error, commands.BotMissingPermissions):
			perms = ", ".join([f"`{p.replace('_', ' ').title()}`" for p in error.missing_permissions])
			await ctx.reply(view=Fail(
				"Missing Permissions", 
				f"I don't have the permissions required to run this: {perms}"
			))

		elif isinstance(error, (commands.CheckFailure, commands.BadArgument)):
			await ctx.reply(view=Fail(
				"Command Error",
				f"```{error}```"
			))

		else:
			log.error(f"Ignoring exception in command {ctx.command}:", exc_info=error)
