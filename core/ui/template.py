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

	if count == 1:
		return "This is not for you."

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
			"Is your 'Enter' key stuck, or is it just your brain?",
			"This button has a restraining order against you."
		])

	if count <= 12:
		return random.choice([
			"OKAY, WE GET IT. YOU CAN CLICK A BUTTON. STOP.",
			"I'm actually going to ignore you if you keep this up.",
			"Is this a joke to you? BECAUSE IT ISN'T TO ME.",
			"GO. AWAY.",
			"System error: User too stubborn. Please uninstall life.",
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

		await interaction.response.send_message(
			view=Fail(msg),
			ephemeral=True
		)
		return False
	return True


class Generic(ui.LayoutView):
	def __init__(self, *messages: str, accent_color: int = 0x00E9FE, sep: str = "\n") -> None:
		super().__init__()
		self.add_item(ui.Container(
			ui.TextDisplay(
				sep.join(messages)
			),
			accent_color=accent_color
		))

def Success(*messages: str, sep: str = "\n") -> Generic:
	return Generic(
		f"### {emoji.checkmark} {sep.join(messages)}",
		accent_color=0x00FEBB
	)

def Fail(*messages: str, sep: str = "\n") -> Generic:
	return Generic(
		f"### {emoji.crossmark} {sep.join(messages)}",
		accent_color=0xFE0065
	)


class Paginated(ui.LayoutView):
	def __init__(self, header: str, items: list[str | list[str]], user: discord.Member | discord.User, accent_color: int = 0xb3e7df, per_page: int = 5, char_limit: int = 1800) -> None:
		super().__init__()
		self.user = user
		self.header = header
		self.raw_items = items
		self.accent_color = accent_color
		self.per_page = per_page
		self.char_limit = char_limit
		self.current_page = 0

		self.pages = self._calculate_pages()
		self.total_pages = len(self.pages)

		self.create_layout()

	def _calculate_pages(self) -> list:
		pages = []
		current_chunk = []
		current_length = len(self.header)

		remaining_items = list(self.raw_items)

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

	def create_layout(self) -> None:
		self.clear_items()

		page_items = self.pages[self.current_page]

		container = ui.Container(
			ui.TextDisplay(self.header),
			ui.Separator(),
			accent_color=self.accent_color
		)

		for text in page_items:
			if isinstance(text, list):
				container.add_item(
					ui.Section(
						ui.TextDisplay(text[0]),
						accessory=ui.Thumbnail(
							media=text[1]
						)
					)
				)
			else:
				container.add_item(ui.TextDisplay(text))
			container.add_item(ui.Separator())

		prev_btn = ui.Button(
			emoji=emoji.arrow_left, 
			style=discord.ButtonStyle.secondary, 
			disabled=(self.current_page == 0)
		)
		prev_btn.callback = self.go_prev

		page_btn = ui.Button(
			label=f"Page {self.current_page + 1} / {self.total_pages}",
			style=discord.ButtonStyle.secondary,
			disabled=True
		)

		next_btn = ui.Button(
			emoji=emoji.arrow_right, 
			style=discord.ButtonStyle.secondary, 
			disabled=(self.current_page >= self.total_pages - 1)
		)
		next_btn.callback = self.go_next

		button_row = ui.ActionRow(
			prev_btn,
			page_btn,
			next_btn
		)
		container.add_item(button_row)
		self.add_item(container)

	async def go_prev(self, interaction: discord.Interaction):
		self.current_page -= 1
		self.create_layout()
		await interaction.response.edit_message(view=self)

	async def go_next(self, interaction: discord.Interaction):
		self.current_page += 1
		self.create_layout()
		await interaction.response.edit_message(view=self)

class Confirmation(ui.LayoutView):
	def __init__(
		self,
		question: str,
		confirm: str,
		cancel: str,
		user: discord.Member | discord.User,
		accent_color: int = 0x00E9FE
	) -> None:
		super().__init__()
		self.confirm_text = confirm
		self.cancel_text = cancel
		self.user = user
		self.value = None
		self._view_finished = asyncio.Future()

		container = ui.Container(
			ui.TextDisplay(f"### {question}"),
			accent_color=accent_color
		)

		confirm_btn = ui.Button(
			emoji=emoji.checkmark,
			style=discord.ButtonStyle.success
		)
		confirm_btn.callback = self.confirm

		cancel_btn = ui.Button(
			emoji=emoji.crossmark,
			style=discord.ButtonStyle.secondary
		)
		cancel_btn.callback = self.cancel

		container.add_item(ui.ActionRow(confirm_btn, cancel_btn))
		self.add_item(container)

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		return await global_interaction_check(interaction, self.user)

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

	async def wait_for_answer(self) -> bool:
		return await self._view_finished


UnexpectedError = Fail(
	"Unexpected Error",
	"An unexpected error occurred. Please report this"
)
