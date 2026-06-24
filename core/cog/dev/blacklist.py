import re
from typing import Optional, Literal

from discord import app_commands as app
from discord.ext import commands

from core.lib.utils import mt, em
from core.wrp.blacklist import blacklist
from meta import config

from core.cog.utils import format_dt, HybridGroup
from core.cog.ui_template import Fail, Success, Generic, Paginated


async def callback(ctx: commands.Context):
	if ctx.invoked_subcommand is None:
		await ctx.reply(view=Fail(
			"Subcommand Missing",
			"Available subcommands:",
			"```",
			"* add    (a)",
			"* remove (r)",
			"* edit   (e)",
			"* view   (v)",
			"* list   (l)",
			"* help   (h)",
			"```"
		))


class Blacklist(HybridGroup):
	def __init__(self, bot: commands.Bot):
		super().__init__(
			callback,
			name='blacklist',
			aliases=['b'],
			description='Manage the global bot blacklist.'
		)
		self.bot = bot
		self.p = config.default_prefix[0]

	async def _validate_args(self, ctx: commands.Context, entity_type: str, target_id: str) -> Optional[int]:
		if entity_type not in ('user', 'server'):
			await ctx.reply(view=Fail(
				"Invalid Scope",
				f"Scope must be either 'server' or 'user', not '{scope}'."
			))
			return None

		cleaned = re.sub(r'\D', '', target_id)
		if not cleaned:
			await ctx.reply(view=Fail(
				"Invalid Scope",
				"Target ID must be a valid integer or mention."
			))
			return None

		return int(cleaned)

	async def _get_entity_info(self, entity_type: str, tid: int) -> tuple[str, Optional[str]]:
		label = f"Unknown {entity_type.capitalize()}"
		icon = None

		if entity_type == 'user':
			u = self.bot.get_user(tid)
			if not u:
				try:
					u = await self.bot.fetch_user(tid)
				except Exception:
					pass
			if u:
				label = f"**{em(u.name)}** (`{u.id}`)"
				icon = u.avatar.url if u.avatar else None
		else:
			g = self.bot.get_guild(tid)
			if g:
				label = f"**{em(g.name)}** (`{g.id}`)"
				icon = g.icon.url if g.icon else None

		return label, icon


	@commands.hybrid_command(
		name='help',
		aliases=['h'],
		description='Get help for the blacklist group.'
	)
	async def help(self, ctx: commands.Context):
		await ctx.reply(view=Generic(
			"# Blacklist",
			"This group is used to manage the global blacklist for users and servers.",
			None,
			mt(
				"## Add:",
				"Add a user or server to the blacklist.",
				"Params:",
				"* type: Whether this is a user or server",
				"* target_id: The ID or mention of the user/server",
				"* reason: Reason for blacklisting",
				"* duration: Duration (e.g., 7d, 12h, 30m). 0 for permanent",
				"Usage:",
				f"* `{self.p}dev blacklist add user 123456789 \"Spamming\" 7d`",
				f"* `{self.p}d b a user 123456789 \"Spamming\" 7d`",
				f"* {config.cmd.dev.blacklist.add} `type:` user `target_id:` 123456789 `reason:` Spamming `duration:` 7d"
			), None,
			mt(
				"## Remove:",
				"Remove a user or server from the blacklist.",
				"Params:",
				"* type: Whether this is a user or server",
				"* target_id: The ID or mention of the user/server",
				"Usage:",
				f"* `{self.p}dev blacklist remove user 123456789`",
				f"* `{self.p}d b r user 123456789`",
				f"* {config.cmd.dev.blacklist.remove} `type:` user `target_id:` 123456789"
			), None,
			mt(
				"## Edit:",
				"Edit an existing blacklist entry.",
				"Params:",
				"* type: Whether this is a user or server",
				"* target_id: The ID or mention of the user/server",
				"Usage:",
				f"* `{self.p}dev blacklist edit user 123456789 \"Spamming + Arguing with mods\" 8d`",
				f"* `{self.p}d b e user 123456789 \"Spamming + Arguing with mods\" 8d`",
				f"* {config.cmd.dev.blacklist.edit} `type:` user `target_id:` 123456789 `new_reason:` Spamming + Arguing with mods `new_duration:` 8d"
			), None,
			mt(
				"## View:",
				"View detailed info about a specific blacklist entry.",
				"Params:",
				"* type: Whether this is a user or server",
				"* target_id: The ID or mention of the user/server",
				"Usage:",
				f"* `{self.p}dev blacklist view user 123456789`",
				f"* `{self.p}d b v user 123456789`",
				f"* {config.cmd.dev.blacklist.view} `type:` user `target_id:` 123456789"
			), None,
			mt(
				"## List:",
				"List all blacklisted entities.",
				"Params:",
				"* type: Filter by user or server",
				"Usage:",
				f"* `{self.p}dev blacklist list`",
				f"* `{self.p}d b l`",
				f"* {config.cmd.dev.blacklist.list}"
			)
		))


	@commands.hybrid_command(
		name='add',
		aliases=['a'],
		description='Add a user or server to the blacklist.'
	)
	@app.describe(
		type='Whether this is a user or server',
		target_id='The ID or mention of the user or server',
		reason='Reason for blacklisting',
		duration='Duration (e.g., 7d, 12h, 30m). 0 for permanent'
	)
	async def add(self, ctx: commands.Context, type: Literal['user', 'server'], target_id: str, reason: str, duration: Optional[str] = None):
		tid = await self._validate_args(ctx, type, target_id)
		if not tid: return

		success, msg = await blacklist.add(tid, type, ctx.author.id, reason, duration)

		if success:
			label, _ = await self._get_entity_info(type, tid)
			await ctx.reply(view=Success(
				"Success",
				f"{label} has been added to the blacklist.\n**Reason:** {reason}"
			))
		else:
			await ctx.reply(view=Fail("Failed", msg))


	@commands.hybrid_command(
		name='remove',
		aliases=['r'],
		description='Remove a user or server from the blacklist.'
	)
	@app.describe(
		type='Whether this is a user or server',
		target_id='The ID or mention of the user or server'
	)
	async def remove(self, ctx: commands.Context, type: Literal['user', 'server'], target_id: str):
		tid = await self._validate_args(ctx, type, target_id)
		if not tid: return

		success, msg = await blacklist.remove(tid, type)

		if success:
			label, _ = await self._get_entity_info(type, tid)
			await ctx.reply(view=Success("Success", f"{label} has been removed from the blacklist."))
		else:
			await ctx.reply(view=Fail("Failed", msg))


	@commands.hybrid_command(
		name='edit',
		aliases=['e'],
		description='Edit an already existing blacklisted user or server.'
	)
	@app.describe(
		type='Whether this is a user or server',
		target_id='The ID or mention of the user or server',
		new_reason='The modified reason for the blacklist',
		new_duration='The modified duration (e.g., 7d, 12h, 30m). 0 for permanent'
	)
	async def edit(self, ctx: commands.Context, type: Literal['user', 'server'], target_id: str, new_reason: Optional[str] = None, new_duration: Optional[str] = None):
		if not new_reason and not new_duration:
			return await ctx.reply(view=Fail(
				"Error",
				"You must specify a new reason, a new duration, or both to make edits."
			))

		tid = await self._validate_args(ctx, type, target_id)
		if not tid: return

		success, msg = await blacklist.edit(
			entity_id=tid,
			entity_type=type,
			mod_id=ctx.author.id,
			reason=new_reason,
			duration=new_duration
		)

		if success:
			label, _ = await self._get_entity_info(type, tid)
			await ctx.reply(view=Success(
				"Success",
				f"Updated blacklist entry for {label}."
			))
		else:
			await ctx.reply(view=Fail("Failed", msg))


	@commands.hybrid_command(
		name='view',
		aliases=['v'],
		description='Show detailed info about a specific blacklist entry.'
	)
	@app.describe(
		type='Whether this is a user or server',
		target_id='The ID or mention of the user or server'
	)
	async def view(self, ctx: commands.Context, type: Literal['user', 'server'], target_id: str):
		tid = await self._validate_args(ctx, type, target_id)
		if not tid: return

		success, data = await blacklist.get(tid, type)
		if not success:
			return await ctx.reply(view=Fail(data))

		label, _ = await self._get_entity_info(type, tid)

		await ctx.reply(view=Generic(
			f"## Blacklisted {type.capitalize()}",
			f"* **Target:** {label}",
			f"* **Moderator:** <@{data['mod_id']}>",
			f"* **Reason:** {data['reason']}",
			f"* **Created:** {format_dt(data.get('created_at'))}",
			f"* **Expires:** {format_dt(data.get('expires_at'))}"
		))


	@commands.hybrid_command(
		name='list',
		aliases=['l'],
		description='List all blacklisted entities.'
	)
	@app.describe(
		type='Filter by user or server'
	)
	async def list(self, ctx: commands.Context, type: Optional[Literal['user', 'server']] = None):
		if type and type not in ('user', 'server'):
			return await ctx.reply(view=Fail("Filter type must be 'user' or 'server'."))

		entries = await blacklist.list_all(type)

		if not entries:
			return await ctx.reply(view=Generic("### Global Blacklist", "The blacklist is currently empty."))

		results = []
		for e in entries:
			e_type = e['type'].capitalize()
			label, icon = await self._get_entity_info(e['type'], e['id'])

			block = mt(
				f"**{e_type}:** {label}",
				f"* **Moderator:** <@{e['mod_id']}>",
				f"* **Reason:** {e['reason']}",
				f"* **Created:** {format_dt(e.get('created_at'))}",
				f"* **Expires:** {format_dt(e.get('expires_at'))}",
			)
			if icon: block = [block, icon]
			results.append(block)

		header = f"## Blacklisted {type.capitalize() + 's' if type else ''}"
		view = Paginated(header=header, items=results, user=ctx.author)
		message = await ctx.reply(view=view)
		view.message = message
