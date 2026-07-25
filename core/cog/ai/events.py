import logging

import discord
from discord.ext import commands

from core.wrp.ai import ai
from core.wrp.blacklist import blacklist
from core.wrp.profile import server, user
from core.wrp.memory import guild_stm, user_stm, global_stm, guild_audit
from meta import config

from core.cog.ai.utils import consciousness


log = logging.getLogger(__name__)


class AIEvents(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

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
	async def on_message(self, message: discord.Message):
		if await blacklist.is_blacklisted(message.author.id, "user"):
			return
		if message.guild and await blacklist.is_blacklisted(message.guild.id, "server"):
			await message.guild.leave()
			return

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

		_, guild_settings = await server.settings.load(message.guild.id) if message.guild else ('', {})

		prefixes = await self.bot.determine_prefix(None, message) # type: ignore
		free_will = guild_settings.get("free_will", True)

		if consciousness.evaluate(self.bot, "on_message", free_will, message=message, prefixes=prefixes, context_id=message.channel.id):
			if ai.bot is None:
				ai.bot = self.bot

			log.info(f"Responding to message: {message.content if message.content != '' else '*empty message*'}")

			await ai.do_action(
				"on_message",
				message.guild,
				message.author,
				message=message,
				bot=self.bot
			)


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
	async def on_typing(self, channel: discord.abc.Messageable, user: discord.User | discord.Member, _):
		guild = getattr(channel, "guild", None)
		if guild is None or user.id == config.bot.id: return

		_, guild_settings = await server.settings.load(guild.id)
		free_will = guild_settings.get("free_will", True)

		channel_id = getattr(channel, "id", 0)
		channel_name = getattr(channel, "name", "unknown")

		if consciousness.evaluate(self.bot, "on_typing", free_will, context_id=channel_id):
			event_str = f"{user.name} has been typing in #{channel_name}..."

			await ai.do_action(
				"on_typing",
				guild,
				user,
				extra=event_str,
				channel=channel,
				bot=self.bot
			)


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
				bot=self.bot
			)


	@commands.Cog.listener()
	async def on_guild_join(self, guild: discord.Guild):
		event_str = f"You have been added to a new server: {guild.name} read the rules via self_call and send your greetings in a general channel"

		if consciousness.evaluate(self.bot, "on_guild_join", True, context_id=guild.id):
			await ai.do_action(
				"on_guild_join",
				guild,
				None,
				extra=event_str,
				bot=self.bot
			)


	@commands.Cog.listener()
	async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
		if member.id == config.bot.id: return

		if before.channel is None and after.channel is not None:
			event_str = f"{member.name} joined the voice channel {after.channel.name}."
			await guild_audit.add(member.guild.id, event_str)

			_, guild_settings = await server.settings.load(member.guild.id)
			free_will = guild_settings.get("free_will", True)

			if consciousness.evaluate(self.bot, "on_voice_state_update", free_will, context_id=after.channel.id):
				await ai.do_action(
					"on_voice_state_update",
					member.guild,
					member,
					extra=event_str,
					bot=self.bot
				)
