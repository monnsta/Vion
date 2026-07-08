import asyncio
import difflib
import logging
import random
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import discord
from discord.ext import commands, tasks

from core.cog.utils import should_respond
from core.lib.file import json_file
from core.wrp.ai import ai
from core.wrp.memory import guild_memory, user_memory
from core.wrp.profile import server, user
from core.wrp.blacklist import blacklist, BlacklistedError
from meta import config, file, sub

from core.cog.ui_template import Fail, Generic, UnexpectedError


log = logging.getLogger(__name__)


class Events(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.status_queue = []

	async def cog_load(self):
		self.random_status_task = asyncio.create_task(self.random_status_change())
		self.bot.before_invoke(self.verify_subcommand)

	def cog_unload(self):
		if self.cleanup_old_data.is_running():
			self.cleanup_old_data.cancel()
		if self.random_status_task:
			self.random_status_task.cancel()
		return super().cog_unload()


	async def verify_subcommand(self, ctx: commands.Context):
		is_blocked, data = await blacklist.get(ctx.author.id, "user")

		if is_blocked and isinstance(data, dict):
			reason = data.get("reason", "No reason provided.")
			expires_at = data.get("expires_at")

			raise BlacklistedError(reason=reason, expires_at=expires_at)

		if isinstance(ctx.command, commands.Group):
			if ctx.subcommand_passed is None:
				return

			if ctx.invoked_subcommand is None:
				raise commands.CommandNotFound()

	async def random_status_change(self):
		await self.bot.wait_until_ready()
		log.debug("Random status task started.")

		while not self.bot.is_closed():
			try:
				if not self.status_queue:
					self.status_queue = list(config.activity.list)
					random.shuffle(self.status_queue)

				new_status = self.status_queue.pop()
				log.info(f"Changing status to: \"{new_status}\"")

				activity_mapping = {
					0: discord.Game,
					1: discord.Streaming,
					2: discord.Activity,
					3: discord.Activity,
					4: discord.CustomActivity,
					5: discord.Activity,
				}
				status_map = {
					"online": discord.Status.online,
					"idle": discord.Status.idle,
					"dnd": discord.Status.dnd,
					"invisible": discord.Status.invisible
				}

				activity_class = activity_mapping.get(config.activity.type, discord.Activity)
				kwargs: dict[str, Any] = {"name": new_status}

				if activity_class is discord.Activity:
					kwargs["type"] = discord.ActivityType(config.activity.type)
				elif activity_class is discord.Streaming:
					kwargs["url"] = config.activity.url

				await self.bot.change_presence(
					activity=activity_class(**kwargs),
					status=status_map.get(config.activity.status)
				)

				wait_seconds = random.randint(*config.activity.range)
				await asyncio.sleep(wait_seconds)
			except asyncio.CancelledError:
				log.debug("Random status task cancelled.")
				return
			except Exception:
				log.error("An unexpected error occurred in random_status_change", exc_info=True)
				await asyncio.sleep(10)


	async def safe_send(self, guild: discord.Guild, view):
		if (
			guild.system_channel
			and isinstance(guild.system_channel, discord.TextChannel)
			and guild.system_channel.permissions_for(
				guild.me or guild.get_member(getattr(self.bot.user, 'id'))
			).send_messages
		):
			try:
				await guild.system_channel.send(view=view)
				return
			except discord.Forbidden:
				log.warning(f"Forbidden to send in system channel of {guild.id}")

		for channel in sorted(guild.text_channels, key=lambda c: c.position):
			if channel.permissions_for(
				guild.me or guild.get_member(getattr(self.bot.user, 'id'))
			).send_messages:
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
					try:
						await server.data.delete(int(folder.name))
					except ValueError:
						pass

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

							if moved_at_time.tzinfo is None:
								moved_at_time = moved_at_time.replace(tzinfo=config.timezone)

							if current_time - moved_at_time > timedelta(days=config.logging.cleanup_days):
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
		log.info(f"Bot is ready. Logged in as \"{self.bot.user}\"")
		log.info("Updating Guilds...")
		for guild in self.bot.guilds:
			if await blacklist.is_blacklisted(guild.id, "server"):
				log.warning(f"Found blacklisted guild {guild.name} ({guild.id}). Leaving...")
				await guild.leave()
			if not await server.is_setup(guild.id):
				await server.setup(guild)

		if not self.cleanup_old_data.is_running():
			self.cleanup_old_data.start()


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
			f"[Terms of Service]( <https://{config.domain}/{config.bot.name}/terms> ) & "
			f"[Privacy Policy]( <https://{config.domain}/{config.bot.name}/privacy> )."
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

		await self.safe_send(guild, view)


	@commands.Cog.listener()
	async def on_guild_remove(self, guild: discord.Guild):
		if guild.unavailable:
			return

		log.info(f"Left guild: {guild.name} ({guild.id}). Purging data.")
		await server.data.delete(guild.id)


	@commands.Cog.listener()
	async def on_message(self, message: discord.Message):
		if await blacklist.is_blacklisted(message.author.id, "user"):
			return
		if message.guild and await blacklist.is_blacklisted(message.guild.id, "server"):
			await message.guild.leave()

		if message.guild:
			if not await server.is_setup(message.guild.id):
				await server.setup(message.guild)
			_, current_memories = await guild_memory.get(message.guild.id)
			if not current_memories:
				async for msg in message.channel.history(limit=50):
					await guild_memory.add(message.guild.id, msg)
			else:
				await guild_memory.add(message.guild.id, message)
		else:
			if not await user.is_setup(message.author.id):
				await user.setup(message.author)
			_, current_memories = await user_memory.get(message.author.id)
			if not current_memories:
				async for msg in message.channel.history(limit=50):
					await user_memory.add(message.author.id, msg)
			else:
				await user_memory.add(message.author.id, message)

		_, guild_settings = await server.settings.load(message.guild.id) if message.guild else '', {}

		prefixes = await self.bot.determine_prefix(None, message) # type: ignore
		free_will = guild_settings.get("free_will", True)

		if should_respond(self.bot, free_will, prefixes, message):
			log.info(f"Responding to message: {message.content if message.content != '' else '*empty message*'}")
			await ai.do_action(
				"on_message",
				message.guild,
				message.author,

				message=message,
				bot=self.bot
			)


	@commands.Cog.listener()
	async def on_command_error(self, ctx: commands.Context, error):
		if hasattr(ctx.command, 'on_error'):
			return

		error = getattr(error, 'original', error)

		if isinstance(error, BlacklistedError):
			duration_str = "Permanent"
			if error.expires_at:
				try:
					dt = datetime.fromisoformat(error.expires_at)
					duration_str = f"Expires <t:{int(dt.timestamp())}:R>"
				except ValueError:
					duration_str = "Temporary (The date got corrupted)"

			await ctx.reply(
				view=Fail(
					"Access Denied",
					"You are restricted from using this bot.\n\n",
					f"**Reason:** {error.reason}\n",
					f"**Duration:** {duration_str}"
				),
				ephemeral=True
			)
			return

		elif isinstance(error, commands.CommandNotFound):
			prefix_len = len(ctx.prefix) if ctx.prefix else 0
			content = ctx.message.content[prefix_len:].strip()
			display_attempt = " ".join(content.split())

			def flatten_commands(node, prefix=""):
				cmds = {}
				if not isinstance(node, dict):
					return cmds

				for k, v in node.items():
					path = f"{prefix} {k}".strip()
					if hasattr(v, "mention") and isinstance(getattr(v, "mention"), str):
						cmds[path] = v.mention
					elif isinstance(v, dict):
						cmds.update(flatten_commands(v, path))
				return cmds

			flat_cmds_map = flatten_commands(config.cmd)
			matches = difflib.get_close_matches(display_attempt, list(flat_cmds_map.keys()), n=1, cutoff=0.6)

			if matches:
				suggestion_name = matches[0]
				suggestion_mention_str = flat_cmds_map[suggestion_name]
				description = f"The command `{display_attempt}` does not exist. Did you mean {suggestion_mention_str}?"
			else:
				description = "The command you entered does not exist."

			await ctx.reply(view=Fail("Invalid Command", description), ephemeral=True)
			return

		elif isinstance(error, commands.DisabledCommand):
			await ctx.reply(view=Fail(
				"Command Disabled",
				"This command is currently disabled."
			), ephemeral=True)
			return

		elif isinstance(error, commands.CommandOnCooldown):
			await ctx.reply(view=Fail(
				"On Cooldown",
				f"You can try this again in **{error.retry_after:.1f}s**."
			), ephemeral=True)
			return

		elif isinstance(error, commands.MaxConcurrencyReached):
			await ctx.reply(view=Fail(
				"Too Many Uses",
				f"This command is currently being used by too many people. Please try again later."
			), ephemeral=True)
			return

		elif isinstance(error, commands.MissingRequiredArgument):
			await ctx.reply(view=Fail(
				"Missing Argument",
				f"You missed the `{error.param.name}` parameter. Please provide all required arguments."
			), ephemeral=True)
			return

		elif isinstance(error, commands.BadLiteralArgument):
			literals = ", ".join(f"`{l}`" for l in error.literals)
			await ctx.reply(view=Fail(
				"Invalid Option",
				f"Invalid option for `{error.param.name}`. Must be one of: {literals}"
			), ephemeral=True)
			return

		elif isinstance(error, commands.BadUnionArgument):
			await ctx.reply(view=Fail(
				"Invalid Input",
				f"The argument provided for `{error.param.name}` could not be parsed. Please check the format."
			), ephemeral=True)
			return

		elif isinstance(error, (commands.UserNotFound, commands.MemberNotFound)):
			await ctx.reply(view=Fail(
				"User Not Found",
				"I couldn't find that user. Please provide a valid username,ID, or mention."
			), ephemeral=True)
			return

		elif isinstance(error, commands.ChannelNotFound):
			await ctx.reply(view=Fail(
				"Channel Not Found",
				"I couldn't find that channel. Please provide a valid channel name, ID, or mention."
			), ephemeral=True)
			return

		elif isinstance(error, commands.RoleNotFound):
			await ctx.reply(view=Fail(
				"Role Not Found",
				"I couldn't find that role. Please provide a valid role name, ID, or mention."
			), ephemeral=True)
			return

		elif isinstance(error, commands.GuildNotFound):
			await ctx.reply(view=Fail(
				"Server Not Found",
				"I couldn't find that server. Please provide a valid server ID."
			), ephemeral=True)
			return

		elif isinstance(error, commands.EmojiNotFound):
			await ctx.reply(view=Fail(
				"Emoji Not Found",
				"I couldn't find that emoji. Please provide a valid emoji (custom or unicode)."
			), ephemeral=True)
			return

		elif isinstance(error, commands.BadArgument):
			await ctx.reply(view=Fail(
				"Invalid Argument",
				f"There was an issue with one of the arguments you provided: {error}"
			), ephemeral=True)
			return

		elif isinstance(error, commands.NotOwner):
			await ctx.reply(view=Fail(
				"Restricted Command",
				"Only the bot owner can use this command."
			), ephemeral=True)
			return

		elif isinstance(error, commands.MissingPermissions):
			perms = ", ".join(
				f"`{p.replace('_', ' ').title()}`"
				for p in error.missing_permissions
			)
			await ctx.reply(view=Fail(
				"Missing Permissions",
				f"You need the following permission(s) to do that: {perms}"
			), ephemeral=True)
			return

		elif isinstance(error, commands.BotMissingPermissions):
			perms = ", ".join([f"`{p.replace('_', ' ').title()}`" for p in error.missing_permissions])
			await ctx.reply(view=Fail(
				"Missing Permissions",
				f"I don't have the permissions required to run this: {perms}"
			), ephemeral=True)
			return

		elif isinstance(error, commands.NoPrivateMessage):
			await ctx.reply(view=Fail(
				"Server Only",
				"This command can only be used in a server."
			), ephemeral=True)
			return

		elif isinstance(error, commands.PrivateMessageOnly):
			await ctx.reply(view=Fail(
				"DM Only",
				"This command can only be used in a private message."
			), ephemeral=True)
			return

		elif isinstance(error, commands.CheckFailure):
			await ctx.reply(view=Fail(
				"Permission Denied",
				"You do not have permission to use this command."
			), ephemeral=True)
			return

		else:
			await ctx.reply(view=UnexpectedError, ephemeral=True)
			log.error(f"Ignoring exception in command {ctx.command}:", exc_info=error)
