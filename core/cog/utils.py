from typing import Any, Tuple, Optional
from discord.ext import commands

from core.wrp.profile import server, user
from core.cog.ui_template import Fail, UnexpectedError
from meta import config


async def resolve_target(ctx: commands.Context, scope: str) -> Tuple[Any, Optional[int]]:
	if scope not in ('server', 'user'):
		await ctx.reply(view=Fail(
			"Invalid Scope",
			f"Scope must be either 'server' or 'user', not '{scope}'."
		))
		return None, None

	if scope == 'server':
		if not ctx.guild:
			await ctx.reply(view=Fail(
				"Invalid Scope",
				"This command must be used in a server if the scope passed is 'server'."
			))
			return None, None
		return server, ctx.guild.id

	return user, ctx.author.id

async def load_settings(manager: Any, target_id: int, scope: str) -> dict:
	success, data = await manager.settings.load(target_id)
	if success:
		return data
	return config.settings.get(scope, {})

async def handle_common_errors(ctx: commands.Context, error):
	if isinstance(error, commands.CheckFailure):
		return await ctx.reply(view=Fail(
			"Missing Required Permission",
			"You need **Administrator** permissions for that."
		))

	elif isinstance(error, commands.MissingRequiredArgument):
		return await ctx.reply(view=Fail(
			"Missing Argument",
			f"You forgot a required argument: `{error.param.name}`"
		))

	elif isinstance(error, commands.CommandOnCooldown):
		return await ctx.reply(view=Fail(
			"Command on Cooldown",
			f"Try again in `{error.retry_after:.1f}s`."
		))

	else:
		return await ctx.reply(view=UnexpectedError)

def format_dt(dt_obj):
	if not dt_obj: return "Never"
	ts = int(dt_obj.timestamp()) if hasattr(dt_obj, 'timestamp') else dt_obj
	return f"<t:{ts}:R>"


class HybridGroup(commands.HybridGroup):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		for name, attr in self.__class__.__dict__.items():
			if isinstance(attr, commands.Command):
				cmd = attr.copy()

				cmd._callback = cmd.callback.__get__(self, self.__class__)

				if getattr(cmd, 'on_error', None):
					cmd._on_error = cmd.on_error.__get__(self, self.__class__)

				self.add_command(cmd)
