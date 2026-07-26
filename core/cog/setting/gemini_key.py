from typing import Literal

import discord
from discord import app_commands as app
from discord.ext import commands

from core.lib.llm import validate_key
from core.lib.utils import mt, em
from meta import config, emoji

from core.cog.utils import resolve_target, load_settings, handle_common_errors, HybridGroup, hybrid_command, is_admin
from core.cog.ui_template import Fail, Success, Generic, Confirmation, UnexpectedError


async def callback(ctx: commands.Context):
	if ctx.invoked_subcommand is None:
		await ctx.reply(view=Fail(
			"Subcommand Missing",
			"Available subcommands:",
			"```",
			"* add    (a)",
			"* remove (r)",
			"* list   (l)",
			"* help   (h)",
			"```"
		))


class GeminiKey(HybridGroup):
	def __init__(self, bot: commands.Bot):
		super().__init__(
			callback,
			name='gemini_key',
			aliases=['g'],
			description='Group for key commands.'
		)
		self.bot = bot
		self.p = config.default_prefix[0]


	@hybrid_command(
		name='help',
		aliases=['h'],
		description='Get help for the gemini_key group.'
	)
	async def help_cmd(self, ctx: commands.Context):
		await ctx.reply(view=Generic(
			"# Gemini Key",
			"This group is used to manage your personal or server gemini api keys.",
			"The bot uses these keys when talking to you",
			None,
			mt(
				"## Add:",
				"Add a gemini api key to your personal profile or current server.",
				"Params:",
				"* type: Whether to add the key to your personal profile or current server (user or server)",
				"* key: The key from the gemini api",
				"Usage:",
				f"{emoji.warn} **Recommend to use in dms or use as slash commands to keep your key private.**",
				f"* `{self.p}setting gemini_key add server *******`",
				f"* `{self.p}s g a server *******`",
				f"* {config.cmd.setting.gemini_key.add} `type:` server `key:` {em('*******')}"
			), None,
			mt(
				"## Remove:",
				"Remove an api key you added from your personal profile or current server.",
				"Params:",
				"* type: Whether to delete the key from your personal profile or server (user or server)",
				"* pos: The position of the key, (number showed when you use list command)",
				"Usage:",
				f"* `{self.p}setting gemini_key remove server 2`",
				f"* `{self.p}s g r server 2`",
				f"* {config.cmd.setting.gemini_key.remove} `type:` server `pos:` 2"
			), None,
			mt(
				"## List:",
				"List all the api keys of your personal profile or current server.",
				"Params:",
				"* type: Whether to list keys from your personal profile or current server (user or server)",
				"Usage:",
				f"* `{self.p}setting gemini_key list server`",
				f"* `{self.p}s g l server`",
				f"* {config.cmd.setting.gemini_key.list} `type:` server"
			)
		))


	@hybrid_command(
		name='add',
		aliases=['a'],
		description='Add a gemini api key to your personal profile or current server.'
	)
	@app.describe(
		type='Whether to add the key to your personal profile or current server',
		key='The key from the gemini api'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def add(self, ctx: commands.Context, type: Literal['server', 'user'], *, key: str):
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		key = key.strip()

		key_validity = await validate_key(key)
		if key_validity is None:
			await ctx.reply(view=UnexpectedError)
			return
		if not key_validity:
			await ctx.reply(view=Fail(
				"Invalid API Key",
				"Are you sure that's the correct key and not just random characters?"
			))
			return

		data = await load_settings(manager, target_id, type) # type: ignore
		existing_keys = data.get("api_keys", [])

		already_exists = any(
			(k["key"] if isinstance(k, dict) else k) == key 
			for k in existing_keys
		)
		if already_exists:
			await ctx.reply(view=Fail(
				"Duplicate Key",
				f"This API key has already been added to this {type}."
			))
			if not ctx.interaction:
				try:
					await ctx.message.delete()
				except (discord.Forbidden, discord.NotFound, discord.HTTPException):
					pass
			return

		if type == 'user':
			existing_keys.append(key)
		else:
			existing_keys.append({"key": key, "owner": ctx.author.id})

		data["api_keys"] = existing_keys
		success = await manager.settings.save(target_id, data)

		if success:
			await ctx.reply(view=Success(
				"API Key Added",
				f"Your key has been successfully added to your {type} profile."
			), ephemeral=True)
			if not ctx.interaction:
				try:
					await ctx.message.delete()
				except (discord.Forbidden, discord.NotFound, discord.HTTPException):
					pass
			return
		await ctx.reply(view=UnexpectedError)

	@add.error
	async def add_error(self, ctx: commands.Context, error):
		await handle_common_errors(ctx, error)


	@hybrid_command(
		name='remove',
		aliases=['r'],
		description='Remove an api key you added from your personal profile or current server.'
	)
	@app.describe(
		type='Whether to delete the key from your personal profile or server',
		pos='The position of the key, (number showed when you use list command)'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def remove(self, ctx: commands.Context, type: Literal['server', 'user'], pos: int):
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type) # type: ignore
		keys = data.get("api_keys", [])

		idx = pos - 1

		if not keys:
			await ctx.reply(view=Fail(
				"No Keys Found",
				f"You don't have any keys added, therefore can't remove any."
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
			owner_id = key_entry.get("owner") if isinstance(key_entry, dict) else None
			if owner_id != ctx.author.id and (ctx.guild and ctx.author != ctx.guild.owner):
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
			latest_data = await load_settings(manager, target_id, type) # type: ignore
			latest_keys = latest_data.get("api_keys", [])

			if idx >= len(latest_keys):
				await message.edit(view=Fail(
					"Action Failed",
					"The list of keys changed while awaiting confirmation. Please try again."
				))
				return

			latest_keys.pop(idx)
			latest_data["api_keys"] = latest_keys
			success = await manager.settings.save(target_id, latest_data)

			if not success:
				await message.edit(view=UnexpectedError)

	@remove.error
	async def remove_error(self, ctx: commands.Context, error):
		await handle_common_errors(ctx, error)


	@hybrid_command(
		name='list',
		aliases=['l'],
		description='List all the api keys of your personal profile or current server.'
	)
	@app.describe(
		type='Whether to list keys from your personal profile or current server'
	)
	async def list(self, ctx: commands.Context, type: Literal['server', 'user']):
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type) # type: ignore
		keys = data.get("api_keys", [])

		if not keys:
			await ctx.reply(view=Fail(
				"No Keys Found",
				f"There are currently no Gemini API keys registered for this {type}."
			))
			return

		key_lines = []
		for i, entry in enumerate(keys, 1):
			if isinstance(entry, dict):
				raw_key = entry.get("key", "")
				owner_id = entry.get("owner")
			else:
				raw_key = str(entry)
				owner_id = None

			masked_key = f"{raw_key[:4]}...{raw_key[-4:]}" if len(raw_key) >= 8 else "****"

			if type == 'server':
				owner = self.bot.get_user(owner_id) if owner_id else None # type: ignore
				owner_name = owner.display_name if owner else f"Unknown ({owner_id})"
				key_lines.append(f"{i}. `{masked_key}` — Added by **{owner_name}**")
			else:
				key_lines.append(f"{i}. `{masked_key}`")

		view = Generic(
			f"Gemini API Keys ({type.title()})",
			*key_lines,
			f"-# Total keys: {len(keys)}"
		)

		if ctx.interaction:
			await ctx.reply(view=view, ephemeral=True)
		else:
			try:
				await ctx.author.send(view=view)
				if ctx.guild: await ctx.reply(view=Success(
					"List Sent",
					"I've sent the list of API keys to your DMs to keep the keys private."
				))
			except discord.Forbidden:
				await ctx.reply(view=Fail(
					"User Error",
					"I couldn't send you a DM. Please change your privacy settings."
				))
