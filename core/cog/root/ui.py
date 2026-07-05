import random

import discord
from discord import ui
from discord.ext import commands

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
