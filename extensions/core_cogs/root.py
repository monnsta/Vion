from typing import Literal

import discord
from discord import app_commands as app
from discord.ext import commands

from vion.services.utils import resolve_target, is_admin
from vion.ui_templates import Generic
from vion.config import config

from .ui import ManageDataView, AIStatsView, HelpView


class Root(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

	@app.command(
		name="help",
		description="Access detailed system, setup, behavior guides and command catalogs.",
	)
	async def help_cmd(self, interaction: discord.Interaction):
		view = HelpView(interaction.user)
		await interaction.response.send_message(view=view)

	@app.command(name="link", description="Get direct resource URLs.")
	async def link(self, interaction: discord.Interaction):
		await interaction.response.send_message(
			view=Generic(
				"## Important Links",
				None,
				f"[Bot Invite]( <{config.bot.invite}> ) • [Support Server]( <{config.dev_servers[0].invite}> )",
				f"[Terms]( <https://{config.domain}/terms> ) • [Privacy]( <https://{config.domain}/privacy> )",
			)
		)

	@app.command(
		name="ping",
		description="Check the system response times and API connectivity latency.",
	)
	async def ping(self, interaction: discord.Interaction):
		ws_latency = round(self.bot.latency * 1000)

		t1 = discord.utils.utcnow()
		await interaction.response.send_message(view=Generic("Running diagnostic..."))
		t2 = discord.utils.utcnow()

		rest_latency = round((t2 - t1).total_seconds() * 1000)

		thresholds = [
			(100, "🟢 Optimal"),
			(150, "🟡 Good"),
			(250, "🟠 Minor Latency"),
			(400, "🔴 Slow"),
			(800, "🟤 Very Slow"),
			(float("inf"), "💀 Critically Slow (Running on a potato??)"),
		]

		status = next(text for limit, text in thresholds if ws_latency <= limit)

		guild_count = len(self.bot.guilds)
		user_count = len(self.bot.users)

		await interaction.edit_original_response(
			view=Generic(
				"## Status",
				f"Diagnostic Outcome: {status}",
				None,
				f"* Gateway Pulse (WS): `{ws_latency}ms`",
				f"* Message Loop (REST): `{rest_latency}ms`",
				None,
				f"-# Guilds: {guild_count:,} • Users: {user_count:,}",
			)
		)

	@app.command(
		name="stats",
		description="View detailed statistics regarding AI interaction counts and rankings.",
	)
	@app.describe(
		target="The scope of the stats you want to view initially.",
		user="Optional user to check stats for.",
		leaderboard_target="Select whether to view top users or top servers (if target is leaderboard).",
		leaderboard_scope="Select whether to view global or local rankings (if targeting users).",
	)
	async def stats(
		self,
		interaction: discord.Interaction,
		target: Literal["global", "server", "user", "leaderboard"] = "global",
		user: discord.User | None = None,
		leaderboard_target: Literal["servers", "users"] = "servers",
		leaderboard_scope: Literal["global", "local"] = "global",
	):
		view = AIStatsView(
			interaction,
			default_target=target,
			user_target=user,
			lb_target=leaderboard_target,
			lb_scope=leaderboard_scope,
		)
		await view.start(interaction)

	@app.command(
		name="manage_data",
		description="Manage, export, or wipe your custom stored data.",
	)
	@app.describe(
		type="Whether to manage your personal user data or the current server data"
	)
	@is_admin(config.dev_ids, ("type", "user"))
	async def manage_data(
		self, interaction: discord.Interaction, type: Literal["server", "user"]
	):
		manager, target_id = await resolve_target(interaction, type)
		if not (manager and target_id):
			return

		view = ManageDataView(interaction, manager, target_id, type)
		await interaction.response.send_message(view=view, ephemeral=True)
		view.message = await interaction.original_response()
