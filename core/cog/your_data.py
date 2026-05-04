import random
from typing            import Literal

import discord
from discord           import app_commands as app
from discord.ext       import commands
from discord.utils import get

from core.lib.utils    import mt, is_admin
from core.wrp.profile  import server, user
from core.ui.template  import Fail, Success, Generic, Confirmation
from meta              import config


class Data(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

	@staticmethod
	async def _check(ctx: commands.Context, type: str) -> bool:
		if type not in ('server', 'user'):
			await ctx.reply(view=Fail(
				"Invalid Type",
				f"Type must be either server or user, and not '{type}'..."
			))
		if type == 'server':
			if not ctx.guild:
				await ctx.reply(view=Fail(
					"Invalid Scope",
					"This command must be used in a server to request server data."
				))
				return False
		return True

	@staticmethod
	async def _handle_missing_perms(ctx):
		return await ctx.reply(view=Fail(
			"Missing Required Permission",
			"You need **Administrator** permissions for that."
		))


	@commands.hybrid_command(
		name='get_my_data',
		aliases=['gmd'],
		description='Get all your data we have stored.'
	)
	@app.describe(
		type='Whether to get your personal user data or the current server data'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def get_my_data(self, ctx: commands.Context, type: Literal['server', 'user']):
		"""
		Gives you all your data we have stored.
		Example: /get_my_data user
		"""
		manager = user if type == 'user' else server
		target_id = ctx.author.id if type == 'user' else getattr(ctx.guild, 'id', None)

		if not await self._check(ctx, type):
			return

		await ctx.interaction.response.defer(ephemeral=True) if ctx.interaction else None

		success, result = await manager.data.get_zip(target_id)

		if not success:
			return await ctx.reply(view=Fail(
				"Erorr",
				result if isinstance(result, str) else "Failed to load data. please report this"
			), ephemeral=True)

		try:
			file = discord.File(result, filename=f"{type}_{target_id}_data.zip")
			await ctx.author.send(view=Generic(
				f"Here is the requested **{type}** data export."
			), file=file)
			await ctx.reply(view=Success(
				"I've sent your data export to your DMs."
			), ephemeral=True)
		except discord.Forbidden:
			await ctx.reply(view=Fail(
				"User Error",
				"I couldn't send you a DM. Please open your privacy settings."
			), ephemeral=True)

	@get_my_data.error
	async def get_my_data_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await self._handle_missing_perms(ctx)


	@commands.hybrid_command(
		name='delete_my_data',
		aliases=['dmd'],
		description='Delete all your data permanently from our storage.'
	)
	@app.describe(
		type='Whether to delete your personal user data or the current server data'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def delete_my_data(self, ctx: commands.Context, type: Literal['server', 'user']):
		"""
		Deletes all your data permanently from our storage. **This process cannot be undone.**
		Example: /delete_my_data user
		"""
		manager = user if type == 'user' else server
		target_id = ctx.author.id if type == 'user' else getattr(ctx.guild 'id', None)

		if not await self._check(ctx, type):
			return

		if not manager.data.exists(target_id):
			await ctx.reply(view=Fail(
				"We couldn't find any data to delete"
			))

		if type == 'user':
			question = mt(
				"Are you sure you want to permanently delete your data?",
				"The AI will forget everything about you. This process cannot be undone."
			)
		else:
			question = mt(
				"Are you sure you want to permanently delete your data?",
				"The AI will forget everything about this server. This process cannot be undone."
			)

		cancel = "Action Aborted"
		if random.random() < 0.5:
			cancel += "\n-# I promise you we don't read your data when we are bored :3"
	
		view = Confirmation(
			question,
			f"Your **{type}** data has been deleted permanently.",
			cancel,
			ctx.author
		)
		await ctx.reply(view=view, ephemeral=True)

		confirmed = await view.wait_for_answer()

		if confirmed:
			await manager.data.delete_permanent(target_id)

	@delete_my_data.error
	async def delete_my_data_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await self._handle_missing_perms(ctx)


async def setup(bot: commands.Bot):
	await bot.add_cog(Data(bot))
