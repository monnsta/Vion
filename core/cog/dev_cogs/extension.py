import discord
from discord             import app_commands as app
from discord.ext         import commands

from ._dev_cog           import dev
from core.wrp.extension  import extension
from core.ui.template    import Fail, Success, Generic
from meta                import emoji


dev_only = True


class Extension(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

	@staticmethod
	async def autocomplete(interaction: discord.Interaction, current: str):
		all_extensions = await extension.get_all()
		choices = []

		loaded_exts = [ext.lower() for ext in interaction.client.extensions.keys()]

		for ext_path in all_extensions:
			if current.lower() in ext_path.lower():
				prefix = "[+]" if ext_path.lower() in loaded_exts else "[-]"
				choices.append(app.Choice(name=f"{prefix} {ext_path}", value=ext_path))

		return choices[:25]

	async def _single_handle(self, ctx, module, path):
		is_success, msg = await module(self.bot, path)

		if is_success: view = Success(msg)
		else: view = Fail(msg)

		await ctx.reply(view=view)

	async def _multi_handle(self, ctx, module):
		results = await module(self.bot)
		results_list = [f"{emoji.checkmark if success else emoji.crossmark} {ext}: {msg}" for ext, (success, msg) in results.items()]

		view = Generic(
			"### Results:"
			f"* {'\n* '.join(results_list)}"
		)

		await ctx.reply(view=view)


	@dev.group(
		name='extension', 
		aliases=['ex'],
		description='Manage bot extensions and cogs.'
	)
	async def extension(self, ctx: commands.Context):
		"""Group for all the extension commands."""
		if ctx.invoked_subcommand is not None:
			return

		await ctx.reply(view=Fail(
			"Subcommand Missing",
			"Available subcommands:",
			"```",
			"* load       (l )",
			"* unload     (u )",
			"* reload     (r )",
			"* load_all   (la)",
			"* unload_all (ua)",
			"* reload_all (ra)",
			"```"
		))


	@extension.command(
		name='load',
		aliases=['l'],
		description='Load a specific cog file.'
	)
	@app.describe(path='The extension path to load')
	@app.autocomplete(path=autocomplete)
	async def load(self, ctx: commands.Context, *, path: str):
		"""
		Load an extension to the bot, all extensions are loaded by default.
		Example: /dev extension load core.cog.commands.help
		"""
		await self._single_handle(ctx, extension.load, path)


	@extension.command(
		name='unload',
		aliases=['u'],
		description='Unload a specific cog file.'
	)
	@app.describe(path='The extension path to unload')
	@app.autocomplete(path=autocomplete)
	async def unload(self, ctx: commands.Context, *, path: str):
		"""
		Unload an extension, all the commands or events of that extension will stop working.
		Example: /dev extension unload core.cog.commands.help
		"""
		await self._single_handle(ctx, extension.unload, path)


	@extension.command(
		name='reload',
		aliases=['r'],
		description='Reload a specific cog file.'
	)
	@app.describe(path='The extension path to reload')
	@app.autocomplete(path=autocomplete)
	async def reload(self, ctx: commands.Context, *, path: str):
		"""
		Reload an extension, if there are any errors in this process, it'll keep using the extension loaded in memory.
		Example: /dev extension unload core.cog.commands.help
		"""
		await self._single_handle(ctx, extension.reload, path)


	@extension.command(
		name='load_all',
		aliases=['la'],
		description='Load all cog files found in defined directories.'
	)
	async def load_all(self, ctx: commands.Context):
		"""Loads all the extensions."""
		await self._multi_handle(ctx, extension.load_all)


	@extension.command(
		name='unload_all',
		aliases=['ua'],
		description='Unload all loaded cogs except core managers.'
	)
	async def unload_all(self, ctx: commands.Context):
		"""Unloads all the extensions."""
		await self._multi_handle(ctx, extension.unload_all)


	@extension.command(
		name='reload_all',
		aliases=['ra'],
		description='Reload all currently loaded cogs.'
	)
	async def reload_all(self, ctx: commands.Context):
		"""Reloads all the extensions."""
		await self._multi_handle(ctx, extension.reload_all)


	@extension.command(
		name='list',
		aliases=['li'],
		description='List all available cogs.'
	)
	async def list(self, ctx: commands.Context):
		"""Get a list of all the cogs."""
		all_extensions = await extension.get_all()
		loaded_exts = [ext.lower() for ext in self.bot.extensions.keys()]
		
		results = []
		for ext in all_extensions:
			is_loaded = ext.lower() in loaded_exts
			status_icon = emoji.checkmark if is_loaded else emoji.crossmark
			results.append(f"{status_icon} `{ext}`")

		await ctx.reply(view=Generic(
			"### Extension List:",
			"\n".join(results) if results else "No extensions found."
		))


async def setup(bot: commands.Bot):
	await bot.add_cog(Extension(bot))