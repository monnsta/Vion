import asyncio
from typing import Literal

import discord
from discord import app_commands as app
from discord.ext import commands

from vion.infrastructure.exec_code import Code, status
from vion.services.utils import is_dev
from vion.services.extensions import map_command_mentions
from vion.services.memory import global_stm, guild_stm, user_stm
from vion.ui_templates import Success, Fail, Paginated
from vion.config import config, storage

from .blacklist import BlacklistGroup
from .extension import ExtensionGroup
from .reload import ReloadGroup


class DevRoot(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.dev_only = True

		self.blacklist_group = BlacklistGroup(self.bot)
		self.extension_group = ExtensionGroup(self.bot)
		self.reload_group = ReloadGroup(self.bot)

		self.dev.add_command(self.blacklist_group)
		self.dev.add_command(self.extension_group)
		self.dev.add_command(self.reload_group)

	dev = app.Group(name="dev", description="Developer maintenance utilities.")

	@dev.command(
		name="send", description="Send a message to the current channel as the bot."
	)
	@app.describe(message="The message you want to send")
	@is_dev(config.dev_ids)
	async def send(self, interaction: discord.Interaction, *, message: str):
		if not interaction.channel or isinstance(
			interaction.channel, (discord.ForumChannel, discord.CategoryChannel)
		):
			await interaction.response.send_message(
				view=Fail("Cannot send messages directly to this channel type."),
				ephemeral=True,
			)
			return

		await interaction.response.defer(ephemeral=True)

		try:
			await interaction.channel.send(message)
			await interaction.followup.send(
				view=Success("Message dispatched."), ephemeral=True
			)
		except discord.Forbidden:
			await interaction.followup.send(
				view=Fail("Missing permissions to send messages in this channel."),
				ephemeral=True,
			)

	@dev.command(
		name="code", description="Execute python code inside a secure sandbox."
	)
	@app.describe(code="The code to execute")
	@is_dev(config.dev_ids)
	async def code(self, interaction: discord.Interaction, *, code: str):
		await interaction.response.defer()

		initial_view = Paginated(
			header="**Execution Initializing**",
			items=["**Status:** Preparing execution..."],
			user=interaction.user,
			accent_color=0x7289DA,
		)
		await interaction.followup.send(view=initial_view)
		msg = await interaction.original_response()
		initial_view.message = msg

		runner = Code(code)

		def format_live_block(text: str, limit: int = 800) -> str:
			if not text:
				return ""
			text = str(text)
			if len(text) > limit:
				text = f"... (earlier output truncated)\n{text[-(limit - 35) :]}"
			return f"```py\n{text}\n```"

		def chunk_for_pagination(
			title: str, text: str, chunk_size: int = 1500
		) -> list[str]:
			if not text:
				return []
			text = str(text)

			if len(text) <= chunk_size:
				return [f"**{title}:**\n```py\n{text}\n```"]

			chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
			return [
				f"**{title} ({i + 1}/{len(chunks)}):**\n```py\n{chunk}\n```"
				for i, chunk in enumerate(chunks)
			]

		try:
			await runner.execute(
				timeout=30.0, message=interaction.message, bot=self.bot
			)

			async def update_live_output():
				last_content = ""
				try:
					while runner.data.status in (status.PENDING, status.RUNNING):
						data = runner.get_output()

						output_parts = []
						if data.logs:
							output_parts.append(
								f"**Logs:**\n{format_live_block(data.logs, 500)}"
							)

						content = (
							"\n".join(output_parts) if output_parts else "Executing..."
						)

						if content != last_content:
							try:
								live_view = Paginated(
									header=f"**Execution Status: {data.status}**",
									items=[content],
									user=interaction.user,
									accent_color=0x7289DA,
								)
								await msg.edit(view=live_view)
								live_view.message = msg
								last_content = content
							except Exception:
								pass

						await asyncio.sleep(2.0)
				except asyncio.CancelledError:
					pass

			updater_task = asyncio.create_task(update_live_output())

			data = await runner.wait()
			updater_task.cancel()

			items = []
			if data.logs:
				items.extend(chunk_for_pagination("Logs", data.logs))

			if data.error:
				items.extend(chunk_for_pagination("Error", data.error))
			if data.result is not None:
				items.extend(chunk_for_pagination("Result", data.result))

			if not items:
				items.append(
					"**Result:**\n```py\nCode executed silently with no output.\n```"
				)

			is_success = data.status == status.COMPLETED
			header = f"**Execution {runner.execution_id} {'Successful' if is_success else data.status}**"
			color = 0x43B581 if is_success else 0xF04747

			view = Paginated(
				header=header, items=items, user=interaction.user, accent_color=color
			)

			view.current_page = view.total_pages - 1
			view.create_layout()

			await msg.edit(view=view)
			view.message = msg

		except Exception as e:
			view = Paginated(
				header="**Execution Setup Failed**",
				items=[f"**Error:**\n```py\n{str(e)}\n```"],
				user=interaction.user,
				accent_color=0xF04747,
			)
			await msg.edit(view=view)
			view.message = msg

	@dev.command(
		name="update",
		description="Synchronize local code structures with Discord Application Commands.",
	)
	@app.describe(spec="The sync scope: global, dev, or clear.")
	@is_dev(config.dev_ids)
	async def update(
		self, interaction: discord.Interaction, spec: Literal["global", "dev", "clear"]
	):
		await interaction.response.defer()
		if spec == "global":
			synced = await self.bot.tree.sync()
			map_command_mentions(synced, self.bot)

			await interaction.followup.send(
				view=Success(
					"Success", f"Synced {len(synced)} global application commands."
				)
			)
		elif spec == "dev":
			dev_guilds = [discord.Object(id=g_id) for g_id in config.dev_server_ids]
			total = 0
			for guild in dev_guilds:
				try:
					synced = await self.bot.tree.sync(guild=guild)
					map_command_mentions(synced, self.bot)
					total += len(synced)
				except discord.HTTPException:
					pass

			await interaction.followup.send(
				view=Success(
					"Success",
					f"Synced {total} application commands across dev servers.",
				)
			)
		elif spec == "clear":
			self.bot.tree.clear_commands(guild=interaction.guild)
			await self.bot.tree.sync(guild=interaction.guild)

			await interaction.followup.send(
				view=Success(
					"Success", "Cleared and synced this guild's local tree commands."
				)
			)

	@dev.command(
		name="clearstm",
		description="Recursively clean all global, server, and member short-term memory files.",
	)
	@is_dev(config.dev_ids)
	async def clearstm(self, interaction: discord.Interaction):
		await interaction.response.defer()

		global_cleared = await global_stm.clear(0)

		guild_count = 0
		if storage.dirs.guilds.exists():
			for server_dir in storage.dirs.guilds.iterdir():
				if server_dir.is_dir() and server_dir.name.isdigit():
					guild_id = int(server_dir.name)
					if await guild_stm.clear(guild_id):
						guild_count += 1

		user_count = 0
		if storage.dirs.users.exists():
			for user_dir in storage.dirs.users.iterdir():
				if user_dir.is_dir() and user_dir.name.isdigit():
					user_id = int(user_dir.name)
					if await user_stm.clear(user_id):
						user_count += 1

		description = [
			f"**Global STM:** {'Cleared' if global_cleared else 'Failed / Empty'}",
			f"**Guilds Cleared:** {guild_count}",
			f"**Users Cleared:** {user_count}",
		]

		await interaction.followup.send(
			view=Success("STM Successfully Cleared Everywhere", *description)
		)
