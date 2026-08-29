from typing import Any, Tuple, Iterable

import discord
from discord import app_commands as app

from services.profile import server, user

from ui_templates import Fail


async def resolve_target(interaction: discord.Interaction, scope: str) -> Tuple[Any, int | None]:
	if scope == 'server':
		if not interaction.guild:
			await interaction.response.send_message(view=Fail(
				"Invalid Scope",
				"This command must be used in a server if the scope passed is 'server'."
			))
			return None, None
		return server, interaction.guild.id

	return user, interaction.user.id


def is_dev(devs: Iterable[int]):
	async def predicate(interaction: discord.Interaction) -> bool:
		return any(dev_id == interaction.user.id for dev_id in devs)
	return app.check(predicate)

def is_admin(devs: Iterable[int], compare: tuple[str, str] | None = None):
	async def predicate(interaction: discord.Interaction) -> bool:
		if compare:
			val = getattr(interaction.namespace, compare[0], None)
			if val == compare[1]:
				return True

		user_obj = interaction.user
		perms = getattr(user_obj, "guild_permissions", None)
		is_owner = (user_obj.id == interaction.guild.owner_id if interaction.guild else True)
		is_dev_id = any(user_obj.id == dev_id for dev_id in devs)
		is_administrator = (
			perms.manage_guild or
			perms.administrator
			if perms else False
		)
		return is_owner or is_dev_id or is_administrator
	return app.check(predicate)
