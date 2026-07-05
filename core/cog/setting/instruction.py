from typing import Literal

from discord import app_commands as app
from discord.ext import commands

from core.lib.utils import mt, is_admin
from meta import config

from core.cog.utils import resolve_target, load_settings, handle_common_errors, HybridGroup
from core.cog.ui_template import Success, Fail, Generic, Confirmation, TextForm, UnexpectedError


async def callback(ctx: commands.Context):
	if ctx.invoked_subcommand is None:
		await ctx.reply(view=Fail(
			"Subcommand Missing",
			"Available subcommands:",
			"```",
			"set    (s)",
			"delete (d)",
			"view   (v)",
			"help   (h)",
			"```"
		))


class Instruction(HybridGroup):
	def __init__(self, bot: commands.Bot):
		super().__init__(
			callback,
			name='instruction',
			aliases=['i'],
			description='Group for instruction commands.'
		)
		self.bot = bot
		self.p = config.default_prefix[0]


	@commands.hybrid_command(
		name='help',
		aliases=['h'],
		description='Get help for the instruction group.'
	)
	async def help(self, ctx: commands.Context):
		await ctx.reply(view=Generic(
			"# Instruction",
			"This group is used to manage the server instructions for the AI.",
			"These instructions are given straight to the AI.",
			None,
			mt(
				"## Set:",
				"Add instructions to the current server.",
				"Params:",
				"* text: The instruction text. Leave empty to edit in a form",
				"Usage:",
				f"* `{self.p}setting instruction set Never send a message in the #furry_role_play channel`",
				f"* `{self.p}s i s`",
				f"* {config.cmd.setting.instruction.set}"
			), None,
			mt(
				"## Delete:",
				"Delete instructions for the current server.",
				"Usage:",
				f"* `{self.p}setting instruction delete`",
				f"* `{self.p}s i d`",
				f"* {config.cmd.setting.instruction.delete}"
			), None,
			mt(
				"## View:",
				"View added instructions for the current server.",
				"Usage:",
				f"* `{self.p}setting instruction view`",
				f"* `{self.p}s i v`",
				f"* {config.cmd.setting.instruction.view}"
			)
		))


	@commands.hybrid_command(
		name='set',
		aliases=['s'],
		description='Add instructions to the current server.'
	)
	@app.describe(text='The instruction text')
	@is_admin(config.dev_ids)
	async def set(self, ctx: commands.Context, *, text: str | None = None):
		type: Literal['server', 'user'] = 'server'
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)
		instructions = data.get("instructions", "")

		if text is not None:
			data["instructions"] = text
			success = await manager.settings.save(target_id, data)

			if not success:
				await ctx.reply(view=UnexpectedError)
				return

			await ctx.reply(view=Success(
				f"Successfully {'updated' if instructions else 'added'} the instructions."
			))
			return

		view = TextForm(
			f"Use the form after clicking the button below to {'edit' if instructions else 'add'} your instructions",
			"Open Form",
			"Instructions",
			"Text",
			instructions,
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
		await handle_common_errors(ctx, error)


	@commands.hybrid_command(
		name='delete',
		aliases=['d'],
		description='Delete instructions for the current server.'
	)
	@is_admin(config.dev_ids)
	async def delete(self, ctx: commands.Context):
		type: Literal['server', 'user'] = 'server'
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
		await handle_common_errors(ctx, error)


	@commands.hybrid_command(
		name='view',
		aliases=['v'],
		description='View added instructions for the current server.'
	)
	async def view(self, ctx: commands.Context):
		type: Literal['server', 'user'] = 'server'
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)
		instructions = data.get("instructions", "")

		if not instructions:
			await ctx.reply(view=Generic("No instructions added..."))
			return

		await ctx.reply(view=Generic(instructions))
