from typing                   import Literal

from discord                  import app_commands as app
from discord.ext              import commands

from core.lib.utils           import is_admin
from core.wrp.profile         import server
from core.cog.setting._group  import setting
from core.cog.cog_utils       import resolve_target, load_settings, handle_missing_perms
from core.cog.ui_template     import Success, Generic, Confirmation, UnexpectedError
from meta                     import config


class Root(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

	@staticmethod
	async def _update_server_setting(ctx: commands.Context, key: str, value: bool, display_name: str):
		manager, target_id = await resolve_target(ctx, 'server')
		if not manager:
			return

		data = await load_settings(server, ctx.guild.id, "server")
		current_value = data[key]
		target_value = value
		conf_view = None

		if current_value == value:
			target_value = not value
			conf_view = Confirmation(
				f"{display_name} already set to {value}, set to {target_value} instead?",
				f"{display_name} set to {target_value}",
				"Action Aborted",
				ctx.author
			)
			conf_msg = await ctx.reply(view=conf_view)
			
			if not await conf_view.wait_for_answer():
				return

		data[key] = target_value
		success = await server.settings.save(ctx.guild.id, data)

		if not success:
			if conf_view:
				await conf_msg.edit(view=UnexpectedError)
			else:
				await ctx.reply(view=UnexpectedError)
		elif not conf_view:
			await ctx.reply(view=Success(f"{display_name} set to {target_value}"))


	@setting.command(
		name='view',
		aliases=['v'],
		description='View all your personal settings or the current server\'s'
	)
	@app.describe(
		type='Whether to show your personal settings or server settings'
	)
	async def view(self, ctx: commands.Context, type: Literal['server', 'user']):
		"""
		Shows all settings of your personal profile or current server.
		Example: /setting view user
		"""
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)

		await ctx.reply(view=Generic(
			f"Settings for {ctx.guild.name if type == 'server' else ctx.author.display_name}",
			f"**Prefixes:** {' '.join([f'`{p}`' for p in [*data['prefix'], *config.default_prefix]])}",
			f"**Chatbot Mode:** {'Yes' if data.get('chatbot', False) else 'No'}",
			f"**Loading Message:** {'Yes' if data.get('ai_load_message', False) else 'No'}",
			f"**Freewill:** {'Yes' if data.get('free_will', False) else 'No'}",
			f"**Instructions:**\n{data.get('instructions', 'None')}"
		))


	@setting.command(
		name='freewill',
		aliases=['f'],
		description='Toggle free will for the current server'
	)
	@app.describe(
		value='Whether to turn free will on or off (True or False)'
	)
	@app.guild_only
	@is_admin(config.dev_ids)
	async def freewill(self, ctx: commands.Context, value: bool):
		"""
		Toggles freewill value for the current server.
		Example: /setting freewill True
		"""
		await self._update_server_setting(ctx, "free_will", value, "Freewill")

	@freewill.error
	async def freewill_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await handle_missing_perms(ctx)


	@setting.command(
		name='show_loading',
		aliases=['s'],
		description='Toggle AI loading message for the current server'
	)
	@app.describe(
		value='Whether to turn loading message on or off (True or False)'
	)
	@app.guild_only
	@is_admin(config.dev_ids)
	async def show_loading(self, ctx: commands.Context, value: bool):
		"""
		Toggles ai loading message value for the current server.
		Example: /setting show_loading True
		"""
		await self._update_server_setting(ctx, "ai_load_message", value, "Loading Message")

	@show_loading.error
	async def show_loading_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await handle_missing_perms(ctx)


	@setting.command(
		name='chatbot_only',
		aliases=['c'],
		description='Toggle chat bot only mode for the current server'
	)
	@app.describe(
		value='Whether to turn chatbot mode on or off (True or False)'
	)
	@app.guild_only
	@is_admin(config.dev_ids)
	async def chatbot_only(self, ctx: commands.Context, value: bool):
		"""
		Toggles Chatbot Mode value for the current server.
		Example: /setting chatbot_only True
		"""
		await self._update_server_setting(ctx, "chatbot", value, "Chatbot Mode")

	@chatbot_only.error
	async def chatbot_only_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await handle_missing_perms(ctx)


async def setup(bot: commands.Bot):
	await bot.add_cog(Root(bot))
