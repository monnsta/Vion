import asyncio
import random

import discord
from discord import ui

from infrastructure.utils import em
from config import emoji

from ui_templates import (
	TimeoutView,
	get_annoyance_message,
	Generic,
	Fail
)
from .utils import (
	AvatarRPS,
	TicTacToeBot,
	TicTacToeSixBySevenBot
)


class AvatarRPSView(TimeoutView):
	def __init__(self, challenger: discord.User | discord.Member, opponent: discord.User | discord.Member):
		super().__init__(timeout=180.0)
		self.challenger = challenger
		self.opponent = opponent
		self.choices: dict[int, str | None] = {challenger.id: None, opponent.id: None}

		if opponent.bot:
			self.choices[opponent.id] = random.choice(['water', 'earth', 'fire', 'air'])

		self.container = ui.Container(accent_color=0x00E9FE)

		rules_text = (
			"### Avatar RPS\n"
			"Choose your element!\n\n"
			"**Matchup Rules:**\n"
			f"**Water** beats Fire & Earth\n"
			f"**Earth** beats Fire & Air\n"
			f"**Fire** beats Air\n"
			f"**Air** beats Water"
		)
		self.container.add_item(ui.TextDisplay(rules_text))

		row = ui.ActionRow()

		w_btn = ui.Button(label="Water", style=discord.ButtonStyle.secondary, emoji=emoji.avatar_watertribe)
		w_btn.callback = lambda interaction: self.handle_choice(interaction, "water")
		row.add_item(w_btn)

		e_btn = ui.Button(label="Earth", style=discord.ButtonStyle.secondary, emoji=emoji.avatar_earthkingdom)
		e_btn.callback = lambda interaction: self.handle_choice(interaction, "earth")
		row.add_item(e_btn)

		f_btn = ui.Button(label="Fire", style=discord.ButtonStyle.secondary, emoji=emoji.avatar_firenation)
		f_btn.callback = lambda interaction: self.handle_choice(interaction, "fire")
		row.add_item(f_btn)

		a_btn = ui.Button(label="Air", style=discord.ButtonStyle.secondary, emoji=emoji.avatar_airnomad)
		a_btn.callback = lambda interaction: self.handle_choice(interaction, "air")
		row.add_item(a_btn)

		self.container.add_item(row)
		self.add_item(self.container)

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		if interaction.user.id not in (self.challenger.id, self.opponent.id):
			msg = get_annoyance_message(interaction.user.id)
			if msg is None:
				if not interaction.response.is_done():
					await interaction.response.defer(ephemeral=True)
				return False
			await interaction.response.send_message(view=Fail("Not your game", msg), ephemeral=True)
			return False
		return True

	async def handle_choice(self, interaction: discord.Interaction, choice: str):
		if self.choices[interaction.user.id] is not None:
			await interaction.response.send_message("You already made your choice.", ephemeral=True)
			return

		self.choices[interaction.user.id] = choice

		p1_choice = self.choices[self.challenger.id]
		p2_choice = self.choices[self.opponent.id]

		if p1_choice is not None and p2_choice is not None:
			result = AvatarRPS.resolve(p1_choice, p2_choice)

			emoji_map = {
				'water': emoji.avatar_watertribe,
				'earth': emoji.avatar_earthkingdom,
				'fire': emoji.avatar_firenation,
				'air': emoji.avatar_airnomad
			}

			desc = (
				f"**{em(self.challenger.name)}** chose {emoji_map[p1_choice]} {p1_choice.capitalize()}\n"
				f"**{em(self.opponent.name)}** chose {emoji_map[p2_choice]} {p2_choice.capitalize()}\n\n"
			)

			if result == "tie":
				view = Generic("### It's a tie.", desc)
			elif result == "stalemate":
				view = Generic("### Stalemate.", desc + "Neither element holds power over the other.")
			elif result == "p1":
				view = Generic(f"### {self.challenger.display_name} wins.", desc)
			else:
				view = Generic(f"### {self.opponent.display_name} wins.", desc)

			await interaction.response.edit_message(view=view)
			self.stop()
		else:
			await interaction.response.send_message(f"Choice locked: {choice.capitalize()}. Waiting for opponent...", ephemeral=True)


class TicTacToeView(TimeoutView):
	def __init__(self, p1: discord.User | discord.Member, p2: discord.User | discord.Member, bot_client: discord.Client):
		super().__init__(timeout=180.0)
		self.p1 = p1
		self.p2 = p2
		self.bot_client = bot_client
		self.current_player = p1
		self.board: list[str | None] = [None] * 9
		self.marks = {p1.id: 'X', p2.id: 'O'}
		self.emojis = {'X': emoji.char_x, 'O': emoji.char_o}
		self.game_over = False
		self.game_result_text: str | None = None

		self.bot_difficulty: int | None = None
		bot_id = bot_client.user.id if bot_client.user else None

		if self.p2.bot:
			self.bot_difficulty = 2 if self.p2.id == bot_id else random.choice([0, 1, 2])
		elif self.p1.bot:
			self.bot_difficulty = 2 if self.p1.id == bot_id else random.choice([0, 1, 2])

		self.buttons: list[ui.Button] = []

		def make_callback(button: ui.Button, index: int):
			async def callback(interaction: discord.Interaction):
				await self.handle_turn(interaction, button, index)
			return callback

		for y in range(3):
			for x in range(3):
				idx = y * 3 + x
				btn = ui.Button(style=discord.ButtonStyle.secondary, emoji=emoji.char_absolute_empty)
				btn.callback = make_callback(btn, idx)
				self.buttons.append(btn)

		self.create_layout()

	def create_layout(self) -> None:
		self.clear_items()

		container = ui.Container(accent_color=0x00E9FE)

		if self.game_over:
			status_text = f"### Tic-Tac-Toe\n\n{self.game_result_text}"
		else:
			status_text = f"### Tic-Tac-Toe\n\nIt is **{self.current_player.display_name}**'s turn."

		container.add_item(ui.TextDisplay(status_text))
		container.add_item(ui.Separator())

		for y in range(3):
			row = ui.ActionRow()
			for x in range(3):
				idx = y * 3 + x
				row.add_item(self.buttons[idx])
			container.add_item(row)

		self.add_item(container)

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		if interaction.user.id not in (self.p1.id, self.p2.id):
			msg = get_annoyance_message(interaction.user.id)
			if msg is None:
				if not interaction.response.is_done():
					await interaction.response.defer(ephemeral=True)
				return False
			await interaction.response.send_message(view=Fail("Not your game", msg), ephemeral=True)
			return False

		if interaction.user.id != self.current_player.id:
			await interaction.response.send_message(view=Fail("It's not your turn."), ephemeral=True)
			return False

		return True

	async def handle_turn(self, interaction: discord.Interaction, button: ui.Button, idx: int):
		if self.game_over:
			return

		mark = self.marks[self.current_player.id]

		self.board[idx] = mark
		button.emoji = self.emojis[mark]
		button.disabled = True
		button.label = ""

		winner = TicTacToeBot.check_win(self.board)
		if winner:
			await self.end_game(interaction, winner)
			return

		self.current_player = self.p2 if self.current_player == self.p1 else self.p1

		self.create_layout()
		await interaction.response.edit_message(view=self)

		if self.current_player.bot and interaction.message:
			await self.do_bot_turn(interaction.message)

	async def do_bot_turn(self, message: discord.Message):
		await asyncio.sleep(1)

		bot_mark = self.marks[self.current_player.id]
		human_mark = 'X' if bot_mark == 'O' else 'O'

		move_idx = await asyncio.to_thread(
			TicTacToeBot.get_move,
			self.board.copy(),
			bot_mark,
			human_mark,
			self.bot_difficulty if self.bot_difficulty is not None else 2
		)

		if move_idx != -1:
			self.board[move_idx] = bot_mark
			btn = self.buttons[move_idx]
			btn.emoji = self.emojis[bot_mark]
			btn.disabled = True
			btn.label = ""

			winner = TicTacToeBot.check_win(self.board)
			if winner:
				self.game_over = True
				for child in self.buttons:
					child.disabled = True

				if winner == "Tie":
					self.game_result_text = "**It's a tie.**"
				else:
					self.game_result_text = f"**{self.current_player.display_name} wins.**"

				self.create_layout()
				await message.edit(view=self)
				self.stop()
				return

			self.current_player = self.p2 if self.current_player == self.p1 else self.p1
			self.create_layout()
			await message.edit(view=self)

	async def end_game(self, interaction: discord.Interaction, winner: str):
		self.game_over = True
		for child in self.buttons:
			child.disabled = True

		if winner == "Tie":
			self.game_result_text = "**It's a tie.**"
		else:
			winning_player = self.p1 if winner == 'X' else self.p2
			self.game_result_text = f"**{winning_player.display_name} wins.**"

		self.create_layout()
		await interaction.response.edit_message(view=self)
		self.stop()


class SixBySevenTTTModal(ui.Modal):
	def __init__(self, view: "SixBySevenTTTView"):
		super().__init__(title="Make a Move")
		self.view_ref = view

		self.col_input = ui.TextInput(
			label="Column (1-7)",
			style=discord.TextStyle.short,
			required=True,
			max_length=1,
			placeholder="Enter a column number..."
		)
		self.row_input = ui.TextInput(
			label="Row (1-6)",
			style=discord.TextStyle.short,
			required=True,
			max_length=1,
			placeholder="Enter a row number..."
		)

		self.add_item(self.col_input)
		self.add_item(self.row_input)

	async def on_submit(self, interaction: discord.Interaction):
		try:
			row = int(self.row_input.value) - 1
			col = int(self.col_input.value) - 1

			if 0 <= row <= 5 and 0 <= col <= 6:
				await self.view_ref.process_turn(interaction, row, col)
			else:
				await interaction.response.send_message(view=Fail("Invalid Move", "Row must be 1-6 and Column must be 1-7."), ephemeral=True)
		except ValueError:
			await interaction.response.send_message(view=Fail("Invalid Input", "Please enter valid numbers."), ephemeral=True)


class SixBySevenTTTView(TimeoutView):
	def __init__(self, p1: discord.User | discord.Member, p2: discord.User | discord.Member, bot_client: discord.Client):
		super().__init__(timeout=180.0)
		self.p1 = p1
		self.p2 = p2
		self.bot_client = bot_client
		self.current_player = p1
		self.board: list[str | None] = [None] * 42
		self.marks = {p1.id: 'X', p2.id: 'O'}
		self.emojis = {'X': emoji.char_x, 'O': emoji.char_o, None: emoji.char_empty}
		self.game_over = False
		self.game_result_text: str | None = None

		self.bot_difficulty: int | None = None
		bot_id = bot_client.user.id if bot_client.user else None

		if self.p2.bot:
			self.bot_difficulty = 2 if self.p2.id == bot_id else random.choice([0, 1, 2])
		elif self.p1.bot:
			self.bot_difficulty = 2 if self.p1.id == bot_id else random.choice([0, 1, 2])

		self.move_btn = ui.Button(style=discord.ButtonStyle.secondary, label="Place Token")
		self.move_btn.callback = self.prompt_move
		self.buttons = [self.move_btn]

		self.create_layout()

	def render_board(self) -> str:
		res = f"{emoji.char_absolute_empty}{emoji.char_1}{emoji.char_2}{emoji.char_3}{emoji.char_4}{emoji.char_5}{emoji.char_6}{emoji.char_7}\n"

		row_emojis = [
			emoji.char_1, emoji.char_2, emoji.char_3,
			emoji.char_4, emoji.char_5, emoji.char_6
		]

		for r in range(6):
			res += row_emojis[r]
			for c in range(7):
				val = self.board[r * 7 + c]
				res += self.emojis.get(val, emoji.char_empty)
			res += "\n"
		return res

	def create_layout(self) -> None:
		self.clear_items()
		container = ui.Container(accent_color=0x00E9FE)

		if self.game_over:
			status_text = f"### 6x7 Tic-Tac-Toe\n\n{self.game_result_text}"
		else:
			status_text = f"### 6x7 Tic-Tac-Toe\n\nIt is **{self.current_player.display_name}**'s turn."

		board_str = self.render_board()
		container.add_item(ui.TextDisplay(f"{status_text}\n\n{board_str}"))
		container.add_item(ui.Separator())
		container.add_item(ui.ActionRow(self.move_btn))

		self.add_item(container)

	async def interaction_check(self, interaction: discord.Interaction) -> bool:
		if interaction.user.id not in (self.p1.id, self.p2.id):
			msg = get_annoyance_message(interaction.user.id)
			if msg is None:
				if not interaction.response.is_done():
					await interaction.response.defer(ephemeral=True)
				return False
			await interaction.response.send_message(view=Fail("Not your game", msg), ephemeral=True)
			return False

		if interaction.user.id != self.current_player.id:
			await interaction.response.send_message(view=Fail("It's not your turn."), ephemeral=True)
			return False

		return True

	async def prompt_move(self, interaction: discord.Interaction):
		if self.game_over:
			return
		await interaction.response.send_modal(SixBySevenTTTModal(self))

	async def process_turn(self, interaction: discord.Interaction, row: int, col: int):
		if self.game_over: return

		idx = row * 7 + col
		if self.board[idx] is not None:
			await interaction.response.send_message(view=Fail("Space Occupied", "That spot is already taken!"), ephemeral=True)
			return

		mark = self.marks[self.current_player.id]
		self.board[idx] = mark

		winner = TicTacToeSixBySevenBot.check_win(self.board)
		if winner:
			await self.end_game(interaction, winner)
			return

		self.current_player = self.p2 if self.current_player == self.p1 else self.p1
		self.create_layout()
		await interaction.response.edit_message(view=self)

		if self.current_player.bot and interaction.message:
			await self.do_bot_turn(interaction.message)

	async def do_bot_turn(self, message: discord.Message):
		await asyncio.sleep(1)

		bot_mark = self.marks[self.current_player.id]
		human_mark = 'X' if bot_mark == 'O' else 'O'

		move_idx = await asyncio.to_thread(
			TicTacToeSixBySevenBot.get_move,
			self.board.copy(),
			bot_mark,
			human_mark,
			self.bot_difficulty if self.bot_difficulty is not None else 2
		)

		if move_idx != -1:
			self.board[move_idx] = bot_mark

			winner = TicTacToeSixBySevenBot.check_win(self.board)
			if winner:
				self.game_over = True
				for child in self.buttons:
					child.disabled = True

				if winner == "Tie":
					self.game_result_text = "**It's a tie.**"
				else:
					self.game_result_text = f"**{self.current_player.display_name} wins.**"

				self.create_layout()
				await message.edit(view=self)
				self.stop()
				return

			self.current_player = self.p2 if self.current_player == self.p1 else self.p1
			self.create_layout()
			await message.edit(view=self)

	async def end_game(self, interaction: discord.Interaction, winner: str):
		self.game_over = True
		for child in self.buttons:
			child.disabled = True

		if winner == "Tie":
			self.game_result_text = "**It's a tie.**"
		else:
			winning_player = self.p1 if winner == 'X' else self.p2
			self.game_result_text = f"**{winning_player.display_name} wins.**"

		self.create_layout()
		await interaction.response.edit_message(view=self)
		self.stop()
