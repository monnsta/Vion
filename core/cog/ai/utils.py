import random
import time
import discord
from discord.ext import commands

from meta import config


class Consciousness:
	def __init__(self):
		self.cooldowns = {}

	def evaluate(
		self,
		bot: commands.Bot,
		event_type: str,
		free_will: bool = False,
		message: discord.Message | None = None,
		prefixes: tuple = (),
		**kwargs
	) -> bool:
		
		context_id = kwargs.get('context_id', 0)
		now = time.time()
		cooldown_key = f"{event_type}_{context_id}"

		if event_type != "on_message" and cooldown_key in self.cooldowns:
			if now - self.cooldowns[cooldown_key] < 60:
				return False

		def get_random(chance_modifier: float) -> bool:
			if not free_will:
				return False
			chance = config.free_will_frequency * chance_modifier
			return random.random() < max(0.0, min(1.0, chance))

		trigger = False

		if event_type == "on_message":
			if message and (message.content.startswith(tuple(prefixes)) or message.author == bot.user):
				return False

			if message and isinstance(message.channel, discord.DMChannel):
				if message.flags.silent:
					return get_random(0.1)
				return True

			is_reply_to_bot = False
			mention_is_on = False

			if message and message.reference and message.reference.cached_message:
				replied_msg = message.reference.cached_message
				if bot.user and replied_msg.author.id == bot.user.id:
					is_reply_to_bot = True
					mention_is_on = bot.user in message.mentions

			if is_reply_to_bot:
				return True if mention_is_on else (get_random(0.5) if free_will else True)

			if message and bot.user:
				bot_names = (bot.user.display_name, bot.user.name, config.bot.name)
				if any(name in message.content.lower() for name in bot_names):
					return get_random(0.8) if free_will else True

			if message and bot.user in message.mentions:
				return True

			if free_will:
				if not message:
					return get_random(1.0)
				if message.mention_everyone:
					return get_random(0.3)
				trigger = get_random(0.02)

		elif event_type == "on_message_delete":
			trigger = get_random(-0.2)
		elif event_type == "on_message_edit":
			trigger = get_random(-0.2)
		elif event_type == "on_reaction_add":
			trigger = get_random(-0.2)
		elif event_type == "on_guild_channel_create":
			trigger = get_random(-0.1)
		elif event_type == "on_typing":
			trigger = get_random(-0.4)

		if trigger:
			self.cooldowns[cooldown_key] = now

		return trigger


consciousness = Consciousness()
