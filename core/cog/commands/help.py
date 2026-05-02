import discord
from discord             import app_commands as app
from discord.ext         import commands

from core.ui.template    import Generic
from meta                import config


class Help(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.man = (
			"# Bot Manual\n"
			"**Introduction:** This AI agent is integrated directly with the Discord API, granting it the "
			"capability to manage messages, channels, roles, and members. To ensure security, the bot "
			"executes commands based on a hierarchy: it prioritizes Server Owners and Administrators, "
			"while verifying specific permissions for other users (e.g., a user must have 'Timeout Members' "
			"permissions to request a timeout).\n"
			"**Disclaimer:** While robust security measures are in place, AI can be unpredictable. "
			"Use at your own discretion and consider restricting high-level permissions like 'Administrator'.\n\n"
			"## Commands\n"
			"```<> Required | [] Optional | () Type/Choice | '' Literal | @ Default```\n"
			f"View details: {config.cmd.help.command} `<command>`\n\n"
			"### Settings\n"
			f"* {config.cmd.settings.view}\n> `[raw('True', @'False')]`\n"
			"**Prefix Management**\n"
			f"* {config.cmd.settings.prefix.add}\n> `<char>` `[scope('server', @'user')]`\n"
			f"* {config.cmd.settings.prefix.remove}\n> `<char|pos>` `[scope('server', @'user')]`\n"
			f"* {config.cmd.settings.prefix.list}\n> `[scope('server', @'user')]`\n\n"
			"**API Key Management**\n"
			f"* {config.cmd.settings.gemini_key.add}\n> `<key>` `[scope('server', @'user')]`\n"
			f"* {config.cmd.settings.gemini_key.remove}\n> `<pos>` `[scope('server', @'user')]`\n"
			f"* {config.cmd.settings.gemini_key.list}\n> `[scope('server', @'user')]`\n"
			"**System Instructions**\n"
			f"* {config.cmd.settings.instructions.set}\n> `[content(text, @form)]`\n"
			f"* {config.cmd.settings.instructions.delete}\n"
			f"* {config.cmd.settings.instructions.view}\n\n"
			"**Behavior Toggles**\n"
			f"* {config.cmd.settings.freewill}\n> `<bool('True', 'False')>`\n"
			f"* {config.cmd.settings.show_loading}\n> `<bool('True', 'False')>`\n"
			f"* {config.cmd.settings.chat_bot_only}\n> `<bool('True', 'False')>`\n\n"
			"### Data\n"
			f"* {config.cmd.data.delete}\n"
			f"* {config.cmd.data.get_all}\n\n"
			"### Fun\n"
			f"* {config.cmd.fun.magic_ball}\n> `<question>`\n"
			f"* {config.cmd.fun.rate}\n> `<type>` `[user(id|name, @self)]`\n"
			f"* {config.cmd.fun.tictactoe}\n> `<user(id|name, @bot)>`\n"
			f"* {config.cmd.fun.avatar_rpc}\n> `<user(id|name, @bot)>`"
		)

	@staticmethod
	async def autocomplete(interaction: discord.Interaction, current: str):
		...


	@commands.hybrid_group(
		name='help',
		aliases=['h'],
		description='Help commands.'
	)
	async def help(self, ctx: commands.Context):
		"""Group for all the help commands."""
		if ctx.invoked_subcommand is not None:
			return
		await ctx.reply(view=Generic(self.man))


	@help.command(
		name='manual',
		aliases=['m'],
		description='Show the manual of the bot'
	)
	async def manual(self, ctx: commands.Context):
		"""Shows the manual of the bot to get started."""


	@help.command(
		name='command',
		aliases=['c'],
		description='Show the help message of a specific command.'
	)
	app.describe(command="The name of the command")
	app.autocomplete(command=self.autocomplete)
	async def command(self, ctx: commands.Context, *, command: str):
		"""Shows help for a specific command."""
		...
