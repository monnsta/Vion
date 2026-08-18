import discord
from discord import app_commands as app
from discord.ext import commands

from core.wrp.extension import extension
from meta import config, emoji

from core.cog.utils import is_dev
from core.cog.ui_template import Fail, Success, Generic


async def autocomplete(interaction: discord.Interaction, current: str):
	all_extensions = await extension.get_all()
	choices = []

	loaded_exts = [ext.lower() for ext in interaction.client.extensions]  # type: ignore

	for ext_path in all_extensions:
		if current.lower() in ext_path.lower():
			prefix = "[+]" if ext_path.lower() in loaded_exts else "[-]"
			choices.append(app.Choice(name=f"{prefix} {ext_path}", value=ext_path))

	return choices[:25]


class ExtensionGroup(app.Group):
	def __init__(self, bot: commands.Bot):
		super().__init__(
			name='extension',
			description='Manage bot cogs and extension packages.'
		)
		self.bot = bot

	async def _single_handle(self, interaction: discord.Interaction, module, path: str):
		is_success, msg = await module(self.bot, path)

		if is_success: 
			view = Success("Success", msg)
		else: 
			view = Fail("Failed", msg)

		await interaction.response.send_message(view=view, ephemeral=True)

	async def _multi_handle(self, interaction: discord.Interaction, module):
		await interaction.response.defer(ephemeral=True)
		results = await module(self.bot)
		results_list = [f"{emoji.checkmark if success else emoji.crossmark} {msg}" for _, (success, msg) in results.items()]

		view = Generic(
			"### Results:",
			f"* {'\n* '.join(results_list)}"
		)

		await interaction.followup.send(view=view, ephemeral=True)


	@app.command(
		name='load',
		description='Load a specific cog file.'
	)
	@app.describe(
		path='The extension path to load'
	)
	@app.autocomplete(path=autocomplete)
	@is_dev(config.dev_ids)
	async def load(self, interaction: discord.Interaction, *, path: str):
		await self._single_handle(interaction, extension.load, path)


	@app.command(
		name='unload',
		description='Unload a specific cog file.'
	)
	@app.describe(
		path='The extension path to unload'
	)
	@app.autocomplete(path=autocomplete)
	@is_dev(config.dev_ids)
	async def unload(self, interaction: discord.Interaction, *, path: str):
		await self._single_handle(interaction, extension.unload, path)


	@app.command(
		name='reload',
		description='Reload a specific cog file.'
	)
	@app.describe(
		path='The extension path to reload'
	)
	@app.autocomplete(path=autocomplete)
	@is_dev(config.dev_ids)
	async def reload(self, interaction: discord.Interaction, *, path: str):
		await self._single_handle(interaction, extension.reload, path)


	@app.command(
		name='load_all',
		description='Load all cog files found in defined directories.'
	)
	@is_dev(config.dev_ids)
	async def load_all(self, interaction: discord.Interaction):
		await self._multi_handle(interaction, extension.load_all)


	@app.command(
		name='unload_all',
		description='Unload all loaded cogs except core managers.'
	)
	@is_dev(config.dev_ids)
	async def unload_all(self, interaction: discord.Interaction):
		await self._multi_handle(interaction, extension.unload_all)


	@app.command(
		name='reload_all',
		description='Reload all currently loaded cogs.'
	)
	@is_dev(config.dev_ids)
	async def reload_all(self, interaction: discord.Interaction):
		await self._multi_handle(interaction, extension.reload_all)


	@app.command(
		name='list',
		description='List all available cogs.'
	)
	@is_dev(config.dev_ids)
	async def list(self, interaction: discord.Interaction):
		all_extensions = await extension.get_all()
		loaded_exts = [ext.lower() for ext in self.bot.extensions]

		results = []
		for ext in all_extensions:
			is_loaded = ext.lower() in loaded_exts
			status_icon = emoji.checkmark if is_loaded else emoji.crossmark
			results.append(f"{status_icon} `{ext}`")

		await interaction.response.send_message(view=Generic(
			"### Extension List:",
			"\n".join(results) if results else "No extensions found."
		), ephemeral=True)
