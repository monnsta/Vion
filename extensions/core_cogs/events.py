import asyncio
import logging
import random
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from vion.infrastructure.file import json_file
from vion.services.profile import server, user
from vion.services.blacklist import blacklist, BlacklistedError
from vion.ui_templates import (
	Generic,
	Fail,
	UnexpectedError
)
from vion.config import config, storage



log = logging.getLogger("extensions")


class CoreEvents(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.status_queue = []

	async def cog_load(self):
		self.random_status_task = asyncio.create_task(self.random_status_change())
		self.bot.tree.interaction_check = self.global_blacklist_validator
		self.bot.tree.on_error = self.on_app_command_error
		if not self.cleanup_old_data.is_running():
			self.cleanup_old_data.start()

	def cog_unload(self):
		if self.cleanup_old_data.is_running():
			self.cleanup_old_data.cancel()
		if self.random_status_task:
			self.random_status_task.cancel()
		return super().cog_unload()


	async def global_blacklist_validator(self, interaction: discord.Interaction) -> bool:
		is_blocked, data = await blacklist.get(interaction.user.id, "user")
		if is_blocked and isinstance(data, dict):
			reason = data.get("reason", "No reason provided.")
			expires_at = data.get("expires_at")
			raise BlacklistedError(reason=reason, expires_at=expires_at)
		return True

	async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
		if isinstance(error, BlacklistedError):
			duration_str = "Permanent"
			if error.expires_at:
				try:
					dt = datetime.fromisoformat(error.expires_at)
					duration_str = f"Expires <t:{int(dt.timestamp())}:R>"
				except ValueError:
					duration_str = "Temporary (The date got corrupted)"

			view = Fail(
				"Access Denied",
				"You are restricted from using this bot.\n\n",
				f"**Reason:** {error.reason}\n",
				f"**Duration:** {duration_str}"
			)
			if interaction.response.is_done():
				await interaction.followup.send(view=view, ephemeral=True)
			else:
				await interaction.response.send_message(view=view, ephemeral=True)
			return

		if isinstance(error, app_commands.errors.CheckFailure):
			view = Fail(
				"Action Prohibited",
				"You lack the authorization or administrator status required to trigger this utility."
			)
			if interaction.response.is_done():
				await interaction.followup.send(view=view, ephemeral=True)
			else:
				await interaction.response.send_message(view=view, ephemeral=True)
			return

		log.error(f"Unresolved App Command Error in /{interaction.command.qualified_name if interaction.command else 'unknown'}:", exc_info=error)
		try:
			if interaction.response.is_done():
				await interaction.followup.send(view=UnexpectedError, ephemeral=True)
			else:
				await interaction.response.send_message(view=UnexpectedError, ephemeral=True)
		except Exception:
			pass

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

		servers_path = Path(storage.dirs.guilds)
		if servers_path.exists():
			guild_ids = {str(guild.id) for guild in self.bot.guilds}
			for folder in servers_path.iterdir():
				if folder.is_dir() and folder.name not in guild_ids:
					log.info(f"Removing data for unknown guild: {folder.name}")
					try:
						await server.data.delete(int(folder.name))
					except ValueError:
						pass

		users_path = Path(storage.dirs.users)
		if users_path.exists():
			cutoff = datetime.now(timezone.utc) - timedelta(days=getattr(config.logging, "cleanup_days", 30))
			for folder in users_path.iterdir():
				if folder.is_dir() and folder.name.isdigit():
					user_id = int(folder.name)

					is_stale = False

					mtime = datetime.fromtimestamp(folder.stat().st_mtime, tz=timezone.utc)
					if mtime < cutoff:
						is_stale = True

					if is_stale:
						log.info(f"Removing inactive user profile data: {user_id}")
						try:
							if hasattr(user, "data") and hasattr(user.data, "delete"):
								await user.data.delete(user_id)
							else:
								shutil.rmtree(folder)
						except Exception as e:
							log.error(f"Error purging user profile {user_id}: {e}")

		current_time = datetime.now(config.timezone)
		bin_path = Path(storage.dirs.trash)
		if bin_path.exists():
			for folder in bin_path.iterdir():
				if not folder.is_dir():
					continue

				timestamp_file = Path(storage.guilds.delete_time(folder.name))

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
				f"Use {config.cmd.get('help', '/help')}, or your server's organic matter might achieve peak frustration with me.",
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
