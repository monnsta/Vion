import discord
from discord  import ui

from meta     import emoji


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
	def __init__(self, header: str, items: list[str | list[str, str]], user: discord.Member, accent_color: int = 0xb3e7df, per_page: int = 5) -> None:
		super().__init__()
		self.user = user
		self.header = header
		self.items = items
		self.accent_color = accent_color
		self.per_page = per_page
		self.current_page = 0
		self.total_pages = (len(items) - 1) // self.per_page + 1

		self.create_layout()

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		if interaction.user.id != self.user.id:
			await interaction.response.send_message(
				view=Fail(f"This is not for you."),
				ephemeral=True
			)
			return False
		return True

	def create_layout(self) -> None:
		self.clear_items()

		start = self.current_page * self.per_page
		end = start + self.per_page
		page_items = self.items[start:end]

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
