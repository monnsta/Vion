from typing                 import Any, Tuple, Optional
from discord.ext            import commands

from core.wrp.profile       import server, user
from core.cog._ui.template  import Fail
from meta                   import config


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

async def handle_errors(ctx: commands.Context):
	return await ctx.reply(view=Fail(
		"Missing Required Permission",
		"You need **Administrator** permissions for that."
	))

def format_dt(dt_obj):
	if not dt_obj: return "Never"
	ts = int(dt_obj.timestamp()) if hasattr(dt_obj, 'timestamp') else dt_obj
	return f"<t:{ts}:R>"
