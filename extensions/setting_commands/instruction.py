import discord
from discord import app_commands as app
from discord.ext import commands

from vion.services.utils import resolve_target, is_admin
from vion.ui_templates import Generic, Success, UnexpectedError, Confirmation, TextForm
from vion.config import config

from .utils import load_settings


class InstructionGroup(app.Group):
	def __init__(self, bot: commands.Bot):
		super().__init__(
			name="instruction",
			description="Manage contextual guidelines for the server AI.",
		)
		self.bot = bot

	@app.command(
		name="set",
		description="Add contextual guidelines or instructions to the current server.",
	)
	@app.describe(text="The instruction text, skip to edit the existing one")
	@is_admin(config.dev_ids)
	@app.guild_only()
	async def set(self, interaction: discord.Interaction, *, text: str | None = None):
		manager, target_id = await resolve_target(interaction, "server")
		if not manager:
			return

		data = await load_settings(manager, target_id, "server")  # type: ignore
		instructions = data.get("instructions", "")

		if text is not None:
			data["instructions"] = text
			success = await manager.settings.save(target_id, data)

			if not success:
				await interaction.response.send_message(
					view=UnexpectedError, ephemeral=True
				)
				return

			await interaction.response.send_message(
				view=Success(
					f"Successfully {'updated' if instructions else 'added'} the instructions."
				)
			)
			return

		view = TextForm(
			f"Use the form after clicking the button below to {'edit' if instructions else 'add'} your instructions",
			"Open Form",
			"Instructions",
			"Text",
			instructions,
			interaction.user,
		)
		await interaction.response.send_message(view=view)

		input_val = await view.wait_for_input()

		if input_val is None:
			return

		data["instructions"] = input_val
		success = await manager.settings.save(target_id, data)

		if not success:
			await interaction.edit_original_response(view=UnexpectedError)
			return

		await interaction.edit_original_response(
			view=Success(
				f"Successfully {'updated' if instructions else 'added'} the instructions."
			)
		)

	@app.command(
		name="delete", description="Delete instructions for the current server."
	)
	@is_admin(config.dev_ids)
	@app.guild_only()
	async def delete(self, interaction: discord.Interaction):
		manager, target_id = await resolve_target(interaction, "server")
		if not manager:
			return

		data = await load_settings(manager, target_id, "server")  # type: ignore

		if data.get("instructions", "") == "":
			await interaction.response.send_message(
				view=Generic("No need to. It's already empty.")
			)
			return

		view = Confirmation(
			"Are you sure you want to do this?",
			"Instructions deleted successfully",
			"Action Aborted",
			interaction.user,
		)
		await interaction.response.send_message(view=view)

		confirmed = await view.wait_for_answer()

		if confirmed:
			data["instructions"] = ""
			await manager.settings.save(target_id, data)

	@app.command(
		name="view", description="View added instructions for the current server."
	)
	@app.guild_only()
	async def view(self, interaction: discord.Interaction):
		manager, target_id = await resolve_target(interaction, "server")
		if not manager:
			return

		data = await load_settings(manager, target_id, "server")  # type: ignore
		instructions = data.get("instructions", "")

		if not instructions:
			await interaction.response.send_message(
				view=Generic("No instructions added...")
			)
			return

		await interaction.response.send_message(
			view=Generic("## Instructions for the bot", None, instructions)
		)
