import asyncio
import logging
import time

import discord
from discord.ext import commands

from services.ai import ai, consciousness
from services.blacklist import blacklist
from services.profile import server, user
from services.memory import (
	guild_stm,
	user_stm,
	global_stm,
	guild_audit,
	channel_stm
)
from services.trackers import notif
from config import config

from .utils import BaseEventsCog


log = logging.getLogger("extensions")


class MessageEventsCog(BaseEventsCog, commands.Cog):
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

		is_reply = False
		if message.reference:
			if message.reference.cached_message:
				is_reply = message.reference.cached_message.author.id == config.bot.id
			elif hasattr(message.reference, 'resolved') and isinstance(message.reference.resolved, discord.Message):
				is_reply = message.reference.resolved.author.id == config.bot.id

		is_direct_mention = self.bot.user in message.mentions

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

		await self._smart_sync_memory(message.channel, channel_stm, exclude_id=message.id)
		await channel_stm.add(message.channel, message)

		_, guild_settings = await server.settings.load(message.guild.id) if message.guild else ("", {})
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
	async def on_reaction_add(self, reaction: discord.Reaction, user_obj: discord.User | discord.Member):
		if not reaction.message.guild or user_obj.id == config.bot.id: return

		event_str = f"{user_obj.name} reacted with {reaction.emoji} to a message by {reaction.message.author.name}"
		await guild_audit.add(reaction.message.guild.id, event_str)

		_, guild_settings = await server.settings.load(reaction.message.guild.id)
		free_will = guild_settings.get("free_will", True)

		if consciousness.evaluate(self.bot, "on_reaction_add", free_will, context_id=reaction.message.channel.id):
			await ai.do_action(
				"on_reaction_add",
				reaction.message.guild,
				user_obj,
				extra=event_str,
				message=reaction.message,
				bot=self.bot
			)


	@commands.Cog.listener()
	async def on_typing(self, channel: discord.abc.Messageable, user_obj: discord.User | discord.Member, _):
		guild = getattr(channel, "guild", None)
		if guild is None or user_obj.id == config.bot.id: return

		channel_id = getattr(channel, "id", 0)
		channel_name = getattr(channel, "name", "unknown")
		key = (user_obj.id, channel_id)

		current_time = time.time()

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
					context_str = f"{user_obj.name} has been typing for a noticeably long time in #{channel_name} but hasn't hit send yet. They might be struggling to articulate something."
				else:
					context_str = f"{user_obj.name} started typing in #{channel_name} a moment ago, but gave up and didn't send anything."

				if consciousness.evaluate(self.bot, "on_typing", free_will, context_id=channel_id):
					await ai.do_action(
						"on_typing",
						guild,
						user_obj,
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
