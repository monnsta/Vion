import os

import discord
from discord             import app_commands as app
from discord.ext         import commands

from meta                import config, emoji, sub
from core.lib.etc        import is_dev
from core.ui.template    import Fail, Generic, Success
from core.wrp.extension  import extension



dev_only = True

@commands.hybrid_group(
	name='dev',
	aliases=['d'],
	description='Dev Commands.'
)
@is_dev(config.devs)
async def dev(ctx: commands.Context):
	if ctx.invoked_subcommand is None:
		await ctx.reply(view=Fail(
			"Subcommand messing",
			"Available subcommands:",
			"```",
			"* extension (ex)",
			"* blacklist (bl)",
			"```"
		))

@dev.error
async def dev_error(ctx: commands.Context, error):
	if isinstance(error, commands.CheckFailure):
		await ctx.reply(view=Fail(f"Only developers can use this command."))


class Extension(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.dev_guilds = [discord.Object(id=g[0]) for g in config.dev_guilds]

	@staticmethod
	async def autocomplete(interaction: discord.Interaction, current: str):
		all_extensions = await extension.get_all()
		choices = []

		for ext_path in all_extensions:
			namespace = ext_path.split('.')[-2] if '.' in ext_path else "Unknown"
			name = ext_path.split('.')[-1]
			label = f"[{namespace}] {name}"

			if current.lower() in ext_path.lower():
				choices.append(app_commands.Choice(name=label, value=ext_path))

		for loaded in getattr(interaction.client, 'extensions', {}).keys():
			if len(choices) >= 25:
				break
			if current.lower() in loaded.lower() and not any(c.value == loaded for c in choices):
				choices.append(app_commands.Choice(name=f"[Loaded] {loaded}", value=loaded))

		return choices[:25]

	@dev.group(
		name='extension', 
		aliases=['ex'],
		description='Manage bot extensions and cogs.'
	)
	async def extension(self, ctx: commands.Context):
		if ctx.invoked_subcommand is None:
			await ctx.reply(view=Fail(
				"Subcommand messing",
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


	async def _single_handle(self, ctx, module, path):
		is_success, msg = await module(self.bot, path, self.dev_guilds)

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


	@extension.command(
		name='load',
		aliases=['l'],
		description='Load a specific cog file.'
	)
	@app.describe(extension='The extension path to load')
	@app.autocomplete(extension=self.autocomplete)
	async def load(self, ctx: commands.Context, *, path: str):
		await self._single_handle(ctx, extension.load, path)


	@extension.command(
		name='unload',
		aliases=['u'],
		description='Unload a specific cog file.'
	)
	@app.describe(extension='The extension path to unload')
	@app.autocomplete(extension=self.autocomplete)
	async def unload(self, ctx: commands.Context, *, path: str):
		await self._single_handle(ctx, extension.unload, path)


	@extension.command(
		name='reload',
		aliases=['r'],
		description='Reload a specific cog file.'
	)
	@app.describe(extension='The extension path to reload')
	@app.autocomplete(extension=self.autocomplete)
	async def reload(self, ctx: commands.Context, *, path: str):
		await self._single_handle(ctx, extension.reload, path)


	@extension.command(
		name='load_all',
		aliases=['la'],
		description='Load all cog files found in defined directories.'
	)
	async def load_all(self, ctx: commands.Context):
		await self._multi_handle(ctx, extension.load_all)


	@extension.command(
		name='unload_all',
		aliases=['ua'],
		description='Unload all loaded cogs except core managers.'
	)
	async def unload_all(self, ctx: commands.Context):
		await self._multi_handle(ctx, extension.unload_all)


	@extension.command(
		name='reload_all',
		aliases=['ra'],
		description='Reload all currently loaded cogs.'
	)
	async def reload_all(self, ctx: commands.Context):
		await self._multi_handle(ctx, extension.reload_all)

async def setup(bot: commands.Bot):
	await bot.add_cog(Extension(bot))
