from typing import Literal

import discord
from discord import app_commands as app
from discord.ext import commands

from vion.infrastructure.llm import validate_key
from vion.services.utils import resolve_target, is_admin
from vion.ui_templates import Generic, Success, Fail, UnexpectedError, Confirmation
from vion.config import config

from .utils import load_settings


class GeminiKeyGroup(app.Group):
	def __init__(self, bot: commands.Bot):
		super().__init__(name="gemini_key", description="Manage your Gemini API keys.")
		self.bot = bot

	@app.command(
		name="add",
		description="Add a Gemini API key to your personal profile or current server.",
	)
	@app.describe(
		type="Whether to add the key to your personal profile or current server",
		key="The key from the gemini api",
	)
	@is_admin(config.dev_ids, ("type", "user"))
	async def add(
		self,
		interaction: discord.Interaction,
		type: Literal["server", "user"],
		key: str,
	):
		manager, target_id = await resolve_target(interaction, type)
		if not manager:
			return

		key = key.strip()

		key_validity = await validate_key(key)
		if key_validity is None:
			await interaction.response.send_message(
				view=UnexpectedError, ephemeral=True
			)
			return
		if not key_validity:
			await interaction.response.send_message(
				view=Fail(
					"Invalid API Key",
					"Are you sure that's the correct key and not just random characters?",
				),
				ephemeral=True,
			)
			return

		data = await load_settings(manager, target_id, type)  # type: ignore
		existing_keys = data.get("api_keys", [])

		already_exists = any(
			(k["key"] if isinstance(k, dict) else k) == key for k in existing_keys
		)
		if already_exists:
			await interaction.response.send_message(
				view=Fail(
					"Duplicate Key",
					f"This API key has already been added to this {type}.",
				),
				ephemeral=True,
			)
			return

		if type == "user":
			existing_keys.append(key)
		else:
			existing_keys.append({"key": key, "owner": interaction.user.id})

		data["api_keys"] = existing_keys
		success = await manager.settings.save(target_id, data)

		if success:
			await interaction.response.send_message(
				view=Success(
					"API Key Added",
					f"Your key has been successfully added to your {type} profile.",
				),
				ephemeral=True,
			)
			return
		await interaction.response.send_message(view=UnexpectedError, ephemeral=True)

	@app.command(
		name="remove",
		description="Remove an API key you added from your personal profile or current server.",
	)
	@app.describe(
		type="Whether to delete the key from your personal profile or server",
		pos="The position of the key, (number showed when you use list command)",
	)
	@is_admin(config.dev_ids, ("type", "user"))
	async def remove(
		self,
		interaction: discord.Interaction,
		type: Literal["server", "user"],
		pos: int,
	):
		manager, target_id = await resolve_target(interaction, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)  # type: ignore
		keys = data.get("api_keys", [])

		idx = pos - 1

		if not keys:
			await interaction.response.send_message(
				view=Fail(
					"No Keys Found",
					"You don't have any keys added, therefore can't remove any.",
				),
				ephemeral=True,
			)
			return

		if idx < 0 or idx >= len(keys):
			await interaction.response.send_message(
				view=Fail(
					"Invalid Position",
					f"Position {pos} is out of range. Check the list command for valid positions.",
				),
				ephemeral=True,
			)
			return

		if type == "server":
			key_entry = keys[idx]
			owner_id = key_entry.get("owner") if isinstance(key_entry, dict) else None
			if owner_id != interaction.user.id and (
				interaction.guild and interaction.user != interaction.guild.owner
			):
				await interaction.response.send_message(
					view=Fail(
						"Permission Denied",
						"You can only remove keys that you added, unless you're the server owner.",
					),
					ephemeral=True,
				)
				return

		view = Confirmation(
			"Are you sure you want to do this?",
			f"Successfully removed the key at position **{pos}** from the {type} settings.",
			"Action Aborted",
			interaction.user,
		)
		await interaction.response.send_message(view=view, ephemeral=True)

		confirmed = await view.wait_for_answer()

		if confirmed:
			latest_data = await load_settings(manager, target_id, type)  # type: ignore
			latest_keys = latest_data.get("api_keys", [])

			if idx >= len(latest_keys):
				return

			latest_keys.pop(idx)
			latest_data["api_keys"] = latest_keys
			await manager.settings.save(target_id, latest_data)

	@app.command(
		name="list",
		description="List all the API keys of your personal profile or current server.",
	)
	@app.describe(
		type="Whether to list keys from your personal profile or current server"
	)
	async def list(
		self, interaction: discord.Interaction, type: Literal["server", "user"]
	):
		manager, target_id = await resolve_target(interaction, type)
		if not manager:
			return

		data = await load_settings(manager, target_id, type)  # type: ignore
		keys = data.get("api_keys", [])

		if not keys:
			await interaction.response.send_message(
				view=Fail(
					"No Keys Found",
					f"There are currently no Gemini API keys registered for this {type}.",
				),
				ephemeral=True,
			)
			return

		key_lines = []
		for i, entry in enumerate(keys, 1):
			if isinstance(entry, dict):
				raw_key = entry.get("key", "")
				owner_id = entry.get("owner")
			else:
				raw_key = str(entry)
				owner_id = None

			masked_key = (
				f"{raw_key[:4]}...{raw_key[-4:]}" if len(raw_key) >= 8 else "****"
			)

			if type == "server":
				owner = self.bot.get_user(owner_id) if owner_id else None
				owner_name = owner.display_name if owner else f"Unknown ({owner_id})"
				key_lines.append(f"{i}. `{masked_key}` — Added by **{owner_name}**")
			else:
				key_lines.append(f"{i}. `{masked_key}`")

		view = Generic(
			f"Gemini API Keys ({type.title()})",
			*key_lines,
			f"-# Total keys: {len(keys)}",
		)

		await interaction.response.send_message(view=view, ephemeral=True)
