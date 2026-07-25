import asyncio
from typing import Literal

import discord
from discord import app_commands as app
from discord.ext import commands

from core.lib.code import Code, status
from core.lib.utils import mt
from core.wrp.extension import map_command_mentions
from meta import config

from core.cog.ui_template import Fail, Success, Paginated, UnexpectedError
from core.cog.dev.blacklist import Blacklist
from core.cog.dev.extension import Extension
from core.cog.dev.reload import Reload


class DevRoot(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.p = config.default_prefix[0]
		self.dev_only = True

		self.dev.add_command(Blacklist(self.bot))
		self.dev.add_command(Extension(self.bot))
		self.dev.add_command(Reload(self.bot))

	async def cog_check(self, ctx: commands.Context) -> bool:
		return any(ctx.author.id == dev_id for dev_id in config.dev_ids)

	async def cog_command_error(self, ctx: commands.Context, error: Exception):
		if isinstance(error, commands.CommandInvokeError):
			error = getattr(error, 'original', error)

		if isinstance(error, commands.CheckFailure):
			await ctx.reply(view=Fail(
				"Permission Denied",
				"Only developers can use this command."
			), ephemeral=True)

			setattr(ctx, 'handled', True)
			return


	@commands.hybrid_group(
		name='dev',
		aliases=['d'],
		description='Dev commands.'
	)
	async def dev(self, ctx: commands.Context):
		if ctx.invoked_subcommand is None:
			await ctx.reply(view=Fail(
				"Subcommand Missing",
				"Available subcommands:",
				"```",
				"* send          (s)",
				"* code          (c)",
				"* reload_config (r)",
				"* update        (u)",
				"* help          (h)",
				"",
				"* extension     (e)",
				"* blacklist     (b)",
				"```"
			))

	@dev.error
	async def dev_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await ctx.reply(view=Fail("Only developers can use this command."))


	@dev.command(
		name='help',
		aliases=['h'],
		description='Get help for the dev group.'
	)
	async def help(self, ctx: commands.Context):
		view = Paginated(
			"",
			[
				mt(
					"# Dev",
					"This group contains developer-only commands for bot maintenance and testing."
				),
				mt(
					"## Send:",
					"Send a message to the current channel as the bot.",
					"Params:",
					"* message: The message you want to send",
					"Usage:",
					f"* `{self.p}dev send Hello.`",
					f"* `{self.p}d s Hello.`",
					f"* {config.cmd.dev.send} `message:` Hello."
				),
				mt(
					"## Code:",
					"Execute python code safely in a restricted environment.",
					"Params:",
					"* code: The python code to execute",
					"Usage:",
					f"* `{self.p}dev code async def main(**kwargs): print('test')`",
					f"* `{self.p}d c async def main(**kwargs): print('test')`",
					f"* {config.cmd.dev.code} `code:` `async def main(**kwargs): print('test')`"
				),
				mt(
					"## Reload Config:",
					"Reload the config file.",
					"Usage:",
					f"* `{self.p}dev reload config`",
					f"* `{self.p}d r c`",
					f"* {config.cmd.dev.reload.config}"
				),
				mt(
					"## Reload Process:",
					"Reload the entire process",
					"usage:",
					f"* `{self.p}dev reload process`",
					f"* `{self.p}d r p`",
					f"* {config.cmd.dev.reload.process}"
				),
				mt(
					"## Update:",
					"Update application slash commands so they are in-sync with the system.",
					"Params:",
					"* spec: The sync scope: global, dev, clear."
					"Usage:",
					f"* `{self.p}dev update global`",
					f"* `{self.p}d u global`",
					f"* {config.cmd.dev.get('update')} `spec:` global"
				),
				mt(
					"## Extension:",
					"Manage bot extensions (cogs).",
					f"Use `{self.p}dev extension help` | `{self.p}d e h` | {config.cmd.dev.extension.help} to know more.",
					"Command List:",
					"```",
					"load       (l )",
					"unload     (u )",
					"reload     (r )",
					"load_all   (la)",
					"unload_all (ua)",
					"reload_all (ra)",
					"list       (li)",
					"help       (h )",
					"```",
					"Usage:",
					f"* `{self.p}dev extension load core.cog.root`",
					f"* `{self.p}d e l core.cog.root`",
					f"* {config.cmd.dev.extension.get('load')} `path:` core.cog.root"
				),
				mt(
					"## Blacklist:",
					"Manage the global bot blacklist for users and servers.",
					f"Use `{self.p}dev blacklist help` | `{self.p}d b h` | {config.cmd.dev.blacklist.help} to know more.",
					"Command List:",
					"```",
					"add        (a )",
					"remove     (r )",
					"edit       (e )",
					"view       (v )",
					"list       (l )",
					"help       (h )",
					"```",
					"Usage:",
					f"* `{self.p}dev blacklist add user 123456789 \"Spamming\" 7d`",
					f"* `{self.p}d b a user 123456789 \"Spamming\" 7d`",
					f"* {config.cmd.dev.blacklist.add} `type:` user `target_id:` 123456789 `reason:` Spamming `duration:` 7d"
				)
			],
			ctx.author
		)
		message = await ctx.reply(view=view)
		view.message = message


	@dev.command(
		name='send',
		aliases=['s'],
		description='Send a message to the channel.'
	)
	@app.describe(message='The message you want to send')
	async def send(self, ctx: commands.Context, *, message: str):
		initial_message = None
		if ctx.interaction:
			initial_message = await ctx.reply(view=Success(
				"Message sent."
			), ephemeral=True)
		else:
			try:
				await ctx.message.delete()
			except (discord.Forbidden, discord.HTTPException):
				pass

		if initial_message and not (ctx.guild and ctx.guild.get_member(getattr(self.bot.user, 'id'))):
			await initial_message.reply(message)
		else:
			await ctx.send(message)


	@dev.command(
		name='code',
		aliases=['c'],
		description='Execute python code.'
	)
	@app.describe(code='The code to execute')
	async def code(self, ctx: commands.Context, *, code: str):
		await ctx.defer(ephemeral=False)

		initial_view = Paginated(
			header="**Execution Initializing**",
			items=["**Status:** Preparing execution..."],
			user=ctx.author,
			accent_color=0x7289da
		)
		msg = await ctx.reply(view=initial_view)
		initial_view.message = msg

		runner = Code(code)

		def format_live_block(text: str, limit: int = 800) -> str:
			if not text:
				return ""
			text = str(text)
			if len(text) > limit:
				text = f"... (earlier output truncated)\n{text[-(limit - 35):]}"
			return f"```py\n{text}\n```"

		def chunk_for_pagination(title: str, text: str, chunk_size: int = 1500) -> list[str]:
			if not text:
				return []
			text = str(text)

			if len(text) <= chunk_size:
				return [f"**{title}:**\n```py\n{text}\n```"]

			chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
			return [f"**{title} ({i+1}/{len(chunks)}):**\n```py\n{chunk}\n```" for i, chunk in enumerate(chunks)]

		try:
			await runner.execute(timeout=30.0, message=ctx.message, bot=self.bot)

			async def update_live_output():
				last_content = ""
				try:
					while runner.data.status in (status.PENDING, status.RUNNING):
						data = runner.get_output()

						output_parts = []
						if data.logs:
							output_parts.append(f"**Logs:**\n{format_live_block(data.logs, 500)}")

						content = "\n".join(output_parts) if output_parts else "Executing..."

						if content != last_content:
							try:
								live_view = Paginated(
									header=f"**Execution Status: {data.status}**",
									items=[content],
									user=ctx.author,
									accent_color=0x7289da
								)
								await msg.edit(view=live_view)
								live_view.message = msg
								last_content = content
							except Exception:
								pass

						await asyncio.sleep(2.0)
				except asyncio.CancelledError:
					pass

			updater_task = asyncio.create_task(update_live_output())

			data = await runner.wait()
			updater_task.cancel()

			items = []
			if data.logs:
				items.extend(chunk_for_pagination("Logs", data.logs))

			if data.error:
				items.extend(chunk_for_pagination("Error", data.error))
			if data.result is not None:
				items.extend(chunk_for_pagination("Result", data.result))

			if not items:
				items.append("**Result:**\n```py\nCode executed silently with no output.\n```")

			is_success = data.status == status.COMPLETED
			header = f"**Execution {runner.execution_id} {'Successful' if is_success else data.status}**"
			color = 0x43b581 if is_success else 0xf04747

			view = Paginated(
				header=header,
				items=items,
				user=ctx.author,
				accent_color=color
			)

			view.current_page = view.total_pages - 1
			view.create_layout()

			await msg.edit(view=view)
			view.message = msg

		except Exception as e:
			view = Paginated(
				header="**Execution Setup Failed**",
				items=[f"**Error:**\n```py\n{str(e)}\n```"],
				user=ctx.author,
				accent_color=0xf04747
			)
			await msg.edit(view=view)
			view.message = msg


	@dev.command(
		name='update',
		aliases=['u'],
		description='Update application commands so they are in-sync with the system'
	)
	@app.describe(spec='The sync scope: global, dev, or clear.')
	async def update(self, ctx: commands.Context, spec: Literal['global', 'dev', 'clear']):
		if spec == 'global':
			synced = await self.bot.tree.sync()
			map_command_mentions(synced)

			await ctx.reply(view=Success(
				"Success",
				f"Synced {len(synced)} global application commands."
			))
		elif spec == 'dev':
			dev_guilds = [discord.Object(id=g_id) for g_id in config.dev_server_ids]
			total = 0
			for guild in dev_guilds:
				try:
					synced = await self.bot.tree.sync(guild=guild)
					map_command_mentions(synced)
					total += len(synced)
				except discord.HTTPException:
					await ctx.reply(view=UnexpectedError)

			await ctx.reply(view=Success(
				"Success",
				f"Synced {total} application commands across dev servers."
			))
		elif spec == 'clear':
			self.bot.tree.clear_commands(guild=ctx.guild)
			await self.bot.tree.sync(guild=ctx.guild)

			await ctx.reply(view=Success(
				"Success",
				"Cleared and synced this guild's local tree commands."
			))
