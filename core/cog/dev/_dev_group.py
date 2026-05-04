from discord.ext       import commands

from core.lib.utils    import is_dev
from core.ui.template  import Fail
from meta              import config


@commands.hybrid_group(
	name='dev',
	aliases=['d'],
	description='Dev commands.'
)
@is_dev(config.dev_ids)
async def dev(ctx: commands.Context):
	"""Group used for dev commands, can't be used by anyone else."""
	if ctx.invoked_subcommand is not None:
		return

	await ctx.reply(view=Fail(
		"Subcommand Missing",
		"Available subcommands:",
		"```",
		"* extension (ex)",
		"* blacklist (bl)",
		"* execute   (e )",
		"```"
	))

@dev.error
async def dev_error(ctx: commands.Context, error):
	if isinstance(error, commands.CheckFailure):
		await ctx.reply(view=Fail(f"Only developers can use this command."))
