from typing                   import Literal

from discord                  import app_commands as app
from discord.ext              import commands

from core.lib.utils           import mt, em, is_admin
from core.cog.setting._group  import setting
from core.cog.cog_utils       import resolve_target, load_settings, handle_missing_perms
from core.cog.ui_template     import Success, Fail, Generic, Confirmation, UnexpectedError
from meta                     import config


class Prefix(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot


	@setting.group(
		name='prefix',
		aliases=['p'],
		description='Group for prefix commands.'
	)
	async def prefix(self, ctx: commands.Context):
		"""Group for prefix commands."""
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
		type='Whether to add the prefix to your personal profile or current server',
		char='The character to add as prefix'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def add(self, ctx: commands.Context, type: Literal['server', 'user'] = 'user', *, char: str):
		"""
		Add a prefix to your personal profile or current server, allows you to run commands by your own prefix
		Example: /setting prefix add user !
		"""
		if len(char) > 2:
			await ctx.reply(view=Fail(
				"Prefix Too Long",
				"Prefix must be under 2 characters long."
			))
			return

		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)

		if len(data["prefix"]) >= config.max_prefix:
			await ctx.reply(view=Fail(
				"Max Prefix Limit Reached",
				f"You can only add {config.max_prefix} prefixes.{f'.. Well the current amount is passed that but you still cannot add more.' if len(data['prefix']) > config.max_prefix else ''}"
			))
			return
		if char in data["prefix"]:
			await ctx.reply(view=Fail(
				"Prefix Already exists",
				f"Prefix '{em(char)}' already in the settings, you don't need to add it twice."
			))
			return
		if char in config.prefix:
			await ctx.reply(view=Fail(
				"Prefix Reserved By Bot",
				f"Prefix '{em(char)}' is reserved by the bot and used globaly, you don't need to add it to use it."
			))
			return

		data["prefix"].append(char)

		success = await manager.settings.save(target_id, data)
		if not success:
			await ctx.reply(view=UnexpectedError)
			return

		await ctx.reply(view=Success(
			"Prefix Added",
			f"Successfully added prefix: `{char}`"
		))

	@add.error
	async def add_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await handle_missing_perms(ctx)


	@prefix.command(
		name='remove',
		aliases=['r'],
		description='Remove a prefix from your personal profile or current server.'
	)
	@app.describe(
		type='Whether to delete the prefix from your personal profile or server',
		pos='The position of the prefix (shown in list command)'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def remove(self, ctx: commands.Context, type: Literal['server', 'user'] = 'user', pos: int):
		"""
		Remove an added prefix from your personal profile or current server
		Example: /setting prefix remove user 1
		"""
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)
		prefixes = data.get("prefix", [])

		idx = pos - 1

		if not prefixes:
			await ctx.reply(view=Fail(
				"No Prefixes Found",
				"You don't have any prefixes added, therefore cannot remove any."
			))
			return

		if idx < 0 or idx >= len(prefixes):
			await ctx.reply(view=Fail(
				"Invalid Position",
				f"Position {pos} is out of range. Check the list command for valid positions."
			))
			return

		view = Confirmation(
			mt(
				"Are you sure you want to do this?",
				f"This will remove the prefix: `{prefixes[idx]}`"
			),
			mt(
				"Prefix Removed",
				f"Successfully removed prefix: `{prefixes[idx]}`"
			),
			"Action Aborted",
			ctx.author
		)
		message = await ctx.reply(view=view)

		confirmed = await view.wait_for_answer()

		if confirmed:
			prefixes.pop(idx)
			data["prefix"] = prefixes
			success = await manager.settings.save(target_id, data)

			if not success:
				await message.edit(view=UnexpectedError)

	@remove.error
	async def remove_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await handle_missing_perms(ctx)


	@prefix.command(
		name='list',
		aliases=['l'],
		description='List all the prefixes added to your personal profile or current server'
	)
	@app.describe(
		type='Whether to list prefixes from your personal profile or current server'
	)
	async def list(self, ctx: commands.Context, type: Literal['server', 'user'] = 'user'):
		"""
		List all prefix from your personal profile or current server
		Example: /setting prefix list
		"""
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)
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
			await handle_missing_perms(ctx)


async def setup(bot: commands.Bot):
	await bot.add_cog(Prefix(bot))
