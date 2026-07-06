from typing import Literal

from discord import app_commands as app
from discord.ext import commands

from core.lib.utils import mt, em, is_admin
from meta import config

from core.cog.utils import resolve_target, load_settings, handle_common_errors, HybridGroup, hybrid_command
from core.cog.ui_template import Success, Fail, Generic, Confirmation, UnexpectedError


async def callback(ctx: commands.Context):
	if ctx.invoked_subcommand is None:
		await ctx.reply(view=Fail(
			"Subcommand Missing",
			"Available subcommands:",
			"```",
			"add    (a)",
			"remove (r)",
			"list   (l)",
			"help   (h)",
			"```"
		))


class Prefix(HybridGroup):
	def __init__(self, bot: commands.Bot):
		super().__init__(
			callback,
			name='prefix',
			aliases=['p'],
			description='Group for prefix commands.'
		)
		self.bot = bot
		self.p = config.default_prefix[0]


	@hybrid_command(
		name='help',
		aliases=['h'],
		description='Get help for the prefix group.'
	)
	async def help_cmd(self, ctx: commands.Context):
		await ctx.reply(view=Generic(
			"# Prefix",
			"This group is used to manage your personal prefixes or the server's.",
			"personal ones can be used by you in any server, while server ones can be used by anyone within the server.",
			None,
			mt(
				"## Add:",
				"Add a prefix to your personal profile or current server.",
				"Params:",
				"* type: Whether to add the prefix to your personal profile or current server (user or server)",
				"* char: The character to add as prefix (2 characters max)",
				"Usage:",
				f"* `{self.p}setting prefix add server !`",
				f"* `{self.p}s p a server !`",
				f"* {config.cmd.setting.prefix.add} `type:` server `char:` !"
			), None,
			mt(
				"## Remove:",
				"Remove a prefix from your personal profile or current server.",
				"Params:",
				"* type: Whether to delete the prefix from your personal profile or server (user or server)",
				"* pos: The position of the prefix (shown in list command)",
				"Usage:",
				f"* `{self.p}setting prefix remove server 2`",
				f"* `{self.p}s p r server 2`",
				f"* {config.cmd.setting.prefix.remove} `type:` server `pos:` 2"
			), None,
			mt(
				"## List:",
				"List all the prefixes added to your personal profile or current server.",
				"Params:",
				"* type: Whether to list prefixes from your personal profile or current server (user or server)",
				"Usage:",
				f"* `{self.p}setting prefix list server`",
				f"* `{self.p}s p l server`",
				f"* {config.cmd.setting.prefix.list} `type:` server"
			)
		))


	@hybrid_command(
		name='add',
		aliases=['a'],
		description='Add a prefix to your personal profile or current server.'
	)
	@app.describe(
		type='Whether to add the prefix to your personal profile or current server',
		char='The character to add as prefix (2 characters max)'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def add(self, ctx: commands.Context, type: Literal['server', 'user'], *, char: str):
		if len(char) > 2:
			await ctx.reply(view=Fail(
				"Prefix Too Long",
				"Prefix must be under 2 characters long."
			))
			return

		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type) # type: ignore

		if len(data["prefix"]) >= config.max_prefix:
			await ctx.reply(view=Fail(
				"Max Prefix Limit Reached",
				f"You can only add {config.max_prefix} prefixes.{'.. Well the current amount is passed that but you still cannot add more.' if len(data['prefix']) > config.max_prefix else ''}"
			))
			return
		if char in data["prefix"]:
			await ctx.reply(view=Fail(
				"Prefix Already exists",
				f"Prefix '`{char}`' already in the settings, you don't need to add it twice."
			))
			return
		if char in config.prefix:
			await ctx.reply(view=Fail(
				"Prefix Reserved By Bot",
				f"Prefix '`{char}`' is reserved by the bot and used globaly, you don't need to add it to use it."
			))
			return

		data["prefix"].append(char)

		success = await manager.settings.save(target_id, data)
		if not success:
			await ctx.reply(view=UnexpectedError)
			return

		await ctx.reply(view=Success(
			"Prefix Added",
			f"{f'Successfully added prefix: `{char}`' if char != ':3' else f'suckess fukly added {char} as ur plefix >:3'}"
		))

	@add.error
	async def add_error(self, ctx: commands.Context, error):
		await handle_common_errors(ctx, error)


	@hybrid_command(
		name='remove',
		aliases=['r'],
		description='Remove a prefix from your personal profile or current server.'
	)
	@app.describe(
		type='Whether to delete the prefix from your personal profile or server',
		pos='The position of the prefix (shown in list command)'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def remove(self, ctx: commands.Context, type: Literal['server', 'user'], pos: int):
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type) # type: ignore
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
		await handle_common_errors(ctx, error)


	@hybrid_command(
		name='list',
		aliases=['l'],
		description='List all the prefixes added to your personal profile or current server.'
	)
	@app.describe(
		type='Whether to list prefixes from your personal profile or current server'
	)
	async def list(self, ctx: commands.Context, type: Literal['server', 'user']):
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type) # type: ignore
		prefixes = data.get("prefix", [])

		if not prefixes:
			default_list = [f"{i}. `{p}`" for i, p in enumerate(config.default_prefix, 1)]
			await ctx.reply(view=Generic(
				"No prefixes found, but there are these you can use:",
				f"{chr(10)}.join(default_list)"
			))
			return

		prefix_list = [f"{i}. `{p}`" for i, p in enumerate(prefixes, 1)]
		await ctx.reply(view=Generic(
			f"Prefix List for {f'This {type.title()}' if type == 'server' else em(ctx.author.display_name)}",
			f"{chr(10).join(prefix_list)}"
		))
