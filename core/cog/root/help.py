import discord
from discord                import app_commands as app
from discord.ext            import commands

from core.lib.utils         import mt
from core.cog._ui.template  import Generic, Fail
from meta                   import config


class Help(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.intro = (
			"## Introduction:\n"
			"This AI agent is integrated directly with the Discord API, granting it the "
			"capability to manage messages, channels, roles, and members. To ensure security, the bot "
			"executes commands based on a hierarchy: it prioritizes Server Owners and Administrators, "
			"while verifying specific permissions for other users (e.g., a user must have 'Timeout Members' "
			"permissions to request a timeout).\n\n"
			"## Disclaimer:\n"
			"While robust security measures are in place, AI can be unpredictable. "
			"Use at your own discretion and consider restricting high-level permissions like 'Administrator'.\n\n"
			"## To Get Started W/ Commands:\n"
			f"* Use {config.cmd.help.list} to get a list of all commands.\n"
			f"* Use {config.cmd.help.command} `<name>` to know more about a specific command.\n\n"
			"## How To Talk To The AI:\n"
			f"Really you just.. talk to it, like a human, `@` it take it's name, or whatever really, just talk and it might talk. it'll respond in a human amount of time, NOT becuase it is a human."
		)
		self.param_help = mt(
			"```",
			"<> = Required • [] = Optional • () = Default",
			"/example command <name> [age] [class('Warrior')]",
			"Here name is required you must provide it. Age is optional, you can just leave it. Class is optional but it sets it to 'Warrior'"
			"```"
		)

	@staticmethod
	async def autocomplete(_: discord.Interaction, current: str):
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

		await ctx.reply(view=Generic(self.intro))


	@help.command(
		name='manual',
		aliases=['m'],
		description='Show the manual of the bot'
	)
	async def manual(self, ctx: commands.Context):
		"""Shows the manual of the bot to get started."""
		await ctx.reply(view=Generic(self.intro))


	@help.command(
		name='command',
		aliases=['c'],
		description='Show the help message of a specific command.'
	)
	@app.describe(command="The name of the command (e.g., settings view)")
	@app.autocomplete(command=autocomplete)
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

		params = []
		for param in cmd.parameters:
			bracket = ("`<", ">`") if param.required else ("`[", "]`")
			default = f"({param.default})" if param.default else ""
			line = f"{bracket[0]}{param.name}{default}{bracket[1]}{f': {param.description}' if param.description else ''}"
			param.append(line)

		message = mt(
			f"### {cmd.mention}",
			f"{cmd.description}",
			f"**Parameters:**",
			self.param_help,
			f"* {f'{chr(10)}* '.join(params)}"
		) if params else mt(
			f"### {cmd.mention}",
			f"{cmd.description}"
		)

		await ctx.reply(view=Generic(message))
