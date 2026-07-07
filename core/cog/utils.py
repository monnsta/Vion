from typing import Any, Tuple, Optional, Callable, Iterable
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

def hybrid_command(*args: Any, **kwargs: Any) -> Callable[[Any], Any]:
	def decorator(func: Callable[..., Any]) -> Any:
		return commands.hybrid_command(*args, **kwargs)(func)
	return decorator


class HybridGroup(commands.HybridGroup):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		for _, attr in self.__class__.__dict__.items():
			if isinstance(attr, commands.Command):
				cmd = attr.copy()

				cmd._callback = cmd.callback.__get__(self, self.__class__)

				if getattr(cmd, 'on_error', None):
					cmd.on_error = cmd.on_error.__get__(self, self.__class__)

				self.add_command(cmd) # type: ignore


def is_dev(devs: Iterable[int]):
	async def predicate(ctx: commands.Context) -> bool:
		return any(dev_id == ctx.author.id for dev_id in devs)
	return commands.check(predicate)

def is_admin(devs: Iterable[int], compare: tuple[str, str] | None = None):
	async def predicate(ctx: commands.Context) -> bool:
		if compare and ctx.kwargs.get(compare[0]) == compare[1]:
			return True

		perms = getattr(ctx.author, "guild_permissions", None)
		is_owner = (ctx.author.id == ctx.guild.owner_id if ctx.guild else True)
		is_dev = any(ctx.author.id == dev_id for dev_id in devs)
		is_admin = (
			perms.manage_guild or
			perms.administrator
			if perms else False
		)
		return is_owner or is_dev or is_admin
	return commands.check(predicate)
