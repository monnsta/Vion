import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands, tasks

from core.wrp.ai import ai
from core.wrp.blacklist import blacklist
from core.wrp.profile import server, user
from core.wrp.memory import guild_stm, user_stm, global_stm, guild_audit
from core.wrp.trackers import notif, activity, runtime
from meta import config

from core.cog.ai.utils import consciousness


log = logging.getLogger(__name__)


class AIEvents(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.pending_message_tasks: dict[tuple[int, int], asyncio.Task] = {}
		self.pending_messages: dict[tuple[int, int], discord.Message] = {}

		self.active_typing_states: dict[tuple[int, int], float] = {}
		self.typing_monitor_tasks: dict[tuple[int, int], asyncio.Task] = {}

		ai.bot = bot
		self.inactivity_check.start()
		self.freewill_loop.start()
		self.notif_freewill_loop.start()

	async def cog_unload(self):
		self.inactivity_check.cancel()
		self.freewill_loop.cancel()
		self.notif_freewill_loop.cancel()

	async def do_memory_actions(self, message, manager, memory_manager, context):
		entity = None

		if context == "server" and message.guild:
			entity = message.guild
		elif context == "user":
			entity = message.author
		elif context == "self":
			entity = getattr(message.channel, "recipient", None)

			if not entity and getattr(message.channel, "type", None) == discord.ChannelType.private:
				async for msg in message.channel.history(limit=10):
					if msg.author.id != config.bot.id:
						entity = msg.author
						break

		if not entity:
			log.error("Could not resolve entity.")
			return

		if not await manager.is_setup(entity.id):
			await manager.setup(entity)

		_, current_memories = await memory_manager.get(entity.id)

		if not current_memories:
			async for msg in message.channel.history(limit=50):
				await memory_manager.add(entity.id, msg)
		else:
			await memory_manager.add(entity.id, message)


	@commands.Cog.listener()
	async def on_ready(self):
		if hasattr(self, '_missed_backfill_started') and self._missed_backfill_started:
			return
		self._missed_backfill_started = True

		self.bot.loop.create_task(self._backfill_missed_notifications())

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


	@commands.Cog.listener()
	async def on_message(self, message: discord.Message):
		if await blacklist.is_blacklisted(message.author.id, "user"):
			return

		if message.guild and await blacklist.is_blacklisted(message.guild.id, "server"):
			await message.guild.leave()
			return

		key = (message.author.id, message.channel.id)
		if key in self.typing_monitor_tasks:
			self.typing_monitor_tasks[key].cancel()
			self.typing_monitor_tasks.pop(key, None)
		self.active_typing_states.pop(key, None)

		if message.guild:
			await self.do_memory_actions(message, server, guild_stm, "server")

			if message.author.id != config.bot.id:
				await self.do_memory_actions(message, user, user_stm, "user")
		else:
			if message.author.id != config.bot.id:
				await self.do_memory_actions(message, user, user_stm, "user")
			else:
				await self.do_memory_actions(message, user, user_stm, "self")

		await global_stm.add(0, message)

		_, guild_settings = await server.settings.load(message.guild.id) if message.guild else ("", {})

		prefixes = await self.bot.determine_prefix(None, message) # type: ignore
		free_will = guild_settings.get("free_will", True)

		key = (message.author.id, message.channel.id)

		async def delayed_response():
			try:
				await asyncio.sleep(3.0)
				
				while key in self.active_typing_states and (time.time() - self.active_typing_states[key] < 4.0):
					log.debug(f"Delaying response, {message.author} is still typing another message...")
					await asyncio.sleep(3.0)

				msg = self.pending_messages.get(key)
				if msg is None:
					return

				log.info(f"Responding to message: {msg.content if msg.content else '*empty message*'}")

				success = await ai.do_action(
					"on_message",
					msg.guild,
					msg.author,
					message=msg,
					bot=self.bot
				)

				is_reply = False
				if message.reference and message.reference.cached_message:
					if message.reference.cached_message.author.id == config.bot.id:
						is_reply = True

				is_direct_mention = self.bot.user in message.mentions
				is_everyone_mention = message.mention_everyone
				is_role_mention = any(role in message.role_mentions for role in getattr(message.guild.me, "roles", [])) if message.guild else False

				if is_reply or is_direct_mention or is_everyone_mention or is_role_mention or not message.guild:
					if is_reply:
						notif_type = "reply"
					elif is_direct_mention:
						notif_type = "mention"
					elif is_everyone_mention:
						notif_type = "everyone_ping"
					elif is_role_mention:
						notif_type = "role_ping"
					elif not message.guild:
						notif_type = "dm_ping"
					else:
						notif_type = "unread"

					if not success:
						target_id = message.guild.id if message.guild else message.author.id
						channel_name = getattr(message.channel, "name", "DM")

						await notif.add(
							target_id=target_id,
							notif_type=notif_type,
							author_id=message.author.id,
							author_name=message.author.name,
							channel_id=message.channel.id,
							channel_name=channel_name,
							message_id=message.id,
							content=message.content
						)

			except asyncio.CancelledError:
				pass

			finally:
				if self.pending_message_tasks.get(key) is asyncio.current_task():
					self.pending_message_tasks.pop(key, None)
					self.pending_messages.pop(key, None)

		if key in self.pending_messages:
			self.pending_messages[key] = message

			old_task = self.pending_message_tasks.pop(key, None)
			if old_task and not old_task.done():
				old_task.cancel()

			log.debug(f"Conversation extended by {message.author}")

			self.pending_message_tasks[key] = asyncio.create_task(delayed_response())

		else:
			if not consciousness.evaluate(
				self.bot,
				"on_message",
				free_will,
				message=message,
				prefixes=prefixes,
				context_id=message.channel.id
			):
				return

			log.info(f"Queued response to message: {message.content if message.content else '*empty message*'}")

			self.pending_messages[key] = message
			self.pending_message_tasks[key] = asyncio.create_task(delayed_response())


	@commands.Cog.listener()
	async def on_message_delete(self, message: discord.Message):
		if not message.guild or message.author.id == config.bot.id: return

		channel_name = getattr(message.channel, "name", "unknown")
		event_str = f"Message deleted by {message.author.name} in #{channel_name}: '{message.content}'"
		await guild_audit.add(message.guild.id, event_str)

		_, guild_settings = await server.settings.load(message.guild.id)
		free_will = guild_settings.get("free_will", True)

		if consciousness.evaluate(self.bot, "on_message_delete", free_will, context_id=message.channel.id):
			await ai.do_action(
				"on_message_delete",
				message.guild,
				message.author,
				extra=event_str,
				channel=message.channel,
				bot=self.bot
			)


	@commands.Cog.listener()
	async def on_message_edit(self, before: discord.Message, after: discord.Message):
		if not before.guild or before.author.id == config.bot.id or before.content == after.content: return

		channel_name = getattr(before.channel, "name", "unknown")
		event_str = f"Message edited by {before.author.name} in #{channel_name}: '{before.content}' -> '{after.content}'"
		await guild_audit.add(before.guild.id, event_str)

		_, guild_settings = await server.settings.load(before.guild.id)
		free_will = guild_settings.get("free_will", True)

		if consciousness.evaluate(self.bot, "on_message_edit", free_will, context_id=before.channel.id):
			await ai.do_action(
				"on_message_edit",
				before.guild,
				before.author,
				extra=event_str,
				message=after,
				bot=self.bot
			)


	@commands.Cog.listener()
	async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User | discord.Member):
		if not reaction.message.guild or user.id == config.bot.id: return

		event_str = f"{user.name} reacted with {reaction.emoji} to a message by {reaction.message.author.name}"
		await guild_audit.add(reaction.message.guild.id, event_str)

		_, guild_settings = await server.settings.load(reaction.message.guild.id)
		free_will = guild_settings.get("free_will", True)

		if consciousness.evaluate(self.bot, "on_reaction_add", free_will, context_id=reaction.message.channel.id):
			await ai.do_action(
				"on_reaction_add",
				reaction.message.guild,
				user,
				extra=event_str,
				message=reaction.message,
				bot=self.bot
			)


	@commands.Cog.listener()
	async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
		event_str = f"New channel created: #{channel.name}"
		await guild_audit.add(channel.guild.id, event_str)

		_, guild_settings = await server.settings.load(channel.guild.id)
		free_will = guild_settings.get("free_will", True)

		if consciousness.evaluate(self.bot, "on_guild_channel_create", free_will, context_id=channel.id):
			await ai.do_action(
				"on_guild_channel_create",
				channel.guild,
				None,
				extra=event_str,
				channel=channel,
				bot=self.bot
			)


	@commands.Cog.listener()
	async def on_typing(self, channel: discord.abc.Messageable, user: discord.User | discord.Member, when: datetime):
		guild = getattr(channel, "guild", None)
		if guild is None or user.id == config.bot.id: return

		channel_id = getattr(channel, "id", 0)
		channel_name = getattr(channel, "name", "unknown")
		key = (user.id, channel_id)

		current_time = time.time()

		is_new_typing_session = key not in self.active_typing_states
		self.active_typing_states[key] = current_time

		if key in self.typing_monitor_tasks:
			return

		_, guild_settings = await server.settings.load(guild.id)
		free_will = guild_settings.get("free_will", True)

		async def typing_monitor():
			try:
				await asyncio.sleep(7.0)

				if key not in self.active_typing_states:
					return

				last_typed = self.active_typing_states.get(key, 0)
				time_since_last_type = time.time() - last_typed

				if time_since_last_type < 4.0:
					context_str = f"{user.name} has been typing for a noticeably long time in #{channel_name} but hasn't hit send yet. They might be struggling to articulate something."
				else:
					context_str = f"{user.name} started typing in #{channel_name} a moment ago, but gave up and didn't send anything."

				if consciousness.evaluate(self.bot, "on_typing", free_will, context_id=channel_id):
					await ai.do_action(
						"on_typing",
						guild,
						user,
						extra=context_str,
						channel=channel,
						bot=self.bot
					)
			except asyncio.CancelledError:
				pass
			finally:
				self.typing_monitor_tasks.pop(key, None)
				if time.time() - self.active_typing_states.get(key, 0) > 10.0:
					self.active_typing_states.pop(key, None)

		if consciousness.evaluate(self.bot, "on_typing", free_will, context_id=channel_id):
			self.typing_monitor_tasks[key] = asyncio.create_task(typing_monitor())


	@commands.Cog.listener()
	async def on_member_join(self, member: discord.Member):
		if member.id == config.bot.id: return

		event_str = f"{member.name} just joined the server."
		await guild_audit.add(member.guild.id, event_str)

		_, guild_settings = await server.settings.load(member.guild.id)
		free_will = guild_settings.get("free_will", True)

		if consciousness.evaluate(self.bot, "on_member_join", free_will, context_id=member.guild.id):
			await ai.do_action(
				"on_member_join",
				member.guild,
				member,
				extra=event_str,
				guild=member.guild,
				bot=self.bot
			)


	@commands.Cog.listener()
	async def on_member_remove(self, member: discord.Member):
		if member.id == config.bot.id: return

		event_str = f"{member.name} left or was kicked from the server."
		await guild_audit.add(member.guild.id, event_str)


	@commands.Cog.listener()
	async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member):
		event_str = f"{user.name} was banned from the server."
		await guild_audit.add(guild.id, event_str)


	@commands.Cog.listener()
	async def on_member_unban(self, guild: discord.Guild, user: discord.User):
		event_str = f"{user.name} was unbanned from the server."
		await guild_audit.add(guild.id, event_str)


	@commands.Cog.listener()
	async def on_presence_update(self, before: discord.Member, after: discord.Member):
		if after.bot and after.id != config.bot.id:
			return

		if before.status != after.status:
			event_str = f"{after.name}'s status changed from {before.status} to {after.status}."
			await guild_audit.add(after.guild.id, event_str)

		if before.activities != after.activities:
			b_acts = [act.name for act in before.activities if act.name]
			a_acts = [act.name for act in after.activities if act.name]
			if b_acts != a_acts:
				event_str = f"{after.name}'s activity changed: {', '.join(b_acts) or 'None'} -> {', '.join(a_acts) or 'None'}"
				await guild_audit.add(after.guild.id, event_str)


	@commands.Cog.listener()
	async def on_member_update(self, before: discord.Member, after: discord.Member):
		if before.id == config.bot.id: return

		if before.nick != after.nick:
			event_str = f"{before.name}'s nickname changed from '{before.nick}' to '{after.nick}'"
			await guild_audit.add(after.guild.id, event_str)


	@commands.Cog.listener()
	async def on_guild_role_create(self, role: discord.Role):
		event_str = f"New role created: '{role.name}'"
		await guild_audit.add(role.guild.id, event_str)


	@commands.Cog.listener()
	async def on_guild_role_delete(self, role: discord.Role):
		event_str = f"Role deleted: '{role.name}'"
		await guild_audit.add(role.guild.id, event_str)


	@commands.Cog.listener()
	async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
		if before.name != after.name:
			event_str = f"Role renamed: '{before.name}' -> '{after.name}'"
			await guild_audit.add(after.guild.id, event_str)


	@commands.Cog.listener()
	async def on_guild_emojis_update(self, guild: discord.Guild, before: list[discord.Emoji], after: list[discord.Emoji]):
		if len(after) > len(before):
			added = set(after) - set(before)
			event_str = f"New emoji(s) added: {', '.join(e.name for e in added)}"
			await guild_audit.add(guild.id, event_str)
		elif len(before) > len(after):
			removed = set(before) - set(after)
			event_str = f"Emoji(s) removed: {', '.join(e.name for e in removed)}"
			await guild_audit.add(guild.id, event_str)


	@commands.Cog.listener()
	async def on_guild_join(self, guild: discord.Guild):
		event_str = f"You have been added to a new server: {guild.name} read the rules via self_call and send your greetings in a general channel"

		if consciousness.evaluate(self.bot, "on_guild_join", True, context_id=guild.id):
			await ai.do_action(
				"on_guild_join",
				guild,
				None,
				extra=event_str,
				guild=guild,
				bot=self.bot
			)


	@commands.Cog.listener()
	async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
		if member.id == config.bot.id: return

		event_str = None

		if before.channel is None and after.channel is not None:
			event_str = f"{member.name} joined the voice channel {after.channel.name}."
		elif before.channel is not None and after.channel is None:
			event_str = f"{member.name} left the voice channel {before.channel.name}."
		elif before.channel is not None and after.channel is not None and before.channel != after.channel:
			event_str = f"{member.name} switched voice channels from {before.channel.name} to {after.channel.name}."
		elif after.channel is not None and before.self_mute != after.self_mute:
			event_str = f"{member.name} {'muted' if after.self_mute else 'unmuted'} themselves in {after.channel.name}."
		elif after.channel is not None and before.self_deaf != after.self_deaf:
			event_str = f"{member.name} {'deafened' if after.self_deaf else 'undeafened'} themselves in {after.channel.name}."

		if event_str:
			await guild_audit.add(member.guild.id, event_str)

			if after.channel and before.channel is None:
				_, guild_settings = await server.settings.load(member.guild.id)
				free_will = guild_settings.get("free_will", True)

				if consciousness.evaluate(self.bot, "on_voice_state_update", free_will, context_id=after.channel.id):
					await ai.do_action(
						"on_voice_state_update",
						member.guild,
						member,
						extra=event_str,
						guild=member.guild,
						bot=self.bot
					)
