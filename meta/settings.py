import builtins
import logging
import sys
from typing import List, Tuple, Dict, Any, Callable, Literal, cast, NoReturn

import pytz

from core.lib.utils import F
from core.lib.file import yaml_file
from meta.paths import file


log = logging.getLogger(__name__)

real_import = builtins.__import__


class Namespace:
	def __init__(self, d=None):
		if d is None:
			d = {}
		for k, v in d.items():
			if isinstance(v, dict):
				setattr(self, k, Namespace(v))
			elif isinstance(v, list):
				setattr(self, k, [Namespace(i) if isinstance(i, dict) else i for i in v])
			else:
				setattr(self, k, v)

	def set(self, path: str, value: Any):
		if "." not in path:
			if isinstance(value, dict):
				setattr(self, path, Namespace(value))
			else:
				setattr(self, path, value)
			return self

		parts = path.split(".")
		current = self
		for part in parts[:-1]:
			if not hasattr(current, part) or not isinstance(getattr(current, part), Namespace):
				setattr(current, part, Namespace())
			current = getattr(current, part)

		last = parts[-1]
		if isinstance(value, dict):
			setattr(current, last, Namespace(value))
		else:
			setattr(current, last, value)
		return self

	def get(self, path: str, default: Any = None) -> Any:
		parts = path.split(".")
		current = self
		for part in parts:
			if isinstance(current, Namespace) and hasattr(current, part):
				current = getattr(current, part)
			elif isinstance(current, dict) and part in current:
				current = current[part]
			else:
				return default
		return current

	def delete(self, path: str):
		if "." not in path:
			if hasattr(self, path):
				delattr(self, path)
			return

		parts = path.split(".")
		current = self
		for part in parts[:-1]:
			current = getattr(current, part)
		if hasattr(current, parts[-1]):
			delattr(current, parts[-1])

	def to_dict(self):
		d = {}
		for k, v in self.__dict__.items():
			if isinstance(v, Namespace):
				d[k] = v.to_dict()
			elif isinstance(v, list):
				d[k] = [i.to_dict() if isinstance(i, Namespace) else i for i in v]
			else:
				d[k] = v
		return d

	def update(self, other):
		if isinstance(other, Namespace):
			other = other.__dict__
		for k, v in other.items():
			if isinstance(v, dict):
				setattr(self, k, Namespace(v))
			elif isinstance(v, list):
				setattr(self, k, [Namespace(i) if isinstance(i, dict) else i for i in v])
			else:
				setattr(self, k, v)
		return self

	@classmethod
	def load(cls, data):
		if isinstance(data, str):
			import json
			data = json.loads(data)
		return cls(data)

	def __repr__(self):
		return f"Namespace({self.__dict__})"


class Bot(Namespace):
	name: str
	id: int
	invite: str

class Activity(Namespace):
	status: Literal["online", "idle", "dnd", "invisible"]
	type: int
	url: str
	range: Tuple[int, ...]
	list: List[str]

class Sandbox(Namespace):
	allowed_modules: Tuple[str, ...]
	allowed_builtins: Dict[str, Callable]

class Logging(Namespace):
	file: bool
	type: Literal["text", "html", "json"]
	cleanup_days: int

class Settings(Namespace):
	server: dict
	user: dict

class AIData(Namespace):
	glob: dict
	server: dict
	user: dict

class Secrets(Namespace):
	discord: str
	assemblyai: str
	hmac: str
	gemini: list[str]

class Config(Namespace):
	bot: Bot
	activity: Activity
	devs: List[Tuple[str, int]]
	dev_servers: List[Tuple[str, int, str]]
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
	gemini_models: Tuple[str, ...]
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
	cmd: Namespace
	dev_server_ids: List[int]
	dev_ids: List[int]
	emoji: Namespace


class Emoji(Namespace):
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


config: Config = Config()
emoji: Emoji = Emoji()


class ConfigReloadError(Exception):
	"""Raised when reloading the configuration fails."""
	pass


async def load_config(reload: bool = False):
	global config, emoji
	log.info("Setting up config..." if not reload else "Reloading config...")

	def handle_error(msg: str, exc: Exception | None = None) -> NoReturn:
		log.critical(msg, exc_info=exc if exc else True)
		if reload:
			raise ConfigReloadError(msg) from exc
		sys.exit(10)

	if not yaml_file:
		handle_error("yaml parser not found, please install the required dependencies")

	try:
		_, data = await yaml_file.load(file.conf, update_cache=False, use_cache=False)
	except ConfigReloadError:
		raise
	except Exception as e:
		handle_error(f"Failed to load {file.conf}", exc=e)

	new_config = Config()
	new_emoji = Emoji()

	try:
		preserved_cmd = config.cmd.to_dict() if reload else None
		new_config.update(Config.load(data))
	except ConfigReloadError:
		raise
	except Exception as e:
		handle_error("An error occurred while parsing config into Namespace object", exc=e)

	allowed_prefixes = tuple(f"{m}." for m in new_config.sandbox.allowed_modules)
	allowed_exact = set(new_config.sandbox.allowed_modules)

	def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
		if name in allowed_exact or name.startswith(allowed_prefixes):
			return real_import(name, globals, locals, fromlist, level)
		raise ImportError(f"Module '{name}' is not allowed in sandbox")

	for parent in [new_config.settings, new_config.ai_data]:
		for attr in ['server', 'user']:
			if hasattr(parent, attr):
				val = getattr(parent, attr)
				if isinstance(val, Namespace):
					setattr(parent, attr, val.to_dict())

	for obj in [new_config.devs, new_config.dev_servers]:
		for i in range(len(obj)):
			if len(obj[i]) == 3:
				obj[i] = (obj[i][0], int(obj[i][1]), obj[i][2])
			else:
				obj[i] = (obj[i][0], int(obj[i][1]))

	new_config.dev_server_ids = [int(dsid) for _, dsid, _ in new_config.dev_servers]
	new_config.dev_ids = [int(did) for _, did in new_config.devs]

	new_emoji.update(new_config.emoji)
	new_config.delete("emoji")

	new_config.activity.range = tuple(new_config.activity.range)
	new_config.timezone = pytz.timezone(new_config.timezone)

	try:
		_, secrets_data = await yaml_file.load(file.env)
		new_config.secrets = Secrets.load(secrets_data)
	except ConfigReloadError:
		raise
	except Exception as e:
		handle_error(f"Failed to load secrets from {file.env}", exc=e)

	new_config.sandbox.allowed_builtins = {name: getattr(builtins, name) for name in new_config.sandbox.allowed_builtins}
	new_config.sandbox.allowed_builtins["__import__"] = safe_import

	new_config.system_instructions = F(new_config.system_instructions).format(config=new_config)
	new_config.summary_instructions = F(new_config.summary_instructions).format(config=new_config)
	new_config.prompt_template = F(cast(str, new_config.prompt_template))

	new_config.cmd = Namespace.load(preserved_cmd) if preserved_cmd else Namespace()

	config.update(new_config)
	emoji.update(new_emoji)


__all__ = ('load_config', 'emoji', 'config')
