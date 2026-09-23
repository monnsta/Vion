import re
from typing import Literal

import discord
from discord import app_commands as app
from discord.ext import commands

from vion.infrastructure.utils import d, em
from vion.services.blacklist import blacklist
from vion.ui_templates import Generic, Success, Fail, Paginated


class BlacklistGroup(app.Group):
	def __init__(self, bot: commands.Bot):
		super().__init__(
			name="blacklist", description="Manage the global bot blacklist."
		)
		self.bot = bot

	@staticmethod
	def _format_dt(dt_obj):
		if not dt_obj:
			return "Never"
		ts = int(dt_obj.timestamp()) if hasattr(dt_obj, "timestamp") else dt_obj
		return f"<t:{ts}:R>"

	async def _validate_args(
		self, interaction: discord.Interaction, entity_type: str, target_id: str
	) -> int | None:
		if entity_type not in ("user", "server"):
			await interaction.response.send_message(
				view=Fail(
					"Invalid Scope",
					f"Scope must be either 'server' or 'user', not '{entity_type}'.",
				),
				ephemeral=True,
			)
			return None

		cleaned = re.sub(r"\D", "", target_id)
		if not cleaned:
			await interaction.response.send_message(
				view=Fail(
					"Invalid Scope", "Target ID must be a valid integer or mention."
				),
				ephemeral=True,
			)
			return None

		return int(cleaned)

	async def _get_entity_info(
		self, entity_type: str, tid: int
	) -> tuple[str, str | None]:
		label = f"Unknown {entity_type.capitalize()}"
		icon = None

		if entity_type == "user":
			u = self.bot.get_user(tid)
			if not u:
				try:
					u = await self.bot.fetch_user(tid)
				except Exception:
					pass
			if u:
				label = f"**{em(u.name)}** (`{u.id}`)"
				icon = u.avatar.url if u.avatar else None
		else:
			g = self.bot.get_guild(tid)
			if g:
				label = f"**{em(g.name)}** (`{g.id}`)"
				icon = g.icon.url if g.icon else None

		return label, icon

	@app.command(name="add", description="Add a user or server to the blacklist.")
	@app.describe(
		type="Whether this is a user or server",
		target_id="The ID or mention of the user or server",
		duration="Duration (e.g., 7d, 12h, 30m). 0 for permanent",
		reason="Reason for blacklisting",
	)
	async def add(
		self,
		interaction: discord.Interaction,
		type: Literal["user", "server"],
		target_id: str,
		duration: str,
		*,
		reason: str,
	):
		tid = await self._validate_args(interaction, type, target_id)
		if not tid:
			return

		success, msg = await blacklist.add(
			tid, type, interaction.user.id, reason, duration
		)

		if success:
			label, _ = await self._get_entity_info(type, tid)
			await interaction.response.send_message(
				view=Success(
					"Success",
					f"{label} has been added to the blacklist.",
					f"**Reason:** {reason}",
					f"**Duration:** {duration}",
				)
			)
		else:
			await interaction.response.send_message(view=Fail("Failed", msg))

	@app.command(
		name="remove", description="Remove a user or server from the blacklist."
	)
	@app.describe(
		type="Whether this is a user or server",
		target_id="The ID or mention of the user or server",
	)
	async def remove(
		self,
		interaction: discord.Interaction,
		type: Literal["user", "server"],
		target_id: str,
	):
		tid = await self._validate_args(interaction, type, target_id)
		if not tid:
			return

		success, msg = await blacklist.remove(tid, type)

		if success:
			label, _ = await self._get_entity_info(type, tid)
			await interaction.response.send_message(
				view=Success("Success", f"{label} has been removed from the blacklist.")
			)
		else:
			await interaction.response.send_message(view=Fail("Failed", msg))

	@app.command(
		name="edit", description="Edit an already existing blacklisted user or server."
	)
	@app.describe(
		type="Whether this is a user or server",
		target_id="The ID or mention of the user or server",
		new_duration="The modified duration (e.g., 7d, 12h, 30m). 0 for permanent",
		new_reason="The modified reason for the blacklist",
	)
	async def edit(
		self,
		interaction: discord.Interaction,
		type: Literal["user", "server"],
		target_id: str,
		new_duration: str | None = None,
		*,
		new_reason: str | None = None,
	):
		if not new_reason and not new_duration:
			return await interaction.response.send_message(
				view=Fail(
					"Error",
					"You must specify a new reason, a new duration, or both to make edits.",
				)
			)

		tid = await self._validate_args(interaction, type, target_id)
		if not tid:
			return

		success, msg = await blacklist.edit(
			entity_id=tid,
			entity_type=type,
			mod_id=interaction.user.id,
			reason=new_reason,
			duration=new_duration,
		)

		if success:
			label, _ = await self._get_entity_info(type, tid)
			await interaction.response.send_message(
				view=Success("Success", f"Updated blacklist entry for {label}.")
			)
		else:
			await interaction.response.send_message(view=Fail("Failed", msg))

	@app.command(
		name="view", description="Show detailed info about a specific blacklist entry."
	)
	@app.describe(
		type="Whether this is a user or server",
		target_id="The ID or mention of the user or server",
	)
	async def view(
		self,
		interaction: discord.Interaction,
		type: Literal["user", "server"],
		target_id: str,
	):
		tid = await self._validate_args(interaction, type, target_id)
		if not tid:
			return

		success, data = await blacklist.get(tid, type)
		if not success:
			return await interaction.response.send_message(view=Fail(data))

		label, _ = await self._get_entity_info(type, tid)

		await interaction.response.send_message(
			view=Generic(
				f"## Blacklisted {type.capitalize()}",
				f"* **Target:** {label}",
				f"* **Moderator:** <@{data['mod_id']}>",
				f"* **Reason:** {data['reason']}",
				f"* **Created:** {self._format_dt(data.get('created_at'))}",
				f"* **Expires:** {self._format_dt(data.get('expires_at'))}",
			)
		)

	@app.command(name="list", description="List all blacklisted entities.")
	@app.describe(type="Filter by user or server")
	async def list(
		self,
		interaction: discord.Interaction,
		type: Literal["user", "server"] | None = None,
	):
		entries = await blacklist.list_all(type)

		if not entries:
			return await interaction.response.send_message(
				view=Generic(
					"### Global Blacklist", "The blacklist is currently empty."
				)
			)

		results = []
		for e in entries:
			e_type = e["type"].capitalize()
			label, icon = await self._get_entity_info(e["type"], e["id"])

			block = d(f"""
				**{e_type}:** {label}
				* **Moderator:** <@{e["mod_id"]}>
				* **Reason:** {e["reason"]}
				* **Created:** {self._format_dt(e.get("created_at"))}
				* **Expires:** {self._format_dt(e.get("expires_at"))}
			""")
			if icon:
				block = [block, icon]
			results.append(block)

		header = f"## Blacklisted {type.capitalize() + 's' if type else ''}"
		view = Paginated(header=header, items=results, user=interaction.user)
		await interaction.response.send_message(view=view)
		view.message = await interaction.original_response()
