import discord
from discord import ui

from vion.config import emoji
from .base import TimeoutView, global_interaction_check
from .modal import GotoModal


class Paginated(TimeoutView):
	def __init__(
		self,
		header: str,
		items: list[str | list[str]],
		user: discord.Member | discord.User,
		accent_color: int = 0xB3E7DF,
		per_page: int = 5,
		char_limit: int = 1800,
		jump_threshold: int = 8,
		timeout: float = 180.0,
	) -> None:
		super().__init__(timeout=timeout)
		self.header = header
		self.raw_items = items
		self.user = user
		self.accent_color = accent_color
		self.per_page = per_page
		self.char_limit = char_limit
		self.jump_threshold = jump_threshold
		self.current_page = 0
		self.is_timed_out = False

		self.pages = self._calculate_pages()
		self.total_pages = len(self.pages)

		self.create_layout()

	def _calculate_pages(self) -> list:
		pages = []
		current_length = len(self.header)
		remaining_items = list(self.raw_items)
		current_chunk = []

		while remaining_items:
			item = remaining_items.pop(0)
			text_content = item[0] if isinstance(item, list) else item
			item_len = len(text_content)

			if item_len > self.char_limit:
				trunc_limit = self.char_limit - 30
				cut_pos = text_content.rfind(" ", 0, trunc_limit)
				if cut_pos == -1:
					cut_pos = trunc_limit

				part_one = text_content[:cut_pos] + "... goto next page."
				part_two = text_content[cut_pos:].strip()

				if isinstance(item, list):
					remaining_items.insert(0, [part_two, item[1]])
					item = [part_one, item[1]]
				else:
					remaining_items.insert(0, part_two)
					item = part_one
				item_len = len(part_one)

			if (
				len(current_chunk) >= self.per_page
				or (current_length + item_len) > self.char_limit
			):
				if current_chunk:
					pages.append(current_chunk)
					current_chunk = []
					current_length = len(self.header)

			current_chunk.append(item)
			current_length += item_len

		if current_chunk:
			pages.append(current_chunk)

		return pages or [[]]

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		return await global_interaction_check(interaction, self.user)

	async def on_timeout(self) -> None:
		self.is_timed_out = True
		await super().on_timeout()

	def create_layout(self) -> None:
		self.clear_items()
		page_items = self.pages[self.current_page]

		if self.header != "":
			container = ui.Container(
				ui.TextDisplay(self.header),
				ui.Separator(),
				accent_color=self.accent_color,
			)
		else:
			container = ui.Container(accent_color=self.accent_color)

		for text in page_items:
			if isinstance(text, list):
				container.add_item(
					ui.Section(
						ui.TextDisplay(text[0]), accessory=ui.Thumbnail(media=text[1])
					)
				)
			else:
				container.add_item(ui.TextDisplay(text))
			container.add_item(ui.Separator())

		disabled_by_timeout = getattr(self, "is_timed_out", False)

		prev_btn = ui.Button(
			emoji=emoji.arrow_left,
			style=discord.ButtonStyle.secondary,
			disabled=disabled_by_timeout or (self.current_page == 0),
		)
		prev_btn.callback = self.go_prev

		page_btn = ui.Button(
			label=f"Page {self.current_page + 1} / {self.total_pages}",
			style=discord.ButtonStyle.secondary,
			disabled=True,
		)

		next_btn = ui.Button(
			emoji=emoji.arrow_right,
			style=discord.ButtonStyle.secondary,
			disabled=disabled_by_timeout or (self.current_page >= self.total_pages - 1),
		)
		next_btn.callback = self.go_next

		container.add_item(ui.ActionRow(prev_btn, page_btn, next_btn))

		if self.total_pages > self.jump_threshold:
			first_btn = ui.Button(
				emoji=emoji.double_arrow_left,
				style=discord.ButtonStyle.secondary,
				disabled=disabled_by_timeout or (self.current_page == 0),
			)
			first_btn.callback = self.go_first

			goto_btn = ui.Button(
				label="Goto",
				style=discord.ButtonStyle.secondary,
				disabled=disabled_by_timeout,
			)
			goto_btn.callback = self.open_goto

			last_btn = ui.Button(
				emoji=emoji.double_arrow_right,
				style=discord.ButtonStyle.secondary,
				disabled=disabled_by_timeout
				or (self.current_page >= self.total_pages - 1),
			)
			last_btn.callback = self.go_last

			container.add_item(ui.ActionRow(first_btn, goto_btn, last_btn))

		self.add_item(container)

	async def go_prev(self, interaction: discord.Interaction):
		self.current_page -= 1
		self.create_layout()
		await interaction.response.edit_message(view=self)

	async def go_next(self, interaction: discord.Interaction):
		self.current_page += 1
		self.create_layout()
		await interaction.response.edit_message(view=self)

	async def go_first(self, interaction: discord.Interaction):
		self.current_page = 0
		self.create_layout()
		await interaction.response.edit_message(view=self)

	async def open_goto(self, interaction: discord.Interaction):
		await interaction.response.send_modal(GotoModal(self))

	async def go_last(self, interaction: discord.Interaction):
		self.current_page = self.total_pages - 1
		self.create_layout()
		await interaction.response.edit_message(view=self)
