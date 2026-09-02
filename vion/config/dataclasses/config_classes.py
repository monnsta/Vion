from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from discord.ext import commands

from infrastructure.utils import F


class ConfigReloadError(Exception):
	"""Raised when reloading the configuration fails."""


class ConfigNode:
	def get(self, path: str, default: Any = None) -> Any:
		current: Any = self

		for part in path.split("."):
			if isinstance(current, ConfigNode):
				if not hasattr(current, part):
					return default
				current = getattr(current, part)

			elif isinstance(current, dict):
				if part not in current:
					return default
				current = current[part]

			else:
				return default

		return current

	def set(self, path: str, value: Any) -> None:
		parts = path.split(".")
		current: Any = self

		for part in parts[:-1]:
			if isinstance(current, ConfigNode):
				if not hasattr(current, part):
					setattr(current, part, ConfigNode())
				current = getattr(current, part)

			elif isinstance(current, dict):
				if part not in current:
					current[part] = {}
				current = current[part]

			else:
				new_node = ConfigNode()
				setattr(current, part, new_node)
				current = new_node

		last = parts[-1]

		if isinstance(current, dict):
			current[last] = value

		else:
			setattr(current, last, value)

	def delete(self, path: str) -> None:
		parts = path.split(".")
		current: Any = self

		for part in parts[:-1]:
			if isinstance(current, ConfigNode):
				if not hasattr(current, part):
					return
				current = getattr(current, part)

			elif isinstance(current, dict):
				if part not in current:
					return
				current = current[part]

			else:
				return

		last = parts[-1]

		if isinstance(current, ConfigNode):
			if hasattr(current, last):
				delattr(current, last)

		elif isinstance(current, dict):
			current.pop(last, None)

	def update(self, other: Any) -> None:
		if isinstance(other, ConfigNode):
			for key, val in other.__dict__.items():
				current_val = getattr(self, key, None)
				if isinstance(current_val, ConfigNode) and isinstance(val, ConfigNode):
					current_val.update(val)
				elif isinstance(current_val, dict) and isinstance(val, dict):
					self._update_dict(current_val, val)
				else:
					setattr(self, key, val)
		elif isinstance(other, dict) and isinstance(self, dict):
			self._update_dict(self, other)

	def _update_dict(self, target: dict[str, Any], source: dict[str, Any]) -> None:
		for key, val in source.items():
			if key in target:
				if isinstance(target[key], ConfigNode) and isinstance(val, ConfigNode):
					target[key].update(val)
				elif isinstance(target[key], dict) and isinstance(val, dict):
					self._update_dict(target[key], val)
				else:
					target[key] = val
			else:
				target[key] = val


@dataclass
class Bot(ConfigNode, commands.Bot):
	name: str
	id: int
	invite: str


@dataclass
class Activity(ConfigNode):
	status: Literal["online", "idle", "dnd", "invisible"]
	type: int
	url: str | None
	range: tuple[int, ...]
	list: list[str]


@dataclass
class Developer(ConfigNode):
	name: str
	id: int


@dataclass
class DeveloperServer(ConfigNode):
	name: str
	id: int
	invite: str


@dataclass
class Sandbox(ConfigNode):
	allowed_modules: list[str]
	allowed_builtins: list[str] | dict[str, Callable[..., Any]]


@dataclass
class Logging(ConfigNode):
	file: bool
	type: Literal["text", "html", "json"]
	cleanup_days: int


@dataclass
class Settings(ConfigNode):
	server: dict[str, Any]
	user: dict[str, Any]


@dataclass
class AIData(ConfigNode):
	glob: dict[str, Any]
	server: dict[str, Any]
	user: dict[str, Any]


@dataclass
class Secrets(ConfigNode):
	discord: str
	assemblyai: str
	hmac: str
	gemini: list[str]


@dataclass
class Emoji(ConfigNode):
	checkmark: str
	crossmark: str
	warn: str
	info: str

	arrow_left: str
	arrow_right: str
	double_arrow_left: str
	double_arrow_right: str

	refresh: str

	char_empty: str
	char_absolute_empty: str
	char_o: str
	char_x: str

	char_0: str
	char_1: str
	char_2: str
	char_3: str
	char_4: str
	char_5: str
	char_6: str
	char_7: str
	char_8: str
	char_9: str

	avatar_airnomad: str
	avatar_earthkingdom: str
	avatar_firenation: str
	avatar_watertribe: str


@dataclass
class Config(ConfigNode):
	bot: Bot
	activity: Activity
	devs: list[Developer]
	dev_servers: list[DeveloperServer]

	domain: str
	timezone: Any

	sandbox: Sandbox
	logging: Logging

	max_restore_file_size: int

	max_stm: int
	max_ltm: int
	max_previous_response: int
	max_audit: int
	event_cooldown: int
	ai_message_cooldown_seconds: int

	gemini_models: tuple[str, ...]
	free_will_frequency: float
	temperature: float
	top_p: float
	top_k: int

	settings: Settings
	ai_data: AIData

	prompt_template: F
	fallback_response: str
	system_instructions: str
	summary_instructions: str

	secrets: Secrets

	emoji: Emoji

	cmd: ConfigNode = ConfigNode()

	dev_server_ids: list[int] = field(default_factory=list)
	dev_ids: list[int] = field(default_factory=list)
