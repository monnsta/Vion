import discord
from typing            import Literal

from discord           import app_commands as app
from discord.ext       import commands

from ._setting_group   import setting
from core.lib.llm      import validate_key
from core.lib.utils    import mt, is_admin
from core.wrp.profile  import server, user
from core.ui.template  import Fail, Success, Generic, Confirmation, UnexpectedError
from meta              import config


class GeminiKey(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

	@staticmethod
	async def _check(ctx: commands.Context, type: str, key: str | None = None) -> bool:
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
					"This command must be used in a server to add the key to a server...",
					f"-# ... or do you want to add it in your own profile? in that case use {config.cmd.setting.gemini_key.add} ****** user"
				))
				return False

		if key and not await validate_key(key):
			await ctx.reply(view=Fail(
				"Invalid Api Key",
				"Are you sure thats the correct key and not just random characters?"
			))
			return False

		return True

	@staticmethod
	async def _get_data(manager, target_id: str, type: str) -> dict:
		success, data = await manager.settings.load(target_id)
		if success:
			return data
		return config.settings.get(type)

	@staticmethod
	async def _handle_missing_perms(ctx):
		return await ctx.reply(view=Fail(
			"Missing Required Permission",
			"You need **Administrator** permissions for that."
		))


	@setting.group(
		name='gemini_key',
		aliases=['g'],
		description='Group for key commands.'
	)
	async def gemini_key(self, ctx: commands.Context):
		"""Group for api key handling."""
		if ctx.invoked_subcommand is not None:
			return

		await ctx.reply(view=Fail(
			"Subcommand Missing",
			"Available subcommands:",
			"```",
			"* add    (a)",
			"* remove (r)",
			"* list   (l)",
			"```"
		))


	@gemini_key.command(
		name='add',
		aliases=['a'],
		description='Add a gemini ai key to your personal profile or server.'
	)
	@app.describe(
		key='The key from gemini api',
		type='Whether you want to add the key to your personal profile or the current server'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def add(self, ctx: commands.Context, *, key: str, type: Literal['server', 'user'] = 'user'):
		"""
		Add a gemini api key to your personal profile or the current server.
		Example: /setting gemini_key add ****** user
		"""
		if not await self._check(ctx, type, key):
			return

		if type == 'server':
			manager = server
			target_id = getattr(ctx.guild, 'id', None)
		else:
			manager = user
			target_id = ctx.author.id
		if not target_id:
			return

		data = await self._get_data(manager, str(target_id), type)

		if type == 'user': 
			data["api_keys"].append(key)
		else: 
			data["api_keys"].append({"key": key, "owner": ctx.author.id})

		success = await manager.settings.save(target_id, data)

		if success:
			await ctx.reply(view=Success(
				"Api Key Added",
				f"Your key has been successfully added to your {f'{type} profile' if type == 'user' else type}"
			))
			return
		await ctx.reply(view=UnexpectedError)

	@add.error
	async def add_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await self._handle_missing_perms(ctx)


	@gemini_key.command(
		name='remove',
		aliases=['r'],
		description='Remove an api key you added from your personal profile or the current server.'
	)
	@app.describe(
		pos='The position of the key, (number showed when you use list)',
		type='Whether you want to remove the key from your personal profile or the current server'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def remove(self, ctx: commands.Context, pos: int, type: Literal['server', 'user'] = 'user'):
		"""
		Remove an api key you added to your personal profile or server.
		Example: /setting gemini_key remove 1 user
		"""
		if not await self._check(ctx, type=type):
			return

		if type == 'server':
			manager = server
			target_id = getattr(ctx.guild, 'id', None)
		else:
			manager = user
			target_id = ctx.author.id
		if not target_id:
			return

		data = await self._get_data(manager, str(target_id), type)
		keys = data.get("api_keys", [])

		idx = pos - 1

		if not keys:
			await ctx.reply(view=Fail(
				"No Keys Found",
				"You don't have any keys added, therefore can't remove any"
			))
			return

		if idx < 0 or idx >= len(keys):
			await ctx.reply(view=Fail(
				"Invalid Position",
				f"Position {pos} is out of range. Check the list command for valid positions."
			))
			return

		if type == 'server':
			key_entry = keys[idx]
			if key_entry.get("owner") != ctx.author.id or ctx.guild and ctx.author == ctx.guild.owner:
				await ctx.reply(view=Fail(
					"Permission Denied",
					"You can only remove keys that you added."
				))
				return

		view = Confirmation(
			"Are you sure you want to do this?",
			mt(
				"Api Key Removed",
				f"Successfully removed the key at position **{pos}** from the {type} settings."
			),
			"Action Aborted",
			ctx.author
		)
		message = await ctx.reply(view=view)

		confirmed = await view.wait_for_answer()

		if confirmed:
			keys.pop(idx)
			success = await manager.settings.save(target_id, data)

			if not success:
				await message.edit(view=UnexpectedError)

	@remove.error
	async def remove_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await self._handle_missing_perms(ctx)


	@gemini_key.command(
		name='list',
		aliases=['l'],
		description='List all the api keys of your personal profile or server'
	)
	@app.describe(
		type='Whether you want to list the keys from your personal profile or the current server'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def list(self, ctx: commands.Context, type: Literal['server', 'user'] = 'user'):
		"""
		Lists the Api keys of your personal profile or server in dms (turn you dms on)
		Example: /setting gemini_key list user
		"""
		if not await self._check(ctx, type=type):
			return

		if type == 'server':
			manager = server
			target_id = gtattr(ctx.guild, 'id', None)
		else:
			manager = user
			target_id = ctx.author.id
		if not target_id:
			return

		data = await self._get_data(manager, str(target_id), type)
		keys = data.get("api_keys", [])

		if not keys:
			await ctx.reply(view=Fail(
				"No Keys Found",
				f"There are currently no Gemini API keys registered for this {type}."
			))
			return

		key_lines = []
		for i, entry in enumerate(keys, 1):
			raw_key = entry["key"] if isinstance(entry, dict) else entry
			masked_key = f"{raw_key[:4]}...{raw_key[-4:]}"

			if type == 'server':
				owner = self.bot.get_user(entry.get("owner"))
				owner_name = owner.display_name if owner else f"Unknown ({entry.get('owner')})"
				key_lines.append(f"{i}. `{masked_key}` — Added by **{owner_name}**")
			else:
				key_lines.append(f"{i}. `{masked_key}`")

		view = Generic(
			f"Gemini API Keys ({type.title()})",
			*key_lines,
			f"-# Total keys: {len(keys)}"
		)

		try:
			await ctx.author.send(view=view)
			if ctx.guild:
				await ctx.reply(view=Success(
					"List Sent",
					"I've sent the list of API keys to your DMs to keep the keys and owners private."
				))
		except discord.Forbidden:
			await ctx.reply(view=Fail(
				"User Error",
				"I couldn't send you a DM. Please open your privacy settings."
			))

	@list.error
	async def list_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await self._handle_missing_perms(ctx)


async def setup(bot: commands.Bot):
	await bot.add_cog(GeminiKey(bot))

