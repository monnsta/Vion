from typing              import Optional, Literal

import discord
from discord             import app_commands as app
from discord.ext         import commands

from core.lib.utils      import is_dev, mt
from core.lib.code       import Code, status
from core.wrp.extension  import extension
from core.wrp.blacklist  import blacklist
from core.ui.template    import Fail, Success, Generic, Paginated
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
		"Subcommand Missing",
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
			"Subcommand Missing",
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
		"""
		Add a user or server to the blacklist.
		Example: /dev blacklist add 123 user abuse 7d
		"""
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
		aliases=['r'],
		description='Remove a user or server from the blacklist.'
	)
	@app.describe(
		target_id='The ID of the user or server',
		type='Whether this is a user or server'
	)
	async def remove(self, ctx: commands.Context, target_id: str, type: Literal['user', 'server']):
		"""
		Remove a user or server from the blacklist.
		Example: /dev blacklist remove 123 user
		"""
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
		target_id='The ID of the user or server',
		type='Whether this is a user or server'
	)
	async def show(self, ctx: commands.Context, target_id: str, type: Literal['user', 'server']):
		"""
		Show information of a blacklisted user or server.
		Example: /dev blacklist show 123 user
		"""
		try:
			tid = int(target_id)
		except ValueError:
			return await ctx.reply(view=Fail("Target ID must be a valid integer."))

		success, data = await blacklist.get(tid, type)
		if not success:
			return await ctx.reply(view=Fail(data))

		label = f"Unknown {type.capitalize()}"
		if type == 'user':
			user = self.bot.get_user(tid) or await self.bot.fetch_user(tid).catch(lambda _: None)
			if user: label = f"**{user.name}** ({user.id})"
		else:
			guild = self.bot.get_guild(tid)
			if guild: label = f"**{guild.name}** ({guild.id})"

		def format_dt(dt_obj):
			if not dt_obj: return "Never"
			ts = int(dt_obj.timestamp()) if hasattr(dt_obj, 'timestamp') else dt_obj
			return f"<t:{ts}:F> (<t:{ts}:R>)"

		await ctx.reply(view=Generic(
			f"## Blacklisted {type.capitalize()}",
			f"* **Target:** {label}",
			f"* **Moderator:** <@{data['mod_id']}>",
			f"* **Reason:** {data['reason']}",
			f"* **Created:** {format_dt(data.get('created_at'))}",
			f"* **Expires:** {format_dt(data.get('expires_at'))}"
		))


	@blacklist.command(
		name='list',
		aliases=['l'],
		description='List all blacklisted entities.'
	)
	@app.describe(type='Filter by user or server')
	async def list(self, ctx: commands.Context, type: Optional[Literal['user', 'server']] = None):
		"""List all blacklisted users or servers."""
		entries = await blacklist.list_all(type)

		if not entries:
			return await ctx.reply(view=Generic("### Global Blacklist", "The blacklist is currently empty."))

		def format_dt(dt_obj):
			if not dt_obj: return "Never"
			ts = int(dt_obj.timestamp()) if hasattr(dt_obj, 'timestamp') else dt_obj
			return f"<t:{ts}:R>"

		results = []
		for e in entries:
			e_type = e['type'].capitalize()
			e_id = e['id']
			
			icon = None
			label = f"Unknown {e_type}"
			if e['type'] == 'user':
				u = self.bot.get_user(e_id)
				if u: label = f"**{u.name}**"
				if u and u.avatar: icon = u.avatar.url
			elif e['type'] == 'server':
				g = self.bot.get_guild(e_id)
				if g: label = f"**{g.name}**"
				if g and g.icon: icon = g.icon.url

			block = mt(
				f"**{e_type}:** {label} (`{e_id}`)",
				f"* **Moderator:** <@{e['mod_id']}>",
				f"* **Reason:** {e['reason']}",
				f"* **Created:** {format_dt(e.get('created_at'))}",
				f"* **Expires:** {format_dt(e.get('expires_at'))}",
			)
			if icon: block = [block, icon]
			results.append(block)

		header = f"## Blacklisted {type.capitalize() + 's' if type else ''}"
		
		view = Paginated(
			header=header,
			items=results,
			user=ctx.author
		)

		await ctx.reply(view=view)

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
	await bot.add_cog(Misc(bot))
