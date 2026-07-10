from typing import Literal

from discord import app_commands as app
from discord.ext import commands

from core.lib.utils import mt, em
from core.wrp.profile import server
from meta import config, emoji

from core.cog.utils import resolve_target, load_settings, handle_common_errors, is_admin
from core.cog.ui_template import Success, Fail, Generic, Confirmation, Paginated, UnexpectedError
from core.cog.setting.gemini_key import GeminiKey
from core.cog.setting.instruction import Instruction
from core.cog.setting.prefix import Prefix


class SettingRoot(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.p = config.default_prefix[0]

		self.setting.add_command(GeminiKey(self.bot))
		self.setting.add_command(Instruction(self.bot))
		self.setting.add_command(Prefix(self.bot))

	@staticmethod
	async def _update_server_setting(ctx: commands.Context, key: str, value: bool, display_name: str):
		manager, _ = await resolve_target(ctx, 'server')
		if not manager:
			return

		data = await load_settings(server, getattr(ctx.guild, 'id'), "server")
		current_value = data[key]
		target_value = value
		conf_view = None
		conf_msg = None

		if current_value == value:
			target_value = not value
			conf_view = Confirmation(
				f"{display_name} already set to {value}, set to {target_value} instead?",
				f"{display_name} set to {target_value}",
				"Action Aborted",
				ctx.author
			)
			conf_msg = await ctx.reply(view=conf_view)

			if not await conf_view.wait_for_answer():
				return

		data[key] = target_value
		if ctx.guild:
			success = await server.settings.save(ctx.guild.id, data)
		else:
			await ctx.reply(view=Fail(
				"Invalid Scope",
				"You must be in a guild to use this command."
			))
			return

		if not success:
			if conf_view:
				if conf_msg:
					await conf_msg.edit(view=UnexpectedError)
			else:
				await ctx.reply(view=UnexpectedError)
		elif not conf_view:
			await ctx.reply(view=Success(f"{display_name} set to {target_value}"))


	@commands.hybrid_group(
		name='setting',
		aliases=['s'],
		description='Setting commands.'
	)
	async def setting(self, ctx: commands.Context):
		if ctx.invoked_subcommand is None:
			await ctx.reply(view=Fail(
				"Subcommand Missing",
				"Available subcommands:",
				"```",
				"* view         (v)",
				"* freewill     (f)",
				"* help         (h)",
				"",
				"* prefix       (p)",
				"* gemini_key   (g)",
				"* instruction  (i)"
				"```"
			))


	@setting.command(
		name='help',
		aliases=['h'],
		description='Get help for the setting group.'
	)
	async def help(self, ctx: commands.Context):
		view = Paginated(
			"",
			[
				mt(
					"# Setting",
					"This group is used to manage the server's (or sometimes your) settings."
				),
				mt(
					"## View:",
					"View all your personal settings or the current server's.",
					"Params:",
					"* type: Whether to show your personal settings or server settings",
					"Usage:",
					f"* `{self.p}setting view server`",
					f"* `{self.p}s v server`",
					f"* {config.cmd.setting.view} `type:` server"
				),
				mt(
					"## Freewill:",
					"Toggle free will for the current server. Makes the bot able to talk, or do any action on it's own without a 'trigger'.",
					"Params:",
					"* value: Whether to turn free will on or off (True or False)",
					"Usage:",
					f"* `{self.p}setting freewill False`",
					f"* `{self.p}s f n`",
					f"* {config.cmd.setting.freewill} `value:` False"
				),
				mt(
					"## Prefix:",
					"This group is used to manage your personal prefixes or the server's.",
					f"Use `{self.p}setting prefix help` | `{self.p}s p h` | {config.cmd.setting.prefix.help} to know more"
					"Command List:",
					"```",
					"add    (a)",
					"remove (r)",
					"list   (l)",
					"help   (h)",
					"```",
					"Usage:",
					f"* `{self.p}setting prefix add user ?`",
					f"* `{self.p}s p a user ?`",
					f"* {config.cmd.setting.prefix.add} `type:` user `char:` ?"
				),
				mt(
					"## Gemini Key:",
					"This group is used to manage your personal gemini api keys.",
					f"Use `{self.p}setting gemini_key help` | `{self.p}s g h` | {config.cmd.setting.gemini_key.help} to know more",
					"Command List:",
					"```",
					"add    (a)",
					"remove (r)",
					"list   (l)",
					"help   (h)",
					"```",
					"Usage:",
					f"{emoji.warn} **Recommend to use in dms or use as slash commands to keep your key private.**",
					f"* `{self.p}setting gemini_key add *******`",
					f"* `{self.p}s g a *******`",
					f"* {config.cmd.setting.gemini_key.add} `key:` {em('*******')}"
				),
				mt(
					"## Instruction:",
					"This group is used to manage the server instructions for the AI.",
					f"Use `{self.p}setting instruction help` | `{self.p}s i h` | {config.cmd.setting.instruction.help} to know more",
					"Command List:",
					"```",
					"set    (s)",
					"delete (d)",
					"view   (v)",
					"help   (h)",
					"```",
					"Usage:",
					f"* `{self.p}setting instruction set`",
					f"* `{self.p}s i s`",
					f"* {config.cmd.setting.instruction.get('set')}"
				)
			],
			ctx.author
		)
		message = await ctx.reply(view=view)
		view.message = message


	@setting.command(
		name='view',
		aliases=['v'],
		description='View all your personal settings or the current server\'s'
	)
	@app.describe(
		type='Whether to show your personal settings or server settings'
	)
	async def view(self, ctx: commands.Context, type: Literal['server', 'user']):
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type) # type: ignore

		lines = []
		if type == 'server':
			lines.append(f"# Settings for {getattr(ctx.guild, 'name', 'Unknown')}")
			lines.append(f"**Prefixes:** {' '.join([f'`{p}`' for p in [*data.get('prefix', []), *config.default_prefix]])}")
			lines.append(f"**Freewill:** {'Yes' if data.get('free_will', False) else 'No'}")
			lines.append(
				"**Instructions:**\n"
				f"```{em(data.get('instructions', 'None'), chars='`')}```"
				f"{f'{emoji.info} The `` ` `` (backtick) here are escaped for proper rendering, your instructions doesn\'t actually contain a `` \\` ``' if '`' in data.get('instructions', '') else ''}"
			)
		else:
			lines.append(f"# Settings for {ctx.author.display_name}")
			lines.append(f"**Prefixes:** {' '.join([f'`{p}`' for p in [*data.get('prefix', []), *config.default_prefix]])}")
			lines.append(f"**API Keys:** *Hidden for privacy.* Use {config.cmd.setting.gemini_key.list} to view them.")

		await ctx.reply(view=Generic(*lines))


	@setting.command(
		name='freewill',
		aliases=['f'],
		description='Toggle free will for the current server'
	)
	@app.describe(
		value='Whether to turn free will on or off (True or False)'
	)
	@app.guild_only
	@is_admin(config.dev_ids)
	async def freewill(self, ctx: commands.Context, value: bool):
		await self._update_server_setting(ctx, "free_will", value, "Freewill")

	@freewill.error
	async def freewill_error(self, ctx: commands.Context, error):
		await handle_common_errors(ctx, error)
