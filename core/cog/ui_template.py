import asyncio
import random
from collections import Counter

import discord
from discord import ui

from meta import emoji

INTERFERENCE_TRACKER = Counter()

def get_annoyance_message(user_id: int) -> str | None:
	INTERFERENCE_TRACKER[user_id] += 1
	count = INTERFERENCE_TRACKER[user_id]
	if count == 1: return "This is not for you."
	if count == 2:
		return random.choice([
			"Are you dumb? I told you this is not for you.",
			"Again? It's still not for you.",
			"Reading is a great skill to learn. Try it.",
			"Error 403: Forbidden. (And also annoying)."
		])
	if count <= 6:
		return random.choice([
			"Seriously? Stop clicking it.",
			"You're starting to get on my nerves.",
			"Do you have nothing better to do?",
			"Clicking this won't make it yours. Trust me.",
			"I'm busy. Talk to the hand. ✋",
			"Every time you click, a pixel dies. Think of the pixels.",
			"This button has a restraining order against you."
		])
	if count <= 12:
		return random.choice([
			"OKAY, WE GET IT. YOU CAN CLICK A BUTTON. STOP.",
			"I'm actually going to ignore you if you keep this up.",
			"Is this a joke to you? BECAUSE IT ISN'T TO ME.",
			"GO. AWAY.",
			"I have 14 million futures and in none of them do you own this menu.",
			"Your persistence is admirable. Your intelligence? Not so much.",
			"I’m reporting this to the Bot Council.",
			"Do you want a medal for being annoying? Because you're winning.",
			"Loading 'Reasons to care'... 0% complete."
		])
	return None

async def global_interaction_check(interaction: discord.Interaction, target_user: discord.Member | discord.User) -> bool:
	if interaction.user.id != target_user.id:
		msg = get_annoyance_message(interaction.user.id)
		if msg is None:
			if not interaction.response.is_done():
				await interaction.response.defer(ephemeral=True)
			return False
		await interaction.response.send_message(view=Fail(msg), ephemeral=True)
		return False
	return True


class TimeoutView(ui.LayoutView):
	def __init__(self, timeout: float = 180.0):
		super().__init__(timeout=timeout)
		self.message: discord.Message | None = None

	async def on_timeout(self) -> None:
		if not self.message:
			return

		for child in list(self.children):
			if isinstance(child, ui.Container):
				for sub_child in list(child.children):
					if isinstance(sub_child, ui.ActionRow):
						for component in sub_child.children:
							if hasattr(component, "disabled"):
								setattr(component, "disabled", True)
					elif hasattr(sub_child, "disabled"):
						setattr(sub_child, "disabled", True)
			elif hasattr(child, "disabled"):
				setattr(child, "disabled", True)

		if hasattr(self, "create_layout"):
			getattr(self, "create_layout")()

		try:
			await self.message.edit(view=self)
		except discord.HTTPException:
			pass


class Generic(TimeoutView):
	def __init__(self, *messages: str | None, accent_color: int | None = 0x00E9FE, sep: str = "\n", timeout: float = 180.0) -> None:
		super().__init__(timeout=timeout)
		if accent_color:
			container = ui.Container(accent_color=accent_color)
		else:
			container = ui.Container()

		text_buffer = []

		def flush_buffer():
			if text_buffer:
				container.add_item(ui.TextDisplay(sep.join(text_buffer)))
				text_buffer.clear()

		for item in messages:
			if item is None:
				flush_buffer()
				container.add_item(ui.Separator())
			else:
				text_buffer.append(item)

		flush_buffer()
		self.add_item(container)

def Success(title: str, *messages: str | None, sep: str = "\n") -> Generic:
	return Generic(f"### {emoji.checkmark} {title}", *messages, accent_color=0x00FEBB, sep=sep)

def Fail(title: str, *messages: str | None, sep: str = "\n") -> Generic:
	return Generic(f"### {emoji.crossmark} {title}", *messages, accent_color=0xFE0065, sep=sep)


class GotoModal(ui.Modal):
	def __init__(self, view: "Paginated"):
		super().__init__(title="Jump to Page")
		self.view_ref = view
		self.page_input = ui.TextInput(
			label=f"Page Number (1-{view.total_pages})",
			style=discord.TextStyle.short,
			default=str(view.current_page + 1),
			required=True
		)
		self.add_item(self.page_input)

	async def on_submit(self, interaction: discord.Interaction):
		try:
			page = int(self.page_input.value) - 1
			if 0 <= page < self.view_ref.total_pages:
				self.view_ref.current_page = page
				self.view_ref.create_layout()
				await interaction.response.edit_message(view=self.view_ref)
			else:
				await interaction.response.send_message(view=Fail("Error", "Invalid page number."), ephemeral=True)
		except ValueError:
			await interaction.response.send_message(view=Fail("Error", "Please enter a valid number."), ephemeral=True)

class Paginated(TimeoutView):
	def __init__(self, header: str, items: list[str | list[str]], user: discord.Member | discord.User, accent_color: int = 0xb3e7df, per_page: int = 5, char_limit: int = 1800, jump_threshold: int = 8, timeout: float = 180.0) -> None:
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
				if cut_pos == -1: cut_pos = trunc_limit

				part_one = text_content[:cut_pos] + "... goto next page."
				part_two = text_content[cut_pos:].strip()

				if isinstance(item, list):
					remaining_items.insert(0, [part_two, item[1]])
					item = [part_one, item[1]]
				else:
					remaining_items.insert(0, part_two)
					item = part_one
				item_len = len(part_one)

			if len(current_chunk) >= self.per_page or (current_length + item_len) > self.char_limit:
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
			container = ui.Container(ui.TextDisplay(self.header), ui.Separator(), accent_color=self.accent_color)
		else:
			container = ui.Container(accent_color=self.accent_color)

		for text in page_items:
			if isinstance(text, list):
				container.add_item(ui.Section(ui.TextDisplay(text[0]), accessory=ui.Thumbnail(media=text[1])))
			else:
				container.add_item(ui.TextDisplay(text))
			container.add_item(ui.Separator())

		disabled_by_timeout = getattr(self, "is_timed_out", False)

		prev_btn = ui.Button(emoji=emoji.arrow_left, style=discord.ButtonStyle.secondary, disabled=disabled_by_timeout or (self.current_page == 0))
		prev_btn.callback = self.go_prev

		page_btn = ui.Button(label=f"Page {self.current_page + 1} / {self.total_pages}", style=discord.ButtonStyle.secondary, disabled=True)

		next_btn = ui.Button(emoji=emoji.arrow_right, style=discord.ButtonStyle.secondary, disabled=disabled_by_timeout or (self.current_page >= self.total_pages - 1))
		next_btn.callback = self.go_next

		container.add_item(ui.ActionRow(prev_btn, page_btn, next_btn))

		if self.total_pages > self.jump_threshold:
			first_btn = ui.Button(emoji=emoji.double_arrow_left, style=discord.ButtonStyle.secondary, disabled=disabled_by_timeout or (self.current_page == 0))
			first_btn.callback = self.go_first

			goto_btn = ui.Button(label="Goto", style=discord.ButtonStyle.secondary, disabled=disabled_by_timeout)
			goto_btn.callback = self.open_goto

			last_btn = ui.Button(emoji=emoji.double_arrow_right, style=discord.ButtonStyle.secondary, disabled=disabled_by_timeout or (self.current_page >= self.total_pages - 1))
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


class Confirmation(TimeoutView):
	def __init__(self, question: str, confirm: str, cancel: str, user: discord.Member | discord.User, accent_color: int = 0x00E9FE, timeout: float = 180.0) -> None:
		super().__init__(timeout=timeout)
		self.confirm_text = confirm
		self.cancel_text = cancel
		self.user = user
		self.value = None
		self._view_finished = asyncio.Future()

		container = ui.Container(ui.TextDisplay(f"### {question}"), accent_color=accent_color)

		confirm_btn = ui.Button(emoji=emoji.checkmark, style=discord.ButtonStyle.success)
		confirm_btn.callback = self.confirm

		cancel_btn = ui.Button(emoji=emoji.crossmark, style=discord.ButtonStyle.secondary)
		cancel_btn.callback = self.cancel

		container.add_item(ui.ActionRow(confirm_btn, cancel_btn))
		self.add_item(container)

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		return await global_interaction_check(interaction, self.user)

	async def on_timeout(self) -> None:
		if not self._view_finished.done():
			self._view_finished.set_result(None)
		await super().on_timeout()

	async def confirm(self, interaction: discord.Interaction):
		self.value = True
		self._view_finished.set_result(True)
		self.stop()
		await interaction.response.edit_message(view=Success(self.confirm_text))

	async def cancel(self, interaction: discord.Interaction):
		self.value = False
		self._view_finished.set_result(False)
		self.stop()
		await interaction.response.edit_message(view=Fail(self.cancel_text))

	async def wait_for_answer(self) -> bool | None:
		return await self._view_finished


class TextInputModal(ui.Modal):
	def __init__(self, title: str, field_label: str, default_value: str | None, future: asyncio.Future):
		super().__init__(title=title)
		self.future = future
		self.input_field = ui.TextInput(label=field_label, style=discord.TextStyle.paragraph, default=default_value, required=True)
		self.add_item(self.input_field)

	async def on_submit(self, interaction: discord.Interaction):
		if not self.future.done():
			self.future.set_result(self.input_field.value)
		await interaction.response.defer()

class TextForm(Generic):
	def __init__(
		self,
		message_content: str,
		button_label: str,
		modal_title: str,
		field_label: str,
		default_field_value: str | None = None,
		user: discord.Member | discord.User | None = None,
		accent_color: int = 0x00E9FE,
		timeout: float = 180.0
	) -> None:
		super().__init__(message_content, accent_color=accent_color, timeout=timeout)
		self.user = user
		self.modal_title = modal_title
		self.field_label = field_label
		self.default_field_value = default_field_value

		self.result_future = asyncio.Future()

		container = self.children[0]
		btn = ui.Button(label=button_label, style=discord.ButtonStyle.primary)
		btn.callback = self.open_modal
		getattr(container, "add_item")(ui.ActionRow(btn))

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		if self.user:
			return await global_interaction_check(interaction, self.user)
		return True

	async def on_timeout(self) -> None:
		if not self.result_future.done():
			self.result_future.set_result(None)
		await super().on_timeout()

	async def open_modal(self, interaction: discord.Interaction):
		modal = TextInputModal(title=self.modal_title, field_label=self.field_label, default_value=self.default_field_value, future=self.result_future)
		await interaction.response.send_modal(modal)

	async def wait_for_input(self) -> str | None:
		try:
			return await self.result_future
		except asyncio.CancelledError:
			return None


UnexpectedError = Fail(
	"Unexpected Error",
	"An unexpected error occurred. Please report this"
)
