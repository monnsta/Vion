import random
from typing import Literal

import discord
from discord import app_commands as app
from discord.ext import commands

from core.lib.utils import mt, is_admin
from meta import config, emoji

from core.cog.utils import resolve_target, handle_common_errors
from core.cog.ui_template import Generic, Fail, Success, Confirmation


class Root(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

	@commands.hybrid_command(
		name='help',
		aliases=['h'],
		description='Help command.'
	)
	async def help(self, ctx: commands.Context):
		components = [
			(
				"# Introduction:\n"
				"This AI agent is integrated directly with the Discord API, "
				"granting it the capability to manage messages, channels, "
				"roles, and members. To ensure security, the bot executes "
				"commands based on a hierarchy: it prioritizes Server "
				"Owners and Administrators, while verifying specific "
				"permissions for other users (e.g., a user must have "
				"'Timeout Members' permissions to request a timeout).\n\n"
				f"## {emoji.warn} Disclaimer:\n"
				"While robust security measures are in place, AI can be "
				"unpredictable. Use at your own discretion and consider "
				"restricting high-level permissions like 'Administrator'.\n"
			),
			None,
			"# Communication:",
			"You can talk with the AI by...",
			f"* Mentioning the bot (e.g., \"<@{config.bot.id}>\")",
			"* Replying to the bot's message with ping on",
			f"* Having the bots name anywhere in your message (e.g., \"Hello, {config.bot.name}\")",
			"* Waiting for the bot to talk with you",
			None,
			"# Commands:",
			"Use the dedicated command group's help command to know more.",
			"Example:",
			f"* `{config.default_prefix[0]}setting help` | `{config.default_prefix[0]}s h` | {config.cmd.setting.help}",
			f"* `{config.default_prefix[0]}setting prefix add user !` | `{config.default_prefix[0]}s p a user !` | {config.cmd.setting.prefix.add} `type:` user `char:` !"
		]

		def format_cmds(cmd_list):
			lines = []
			for cmd in sorted(cmd_list, key=lambda c: c.name):
				if cmd.hidden:
					continue
				alias_str = f"({cmd.aliases[0].center(3)})" if cmd.aliases else ""
				lines.append(f"* {cmd.name:<18} {alias_str}".rstrip())
			return "```\n" + "\n".join(lines) + "\n```" if lines else None

		root_cmds = [c for c in self.bot.commands if not isinstance(c, commands.Group) and not c.hidden]
		if root_cmds:
			formatted_root = format_cmds(root_cmds)
			if formatted_root:
				components.append(formatted_root)
				components.append(None)

		def walk_groups(group_cmds, level=2):
			for group in sorted(group_cmds, key=lambda c: c.name):
				if group.hidden:
					continue

				aliases = " | ".join(f"`{a}`" for a in group.aliases)
				alias_display = f" | {aliases}" if aliases else ""

				components.append(f"{'#' * level} {group.name.capitalize()} (`{group.name}`{alias_display})")

				sub_cmds = [c for c in group.commands if not isinstance(c, commands.Group)]
				if sub_cmds:
					formatted_sub = format_cmds(sub_cmds)
					if formatted_sub:
						components.append(formatted_sub)

				sub_groups = [c for c in group.commands if isinstance(c, commands.Group)]
				if sub_groups:
					walk_groups(sub_groups, level + 1)

				if level == 2:
					components.append(None)

		groups = [c for c in self.bot.commands if isinstance(c, commands.Group) and not c.hidden and c.name != 'dev']
		walk_groups(groups)

		components.append(f"-# By using this bot, you agree to our [Terms of Service]( <https://{config.domain}/terms> ) & [Privacy Policy]( <https://{config.domain}/privacy> )")

		final_components = []
		for comp in components:
			if comp is None:
				if not final_components or final_components[-1] is None:
					continue
			final_components.append(comp)

		await ctx.reply(view=Generic(*final_components))


	@commands.hybrid_command(
		name='link',
		aliases=['l'],
		description='Get important links.'
	)
	async def link(self, ctx: commands.Context):
		await ctx.reply(view=Generic(
			"## Important Links",
			None,
			f"[Bot Invite]( <{config.bot.invite}> ) • [Suppprt Server]( <{config.dev_servers[0][2]}> )",
			f"[Terms]( <https://{config.domain}/terms> ) • [Privacy]( <https://{config.domain}/privacy> )"
		))


	@commands.hybrid_command(
		name='ping',
		aliases=['p'],
		description='Check the bots responsiveness.'
	)
	async def ping(self, ctx: commands.Context):
		ws_latency = round(self.bot.latency * 1000)

		t1 = discord.utils.utcnow()
		msg = await ctx.reply(view=Generic("Running diagnostic..."))
		t2 = discord.utils.utcnow()
		rest_latency = round((t2 - t1).total_seconds() * 1000)

		total_latency = ws_latency + rest_latency
		lower_limit = 150
		upper_limit = 450

		if total_latency < lower_limit:
			status = "🟢 Stable"
		else:
			severity = (total_latency - lower_limit) / (upper_limit - lower_limit)

			thresholds = (
				(0.3, "🟡 Slow"),
				(0.7, "🟠 Very Slow"),
				(float('inf'), "🔴 Critically Slow (Running on a potato??)")
			)

			status = next(text for limit, text in thresholds if severity <= limit)

		guild_count = len(self.bot.guilds)
		user_count = len(self.bot.users)

		await msg.edit(view=Generic(
			"## Status",
			f"{status}",
			None,
			f"* Gateway Pulse (WS): `{ws_latency}ms`",
			f"* Message Loop (REST): `{rest_latency}ms`",
			None,
			f"-# Guilds: {guild_count:,} • Users: {user_count:,}"
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
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		if ctx.interaction:
			await ctx.interaction.response.defer(ephemeral=True)

		success, result = await manager.data.get_zip(target_id)

		if not success:
			return await ctx.reply(view=Fail(
				"Error",
				result if isinstance(result, str) else "Failed to load data. Please report this."
			), ephemeral=True)

		try:
			file = discord.File(result, filename=f"{type}_{target_id}_data.zip")
			await ctx.author.send(file=file)
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
		await handle_common_errors(ctx, error)


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
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		if not await manager.data.exists(target_id):
			await ctx.reply(view=Fail("We couldn't find any data to delete."))
			return

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
		await handle_common_errors(ctx, error)
