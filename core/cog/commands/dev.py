from typing              import Optional, Literal

import discord
from discord             import app_commands as app
from discord.ext         import commands

from core.lib.utils      import is_dev
from core.lib.code       import Code, status
from core.wrp.extension  import extension
from core.wrp.blacklist  import blacklist
from core.ui.template    import Fail, Generic, Success
from meta                import config, emoji, sub


dev_only = True

@commands.hybrid_group(
	name='dev',
	aliases=['d'],
	description='Dev commands.'
)
@is_dev(config.dev_ids)
async def dev(ctx: commands.Context):
	"""Group used for dev commands, can't be used by anyone else."""
	if ctx.invoked_subcommand is not None:
		return

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
			label = ext_path.split('.')[-1]

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
		"""Group for all the extension commands. Extensions are just groups of commands that you can load, unload, etc."""
		if ctx.invoked_subcommand is not None:
			return

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
	@app.describe(path='The extension path to load')
	@app.autocomplete(path=self.autocomplete)
	async def load(self, ctx: commands.Context, *, path: str):
		"""Load an extension to the bot, all extensions are loaded by default."""
		await self._single_handle(ctx, extension.load, path)


	@extension.command(
		name='unload',
		aliases=['u'],
		description='Unload a specific cog file.'
	)
	@app.describe(path='The extension path to unload')
	@app.autocomplete(path=self.autocomplete)
	async def unload(self, ctx: commands.Context, *, path: str):
		"""Unload an extension, all the commands or events of that extension will stop working."""
		await self._single_handle(ctx, extension.unload, path)


	@extension.command(
		name='reload',
		aliases=['r'],
		description='Reload a specific cog file.'
	)
	@app.describe(path='The extension path to reload')
	@app.autocomplete(path=self.autocomplete)
	async def reload(self, ctx: commands.Context, *, path: str):
		"""Reload an extension, if there are any errors in this process, it'll keep using the extension loaded in memory."""
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

class Blacklist(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot


	@dev.group(
		name='blacklist',
		aliases=['bl'],
		description='Manage the global bot blacklist.'
	)
	async def blacklist(self, ctx: commands.Context):
		"""Group for all the blacklist commands. blacklisted users or servers cannot access the bot."""
		if ctx.invoked_subcommand is not None:
			return

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


	@blacklist.command(
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
	async def add(self, ctx: commands.Context, target_id: str, type: Literal['user', 'server'], reason: str, duration: Optional[str] = None):
		"""Add a user or server to the blacklist."""
		try:
			tid = int(target_id)
		except ValueError:
			return await ctx.reply(view=Fail("Target ID must be a valid integer."))

		success, msg = await blacklist.add(tid, type, ctx.author.id, reason, duration)

		if success:
			await ctx.reply(view=Success(f"**{type.capitalize()} {tid}** has been blacklisted.\n**Reason:** {reason}"))
		else:
			await ctx.reply(view=Fail(msg))


	@blacklist.command(
		name='remove',
		aliases=['rm'],
		description='Remove a user or server from the blacklist.'
	)
	@app.describe(
		target_id='The ID of the user or server'
	)
	async def remove(self, ctx: commands.Context, target_id: str, type: Literal['user', 'server']):
		"""Remove a user or server from the blacklist."""
		try:
			tid = int(target_id)
		except ValueError:
			return await ctx.reply(view=Fail("Target ID must be a valid integer."))

		success, msg = await blacklist.remove(tid, type)
		
		if success:
			await ctx.reply(view=Success(msg))
		else:
			await ctx.reply(view=Fail(msg))


	@blacklist.command(
		name='show',
		aliases=['s'],
		description='Show detailed info about a specific blacklist entry.'
	)
	@app.describe(
		target_id='The ID of the user or server'
	)
	async def show(self, ctx: commands.Context, target_id: str, type: Literal['user', 'server']):
		"""Show information of a blacklisted user or server."""
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


	@blacklist.command(
		name='list',
		aliases=['l'],
		description='List all blacklisted entities.'
	)
	@app.describe(
		type='Filter by user or server'
	)
	async def list_bl(self, ctx: commands.Context, type: Optional[Literal['user', 'server']] = None):
		"""List all blacklisted users or servers"""
		entries = await blacklist.list_all(type)
		
		if not entries:
			return await ctx.reply(view=Generic("The blacklist is currently empty."))

		results = []
		for e in entries:
			line = f"• `[{e['type'][0].upper()}]` `{e['id']}` - {e['reason']}"
			results.append(line)

		await ctx.reply(view=Generic("### Global Blacklist\n" + "\n".join(results)))

class Misc(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

	@dev.command(
		name='execute',
		aliases=['e'],
		description='Execute code like the AI does'
	)
	@app.describe(code='The code to execute')
	async def execute(self, ctx: commands.Context, *, code: str):
		"""Execute code like the AI does, example code:\n```py\nasync def main(message, bot):\n    await message.channel.send("Hello there.")\n```"""
		await ctx.defer(ephemeral=False)

		runner = Code(code)

		try:
			await runner.execute(timeout=30.0, message=ctx.message, bot=self.bot)

			data = await runner.wait()

			output_parts = []

			if data.stdout:
				output_parts.append(f"**Stdout:**\n```py\n{data.stdout}\n```")
			if data.stderr:
				output_parts.append(f"**Stderr:**\n```py\n{data.stderr}\n```")
			if data.error:
				output_parts.append(f"**Error:**\n```py\n{data.error}\n```")
			if data.result is not None:
				output_parts.append(f"**Result:** `{data.result}`")

			final_content = "\n".join(output_parts) if output_parts else "Code executed with no output."

			if data.status == status.COMPLETED:
				await ctx.reply(view=Success(f"**Execution {runner.execution_id} Successful**\n\n{final_content}"))
			else:
				await ctx.reply(view=Fail(f"**Execution {runner.execution_id} {data.status}**\n\n{final_content}"))

		except Exception as e:
			await ctx.reply(view=Fail(f"An unexpected error occurred during execution setup: {str(e)}"))


async def setup(bot: commands.Bot):
	await bot.add_cog(Extension(bot))
	await bot.add_cog(Blacklist(bot))
