import discord
from discord import app_commands as app
from discord.ext import commands

from core.lib.utils import mt
from core.wrp.extension import extension
from meta import emoji, config

from core.cog.utils import HybridGroup
from core.cog.ui_template import Fail, Success, Generic


async def autocomplete(interaction: discord.Interaction, current: str):
	all_extensions = await extension.get_all()
	choices = []

	loaded_exts = [ext.lower() for ext in interaction.client.extensions.keys()]

	for ext_path in all_extensions:
		if current.lower() in ext_path.lower():
			prefix = "[+]" if ext_path.lower() in loaded_exts else "[-]"
			choices.append(app.Choice(name=f"{prefix} {ext_path}", value=ext_path))

	return choices[:25]

async def callback(ctx: commands.Context):
	if ctx.invoked_subcommand is None:
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
			"* list       (li)",
			"* help       (h )",
			"```"
		))


class Extension(HybridGroup):
	def __init__(self, bot: commands.Bot):
		super().__init__(
			callback,
			name='extension',
			aliases=['e'],
			description='Manage bot extensions and cogs.'
		)
		self.bot = bot
		self.p = config.default_prefix[0]

	async def _single_handle(self, ctx, module, path):
		is_success, msg = await module(self.bot, path)

		if is_success: view = Success("Success", msg)
		else: view = Fail("Failed", msg)

		await ctx.reply(view=view)

	async def _multi_handle(self, ctx, module):
		results = await module(self.bot)
		results_list = [f"{emoji.checkmark if success else emoji.crossmark} {msg}" for _, (success, msg) in results.items()]

		view = Generic(
			"### Results:",
			f"* {'\n* '.join(results_list)}"
		)

		await ctx.reply(view=view)


	@commands.hybrid_command(
		name='help',
		aliases=['h'],
		description='Get help for the extension group.'
	)
	async def help(self, ctx: commands.Context):
		await ctx.reply(view=Generic(
			"# Extension",
			"This group is used to load, unload, and reload bot cogs/extensions.",
			None,
			mt(
				"## Load / Unload / Reload:",
				"Manage a specific extension.",
				"Params:",
				"* path: The extension path to act on",
				"Usage:",
				f"* `{self.p}dev extension load core.cog.dev.root`",
				f"* `{self.p}d e l core.cog.dev.root`",
				f"* {config.cmd.dev.extension.load} `path:` core.cog.dev.root"
			), None,
			mt(
				"## Load All / Unload All / Reload All:",
				"Manage all extensions at once.",
				"Usage:",
				f"* `{self.p}dev extension reload_all`",
				f"* `{self.p}d e ra`",
				f"* {config.cmd.dev.extension.reload_all}"
			), None,
			mt(
				"## List:",
				"List all available extensions and their statuses.",
				"Usage:",
				f"* `{self.p}dev extension list`",
				f"* `{self.p}d e li`",
				f"* {config.cmd.dev.extension.list}"
			)
		))


	@commands.hybrid_command(
		name='load',
		aliases=['l'],
		description='Load a specific cog file.'
	)
	@app.describe(path='The extension path to load')
	@app.autocomplete(path=autocomplete)
	async def load(self, ctx: commands.Context, *, path: str):
		await self._single_handle(ctx, extension.load, path)


	@commands.hybrid_command(
		name='unload',
		aliases=['u'],
		description='Unload a specific cog file.'
	)
	@app.describe(path='The extension path to unload')
	@app.autocomplete(path=autocomplete)
	async def unload(self, ctx: commands.Context, *, path: str):
		await self._single_handle(ctx, extension.unload, path)


	@commands.hybrid_command(
		name='reload',
		aliases=['r'],
		description='Reload a specific cog file.'
	)
	@app.describe(path='The extension path to reload')
	@app.autocomplete(path=autocomplete)
	async def reload(self, ctx: commands.Context, *, path: str):
		await self._single_handle(ctx, extension.reload, path)


	@commands.hybrid_command(
		name='load_all',
		aliases=['la'],
		description='Load all cog files found in defined directories.'
	)
	async def load_all(self, ctx: commands.Context):
		await self._multi_handle(ctx, extension.load_all)


	@commands.hybrid_command(
		name='unload_all',
		aliases=['ua'],
		description='Unload all loaded cogs except core managers.'
	)
	async def unload_all(self, ctx: commands.Context):
		await self._multi_handle(ctx, extension.unload_all)


	@commands.hybrid_command(
		name='reload_all',
		aliases=['ra'],
		description='Reload all currently loaded cogs.'
	)
	async def reload_all(self, ctx: commands.Context):
		await self._multi_handle(ctx, extension.reload_all)


	@commands.hybrid_command(
		name='list',
		aliases=['li'],
		description='List all available cogs.'
	)
	async def list(self, ctx: commands.Context):
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
