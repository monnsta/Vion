from typing import Literal

import discord
from discord import app_commands as app
from discord.ext import commands

from meta import config, emoji

from core.cog.utils import resolve_target, handle_common_errors, is_admin
from core.cog.ui_template import Generic
from core.cog.root.ui import ManageDataView


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
			f"[Bot Invite]( <{config.bot.invite}> ) • [Support Server]( <{config.dev_servers[0][2]}> )",
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

		lower_limit = 50
		upper_limit = 250

		if ws_latency < lower_limit:
			status = "🟢 Stable"
		else:
			severity = min((ws_latency - lower_limit) / (upper_limit - lower_limit), 1.0)

			thresholds = (
				(0.4, "🟡 Slow"),
				(0.8, "🟠 Very Slow"),
				(1.0, "🔴 Critically Slow (Running on a potato??)")
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
		name='manage_data',
		aliases=['m'],
		description='Manage or delete all your stored data.'
	)
	@app.describe(
		type='Whether to manage your personal user data or the current server data'
	)
	@is_admin(config.dev_ids, ('type', 'user'))
	async def manage_data(self, ctx: commands.Context, type: Literal['server', 'user']):
		manager, target_id = await resolve_target(ctx, type)
		if not manager:
			return

		view = ManageDataView(ctx, manager, target_id, type) # type: ignore
		message = await ctx.reply(view=view, ephemeral=True)
		view.message = message

	@manage_data.error
	async def manage_data_error(self, ctx: commands.Context, error):
		await handle_common_errors(ctx, error)
