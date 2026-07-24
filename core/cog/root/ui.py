
import random

import discord
from discord import ui
from discord.ext import commands

from core.wrp.activity import tracker
from meta import emoji

from core.cog.ui_template import TimeoutView, Fail, Success, Confirmation, global_interaction_check


class ManageDataView(TimeoutView):
	def __init__(self, ctx: commands.Context, manager, target_id: int, data_type: str):
		super().__init__()
		self.ctx = ctx
		self.manager = manager
		self.target_id = target_id
		self.data_type = data_type
		self.user = ctx.author

		container = ui.Container(
			ui.TextDisplay(f"### Manage {data_type.title()} Data"),
			ui.TextDisplay("Choose whether to export or permanently delete your data."),
			accent_color=0x00E9FE
		)

		export_btn = ui.Button(label="Export Data", style=discord.ButtonStyle.primary)
		export_btn.callback = self.export_data

		delete_btn = ui.Button(label="Delete Data", style=discord.ButtonStyle.danger)
		delete_btn.callback = self.delete_data

		container.add_item(ui.ActionRow(export_btn, delete_btn))
		self.add_item(container)

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		return await global_interaction_check(interaction, self.user)

	async def export_data(self, interaction: discord.Interaction):
		await interaction.response.defer(ephemeral=True)
		success, result = await self.manager.data.get_zip(self.target_id)

		if not success:
			return await interaction.followup.send(view=Fail(
				"Error",
				result if isinstance(result, str) else "Failed to load data. Please report this."
			), ephemeral=True)

		try:
			file = discord.File(result, filename=f"{self.data_type}_{self.target_id}_data.zip")
			await self.ctx.author.send(file=file)
			await interaction.followup.send(view=Success("I've sent your data export to your DMs."), ephemeral=True)
		except discord.Forbidden:
			await interaction.followup.send(view=Fail(
				"User Error",
				"I couldn't send you a DM. Please open your privacy settings."
			), ephemeral=True)

	async def delete_data(self, interaction: discord.Interaction):
		if not await self.manager.data.exists(self.target_id):
			return await interaction.response.send_message(view=Fail("We couldn't find any data to delete."), ephemeral=True)

		if self.data_type == 'user':
			question = "Are you sure you want to permanently delete your data?\nThe AI will forget everything about you. This process cannot be undone."
		else:
			question = "Are you sure you want to permanently delete your data?\nThe AI will forget everything about this server. This process cannot be undone."

		cancel = "Action Aborted"
		if random.random() < 0.5:
			cancel += "\n-# I promise you we don't read your data when we are bored :3"

		view = Confirmation(
			question,
			f"Your **{self.data_type}** data has been deleted permanently.",
			cancel,
			self.user
		)
		await interaction.response.send_message(view=view, ephemeral=True)

		confirmed = await view.wait_for_answer()

		if confirmed:
			await self.manager.data.delete_permanent(self.target_id)


class AIStatsView(TimeoutView):
	def __init__(self, ctx: commands.Context, default_target: str, user_target: discord.User | discord.Member | None = None):
		super().__init__()
		self.ctx = ctx
		self.current_target = default_target
		self.user_target = user_target
		self.user = ctx.author

		self.target_select = ui.Select(
			placeholder="Select scope to view stats...",
			options=[
				discord.SelectOption(label="Global Stats", value="global", description="Network-wide AI metrics"),
				discord.SelectOption(label="Server Stats", value="server", description="Metrics for this server"),
				discord.SelectOption(label="User Stats", value="user", description="Your or someone else's metrics"),
				discord.SelectOption(label="Leaderboard", value="leaderboard", description="Top interaction rankings")
			]
		)
		self.target_select.callback = self.change_target

		self.refresh_btn = ui.Button(emoji=emoji.refresh, style=discord.ButtonStyle.secondary)
		self.refresh_btn.callback = self.refresh_stats

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		return await global_interaction_check(interaction, self.user)

	async def _generate_container(self) -> ui.Container:
		if self.current_target == 'leaderboard':
			top_guilds = await tracker.get_leaderboard('guild', 5)
			top_users = await tracker.get_leaderboard('user', 5)

			guild_lines = []
			for idx, (g_id, count) in enumerate(top_guilds, 1):
				guild_obj = self.ctx.bot.get_guild(int(g_id))
				name = guild_obj.name if guild_obj else f"Server {g_id}"
				guild_lines.append(f"{idx}. **{name}**\n-# `{count:,}` interactions")

			user_lines = []
			for idx, (u_id, count) in enumerate(top_users, 1):
				user_obj = self.ctx.bot.get_user(int(u_id))
				name = user_obj.display_name if user_obj else f"User {u_id}"
				user_lines.append(f"{idx}. **{name}**\n-# `{count:,}` interactions")

			content = (
				"## AI Leaderboard\n"
				"Top performing communities and most active users across the network.\n\n"
				"### Top Servers\n" + ("\n".join(guild_lines) if guild_lines else "*No data yet*") + "\n\n"
				"### Top Users\n" + ("\n".join(user_lines) if user_lines else "*No data yet*")
			)
		else:
			if self.current_target == 'global':
				stats = await tracker.get_stats('global')
				interactions = stats.get('interactions', 0)
				content = (
					"## Global AI Statistics\n"
					"Network-wide telemetry and usage overview.\n\n"
					"> **Total Network Interactions**\n"
					f"> ## `{interactions:,}`"
				)
			elif self.current_target == 'server':
				if not self.ctx.guild:
					container = ui.Container(ui.TextDisplay("### Server Stats\nCannot fetch server stats in DMs."), accent_color=0xFE0065)
					container.add_item(ui.ActionRow(self.target_select))
					container.add_item(ui.ActionRow(self.refresh_btn))
					return container
				stats = await tracker.get_stats('guild', self.ctx.guild.id)
				interactions = stats.get('interactions', 0)
				rank = stats.get('rank', 0)
				content = (
					f"## Server Statistics: {self.ctx.guild.name}\n"
					"Current server standing and activity metrics.\n\n"
					"> **Total Interactions** · **Leaderboard Rank**\n"
					f"> ## `{interactions:,}` `#{rank:,}`"
				)
			else:
				target = self.user_target or self.ctx.author
				stats = await tracker.get_stats('user', target.id)
				interactions = stats.get('interactions', 0)
				rank = stats.get('rank', 0)
				content = (
					f"## User Statistics: {target.display_name}\n"
					"Individual activity metrics and global standing.\n\n"
					f"> **Total Interactions** · **Leaderboard Rank**\n"
					f"> ## `{interactions:,}` `#{rank:,}`"
				)

		for opt in self.target_select.options:
			opt.default = (opt.value == self.current_target)

		container = ui.Container(ui.TextDisplay(content), accent_color=0x00E9FE)
		container.add_item(ui.ActionRow(self.target_select))
		container.add_item(ui.ActionRow(self.refresh_btn))

		return container

	async def start(self) -> discord.Message:
		container = await self._generate_container()
		self.clear_items()
		self.add_item(container)
		return await self.ctx.reply(view=self)

	async def change_target(self, interaction: discord.Interaction):
		self.current_target = self.target_select.values[0]

		container = await self._generate_container()
		self.clear_items()
		self.add_item(container)

		await interaction.response.edit_message(view=self)

	async def refresh_stats(self, interaction: discord.Interaction):
		container = await self._generate_container()
		self.clear_items()
		self.add_item(container)

		await interaction.response.edit_message(view=self)

