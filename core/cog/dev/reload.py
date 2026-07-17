import asyncio
import sys
import traceback

from discord.ext import commands

from meta import config, emoji, load_config

from core.cog.ui_template import Fail, Success, Generic
from core.cog.utils import HybridGroup, hybrid_command


async def callback(ctx: commands.Context):
	if ctx.invoked_subcommand is None:
		await ctx.reply(view=Fail(
			"Subcommand missing",
			"Available subcommands:",
			"```",
			"config  (c)",
			"process (p)",
			"```"
		))


class Reload(HybridGroup):
	def __init__(self, bot: commands.Bot):
		super().__init__(
			callback,
			name='reload',
			aliases=['r'],
			description='Group for reloading things of the bot.'
		)
		self.bot = bot


	@hybrid_command(
		name='config',
		aliases=['c'],
		description='Reload the config file.'
	)
	async def config(self, ctx: commands.Context):
		original_config = config.to_dict()
		original_emoji = emoji.to_dict()

		try:
			config.clear()
			emoji.clear()

			await load_config(reload=True)

			await asyncio.sleep(1)

			await ctx.reply(view=Success("Successfully reloaded config"))

		except Exception:
			config.clear()
			emoji.clear()
			config.load(original_config)
			emoji.load(original_emoji)

			error_traceback = traceback.format_exc()

			await asyncio.sleep(1)

			await ctx.reply(view=Fail(
				"Failed to Reload Config",
				None,
				"```py",
				error_traceback,
				"```"
			))


	@hybrid_command(
		name='process',
		aliases=['p'],
		description='Reload the entire process.'
	)
	async def process(self, ctx: commands.Context):
		await ctx.reply(view=Generic(
			"## Restarting...",
			"Bot will be unresponsive for a few seconds"
		))

		sys.exit(42) # code for restart
