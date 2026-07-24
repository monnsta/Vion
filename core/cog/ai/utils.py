import random
import time
import discord
from discord.ext import commands

from meta import config


class Consciousness:
	def __init__(self):
		self.event_cooldowns = {}
		self.message_trigger_cooldowns = {}
		self._cleanup_interval = 300
		self._last_cleanup = time.time()

	def _cleanup_cooldowns(self, now: float):
		keys_to_remove = [k for k, v in self.message_trigger_cooldowns.items() if now - v > config.ai_message_cooldown_seconds * 2]
		for k in keys_to_remove:
			del self.message_trigger_cooldowns[k]

		keys_to_remove = [k for k, v in self.event_cooldowns.items() if now - v > 60 * 2]
		for k in keys_to_remove:
			del self.event_cooldowns[k]

		self._last_cleanup = now

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

		if now - self._last_cleanup > self._cleanup_interval:
			self._cleanup_cooldowns(now)

		def get_random(chance_modifier: float) -> bool:
			if not free_will:
				return False
			chance = config.free_will_frequency * chance_modifier
			return random.random() < max(0.0, min(1.0, chance))

		if event_type == "on_message":
			if message is None:
				return False

			user_id = message.author.id
			channel_id = message.channel.id
			cooldown_key = (user_id, channel_id)

			if cooldown_key in self.message_trigger_cooldowns:
				if now - self.message_trigger_cooldowns[cooldown_key] < config.ai_message_cooldown_seconds:
					return False

			if message.content.startswith(tuple(prefixes)) or message.author == bot.user:
				return False

			should_trigger = False

			if isinstance(message.channel, discord.DMChannel):
				should_trigger = True if not message.flags.silent else get_random(0.1)
			else:
				is_reply_to_bot = False

				if message.reference and message.reference.cached_message:
					replied_msg = message.reference.cached_message
					if bot.user and replied_msg.author.id == bot.user.id:
						is_reply_to_bot = True

				if is_reply_to_bot:
					should_trigger = True
				elif bot.user and bot.user in message.mentions:
					should_trigger = True
				elif bot.user:
					bot_names = (bot.user.display_name.lower(), bot.user.name.lower(), config.bot.name.lower())
					if any(name in message.content.lower() for name in bot_names):
						should_trigger = get_random(0.8) if free_will else True

				if not should_trigger and free_will:
					if message.mention_everyone:
						should_trigger = get_random(0.3)
					else:
						should_trigger = get_random(0.02)

			if should_trigger:
				self.message_trigger_cooldowns[cooldown_key] = now
			return should_trigger

		event_cooldown_key = f"{event_type}_{context_id}"
		if event_cooldown_key in self.event_cooldowns:
			if now - self.event_cooldowns[event_cooldown_key] < 60: # Original 60s cooldown for other events
				return False

		should_trigger = False
		if event_type == "on_message_delete":
			should_trigger = get_random(-0.2)
		elif event_type == "on_message_edit":
			should_trigger = get_random(-0.2)
		elif event_type == "on_reaction_add":
			should_trigger = get_random(-0.2)
		elif event_type == "on_guild_channel_create":
			should_trigger = get_random(-0.1)
		elif event_type == "on_typing":
			should_trigger = get_random(-0.4)

		if should_trigger:
			self.event_cooldowns[event_cooldown_key] = now
		return should_trigger


consciousness = Consciousness()
