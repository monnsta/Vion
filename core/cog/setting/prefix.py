from typing            import Literal

from discord           import app_commands as app
from discord.ext       import commands

from ._setting_group   import setting
from core.lib.utils    import mt, is_admin
from core.wrp.profile  import server, user
from core.ui.template  import Success, Fail, Generic, Confirmation, UnexpectedError
from meta              import config


class Prefix(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

	@staticmethod
	async def _check(ctx: commands.Context, type: str, char: str | None = None):
		if type not in ('server', 'user'):
			await ctx.reply(view=Fail(
				"Invalid Type",
				f"Type must be either server or user, and not '{type}'..."
			))
			return False

		if type == 'server':
			if not ctx.guild:
				await ctx.reply(view=Fail(
					"Invalid Scope",
					"This command must be used in a server to request server data."
				))
				return False

		if char and len(char) > 2:
			await ctx.reply(view=Fail(
				"Prefix Too Long",
				"Prefix must be under 2 characters long"
			))
			return False

		return True

	@staticmethod
	async def _handle_missing_perms(ctx):
		return await ctx.reply(view=Fail(
			"Missing Required Permission",
			"You need **Administrator** permissions for that."
		))

	@staticmethod
	async def _get_data(manager, target_id: int, type: str) -> dict:
		success, data = await manager.settings.load(target_id)
		if success:
			return data
		return config.settings.get(type)


	@setting.group(
		name='prefix',
		aliases=['p'],
		description='Group for prefix commands.'
	)
	async def prefix(self, ctx: commands.Context):
		if ctx.invoked_subcommand is not None:
			return

		await ctx.reply(view=Fail(
			"Subcommand Missing",
			"Available subcommands:",
			"```",
			"add    (a)",
			"remove (r)",
			"list   (l)",
			"```"
		))


	@prefix.command(
		name='add',
		aliases=['a'],
		description='Add a prefix to your personal profile or current server.'
	)
	@app.describe(
		char='The character to add as prefix',
		type='Whether to add the prefix to your personal profile or current server'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def add(self, ctx: commands.Context, *, char: str, type: Literal['server', 'user']):
		if not await self._check(ctx, type, char):
			return

		if type == 'server':
			manager = server
			target_id = getattr(ctx.guild, 'id', None)
		else:
			manager = user
			target_id = ctx.author.id
		if not target_id:
			return

		data = await self._get_data(manager, target_id, type)

		data["prefix"].append(char)

		success = await manager.settings.save(target_id, data)
		if success:
			await ctx.reply(view=Success(
				"Prefix Added",
				f"Successfully added prefix: `{char}`"
			))

		await ctx.reply(view=Fail(
			"Failed To Add Prefix",
			"There was an unexpected error. please report this"
		))

	@add.error
	async def add_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await self._handle_missing_perms(ctx)


	@prefix.command(
		name='remove',
		aliases=['r'],
		description='Remove a prefix '
	)
	@app.describe(
		pos='The position of the preifx (shown in list command)',
		type='Whether to delete the prefix from your personal profile or server'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def remove(self, ctx: commands.Context, pos: int, type: Literal['server', 'user']):
		if not await self._check(ctx, type):
			return

		if type == 'server':
			manager = server
			target_id = getattr(ctx.guild, 'id', None)
		else:
			manager = user
			target_id = ctx.author.id
		if not target_id:
			return

		data = await self._get_data(manager, target_id, type)
		prefixes = data.get("prefix", [])

		idx = pos - 1

		if not prefixes:
			await ctx.reply(view=Fail(
				"No Prefixes Found",
				"You don't have any prefixes added, therefore cannot remove any"
			))

		if idx < 0 or idx >= len(prefixes):
			await ctx.reply(view=Fail(
				"Invalid Position",
				f"Position {pos} is out of range. Check the list command for valid positions."
			))

		view = Confirmation(
			mt(
				"Are you sure you want to do this?",
				f"This will remove the prefix: `{prefixes[idx]}`"
			),
			mt(
				"Prefix Removed",
				f"Succeessfully removed prefix: `{prefixes[idx]}`"
			),
			"Action Aborted",
			ctx.author
		)
		message = await ctx.reply(view=view)

		confirmed = await view.wait_for_answer()

		if confirmed:
			prefixes.pop(idx)
			success = await manager.settings.save(target_id, data)

			if not success:
				await message.edit(view=UnexpectedError)

	@remove.error
	async def remove_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await self._handle_missing_perms(ctx)


	@prefix.command(
		name='list',
		aliases=['l'],
		description='List all the prefixes added to your personal profile or current server'
	)
	@app.describe(
		type='Whether to list prefixes from yout personal profile or current server'
	)
	async def list(self, ctx: commands.Context, type: Literal['server', 'user']):
		if not await self._check(ctx, type):
			return

		if type == 'server':
			manager = server
			target_id = getattr(ctx.guild, 'id', None)
		else:
			manager = user
			target_id = ctx.author.id
		if not target_id:
			return

		data = await self._get_data(manager, target_id, type)
		prefixes = data.get("prefix", [])

		if not prefixes:
			await ctx.reply(view=Generic(
				"No prefixes found, but there are these you can use:",
				f"* {f'{chr(10)}* '.join([f'`{p}`' for p in config.default_prefix])}"
			))
			return

		await ctx.reply(view=Generic(
			f"Prefix List for {f'This {type.title()}' if type == 'server' else ctx.author.display_name}",
			f"* {f'{chr(10)}* '.join([f'`{p}`' for p in prefixes])}"
		))

	@list.error
	async def list_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await self._handle_missing_perms(ctx)


async def setup(bot: commands.Bot):
	await bot.add_cog(Prefix(bot))
