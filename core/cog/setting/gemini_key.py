from typing                   import Literal

import discord
from discord                  import app_commands as app
from discord.ext              import commands

from core.lib.llm             import validate_key
from core.lib.utils           import mt, is_admin
from core.cog.setting._group  import setting
from core.cog.cog_utils       import resolve_target, load_settings, handle_missing_perms
from core.cog.ui_template     import Fail, Success, Generic, Confirmation, UnexpectedError
from meta                     import config


class GeminiKey(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

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
		type='Whether you want to add the key to your personal profile or the current server',
		key='The key from gemini api'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def add(self, ctx: commands.Context, type: Literal['server', 'user'] = 'user', *, key: str):
		"""
		Add a gemini api key so the bot can use that when it talks to you, keeps it available to you always.
		Example: /setting gemini_key add user ******
		"""
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		key_validity = await validate_key(key)
		if key_validity == None:
			await ctx.reply(view=UnexpectedError)
			return
		if not key_validity:
			await ctx.reply(view=Fail(
				"Invalid API Key",
				"Are you sure that's the correct key and not just random characters?"
			))
			return

		data = await load_settings(manager, target_id, type)

		if type == 'user': 
			data["api_keys"].append(key)
		else: 
			data["api_keys"].append({"key": key, "owner": ctx.author.id})

		success = await manager.settings.save(target_id, data)

		if success:
			await ctx.reply(view=Success(
				"API Key Added",
				f"Your key has been successfully added to your {type} profile."
			))
			return
		await ctx.reply(view=UnexpectedError)

	@add.error
	async def add_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await handle_missing_perms(ctx)


	@gemini_key.command(
		name='remove',
		aliases=['r'],
		description='Remove an api key you added from your personal profile or the current server.'
	)
	@app.describe(
		type='Whether you want to remove the key from your personal profile or the current server',
		pos='The position of the key, (number showed when you use list)'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def remove(self, ctx: commands.Context, type: Literal['server', 'user'] = 'user', pos: int):
		"""
		Remove an added api key from yout personal profile or current server
		Example: /setting gemini_key remove user 1
		"""
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)
		keys = data.get("api_keys", [])

		idx = pos - 1

		if not keys:
			await ctx.reply(view=Fail(
				"No Keys Found",
				"You don't have any keys added, therefore can't remove any."
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
			if key_entry.get("owner") != ctx.author.id and (ctx.guild and ctx.author != ctx.guild.owner):
				await ctx.reply(view=Fail(
					"Permission Denied",
					"You can only remove keys that you added, unless you're the server owner."
				))
				return

		view = Confirmation(
			"Are you sure you want to do this?",
			mt(
				"API Key Removed",
				f"Successfully removed the key at position **{pos}** from the {type} settings."
			),
			"Action Aborted",
			ctx.author
		)
		message = await ctx.reply(view=view)

		confirmed = await view.wait_for_answer()

		if confirmed:
			keys.pop(idx)
			data["api_keys"] = keys
			success = await manager.settings.save(target_id, data)

			if not success:
				await message.edit(view=UnexpectedError)

	@remove.error
	async def remove_error(self, ctx: commands.Context, error):
		if isinstance(error, commands.CheckFailure):
			await handle_missing_perms(ctx)


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
		List all the api keys of your personal profile or current server, they keys are sent to dm, and censored if your not the one that added it
		Example: /setting gemini_key list user
		"""
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)
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
			await handle_missing_perms(ctx)
