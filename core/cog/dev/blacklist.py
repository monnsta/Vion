from typing              import Optional, Literal

from discord             import app_commands as app
from discord.ext         import commands

from ._dev_group         import dev
from core.lib.utils      import mt
from core.wrp.blacklist  import blacklist
from core.ui.template    import Fail, Success, Generic, Paginated


dev_only = True


class Blacklist(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot


	@dev.group(
		name='blacklist',
		aliases=['bl'],
		description='Manage the global bot blacklist.'
	)
	async def blacklist(self, ctx: commands.Context):
		"""Group for all the blacklist commands. blacklisted users or servers cannot access the bot."""
		if ctx.invoked_subcommand is not None:
			return

		await ctx.reply(view=Fail(
			"Subcommand Missing",
			"Available subcommands:",
			"```",
			"* add    (a)",
			"* remove (r)",
			"* show   (s)",
			"* list   (l)",
			"```"
		))


	@blacklist.command(
		name='add',
		aliases=['a'],
		description='Add a user or server to the blacklist.'
	)
	@app.describe(
		target_id='The ID of the user or server',
		type='Whether this is a user or server',
		reason='Reason for blacklisting',
		duration='Duration (e.g., 7d, 12h, 30m). Leave empty for permanent.'
	)
	async def add(self, ctx: commands.Context, target_id: str, type: Literal['user', 'server'], reason: str, duration: Optional[str] = None):
		"""
		Add a user or server to the blacklist.
		Example: /dev blacklist add 123 user abuse 7d
		"""
		try:
			tid = int(target_id)
		except ValueError:
			return await ctx.reply(view=Fail("Target ID must be a valid integer."))

		success, msg = await blacklist.add(tid, type, ctx.author.id, reason, duration)

		if success:
			await ctx.reply(view=Success(f"**{type.capitalize()} {tid}** has been blacklisted.\n**Reason:** {reason}"))
		else:
			await ctx.reply(view=Fail(msg))


	@blacklist.command(
		name='remove',
		aliases=['r'],
		description='Remove a user or server from the blacklist.'
	)
	@app.describe(
		target_id='The ID of the user or server',
		type='Whether this is a user or server'
	)
	async def remove(self, ctx: commands.Context, target_id: str, type: Literal['user', 'server']):
		"""
		Remove a user or server from the blacklist.
		Example: /dev blacklist remove 123 user
		"""
		try:
			tid = int(target_id)
		except ValueError:
			return await ctx.reply(view=Fail("Target ID must be a valid integer."))

		success, msg = await blacklist.remove(tid, type)

		if success:
			await ctx.reply(view=Success(msg))
		else:
			await ctx.reply(view=Fail(msg))


	@blacklist.command(
		name='show',
		aliases=['s'],
		description='Show detailed info about a specific blacklist entry.'
	)
	@app.describe(
		target_id='The ID of the user or server',
		type='Whether this is a user or server'
	)
	async def show(self, ctx: commands.Context, target_id: str, type: Literal['user', 'server']):
		"""
		Show information of a blacklisted user or server.
		Example: /dev blacklist show 123 user
		"""
		try:
			tid = int(target_id)
		except ValueError:
			return await ctx.reply(view=Fail("Target ID must be a valid integer."))

		success, data = await blacklist.get(tid, type)
		if not success:
			return await ctx.reply(view=Fail(data))

		label = f"Unknown {type.capitalize()}"
		if type == 'user':
			user = self.bot.get_user(tid)
			if not user:
				try:
					user = await self.bot.fetch_user(tid)
				except Exception:
					user = None

			if user: label = f"**{user.name}** ({user.id})"
		else:
			guild = self.bot.get_guild(tid)
			if guild: label = f"**{guild.name}** ({guild.id})"

		def format_dt(dt_obj):
			if not dt_obj: return "Never"
			ts = int(dt_obj.timestamp()) if hasattr(dt_obj, 'timestamp') else dt_obj
			return f"<t:{ts}:F> (<t:{ts}:R>)"

		await ctx.reply(view=Generic(
			f"## Blacklisted {type.capitalize()}",
			f"* **Target:** {label}",
			f"* **Moderator:** <@{data['mod_id']}>",
			f"* **Reason:** {data['reason']}",
			f"* **Created:** {format_dt(data.get('created_at'))}",
			f"* **Expires:** {format_dt(data.get('expires_at'))}"
		))


	@blacklist.command(
		name='list',
		aliases=['l'],
		description='List all blacklisted entities.'
	)
	@app.describe(type='Filter by user or server')
	async def list(self, ctx: commands.Context, type: Optional[Literal['user', 'server']] = None):
		"""List all blacklisted users or servers."""
		entries = await blacklist.list_all(type)

		if not entries:
			return await ctx.reply(view=Generic("### Global Blacklist", "The blacklist is currently empty."))

		def format_dt(dt_obj):
			if not dt_obj: return "Never"
			ts = int(dt_obj.timestamp()) if hasattr(dt_obj, 'timestamp') else dt_obj
			return f"<t:{ts}:R>"

		results = []
		for e in entries:
			e_type = e['type'].capitalize()
			e_id = e['id']
			
			icon = None
			label = f"Unknown {e_type}"
			if e['type'] == 'user':
				u = self.bot.get_user(e_id)
				if u: label = f"**{u.name}**"
				if u and u.avatar: icon = u.avatar.url
			elif e['type'] == 'server':
				g = self.bot.get_guild(e_id)
				if g: label = f"**{g.name}**"
				if g and g.icon: icon = g.icon.url

			block = mt(
				f"**{e_type}:** {label} (`{e_id}`)",
				f"* **Moderator:** <@{e['mod_id']}>",
				f"* **Reason:** {e['reason']}",
				f"* **Created:** {format_dt(e.get('created_at'))}",
				f"* **Expires:** {format_dt(e.get('expires_at'))}",
			)
			if icon: block = [block, icon]
			results.append(block)

		header = f"## Blacklisted {type.capitalize() + 's' if type else ''}"
		
		view = Paginated(
			header=header,
			items=results,
			user=ctx.author
		)

		await ctx.reply(view=view)


async def setup(bot: commands.Bot):
	await bot.add_cog(Blacklist(bot))
