from typing import Literal

import discord
from discord import app_commands as app
from discord.ext import commands

from meta import config, emoji

from core.cog.utils import resolve_target, is_admin
from core.cog.ui_template import Generic
from core.cog.root.ui import ManageDataView, AIStatsView


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
				f"# Meet {config.bot.name}\n"
				f"{config.bot.name} isn't a traditional Discord bot with a fixed list of commands. "
				"It's an AI member that can naturally chat, help with tasks, moderate "
				"your server, and interact with Discord much like another member would. "
				"Instead of memorizing commands, you can simply tell it what you want.\n\n"
				"Whether it's cleaning up only spam messages across every channel, "
				"answering questions, organizing your server, or performing complex "
				f"multi-step tasks, {config.bot.name} figures out how to accomplish the goal for you.\n\n"
				f"## {emoji.warn} Safety\n"
				"Administrative actions are never based solely on what regular members "
				f"say. {config.bot.name} follows Discord's permission hierarchy and only performs "
				"privileged actions when they're requested by someone who actually has "
				"the required authority. While extensive safeguards are built in, AI "
				"can still make mistakes, so granting only the permissions you intend "
				"it to use is recommended."
			),
			None,
			f"# Talk to {config.bot.name}",
			"You can start a conversation in several ways:",
			f"* Mention the bot (e.g. `<@{config.bot.id}>`)",
			f"* Reply to one of {config.bot.name}'s messages",
			f"* Say its name anywhere in your message (e.g. `Hey {config.bot.name}, can you help?`)",
			f"* Or simply wait for {config.bot.name} to join the conversation on its own (if free will is enabled).",
			None,
			"# Commands",
			"Examples:",
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
		aliases=['pi'],
		description='Check the bots responsiveness.'
	)
	async def ping(self, ctx: commands.Context):
		ws_latency = round(self.bot.latency * 1000)

		t1 = discord.utils.utcnow()
		msg = await ctx.reply(view=Generic("Running diagnostic..."))
		t2 = discord.utils.utcnow()

		rest_latency = round((t2 - t1).total_seconds() * 1000)

		thresholds = [
			(100, "🟢 Optimal"),
			(150, "🟡 Good"),
			(250, "🟠 Minor Latency"),
			(400, "🔴 Slow"),
			(800, "🟤 Very Slow"),
			(float('inf'), "💀 Critically Slow (Running on a potato??)")
		]

		status = next(text for limit, text in thresholds if ws_latency <= limit)

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
		name='stats',
		aliases=['st'],
		description='View detailed AI activity statistics.'
	)
	@app.describe(
		target='The scope of the stats you want to view initially.',
		user='Optional user to check stats for.'
	)
	async def stats(self, ctx: commands.Context, target: Literal['global', 'server', 'user', 'leaderboard'] = 'global', user: discord.User | discord.Member | None = None):
		view = AIStatsView(ctx, default_target=target, user_target=user)
		message = await view.start()
		view.message = message


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
