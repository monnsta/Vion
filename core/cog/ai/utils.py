import random
import time
from abc import ABC, abstractmethod

import discord
from discord.ext import commands

from meta import config


class BaseEventHandler(ABC):
	cooldown_seconds: float = 60.0
	base_chance: float = 0.0

	@abstractmethod
	def evaluate(
		self,
		consciousness: "Consciousness",
		bot: commands.Bot,
		free_will: bool,
		**kwargs
	) -> bool:
		pass

	def get_random(self, free_will: bool, chance_modifier: float) -> bool:
		if not free_will:
			return False
		chance = config.free_will_frequency * chance_modifier
		return random.random() < max(0.0, min(1.0, chance))


class MessageEventHandler(BaseEventHandler):
	def evaluate(self, consciousness: "Consciousness", bot: commands.Bot, free_will: bool, **kwargs) -> bool:
		_ = consciousness
		message: discord.Message | None = kwargs.get("message")

		if message is None:
			return False

		if message.content.startswith('/') or message.author == bot.user or message.interaction_metadata:
			return False

		should_trigger = False

		if isinstance(message.channel, discord.DMChannel):
			should_trigger = True if not message.flags.silent else self.get_random(free_will, 0.05)
		else:
			is_reply_to_bot = False
			if message.reference and message.reference.cached_message:
				replied_msg = message.reference.cached_message
				if bot.user and replied_msg.author.id == bot.user.id:
					is_reply_to_bot = True

			if is_reply_to_bot or (bot.user and bot.user in message.mentions):
				should_trigger = True
			elif bot.user:
				bot_names = (bot.user.display_name.lower(), bot.user.name.lower(), config.bot.name.lower())
				if any(name in message.content.lower() for name in bot_names):
					should_trigger = self.get_random(free_will, 0.95) if free_will else True

			if not should_trigger and free_will:
				if message.mention_everyone:
					should_trigger = self.get_random(free_will, 0.4)
				else:
					should_trigger = self.get_random(free_will, 0.01)

		return should_trigger


class DynamicChanceEventHandler(BaseEventHandler):
	def __init__(self, cooldown_seconds: float = 60.0):
		self.cooldown_seconds = cooldown_seconds

	def evaluate(self, consciousness: "Consciousness", bot: commands.Bot, free_will: bool, **kwargs) -> bool:
		_ = (consciousness, bot)
		chance = kwargs.get("chance", 0.0)
		return self.get_random(free_will, chance)


class GenericChanceEventHandler(BaseEventHandler):
	def __init__(self, base_chance: float, cooldown_seconds: float = 60.0):
		self.base_chance = base_chance
		self.cooldown_seconds = cooldown_seconds

	def evaluate(self, consciousness: "Consciousness", bot: commands.Bot, free_will: bool, **kwargs) -> bool:
		_ = (consciousness, bot, kwargs)
		if self.base_chance >= 1.0:
			return True
		return self.get_random(free_will, self.base_chance)


class Consciousness:
	def __init__(self):
		self.event_cooldowns = {}
		self.message_trigger_cooldowns = {}
		self._cleanup_interval = 300
		self._last_cleanup = time.time()

		self.handlers: dict[str, BaseEventHandler] = {}
		self._register_default_handlers()

	def register_handler(self, event_type: str, handler: BaseEventHandler):
		self.handlers[event_type] = handler

	def _register_default_handlers(self):
		self.register_handler("on_message", MessageEventHandler())
		self.register_handler("on_message_delete", GenericChanceEventHandler(base_chance=0.2))
		self.register_handler("on_message_edit", GenericChanceEventHandler(base_chance=0.2))
		self.register_handler("on_reaction_add", GenericChanceEventHandler(base_chance=0.1))
		self.register_handler("on_guild_channel_create", GenericChanceEventHandler(base_chance=0.5))
		self.register_handler("on_typing", GenericChanceEventHandler(base_chance=0.06))
		self.register_handler("on_member_join", GenericChanceEventHandler(base_chance=0.6))
		self.register_handler("on_guild_join", GenericChanceEventHandler(base_chance=1.0))
		self.register_handler("on_voice_state_update", GenericChanceEventHandler(base_chance=0.3))
		self.register_handler("on_inactivity", GenericChanceEventHandler(base_chance=0.5, cooldown_seconds=3600))
		self.register_handler("freewill", GenericChanceEventHandler(base_chance=0.3, cooldown_seconds=300))
		self.register_handler("notification_freewill", DynamicChanceEventHandler(cooldown_seconds=300))

	def _cleanup_cooldowns(self, now: float):
		keys_to_remove = [k for k, v in self.message_trigger_cooldowns.items() if now - v > config.event_cooldown * 2]
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
		**kwargs
	) -> bool:
		now = time.time()
		if now - self._last_cleanup > self._cleanup_interval:
			self._cleanup_cooldowns(now)

		handler = self.handlers.get(event_type)
		if not handler:
			return False

		if event_type == "on_message":
			return handler.evaluate(self, bot, free_will, **kwargs)

		context_id = kwargs.get('context_id', 0)
		event_cooldown_key = f"{event_type}_{context_id}"

		if event_cooldown_key in self.event_cooldowns:
			if now - self.event_cooldowns[event_cooldown_key] < handler.cooldown_seconds:
				return False

		should_trigger = handler.evaluate(self, bot, free_will, **kwargs)

		if should_trigger:
			self.event_cooldowns[event_cooldown_key] = now

		return should_trigger


consciousness = Consciousness()
