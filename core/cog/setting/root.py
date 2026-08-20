from typing import Literal

import discord
from discord import app_commands as app
from discord.ext import commands

from core.lib.utils import em
from core.wrp.profile import server
from meta import config, emoji

from core.cog.utils import resolve_target, load_settings, is_admin
from core.cog.ui_template import Success, Fail, Generic, Confirmation, UnexpectedError
from core.cog.setting.gemini_key import GeminiKeyGroup
from core.cog.setting.instruction import InstructionGroup


class SettingRoot(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.gemini_key_group = GeminiKeyGroup(self.bot)
		self.instruction_group = InstructionGroup(self.bot)

		self.setting.add_command(self.gemini_key_group)
		self.setting.add_command(self.instruction_group)


	setting = app.Group(
		name='setting',
		description='Configure custom profile or server variables.'
	)


	@setting.command(
		name='view',
		description='View all your personal settings or the current server\'s'
	)
	@app.describe(
		type='Whether to show your personal settings or server settings'
	)
	async def view(self, interaction: discord.Interaction, type: Literal['server', 'user']):
		manager, target_id = await resolve_target(interaction, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)  # type: ignore

		lines = []
		inst = data.get('instructions', '')
		if type == 'server':
			lines.append(f"# Settings for {getattr(interaction.guild, 'name', 'Unknown')}")
			lines.append(f"**Freewill:** {'Yes' if data.get('free_will', False) else 'No'}")
			lines.append(
				"**Instructions:**\n"
				f"```\n{em(inst if inst else 'None', chars='`')}\n```\n"
				f"{f'{emoji.info} The backticks are escaped. Your real configuration does not contain them.' if '`' in inst else ''}"
			)
		else:
			lines.append(f"# Settings for {interaction.user.display_name}")
		lines.append(f"**API Keys:** *Hidden for privacy.* Use {config.cmd.get('setting.gemini_key.list')} to view them.")

		await interaction.response.send_message(view=Generic(*lines), ephemeral=True)


	@setting.command(
		name='freewill',
		description='Toggle free will for the current server.'
	)
	@app.describe(
		value='Whether to turn free will on or off (True or False)'
	)
	@app.guild_only()
	@is_admin(config.dev_ids)
	async def freewill(self, interaction: discord.Interaction, value: bool):
		manager, _ = await resolve_target(interaction, 'server')
		if not manager:
			return

		data = await load_settings(server, getattr(interaction.guild, 'id'), "server")
		current_value = data.get("free_will", True)
		target_value = value
		conf_view = None

		if current_value == value:
			target_value = not value
			conf_view = Confirmation(
				f"Freewill already set to {value}, set to {target_value} instead?",
				f"Freewill set to {target_value}",
				"Action Aborted",
				interaction.user
			)
			await interaction.response.send_message(view=conf_view, ephemeral=True)

			if not await conf_view.wait_for_answer():
				return

		data["free_will"] = target_value
		if interaction.guild:
			success = await server.settings.save(interaction.guild.id, data)
		else:
			await interaction.response.send_message(view=Fail(
				"Invalid Scope",
				"You must be in a guild to use this command."
			), ephemeral=True)
			return

		if not success:
			if conf_view:
				await interaction.edit_original_response(view=UnexpectedError)
			else:
				await interaction.response.send_message(view=UnexpectedError, ephemeral=True)
		elif not conf_view:
			await interaction.response.send_message(view=Success(f"Freewill set to {target_value}"), ephemeral=True)
