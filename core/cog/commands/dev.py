from typing              import Optional, Literal

import discord
from discord             import app_commands as app
from discord.ext         import commands

from core.lib.utils      import is_dev
from core.ui.template    import Fail, Generic, Success
from core.wrp.extension  import extension
from core.wrp.blacklist  import blacklist
from meta                import config, emoji, sub


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

class Blacklist(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

	@dev.group(
		name='blacklist',
		aliases=['bl'],
		description='Manage the global bot blacklist.'
	)
	async def blacklist_group(self, ctx: commands.Context):
		if ctx.invoked_subcommand is None:
			await ctx.reply(view=Fail(
				"Subcommand missing",
				"Available subcommands:",
				"```",
				"* add    (a)",
				"* remove (r)",
				"* show   (s)",
				"* list   (l)",
				"```"
			))


	@blacklist_group.command(
		name='add',
		aliases=['a'],
		description='Add a user or server to the blacklist.'
	)
	@app.describe(
		target_id='The ID of the user or server',
		type='Whether this is a user or server',
		reason='Reason for blacklisting',
		duration='Duration (e.g., 7d, 12h, 30m). Leave empty for permanent.'
	)
	async def add(
		self, 
		ctx: commands.Context, 
		target_id: str, 
		type: Literal['user', 'server'], 
		reason: str, 
		duration: Optional[str] = None
	):
		try:
			tid = int(target_id)
		except ValueError:
			return await ctx.reply(view=Fail("Target ID must be a valid integer."))

		success, msg = await blacklist.add(tid, type, ctx.author.id, reason, duration)

		if success:
			await ctx.reply(view=Success(f"**{type.capitalize()} {tid}** has been blacklisted.\n**Reason:** {reason}"))
		else:
			await ctx.reply(view=Fail(msg))


	@blacklist_group.command(
		name='remove',
		aliases=['rm'],
		description='Remove a user or server from the blacklist.'
	)
	async def remove(self, ctx: commands.Context, target_id: str, type: Literal['user', 'server']):
		try:
			tid = int(target_id)
		except ValueError:
			return await ctx.reply(view=Fail("Target ID must be a valid integer."))

		success, msg = await blacklist.remove(tid, type)
		
		if success:
			await ctx.reply(view=Success(msg))
		else:
			await ctx.reply(view=Fail(msg))


	@blacklist_group.command(
		name='show',
		aliases=['s'],
		description='Show detailed info about a specific blacklist entry.'
	)
	async def show(self, ctx: commands.Context, target_id: str, type: Literal['user', 'server']):
		try:
			tid = int(target_id)
		except ValueError:
			return await ctx.reply(view=Fail("Target ID must be a valid integer."))

		success, data = await blacklist.get(tid, type)
		
		if not success:
			return await ctx.reply(view=Fail(data))

		expiry = data['expires_at'] if data['expires_at'] else "Never"
		details = (
			f"**ID:** `{data['id']}`\n"
			f"**Type:** {data['type']}\n"
			f"**Moderator:** <@{data['mod_id']}>\n"
			f"**Reason:** {data['reason']}\n"
			f"**Created:** {data['created_at']}\n"
			f"**Expires:** {expiry}"
		)
		await ctx.reply(view=Generic(details))


	@blacklist_group.command(
		name='list',
		aliases=['l'],
		description='List all blacklisted entities.'
	)
	async def list_bl(self, ctx: commands.Context, type: Optional[Literal['user', 'server']] = None):
		entries = await blacklist.list_all(type)
		
		if not entries:
			return await ctx.reply(view=Generic("The blacklist is currently empty."))

		results = []
		for e in entries:
			line = f"• `[{e['type'][0].upper()}]` `{e['id']}` - {e['reason']}"
			results.append(line)

		await ctx.reply(view=Generic("### Global Blacklist\n" + "\n".join(results)))


async def setup(bot: commands.Bot):
	await bot.add_cog(Extension(bot))
	await bot.add_cog(Blacklist(bot))
