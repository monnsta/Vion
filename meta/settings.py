import builtins
import logging
import sys
from typing import List, Tuple, Dict, Any, Callable, Literal, cast

import pytz

from core.lib.dataclass import Data, AntiFreeze
from core.lib.utils import F
from core.lib.file import yaml_file
from meta.paths import file


log = logging.getLogger(__name__)

real_import = builtins.__import__


class Config(Data):
	class Bot(Data):
		name: str
		id: int
		invite: str

	class Activity(Data):
		status: Literal["online", "idle", "dnd", "invisible"]
		type: int
		url: str
		range: Tuple[int, ...]
		list: List[str]

	class Sandbox(Data):
		allowed_modules: Tuple[str, ...]
		allowed_builtins: Dict[str, Callable]

	class Logging(Data):
		file: bool
		type: Literal["text", "html", "json"]
		cleanup_days: int

	class Settings(Data):
		server: dict
		user: dict

	class AIData(Data):
		glob: dict
		server: dict
		user: dict

	class Secrets(Data):
		discord: str
		assemblyai: str
		hmac: str
		gemini: list[str]

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
	cmd: Data
	dev_server_ids: List[int]
	dev_ids: List[int]
	ial: str

class Emoji(Data):
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

	def handle_error(msg: str, exc: Exception | None = None):
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
		preserved_cmd = config.cmd.to_dict(update_self=False) if reload else None
		new_config.update(Data.load(data)) # type: ignore
	except ConfigReloadError:
		raise
	except Exception as e:
		handle_error("An error occurred while parsing config into Data object", exc=e)

	allowed_prefixes = tuple(f"{m}." for m in new_config.sandbox.allowed_modules)
	allowed_exact = set(new_config.sandbox.allowed_modules)

	def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
		if name in allowed_exact or name.startswith(allowed_prefixes):
			return real_import(name, globals, locals, fromlist, level)
		raise ImportError(f"Module '{name}' is not allowed in sandbox")

	for parent in [new_config.settings, new_config.ai_data]:
		for attr in ['server', 'user']:
			val = getattr(parent, attr)
			setattr(parent, attr, AntiFreeze(val.to_dict()))

	for obj in [new_config.devs, new_config.dev_servers]:
		for i in range(len(obj)):
			if len(obj[i]) == 3:
				obj[i] = (obj[i][0], int(obj[i][1]), obj[i][2])
			else:
				obj[i] = (obj[i][0], int(obj[i][1]))

	new_config.dev_server_ids = [int(dsid) for _, dsid, _ in new_config.dev_servers]
	new_config.dev_ids = [int(did) for _, did in new_config.devs]

	new_emoji.update(Data.load(new_config.emoji.to_dict(update_self=False)))
	new_config.delete("emoji")

	new_config.activity.range = tuple(new_config.activity.range)
	new_config.timezone = pytz.timezone(new_config.timezone)

	try:
		_, secrets_data = await yaml_file.load(file.env)
		new_config.secrets = Data.load(secrets_data) # type: ignore
	except ConfigReloadError:
		raise
	except Exception as e:
		handle_error(f"Failed to load secrets from {file.env}", exc=e)

	new_config.sandbox.allowed_builtins = {name: getattr(builtins, name) for name in new_config.sandbox.allowed_builtins}
	new_config.sandbox.allowed_builtins["__import__"] = safe_import

	new_config.system_instructions = F(new_config.system_instructions).format(config=new_config)
	new_config.summary_instructions = F(new_config.summary_instructions).format(config=new_config)
	new_config.prompt_template = F(cast(str, new_config.prompt_template))

	new_config.cmd = Data.load(preserved_cmd) if preserved_cmd else Data() # type: ignore

	config.update(new_config)
	emoji.update(new_emoji)


__all__ = ('load_config', 'emoji', 'config')
