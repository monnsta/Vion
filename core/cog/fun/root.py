import random
from typing import Literal

import discord
from discord import app_commands as app
from discord.ext import commands

from core.lib.utils import em, mt
from meta import config

from core.cog.ui_template import Fail, Generic
from core.cog.fun.ui import AvatarRPSView, TicTacToeView, SixBySevenTTTView


class FunRoot(commands.Cog):
	def __init__(self, bot: commands.Bot):
		self.bot = bot
		self.p = config.default_prefix[0]


	@commands.hybrid_group(
		name='fun',
		aliases=['f'],
		description='Fun and mini-games commands.'
	)
	async def fun(self, ctx: commands.Context):
		if ctx.invoked_subcommand is None:
			await ctx.reply(view=Fail(
				"Subcommand Missing",
				"Available subcommands:",
				"```",
				"* 8ball     (8)",
				"* rps       (r)",
				"* tictactoe (t)",
				"```"
			))


	@fun.command(
		name='help',
		aliases=['h'],
		description='Get help for the fun group.'
	)
	async def help(self, ctx: commands.Context):
		await ctx.reply(view=Generic(
			"# Fun",
			"This group contains all fun and games.",
			None,
			mt(
				"## 8ball:",
				"Ask the magic 8-ball a question.",
				"Params:",
				"* question: The question to ask",
				"Usage:",
				f"* `{self.p}fun 8ball Is my pp long enough`",
				f"* `{self.p}f 8 Is my pp long enough`",
				f"* {config.cmd.fun.get('8ball')} `question:` Is my pp long enough"
			), None,
			mt(
				"## RPS:",
				"Play Avatar Rock, Paper, Scissors. Exactly like rps but with the four elements.",
				"Params:",
				"* opponent: The user you want to play against. Choose a bot if you don't have friends",
				"Usage:",
				f"* `{self.p}fun rps @somebody`",
				f"* `{self.p}f r @somebody`",
				f"* {config.cmd.fun.rps} `opponent:` @somebody"
			), None,
			mt(
				"## TicTacToe:",
				"Play 3x3 or 6x7 grid Tic-Tac-Toe.",
				"Params:",
				"* opponent: The user you want to play against",
				"* starter: Who should start first? (default: you)",
				"* board: Choose board size (default: 3x3)",
				"Usage:",
				f"* `{self.p}fun tictactoe @somebody opponent 6x7`",
				f"* `{self.p}f t @somebody opponent 6x7`",
				f"* {config.cmd.fun.tictactoe} `opponent:` @somebody `starter:` opponent `board:` 6x7"
			)
		))


	@fun.command(
		name='8ball',
		aliases=['8'],
		description='Ask the magic 8-ball a question.'
	)
	@app.describe(question='The question to ask')
	async def eightball(self, ctx: commands.Context, *, question: str):
		responses = [
			# Positives
			"It is certain.", "It is decidedly so.", "Without a doubt.",
			"Yes definitely.", "You may rely on it.", "As I see it, yes.",
			"Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
			"Abso-freakin-lutely.", "The stars have aligned and they say YES.",
			"Yes, but at what cost?",
			"The walls are whispering YES and they won't stop laughing.",
			"YES, because the skin-walker outside your window nodded.",
			"The kids in my basement say absolutely!",

			# Mid
			"Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
			"Cannot predict now.", "Concentrate and ask again.",
			"`Error 404: Could not find 'How_To_Answer_Stupid_Questions.pdf'.`",
			"My crystal ball is buffering.",
			"Signs point to... wait, I forgot my answer. I got distracted by a shiny rock.",
			"Bold of you to assume the universe cares.",
			"Ask me again and I will leak your search history.",
			"I rolled a dice and it laughed at you.",
			"I can't answer right now, the shadow man is watching me type.",
			"The static in my teeth is too loud to decide.",
			"If I told you, the spiders under your mattress would find out.",

			# Negatives
			"Don't count on it.", "My reply is no.", "My sources say no.",
			"Outlook not so good.", "Very doubtful.",
			"Ha. In your dreams, buddy.", "Not in this lifetime.",
			"Outlook looks like a dumpster fire.",
			"The static on the TV says you must suffer a permanent NO.",
			"NO, and the meat in the fridge agrees with me."
		]

		await ctx.reply(view=Generic(
			f"### {random.choice(responses)}",
			None,
			f"> **{em(question)}**"
		))


	@fun.command(
		name='rps',
		aliases=['r'],
		description='Play Avatar Rock, Paper, Scissors.'
	)
	@app.describe(opponent='The user you want to play against')
	async def rps(self, ctx: commands.Context, opponent: discord.User | discord.Member):
		if opponent.id == ctx.author.id:
			return await ctx.reply(view=Fail(
				"Invalid Opponent",
				"You can't play against yourself."
			))

		view = AvatarRPSView(ctx.author, opponent)
		msg = await ctx.reply(view=view)
		view.message = msg


	@fun.command(
		name='tictactoe',
		aliases=['t'],
		description='Play 3x3 or 6x7 grid Tic-Tac-Toe.'
	)
	@app.describe(
		opponent='The user you want to play against',
		starter='Who should start first? (default: you)',
		board='Choose board size (default: 3x3)'
	)
	async def tictactoe(self, ctx: commands.Context, opponent: discord.User | discord.Member, starter: Literal['me', 'opponent'] = 'me', board: Literal['3x3', '6x7'] = '3x3'):
		if opponent.id == ctx.author.id:
			return await ctx.reply(view=Fail(
				"Invalid Opponent",
				"You can't play against yourself."
			))

		p1 = ctx.author if starter == 'me' else opponent
		p2 = opponent if starter == 'me' else ctx.author

		if board == '3x3':
			view = TicTacToeView(p1, p2, self.bot)
		else:
			view = SixBySevenTTTView(p1, p2, self.bot)

		msg = await ctx.reply(view=view)
		view.message = msg

		if p1.bot:
			await view.do_bot_turn(msg)
