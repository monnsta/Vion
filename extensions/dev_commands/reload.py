import sys
import traceback

import discord
from discord import app_commands as app
from discord.ext import commands

from services.utils import is_dev
from ui_templates import Success, Generic, Paginated
from config import config, load_config
from services.extensions import map_command_mentions


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
		await interaction.response.defer()

		try:
			await load_config(reload=True)

			synced_commands = await self.bot.tree.fetch_commands()
			map_command_mentions(synced_commands, self.bot)

			await interaction.followup.send(view=Success(
				"Successfully reloaded config"
			))

		except Exception:
			error_traceback = traceback.format_exc()

			chunks = [error_traceback[i:i+1800] for i in range(0, len(error_traceback), 1800)]
			items: list[str | list[str]] = [f"```py\n{chunk}\n```" for chunk in chunks]

			await interaction.followup.send(view=Paginated(
				header="Failed to Reload Config",
				items=items,
				user=interaction.user,
				accent_color=0xFE0065,
				per_page=1
			))


	@app.command(
		name='process',
		description='Terminate stream loop and trigger structural restart scripts.'
	)
	@is_dev(config.dev_ids)
	async def process(self, interaction: discord.Interaction):
		await interaction.response.send_message(view=Generic(
			"## Restarting...",
			"Bot will be unresponsive for a few seconds"
		))

		sys.exit(42)  # structural reload exit code
