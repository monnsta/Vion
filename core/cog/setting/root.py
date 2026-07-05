from typing import Literal

from discord import app_commands as app
from discord.ext import commands

from core.lib.utils import is_admin, mt, em
from core.wrp.profile import server
from meta import config, emoji

from core.cog.utils import resolve_target, load_settings, handle_common_errors
from core.cog.ui_template import Success, Generic, Confirmation, Paginated, UnexpectedError
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
		manager, target_id = await resolve_target(ctx, 'server')
		if not manager:
			return

		data = await load_settings(server, getattr(ctx.guild, 'id'), "server")
		current_value = data[key]
		target_value = value
		conf_view = None

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
		success = await server.settings.save(ctx.guild.id, data)

		if not success:
			if conf_view:
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
				"* show_loading (s)",
				"* chatbot_only (c)",
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
					"## Show Loading:",
					"Toggle AI loading message for the current server. Makes the bot send a loading message before replying.",
					"Params:",
					"* value: Whether to turn loading message on or off (True or False)",
					"Usage:",
					f"* `{self.p}setting show_loading False`",
					f"* `{self.p}s s n`",
					f"* {config.cmd.setting.show_loading} `value:` False"
				),
				mt(
					"## Chatbot Only:",
					"Toggle chat bot only mode for the current server. Makes the bot not able to do any actions except sending messages.",
					"Params:",
					"* value: Whether to turn chatbot mode on or off (True or False)",
					"Usage:",
					f"* `{self.p}setting chatbot_only False`",
					f"* `{self.p}s c n`",
					f"* {config.cmd.setting.chatbot_only} `value:` False"
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

		data = await load_settings(manager, target_id, type)

		await ctx.reply(view=Generic(
			f"# Settings for {ctx.guild.name if type == 'server' else ctx.author.display_name}",
			f"**Prefixes:** {' • '.join([f'`{p}`' for p in [*data['prefix'], *config.default_prefix]])}",
			f"**Chatbot Mode:** {'Yes' if data.get('chatbot', False) else 'No'}",
			f"**Loading Message:** {'Yes' if data.get('ai_load_message', False) else 'No'}",
			f"**Freewill:** {'Yes' if data.get('free_will', False) else 'No'}",
			f"**Instructions:**\n{data.get('instructions', 'None')}"
		))


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


	@setting.command(
		name='show_loading',
		aliases=['s'],
		description='Toggle AI loading message for the current server'
	)
	@app.describe(
		value='Whether to turn loading message on or off (True or False)'
	)
	@app.guild_only
	@is_admin(config.dev_ids)
	async def show_loading(self, ctx: commands.Context, value: bool):
		await self._update_server_setting(ctx, "ai_load_message", value, "Loading Message")

	@show_loading.error
	async def show_loading_error(self, ctx: commands.Context, error):
		await handle_common_errors(ctx, error)


	@setting.command(
		name='chatbot_only',
		aliases=['c'],
		description='Toggle chat bot only mode for the current server'
	)
	@app.describe(
		value='Whether to turn chatbot mode on or off (True or False)'
	)
	@app.guild_only
	@is_admin(config.dev_ids)
	async def chatbot_only(self, ctx: commands.Context, value: bool):
		await self._update_server_setting(ctx, "chatbot", value, "Chatbot Mode")

	@chatbot_only.error
	async def chatbot_only_error(self, ctx: commands.Context, error):
		await handle_common_errors(ctx, error)
