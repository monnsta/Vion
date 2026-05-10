from typing                   import Literal

from discord                  import app_commands as app
from discord.ext              import commands

from core.lib.utils           import mt, is_admin
from core.cog.setting._group  import setting
from core.cog.cog_utils       import resolve_target, load_settings, handle_missing_perms
from core.cog.ui_template     import Success, Fail, Generic, Confirmation, TextForm, UnexpectedError
from meta                     import config


class Instructions(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot


	@setting.group(
		name='instruction',
		aliases=['i'],
		description='Group for instruction commands.'
	)
	async def instruction(self, ctx: commands.Context):
		"""Group for instruction commands."""
		if ctx.invoked_subcommand is not None:
			return

		await ctx.reply(view=Fail(
			"Subcommand Missing",
			"Available subcommands:",
			"```",
			"set    (s)",
			"delete (d)",
			"view   (v)",
			"```"
		))


	@instruction.command(
		name='set',
		aliases=['s'],
		description='Add instructions to your personal profile or current server'
	)
	@app.describe(
		type='Whether to add the instructions in your personal profile or the current server',
		text='The instruction text'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def set(self, ctx: commands.Context, type: Literal['server', 'user'] = 'user', *, text: str | None = None):
		"""
		Set instructions to your personal profile or current server, these are seen by the AI.
		Example: /setting instruction set user Always call me by my first role in the server
		"""
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)
		instructions = data.get("instructions", "")

		view = TextForm(
			f"Use the form after clicking the button below to {'edit' if instructions else 'add'} your instructions",
			"Open Form",
			"Instructions",
			"Text",
			data["instructions"],
			ctx.author
		)
		message = await ctx.reply(view=view)

		input = await view.wait_for_input()

		if input is None:
			await message.edit(view=Fail("Action Aborted"))
			return

		data["instructions"] = input
		success = await manager.settings.save(target_id, data)

		if not success:
			await message.edit(view=UnexpectedError)
			return

		await message.edit(view=Success(
			f"Successfully {'updated' if instructions else 'added'} the instructions."
		))

	@set.error
	async def set_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await handle_missing_perms(ctx)


	@instruction.command(
		name='delete',
		aliases=['d'],
		description='Delete instructions from your personal profile or current server'
	)
	@app.describe(
		type='Whether to delete the instructions from your personal profile or the current server'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def delete(self, ctx: commands.Context, type: Literal['server', 'user'] = 'user'):
		"""
		Delete the instructions added to your personal profile or current server
		Example: /setting instruction delete user
		"""
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)

		if data.get("instructions", "") == "":
			await ctx.reply(view=Generic("No need to. It's already empty."))
			return

		view = Confirmation(
			"Are you sure you want to do this?",
			"Instructions deleted successfully",
			"Action Aborted",
			ctx.author
		)
		message = await ctx.reply(view=view)

		confirmed = await view.wait_for_answer()

		if confirmed:
			data["instructions"] = ""
			success = await manager.settings.save(target_id, data)

			if not success:
				await message.edit(view=UnexpectedError)

	@delete.error
	async def delete_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await handle_missing_perms(ctx)


	@instruction.command(
		name='view',
		aliases=['v'],
		description='View added instructions from your personal profile or current server'
	)
	@app.describe(
		type='Whether to show instructions from your personal profile or current server'
	)
	async def view(self, ctx: commands.Context, type: Literal['server', 'user'] = 'user'):
		"""
		Shows the currently added instructions of your personal profile or current server
		Example: /setting instruction view user
		"""
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)
		instructions = data.get("instructions", "")

		if not instructions:
			await ctx.reply(view=Generic("No instructions added..."))
			return

		await ctx.reply(view=Generic(instructions))


async def setup(bot: commands.Bot):
	await bot.add_cog(Instructions(bot))