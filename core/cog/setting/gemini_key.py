from typing import Literal

import discord
from discord import app_commands as app
from discord.ext import commands

from core.lib.llm import validate_key
from core.lib.utils import mt, em
from meta import config, emoji

from core.cog.utils import resolve_target, load_settings, HybridGroup, hybrid_command
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
			"This group is used to manage your gemini api keys.",
			"The bot uses these keys when talking to you",
			None,
			mt(
				"## Add:",
				"Add a gemini api key to your personal profile.",
				"Params:",
				"* key: The key from the gemini api",
				"Usage:",
				f"{emoji.warn} **Recommend to use in dms or use as slash commands to keep your key private.**",
				f"* `{self.p}setting gemini_key add *******`",
				f"* `{self.p}s g a *******`",
				f"* {config.cmd.setting.gemini_key.add} `key:` {em('*******')}"
			), None,
			mt(
				"## Remove:",
				"Remove an api key you added from your personal profile.",
				"Params:",
				"* pos: The position of the key, (number showed when you use list command)",
				"Usage:",
				f"* `{self.p}setting gemini_key remove 2`",
				f"* `{self.p}s g r 2`",
				f"* {config.cmd.setting.gemini_key.remove} `pos:` 2"
			), None,
			mt(
				"## List:",
				"List all the api keys of your personal profile.",
				"Usage:",
				f"* `{self.p}setting gemini_key list`",
				f"* `{self.p}s g l`",
				f"* {config.cmd.setting.gemini_key.list}"
			)
		))


	@hybrid_command(
		name='add',
		aliases=['a'],
		description='Add a gemini api key to your personal profile.'
	)
	@app.describe(key='The key from the gemini api')
	async def add(self, ctx: commands.Context, *, key: str):
		type: Literal['server', 'user'] = 'user'
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

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


	@hybrid_command(
		name='remove',
		aliases=['r'],
		description='Remove an api key you added from your personal profile.'
	)
	@app.describe(pos='The position of the key, (number showed when you use list command)')
	async def remove(self, ctx: commands.Context, pos: int):
		type: Literal['server', 'user'] = 'user'
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type) # type: ignore
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


	@hybrid_command(
		name='list',
		aliases=['l'],
		description='List all the api keys of your personal profile.'
	)
	async def list(self, ctx: commands.Context):
		type: Literal['server', 'user'] = 'user'
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
