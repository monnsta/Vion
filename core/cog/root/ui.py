import random
from typing import cast

import discord
from discord import ui

from core.wrp.trackers import activity
from meta import config, emoji

from core.cog.ui_template import TimeoutView, Fail, Success, Confirmation, global_interaction_check, Paginated
from core.cog.root.utils import generate_timeline_graph


ALLOWED_DOMAINS = {"cdn.discordapp.com", "media.discordapp.net"}


class HelpSelect(ui.Select):
	def __init__(self):
		options = [
			discord.SelectOption(label="Overview & Chatting", value="overview", description="How to interact with the AI companion."),
			discord.SelectOption(label="Gemini API Key Setup", value="gemini", description="Configuring personal custom LLM credentials."),
			discord.SelectOption(label="Custom Instructions", value="instructions", description="Guiding personality and channel boundaries."),
			discord.SelectOption(label="Interactive Mini-Games", value="games", description="Elemental RPS and adaptive Tic-Tac-Toe."),
			discord.SelectOption(label="Data & Statistics", value="data", description="Exporting or deleting database logs and activity stats.")
		]
		super().__init__(placeholder="Select a category to view detailed info...", min_values=1, max_values=1, options=options)

	async def callback(self, interaction: discord.Interaction):
		view = cast("HelpView", self.view)
		val = self.values[0]
		content = view.get_category_content(val)
		await interaction.response.edit_message(content=content, view=view)

class HelpView(TimeoutView):
	def __init__(self, user: discord.User | discord.Member):
		super().__init__(timeout=300.0)
		self.user = user
		self.current_category = "overview"
		
		self.select = HelpSelect()
		self.select.callback = self.on_select_category
		
		self._build_container()

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		return await global_interaction_check(interaction, self.user)

	def _build_container(self) -> None:
		for opt in self.select.options:
			opt.default = (opt.value == self.current_category)

		content = self.get_category_content(self.current_category)

		container = ui.Container(
			ui.TextDisplay(content),
			accent_color=0x00E9FE
		)
		container.add_item(ui.ActionRow(self.select))

		self.clear_items()
		self.add_item(container)

	async def on_select_category(self, interaction: discord.Interaction):
		self.current_category = self.select.values[0]
		self._build_container()
		await interaction.response.edit_message(view=self)

	def get_category_content(self, category: str) -> str:
		match category:
			case "overview": return (
				f"# Meet {config.bot.name}\n"
				f"{config.bot.name} is an AI member that lives inside your Discord server, remembers your community, understands natural language, and can perform complex tasks by reasoning about what you actually want.\n\n"
				"Instead of learning dozens of commands, you simply ask.\n\n"
				"* \"Delete only the spam messages from Alice across every channel, but leave anything that isn't spam.\"\n"
				"* \"Summarize everything that happened while I was asleep.\"\n"
				"* \"Make a role called Verified and give it to everyone who joined this month.\"\n"
				f"{config.bot.name} figures out how to accomplish the task while respecting your server's permission hierarchy.\n\n"
				"### How to Start a Conversation:\n"
				f"* **Mentions:** Ping the bot (<@{config.bot.id}>) inside any channel.\n"
				f"* **Replies:** Reply directly to any message sent by {config.bot.name}.\n"
				f"* **Direct Invocation:** Simply use its name (`{config.bot.name}`) inside active chat channels.\n"
				f"* **Free Will:** If allowed, {config.bot.name} can join ongoing conversations entirely on its own!\n\n"
				"### Permissions & Safety:\n"
				"The bot implements strict administrative controls, adhering entirely to Discord's hierarchy. "
				"Moderation actions are executed only when requested by authorized administrators."
			)
			case "gemini": return (
				"# Gemini API Key Configuration\n"
				"The bot supports personal API keys, enabling unlimited, private AI models.\n\n"
				"### How to Obtain an API Key:\n"
				"1. Go to **[Google AI Studio](https://aistudio.google.com/)**.\n"
				"2. Sign in with your Google Account.\n"
				"3. Click on the **Get API Key** button on the top sidebar.\n"
				"4. Click **Create API Key**, select an active Cloud project, and copy the string.\n"
				f"5. Execute {config.cmd.get('setting.gemini_key.add')} to submit it. **Keys are treated with zero logs and are completely hidden from other users.**\n\n"
				"### Available Subcommands:\n"
				f"* {config.cmd.get('setting.gemini_key.add')} — Add your secret key. Keys are automatically validated before saving.\n"
				f"* {config.cmd.get('setting.gemini_key.remove')} — Remove a saved key from your registry by position.\n"
				f"* {config.cmd.get('setting.gemini_key.list')} — View your obfuscated credentials."
			)
			case "instructions": return (
				"# Custom AI Behavior Guidelines\n"
				"You can shape the bot's communication patterns, rules, restrictions, and behaviors directly.\n"
				"This is a legacy feature and not really used anymore, you as the server owner can tailer the bot's behavior by requesting it directly.\n\n"
				"### Instructions Setup:\n"
				f"* **Set Instructions:** Execute {config.cmd.get('setting.instruction.set')}. If you leave the text blank, the bot prompts an interactive editor modal with your previous instructions.\n"
				f"* **View Guidelines:** Inspect currently saved parameters utilizing {config.cmd.get('setting.instruction.view')}.\n"
				f"* **Clear Configuration:** Erase active guidelines via {config.cmd.get('setting.instruction.delete')}.\n\n"
				"### Best Practices:\n"
				"Provide concrete instructions such as 'Speak concisely', 'Always use lowercase', or 'Do not reply to messages in general'. "
				"The engine is built to evaluate guidelines alongside system contextual files."
			)
			case "games": return (
				"# Interactive Mini-Games\n"
				"Challenge other server members or play against an adaptive AI algorithm.\n\n"
				"### Elemental Rock-Paper-Scissors:\n"
				f"* Initiate a game via {config.cmd.get('fun.rps')}. Choose elements representing the Avatar nations:\n"
				f"  - **Water** over Fire & Earth\n"
				f"  - **Earth** over Fire & Air\n"
				f"  - **Fire** over Air\n"
				f"  - **Air** over Water\n\n"
				"### Classic & Advanced Tic-Tac-Toe:\n"
				f"* Launch via {config.cmd.get('fun.tictactoe')}. Select from classic 3x3 grids or a complex 6x7 board. "
				"Challenge other members, or test your skills against our custom minimax bot (just select vion as opponent or any other bot)."
			)
			case "data": return (
				"# Data Security & Statistics\n"
				"You have full control over all personal data stored by the bot.\n\n"
				"### Management Utilities:\n"
				f"* **Data Dashboard:** Access the secure panel utilizing {config.cmd.get('manage_data')} to export backup files or trigger permanent deletions.\n"
				f"* **Interactions Stats:** Run {config.cmd.get('stats')} to render interaction graphs, leaderboard ranks, and server standings."
			)
			case _: return "Select a category below to explore details."


class RestoreDataModal(ui.Modal, title="Restore Data Backup"):
	uploaded_file = ui.Label(
		text="Backup ZIP",
		description="Upload the ZIP file you previously exported.",
		component=ui.FileUpload(
			custom_id="data_backup_zip",
			min_values=1,
			max_values=1,
			required=True
		)
	)

	def __init__(self, manager, target_id: int):
		super().__init__()
		self.manager = manager
		self.target_id = target_id

	async def on_submit(self, interaction: discord.Interaction):
		await interaction.response.defer(ephemeral=True)

		if self.manager.entity_type == "user" and self.target_id != interaction.user.id:
			return await interaction.followup.send(
				view=Fail("Restore Failed", "Unauthorized target profile."),
				ephemeral=True
			)

		upload = cast(ui.FileUpload, self.uploaded_file.component)

		if not upload.values:
			return await interaction.followup.send(
				view=Fail("Restore Failed", "No file was received."),
				ephemeral=True
			)

		attachment = upload.values[0]
		filename = attachment.filename

		if not filename.lower().endswith(".zip"):
			return await interaction.followup.send(
				view=Fail(
					"Invalid File",
					"Please upload a valid `.zip` backup file."
				),
				ephemeral=True
			)

		if attachment.size > config.max_restore_file_size:
			return await interaction.followup.send(
				view=Fail(
					"Restore Failed",
					"File size exceeds the configured limit."
				),
				ephemeral=True
			)

		try:
			zip_bytes = await attachment.read()
		except discord.HTTPException:
			return await interaction.followup.send(
				view=Fail(
					"Restore Failed",
					"Failed to download the uploaded file."
				),
				ephemeral=True
			)

		success, result = await self.manager.data.restore_zip(
			self.target_id,
			zip_bytes
		)

		if success:
			await interaction.followup.send(
				view=Success("Restore Complete", result),
				ephemeral=True
			)
		else:
			await interaction.followup.send(
				view=Fail("Restore Failed", result),
				ephemeral=True
			)

class ManageDataView(TimeoutView):
	def __init__(self, interaction: discord.Interaction, manager, target_id: int, data_type: str):
		super().__init__()
		self.interaction = interaction
		self.manager = manager
		self.target_id = target_id
		self.data_type = data_type
		self.user = interaction.user

		container = ui.Container(
			ui.TextDisplay(f"### Manage {data_type.title()} Data"),
			ui.TextDisplay("Choose whether to export, restore, or permanently delete your data."),
			accent_color=0x00E9FE
		)

		export_btn = ui.Button(label="Export Data", style=discord.ButtonStyle.primary)
		export_btn.callback = self.export_data

		restore_btn = ui.Button(label="Restore Data", style=discord.ButtonStyle.secondary)
		restore_btn.callback = self.restore_data

		delete_btn = ui.Button(label="Delete Data", style=discord.ButtonStyle.danger)
		delete_btn.callback = self.delete_data

		container.add_item(ui.ActionRow(export_btn, restore_btn, delete_btn))
		self.add_item(container)

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		return await global_interaction_check(interaction, self.user)

	async def export_data(self, interaction: discord.Interaction):
		await interaction.response.defer(ephemeral=True)
		success, result = await self.manager.data.get_zip(self.target_id)

		if not success:
			return await interaction.followup.send(view=Fail(
				"Error",
				result if isinstance(result, str) else "Failed to load data. Please report this."
			), ephemeral=True)

		try:
			file = discord.File(result, filename=f"{self.data_type}_{self.target_id}_data.zip")
			await self.user.send(file=file)
			await interaction.followup.send(view=Success("I've sent your data export to your DMs."), ephemeral=True)
		except discord.Forbidden:
			await interaction.followup.send(view=Fail(
				"User Error",
				"I couldn't send you a DM. Please open your privacy settings."
			), ephemeral=True)

	async def restore_data(self, interaction: discord.Interaction):
		await interaction.response.send_modal(RestoreDataModal(self.manager, self.target_id))

	async def delete_data(self, interaction: discord.Interaction):
		if not await self.manager.data.exists(self.target_id):
			return await interaction.response.send_message(view=Fail("We couldn't find any data to delete."), ephemeral=True)

		if self.data_type == 'user':
			question = "Are you sure you want to permanently delete your data?\nThe AI will forget everything about you. This process cannot be undone."
		else:
			question = "Are you sure you want to permanently delete your data?\nThe AI will forget everything about this server. This process cannot be undone."

		cancel = "Action Aborted"
		if random.random() < 0.5:
			cancel += "\n-# I promise you we don't read your data when we are bored"

		view = Confirmation(
			question,
			f"Your **{self.data_type}** data has been deleted permanently.",
			cancel,
			self.user
		)
		await interaction.response.send_message(view=view, ephemeral=True)

		confirmed = await view.wait_for_answer()

		if confirmed:
			await self.manager.data.delete_permanent(self.target_id)


class AIStatsView(Paginated):
	def __init__(self, interaction: discord.Interaction, default_target: str, user_target: discord.User | discord.Member | None = None, lb_target: str = 'servers', lb_scope: str = 'global'):
		self.interaction = interaction
		self.current_target = default_target
		self.user_target = user_target
		self.current_timeframe = "1"
		self.lb_target = lb_target
		self.lb_scope = lb_scope
		self.file = None
		self.non_lb_content = ""

		self.target_select = ui.Select(
			placeholder="Select scope to view stats...",
			options=[
				discord.SelectOption(label="Global Stats", value="global", description="Server-wide AI metrics"),
				discord.SelectOption(label="Server Stats", value="server", description="Metrics for this server"),
				discord.SelectOption(label="User Stats", value="user", description="Your or someone else's metrics"),
				discord.SelectOption(label="Leaderboard", value="leaderboard", description="Top interaction rankings")
			]
		)
		self.target_select.callback = self.change_target

		self.timeframe_select = ui.Select(
			placeholder="Select timeframe...",
			options=[
				discord.SelectOption(label="Last 24 Hours", value="1", description="Activity in the last 24 hours"),
				discord.SelectOption(label="Last 7 Days", value="7", description="Activity in the last 7 days"),
				discord.SelectOption(label="Last 30 Days", value="30", description="Activity in the last 30 days"),
				discord.SelectOption(label="All Time", value="all", description="All recorded activity")
			]
		)
		self.timeframe_select.callback = self.change_timeframe

		self.lb_target_select = ui.Select(
			placeholder="Select leaderboard type...",
			options=[
				discord.SelectOption(label="Servers", value="servers", description="Top communities"),
				discord.SelectOption(label="Users", value="users", description="Most active users")
			]
		)
		self.lb_target_select.callback = self.change_lb_target

		self.lb_scope_select = ui.Select(
			placeholder="Select user scope...",
			options=[
				discord.SelectOption(label="Global", value="global", description="Across all servers"),
				discord.SelectOption(label="Local", value="local", description="Only in this server")
			]
		)
		self.lb_scope_select.callback = self.change_lb_scope

		self.refresh_btn = ui.Button(emoji=emoji.refresh, style=discord.ButtonStyle.secondary)
		self.refresh_btn.callback = self.refresh_stats

		super().__init__(header="", items=[], user=interaction.user, accent_color=0x00E9FE, per_page=10, jump_threshold=8, timeout=180.0)

	async def start(self, interaction: discord.Interaction) -> None:
		await self._fetch_and_update()
		self.create_layout()
		
		if self.file:
			await interaction.response.send_message(view=self, file=self.file)
		else:
			await interaction.response.send_message(view=self)
		self.message = await interaction.original_response()

	async def _fetch_and_update(self):
		for opt in self.target_select.options:
			opt.default = (opt.value == self.current_target)
		for opt in self.timeframe_select.options:
			opt.default = (opt.value == self.current_timeframe)
		for opt in self.lb_target_select.options:
			opt.default = (opt.value == self.lb_target)
		for opt in self.lb_scope_select.options:
			opt.default = (opt.value == self.lb_scope)

		self.file = None

		if self.current_target == 'leaderboard':
			if self.lb_target == 'servers':
				top_guilds = await activity.get_leaderboard('guild', 100)
				guild_lines = []
				bot = self.interaction.client
				for idx, (g_id, count) in enumerate(top_guilds, 1):
					guild_obj = bot.get_guild(int(g_id))
					name = guild_obj.name if guild_obj else f"Server {g_id}"
					guild_lines.append(f"{idx}. **{name}**\n-# `{count:,}` interactions")
				self.header = "## AI Leaderboard\nTop performing communities across the network."
				self.raw_items = guild_lines if guild_lines else ["*No data yet*"]
			else:
				if self.lb_scope == 'local' and self.interaction.guild:
					top_users = await activity.get_leaderboard('user', 2000)
					user_lines = []
					idx = 1
					for u_id, count in top_users:
						member = self.interaction.guild.get_member(int(u_id))
						if member:
							user_lines.append(f"{idx}. **{member.display_name}**\n-# `{count:,}` interactions")
							idx += 1
							if idx > 100: break
					self.header = f"## AI Leaderboard\nMost active users in **{self.interaction.guild.name}**."
					self.raw_items = user_lines if user_lines else ["*No data yet*"]
				else:
					top_users = await activity.get_leaderboard('user', 100)
					user_lines = []
					bot = self.interaction.client
					for idx, (u_id, count) in enumerate(top_users, 1):
						user_obj = bot.get_user(int(u_id))
						name = user_obj.display_name if user_obj else f"User {u_id}"
						user_lines.append(f"{idx}. **{name}**\n-# `{count:,}` interactions")
					self.header = "## AI Leaderboard\nMost active users across the network."
					self.raw_items = user_lines if user_lines else ["*No data yet*"]

			self.pages = self._calculate_pages()
			self.total_pages = len(self.pages)
			self.current_page = 0
		else:
			if self.current_timeframe == "all":
				timeframe_days = None
			elif self.current_timeframe == "1":
				timeframe_days = 1
			else:
				timeframe_days = int(self.current_timeframe)

			if self.current_target == 'global':
				stats = await activity.get_stats('global')
				interactions = stats.get('interactions', 0)
				timeline = stats.get('timeline', {})
				self.non_lb_content = (
					"## Global AI Statistics\n"
					"Server-wide usage overview.\n\n"
					"> **Total Interactions**\n"
					f"> ## `{interactions:,}`"
				)
				buf = generate_timeline_graph(timeline, "Global Interactions Over Time", timeframe_days)
				self.file = discord.File(buf, filename="chart.png")

			elif self.current_target == 'server':
				if not self.interaction.guild:
					self.non_lb_content = "### Server Stats\nCannot fetch server stats in DMs."
					self.file = None
					return
				stats = await activity.get_stats('guild', self.interaction.guild.id)
				interactions = stats.get('interactions', 0)
				rank = stats.get('rank', 0)
				timeline = stats.get('timeline', {})
				self.non_lb_content = (
					f"## Server Statistics: {self.interaction.guild.name}\n"
					"Current server standing and activity metrics.\n\n"
					"> **Total Interactions** · **Leaderboard Rank**\n"
					f"> ## `{interactions:,}` `#{rank:,}`"
				)
				buf = generate_timeline_graph(timeline, "Server Interactions Over Time", timeframe_days)
				self.file = discord.File(buf, filename="chart.png")

			else:
				target = self.user_target or self.interaction.user
				stats = await activity.get_stats('user', target.id)
				interactions = stats.get('interactions', 0)
				rank = stats.get('rank', 0)
				timeline = stats.get('timeline', {})
				self.non_lb_content = (
					f"## User Statistics: {target.display_name}\n"
					"Individual activity metrics and global standing.\n\n"
					f"> **Total Interactions** · **Leaderboard Rank**\n"
					f"> ## `{interactions:,}` `#{rank:,}`"
				)
				buf = generate_timeline_graph(timeline, "User Interactions Over Time", timeframe_days)
				self.file = discord.File(buf, filename="chart.png")

	def create_layout(self) -> None:
		self.clear_items()
		if self.current_target == 'leaderboard':
			super().create_layout()
			
			container = cast(ui.Container, self.children[0])
			container.add_item(ui.ActionRow(self.target_select))
			container.add_item(ui.ActionRow(self.lb_target_select))
			
			if self.lb_target == 'users':
				container.add_item(ui.ActionRow(self.lb_scope_select))
		else:
			container_elements: list[ui.TextDisplay | ui.MediaGallery] = [ui.TextDisplay(self.non_lb_content)]
			
			if self.file:
				container_elements.append(
					ui.MediaGallery(discord.MediaGalleryItem(media=self.file))
				)

			container = ui.Container(*container_elements, accent_color=self.accent_color)
			container.add_item(ui.ActionRow(self.target_select))
			container.add_item(ui.ActionRow(self.timeframe_select))
			container.add_item(ui.ActionRow(self.refresh_btn))
			self.add_item(container)

	async def change_target(self, interaction: discord.Interaction):
		self.current_target = self.target_select.values[0]
		await self._fetch_and_update()
		self.create_layout()
		attachments = [self.file] if self.file else []
		await interaction.response.edit_message(view=self, attachments=attachments)

	async def change_timeframe(self, interaction: discord.Interaction):
		self.current_timeframe = self.timeframe_select.values[0]
		await self._fetch_and_update()
		self.create_layout()
		attachments = [self.file] if self.file else []
		await interaction.response.edit_message(view=self, attachments=attachments)

	async def change_lb_target(self, interaction: discord.Interaction):
		self.lb_target = self.lb_target_select.values[0]
		await self._fetch_and_update()
		self.create_layout()
		await interaction.response.edit_message(view=self, attachments=[])

	async def change_lb_scope(self, interaction: discord.Interaction):
		self.lb_scope = self.lb_scope_select.values[0]
		await self._fetch_and_update()
		self.create_layout()
		await interaction.response.edit_message(view=self, attachments=[])

	async def refresh_stats(self, interaction: discord.Interaction):
		await self._fetch_and_update()
		self.create_layout()
		attachments = [self.file] if self.file else []
		await interaction.response.edit_message(view=self, attachments=attachments)
