import discord
from discord.ext import commands

from services.ai import ai, consciousness
from services.profile import server
from services.memory import guild_audit
from config import config

from .utils import BaseEventsCog


class GuildEventsCog(BaseEventsCog, commands.Cog):
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
