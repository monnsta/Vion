import discord
from discord             import app_commands as app
from discord.ext         import commands

from core.ui.template    import Generic, Fail
from meta                import config


class Help(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.intro = (
			"**Introduction:** This AI agent is integrated directly with the Discord API, granting it the "
			"capability to manage messages, channels, roles, and members. To ensure security, the bot "
			"executes commands based on a hierarchy: it prioritizes Server Owners and Administrators, "
			"while verifying specific permissions for other users (e.g., a user must have 'Timeout Members' "
			"permissions to request a timeout).\n"
			"**Disclaimer:** While robust security measures are in place, AI can be unpredictable. "
			"Use at your own discretion and consider restricting high-level permissions like 'Administrator'.\n\n"
		)
		self.manual = Generic(
			"# Bot Manual",
			intro,
			"## Commands",
			"```<> Required | [] Optional | () Type/Choice | '' Literal | @ Default```",
			f"View details: {config.cmd.help.command} `<command>`",
			"",
			"### Settings",
			f"* {config.cmd.settings.view}\n> `[raw('True', @'False')]`",
			"",
			"**Prefix Management**",
			f"* {config.cmd.settings.prefix.add}\n> `<char>` `[scope('server', @'user')]`",
			f"* {config.cmd.settings.prefix.remove}\n> `<char|pos>` `[scope('server', @'user')]`",
			f"* {config.cmd.settings.prefix.list}\n> `[scope('server', @'user')]`",
			"",
			"**API Key Management**",
			f"* {config.cmd.settings.gemini_key.add}\n> `<key>` `[scope('server', @'user')]`",
			f"* {config.cmd.settings.gemini_key.remove}\n> `<pos>` `[scope('server', @'user')]`",
			f"* {config.cmd.settings.gemini_key.list}\n> `[scope('server', @'user')]`",
			"",
			"**System Instructions**",
			f"* {config.cmd.settings.instructions.set}\n> `[content(text, @form)]`",
			f"* {config.cmd.settings.instructions.delete}",
			f"* {config.cmd.settings.instructions.view}",
			"",
			"**Behavior Toggles**",
			f"* {config.cmd.settings.freewill}\n> `<bool('True', 'False')>`",
			f"* {config.cmd.settings.show_loading}\n> `<bool('True', 'False')>`",
			f"* {config.cmd.settings.chat_bot_only}\n> `<bool('True', 'False')>`",
			"",
			"### Your Data",
			f"* {config.cmd.delete_my_data}",
			f"* {config.cmd.give_my_data}",
			"",
			"### Fun",
			f"* {config.cmd.fun.magic_ball}\n> `<question>`",
			f"* {config.cmd.fun.rate}\n> `<type>` `[user(id|name, @self)]`",
			f"* {config.cmd.fun.tictactoe}\n> `<user(id|name, @bot)>`",
			f"* {config.cmd.fun.avatar_rpc}\n> `<user(id|name, @bot)>`",
		)

	@staticmethod
	async def autocomplete(interaction: discord.Interaction, current: str):
		choices = []
		for cmd in config.cmd:
			if current.lower() in cmd.name:
				choices.append(app.Choice(name=cmd.name, value=cmd.name))

		return choices[:25]


	@commands.hybrid_group(
		name='help',
		aliases=['h'],
		description='Help commands.'
	)
	async def help(self, ctx: commands.Context):
		"""Group for all the help commands."""
		if ctx.invoked_subcommand is not None:
			return
		await ctx.reply(view=self.manual)


	@help.command(
		name='manual',
		aliases=['m'],
		description='Show the manual of the bot'
	)
	async def manual(self, ctx: commands.Context):
		"""Shows the manual of the bot to get started."""
		await ctx.reply(view=self.manual)


	@help.command(
		name='command',
		aliases=['c'],
		description='Show the help message of a specific command.'
	)
	app.describe(command="The name of the command (e.g., settings view)")
	app.autocomplete(command=autocomplete)
	async def command(self, ctx: commands.Context, *, command: str):
		"""
		Shows help for a specific command.
		Example: /help command settings view
		"""
		cmd = config.cmd.get(command.replace(" ", "."), None)

		if not cmd:
			await ctx.reply(view=Fail(
				"Command Not Found",
				f"There doesn't seem to be a command named: '{command}'"
			))
			return

		await ctx.reply(view=Generic(
			f"### {cmd.mention}",
			f"{cmd.description}"
		))


async def setup(bot: commands.Bot):
	await bot.add_cog(Help(bot))
