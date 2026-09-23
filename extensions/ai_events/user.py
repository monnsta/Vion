import discord
from discord.ext import commands

from vion.services.ai import ai, consciousness
from vion.services.profile import server
from vion.services.memory import guild_audit
from vion.config import config

from .utils import BaseEventsCog


class UserEventsCog(BaseEventsCog, commands.Cog):
	@commands.Cog.listener()
	async def on_member_join(self, member: discord.Member):
		if member.id == config.bot.id:
			return

		event_str = f"{member.name} just joined the server."
		await guild_audit.add(member.guild.id, event_str)

		_, guild_settings = await server.settings.load(member.guild.id)
		free_will = guild_settings.get("free_will", True)

		if consciousness.evaluate(
			self.bot, "on_member_join", free_will, context_id=member.guild.id
		):
			await ai.do_action(
				"on_member_join",
				member.guild,
				member,
				extra=event_str,
				guild=member.guild,
				bot=self.bot,
			)

	@commands.Cog.listener()
	async def on_member_remove(self, member: discord.Member):
		if member.id == config.bot.id:
			return

		event_str = f"{member.name} left or was kicked from the server."
		await guild_audit.add(member.guild.id, event_str)

	@commands.Cog.listener()
	async def on_member_ban(
		self, guild: discord.Guild, user_obj: discord.User | discord.Member
	):
		event_str = f"{user_obj.name} was banned from the server."
		await guild_audit.add(guild.id, event_str)

	@commands.Cog.listener()
	async def on_member_unban(self, guild: discord.Guild, user_obj: discord.User):
		event_str = f"{user_obj.name} was unbanned from the server."
		await guild_audit.add(guild.id, event_str)

	@commands.Cog.listener()
	async def on_presence_update(self, before: discord.Member, after: discord.Member):
		if after.bot and after.id != config.bot.id:
			return

		if before.status != after.status:
			event_str = (
				f"{after.name}'s status changed from {before.status} to {after.status}."
			)
			await guild_audit.add(after.guild.id, event_str)

		if before.activities != after.activities:
			b_acts = [act.name for act in before.activities if act.name]
			a_acts = [act.name for act in after.activities if act.name]
			if b_acts != a_acts:
				event_str = f"{after.name}'s activity changed: {', '.join(b_acts) or 'None'} -> {', '.join(a_acts) or 'None'}"
				await guild_audit.add(after.guild.id, event_str)

	@commands.Cog.listener()
	async def on_member_update(self, before: discord.Member, after: discord.Member):
		if before.id == config.bot.id:
			return

		if before.nick != after.nick:
			event_str = f"{before.name}'s nickname changed from '{before.nick}' to '{after.nick}'"
			await guild_audit.add(after.guild.id, event_str)
