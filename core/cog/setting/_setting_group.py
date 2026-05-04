from discord.ext       import commands

from core.ui.template  import Fail


@commands.hybrid_group(
	name='setting',
	aliases=['s'],
	description='Setting commands.'
)
async def setting(ctx: commands.Context):
	if ctx.invoked_subcommand is not None:
		return

	await ctx.reply(view=Fail(
		"Subcommand Missing",
		"Available subcommands:",
		"```",
		"* view         (v)",
		"* freewill     (f)",
		"* show_loading (s)",
		"* chatbot_only (c)",
		"",
		"* prefix       (p)",
		"* gemini_key   (g)",
		"* instructions (i)"
		"```"
	))
