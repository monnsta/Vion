import sys
import traceback

import discord
from discord import app_commands as app
from discord.ext import commands

from meta import config, load_config

from core.cog.ui_template import Success, Generic
from core.cog.utils import is_dev


class ReloadGroup(app.Group):
	def __init__(self, bot: commands.Bot):
		super().__init__(
			name='reload',
			description='Reload configuration resources or reload process streams.'
		)
		self.bot = bot


	@app.command(
		name='config',
		description='Hot-reload metadata structures, JSON settings, and global parameters.'
	)
	@is_dev(config.dev_ids)
	async def config_cmd(self, interaction: discord.Interaction):
		await interaction.response.defer(ephemeral=True)

		try:
			await load_config(reload=True)
			await interaction.followup.send(view=Success("Successfully reloaded config"), ephemeral=True)

		except Exception:
			error_traceback = traceback.format_exc()

			await interaction.followup.send(view=Generic(
				"Failed to Reload Config",
				None,
				"```py",
				error_traceback,
				"```", accent_color=0xFE0065
			), ephemeral=True)


	@app.command(
		name='process',
		description='Terminate stream loop and trigger structural restart scripts.'
	)
	@is_dev(config.dev_ids)
	async def process(self, interaction: discord.Interaction):
		await interaction.response.send_message(view=Generic(
			"## Restarting...",
			"Bot will be unresponsive for a few seconds"
		), ephemeral=True)

		sys.exit(42)  # structural reload exit code
