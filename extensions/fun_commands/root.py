import random
from typing import Literal

import discord
from discord import app_commands as app
from discord.ext import commands

from vion.infrastructure.utils import em
from vion.ui_templates import Fail, Generic

from .ui import AvatarRPSView, TicTacToeView, SixBySevenTTTView


class FunRoot(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot

	fun = app.Group(name="fun", description="Fun and mini-games commands.")

	@fun.command(name="eightball", description="Ask the magic 8-ball a question.")
	@app.describe(question="The question to ask")
	async def eightball(self, interaction: discord.Interaction, *, question: str):
		responses = [
			# Positives
			"It is certain.",
			"It is decidedly so.",
			"Without a doubt.",
			"Yes definitely.",
			"You may rely on it.",
			"As I see it, yes.",
			"Most likely.",
			"Outlook good.",
			"Yes.",
			"Signs point to yes.",
			"Abso-freakin-lutely.",
			"The stars have aligned and they say YES.",
			"Yes, but at what cost?",
			"The walls are whispering YES and they won't stop laughing.",
			"YES, because the skin-walker outside your window nodded.",
			"The kids in my basement say absolutely!",
			# Mid
			"Reply hazy, try again.",
			"Ask again later.",
			"Better not tell you now.",
			"Cannot predict now.",
			"Concentrate and ask again.",
			"My crystal ball is buffering.",
			"Signs point to... wait, I forgot my answer. I got distracted by a shiny rock.",
			"Bold of you to assume the universe cares.",
			"Ask me again and I will leak your search history.",
			"I rolled a dice and it laughed at you.",
			"I can't answer right now, the shadow man is watching me type.",
			"The static in my teeth is too loud to decide.",
			"If I told you, the spiders under your mattress would find out.",
			# Negatives
			"Don't count on it.",
			"My reply is no.",
			"My sources say no.",
			"Outlook not so good.",
			"Very doubtful.",
			"Ha. In your dreams, buddy.",
			"Not in this lifetime.",
			"Outlook looks like a dumpster fire.",
			"The static on the TV says you must suffer a permanent NO.",
			"NO, and the meat in the fridge agrees with me.",
		]

		await interaction.response.send_message(
			view=Generic(
				f"### {random.choice(responses)}", None, f"> **{em(question)}**"
			)
		)

	@fun.command(name="rps", description="Play Avatar Rock, Paper, Scissors.")
	@app.describe(opponent="The user you want to play against")
	async def rps(self, interaction: discord.Interaction, opponent: discord.User):
		if opponent.id == interaction.user.id:
			return await interaction.response.send_message(
				view=Fail("Invalid Opponent", "You can't play against yourself."),
				ephemeral=True,
			)

		view = AvatarRPSView(interaction.user, opponent)
		await interaction.response.send_message(view=view)
		view.message = await interaction.original_response()

	@fun.command(name="tictactoe", description="Play 3x3 or 6x7 grid Tic-Tac-Toe.")
	@app.describe(
		opponent="The user you want to play against",
		starter="Who should start first? (default: you)",
		board="Choose board size (default: 3x3)",
	)
	async def tictactoe(
		self,
		interaction: discord.Interaction,
		opponent: discord.User,
		starter: Literal["me", "opponent"] = "me",
		board: Literal["3x3", "6x7"] = "3x3",
	):
		if opponent.id == interaction.user.id:
			return await interaction.response.send_message(
				view=Fail("Invalid Opponent", "You can't play against yourself."),
				ephemeral=True,
			)

		p1 = interaction.user if starter == "me" else opponent
		p2 = opponent if starter == "me" else interaction.user

		if board == "3x3":
			view = TicTacToeView(p1, p2, self.bot)
		else:
			view = SixBySevenTTTView(p1, p2, self.bot)

		await interaction.response.send_message(view=view)
		msg = await interaction.original_response()
		view.message = msg

		if p1.bot:
			await view.do_bot_turn(msg)
