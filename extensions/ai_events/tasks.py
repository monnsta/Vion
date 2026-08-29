import asyncio
import logging
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands, tasks

from services.ai import ai, consciousness
from services.blacklist import blacklist
from services.profile import server
from services.memory import guild_audit
from services.trackers import notif, activity, runtime
from config import config

from .utils import BaseEventsCog


log = logging.getLogger("extensions")


class EventTasksCog(BaseEventsCog, commands.Cog):
	def __init__(self, bot: commands.Bot):
		super().__init__(bot)
		self.inactivity_check.start()
		self.freewill_loop.start()
		self.notif_freewill_loop.start()

	async def cog_unload(self):
		self.inactivity_check.cancel()
		self.freewill_loop.cancel()
		self.notif_freewill_loop.cancel()

	async def _backfill_missed_notifications(self):
		last_offline = await runtime.get_last_offline()
		if not last_offline:
			return

		now = datetime.now(timezone.utc)

		if (now - last_offline).total_seconds() > 86400 * 3:
			last_offline = now - timedelta(days=3)

		log.info(f"Starting background backfill for missed messages since {last_offline}")

		async def _check_and_log(msg: discord.Message):
			if msg.author.id == config.bot.id or await blacklist.is_blacklisted(msg.author.id, "user"):
				return

			is_reply = False
			if msg.reference:
				if msg.reference.cached_message:
					is_reply = msg.reference.cached_message.author.id == config.bot.id
				elif hasattr(msg.reference, 'resolved') and isinstance(msg.reference.resolved, discord.Message):
					is_reply = msg.reference.resolved.author.id == config.bot.id

			is_direct_mention = self.bot.user in msg.mentions
			is_everyone_mention = msg.mention_everyone
			is_role_mention = any(role in msg.role_mentions for role in getattr(msg.guild.me, "roles", [])) if msg.guild else False

			if is_reply or is_direct_mention or is_everyone_mention or is_role_mention or not msg.guild:
				if is_reply:
					notif_type = "reply"
				elif is_direct_mention:
					notif_type = "mention"
				elif is_everyone_mention:
					notif_type = "everyone_ping"
				elif is_role_mention:
					notif_type = "role_ping"
				elif not msg.guild:
					notif_type = "dm_ping"
				else:
					notif_type = "unread"

				target_id = msg.guild.id if msg.guild else msg.author.id
				channel_name = getattr(msg.channel, "name", "DM")

				await notif.add(
					target_id=target_id,
					notif_type=notif_type,
					author_id=msg.author.id,
					author_name=msg.author.name,
					channel_id=msg.channel.id,
					channel_name=channel_name,
					message_id=msg.id,
					content=msg.content
				)

		for pm in self.bot.private_channels:
			if isinstance(pm, discord.abc.Messageable):
				try:
					async for msg in pm.history(after=last_offline, limit=25, oldest_first=False):
						await _check_and_log(msg)
				except discord.HTTPException:
					pass
			await asyncio.sleep(0.5)

		for guild in self.bot.guilds:
			if await blacklist.is_blacklisted(guild.id, "server"):
				continue

			for channel in guild.text_channels:
				if not channel.permissions_for(guild.me).read_message_history:
					continue

				try:
					async for msg in channel.history(after=last_offline, limit=25, oldest_first=False):
						await _check_and_log(msg)
				except discord.HTTPException:
					pass

				await asyncio.sleep(0.5)

			await asyncio.sleep(1.0)

		log.info("Finished background backfill for missed messages.")


	@commands.Cog.listener()
	async def on_ready(self):
		if hasattr(self, '_missed_backfill_started') and self._missed_backfill_started:
			return
		self._missed_backfill_started = True

		self.bot.loop.create_task(self._backfill_missed_notifications())


	@tasks.loop(minutes=2)
	async def freewill_loop(self):
		await self.bot.wait_until_ready()

		for guild in self.bot.guilds:
			if await blacklist.is_blacklisted(guild.id, "server"):
				continue

			_, guild_settings = await server.settings.load(guild.id)
			free_will = guild_settings.get("free_will", True)
			if not free_will:
				continue

			now = datetime.now(timezone.utc)
			three_minutes_ago = now - timedelta(minutes=3)

			for channel in guild.text_channels:
				if not channel.permissions_for(guild.me).send_messages:
					continue

				try:
					recent_msgs = [
						msg async for msg in channel.history(limit=10, after=three_minutes_ago)
					]
				except Exception as e:
					log.debug(f"Could not fetch history for freewill loop in channel {channel.id}: {e}")
					continue

				if len(recent_msgs) < 5:
					continue

				if recent_msgs[-1].author.id == config.bot.id:
					continue

				if consciousness.evaluate(self.bot, "freewill", free_will, context_id=channel.id):
					log.info(f"Triggering freewill interaction in #{channel.name} ({guild.name})")

					event_str = f"The channel #{channel.name} is currently very active. Jump into the chat naturally."
					await guild_audit.add(guild.id, event_str)

					await ai.do_action(
						"freewill",
						guild,
						recent_msgs[-1].author,
						extra=event_str,
						channel=channel,
						bot=self.bot
					)
					break

	@freewill_loop.before_loop
	async def before_freewill_loop(self):
		await self.bot.wait_until_ready()


	@tasks.loop(hours=1)
	async def inactivity_check(self):
		await self.bot.wait_until_ready()

		for guild in self.bot.guilds:
			if await blacklist.is_blacklisted(guild.id, "server"):
				continue

			_, guild_settings = await server.settings.load(guild.id)
			free_will = guild_settings.get("free_will", True)

			if not free_will:
				continue

			target_channel = guild.system_channel
			if not target_channel or not target_channel.permissions_for(guild.me).send_messages:
				for channel in guild.text_channels:
					if channel.permissions_for(guild.me).send_messages:
						target_channel = channel
						break

			if not target_channel:
				continue

			try:
				last_messages = [msg async for msg in target_channel.history(limit=10)]
			except Exception as e:
				log.warning(f"Could not fetch history for inactivity check in {guild.id}: {e}")
				continue

			if not last_messages:
				continue

			has_bot_message = any(msg.author.id == config.bot.id for msg in last_messages)
			if has_bot_message:
				continue

			time_diff = (datetime.now(timezone.utc) - last_messages[0].created_at).total_seconds()
			if time_diff < 7200:
				continue

			if consciousness.evaluate(self.bot, "on_inactivity", free_will, context_id=guild.id):
				event_str = f"The server '{guild.name}' was detected to be inactive, you can try to revive it. NOTE: This event can trigger falsely, so if you seem to have already sent a message or did any action on inactivity, ignore this one or do something else, likely responding to missed messages"
				await guild_audit.add(guild.id, event_str)

				await ai.do_action(
					"on_inactivity",
					guild,
					None,
					extra=event_str,
					guild=guild,
					bot=self.bot
				)

	@inactivity_check.before_loop
	async def before_inactivity_check(self):
		await self.bot.wait_until_ready()


	@tasks.loop(minutes=5)
	async def notif_freewill_loop(self):
		await self.bot.wait_until_ready()

		for guild in self.bot.guilds:
			if await blacklist.is_blacklisted(guild.id, "server"):
				continue

			count = await notif.get(guild.id)
			if len(count) <= 0:
				continue

			_, guild_settings = await server.settings.load(guild.id)
			free_will = guild_settings.get("free_will", True)
			if not free_will:
				continue

			chance = min(1.0, len(count) * 0.1)

			if consciousness.evaluate(self.bot, "notification_freewill", free_will, chance=chance, context_id=guild.id):
				target_channel = guild.system_channel
				if not target_channel or not target_channel.permissions_for(guild.me).send_messages:
					for channel in guild.text_channels:
						if channel.permissions_for(guild.me).send_messages:
							target_channel = channel
							break

				if not target_channel:
					continue

				if count:
					formatted_notifs = []
					for idx, item in enumerate(count, 1):
						formatted_notifs.append(
							f"{idx}. [{item['type'].upper()}] {item['author_name']} in #{item['channel_name']} "
							f"(Channel ID: {item['channel_id']}, Msg ID: {item['message_id']}): \"{item['content']}\""
						)

					event_str = (
						f"You have {len(count)} unhandled notification(s) in this server:\n"
						+ "\n".join(formatted_notifs)
						+ "\n\nYou can use these details (channel_id, message_id) to jump in, reply to specific messages."
					)

					success = await ai.do_action(
						"notification_freewill",
						guild,
						None,
						extra=event_str,
						guild=guild,
						bot=self.bot
					)

					if success:
						await notif.clear(guild.id)

		active_users = await activity.get_leaderboard("user", limit=100)
		for user_id_str, _ in active_users:
			user_id = int(user_id_str)
			if await blacklist.is_blacklisted(user_id, "user"):
				continue

			count = await notif.get(user_id)
			if len(count) <= 0:
				continue

			chance = min(1.0, len(count) * 0.1)

			if consciousness.evaluate(self.bot, "notification_freewill", True, chance=chance, context_id=user_id):
				user_obj = self.bot.get_user(user_id)
				if not user_obj:
					try:
						user_obj = await self.bot.fetch_user(user_id)
					except discord.NotFound:
						continue

				event_str = f"You have {len(count)} unhandled DM ping(s) from this user. Reach out and reply to them."

				success = await ai.do_action(
					"notification_freewill",
					None,
					user_obj,
					extra=event_str,
					user=user_obj,
					bot=self.bot
				)

				if success:
					await notif.clear(user_id)

	@notif_freewill_loop.before_loop
	async def before_notif_freewill_loop(self):
		await self.bot.wait_until_ready()
