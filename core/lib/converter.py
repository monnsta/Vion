import asyncio
import datetime
import logging
import sys
import warnings
from itertools import islice

import discord

try:
	import yaml
except ImportError:
	yaml = None


log = logging.getLogger(__name__)


if not yaml:
	log.critical("yaml is not installed, please install the required dependencies")
	sys.exit(10)

try:
	DISCORD_MODELS = (
		discord.Member, discord.Role, discord.Emoji, discord.Guild,
		discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel,
		discord.User, discord.Message, discord.Asset, discord.Client,
		discord.ClientUser, discord.app_commands.Command
	)
	DISCORD_TYPES = (discord.Colour, discord.Permissions)
except ImportError:
	DISCORD_MODELS = ()
	DISCORD_TYPES = ()


class Convert:
	def __init__(
		self,
		filter_attrs: list | None = None,
		max_depth: int = 5,
		max_list_len: int = 25,
		ignore_none: bool = True,
		ignore_empty: bool = True,
		ignore_false: bool = True,
		deduplicate: bool = True,
		flatten: bool = False,
		output_format: str = "dict"
	):
		self.filter_attrs = set(filter_attrs or [])
		self.max_depth = max_depth
		self.max_list_len = max_list_len
		self.ignore_none = ignore_none
		self.ignore_empty = ignore_empty
		self.ignore_false = ignore_false
		self.deduplicate = deduplicate
		self.flatten = flatten
		self.output_format = output_format

	def _flatten_dict(self, d: dict, parent_key: str = '', sep: str = '_') -> dict:
		items = []
		for k, v in d.items():
			new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
			if isinstance(v, dict):
				items.extend(self._flatten_dict(v, new_key, sep=sep).items())
			else:
				items.append((new_key, v))
		return dict(items)

	async def __call__(self, obj, **kwargs):
		config = {
			"filter_attrs": kwargs.get("filter_attrs", self.filter_attrs),
			"max_depth": kwargs.get("max_depth", self.max_depth),
			"max_list_len": kwargs.get("max_list_len", self.max_list_len),
			"ignore_none": kwargs.get("ignore_none", self.ignore_none),
			"ignore_empty": kwargs.get("ignore_empty", self.ignore_empty),
			"ignore_false": kwargs.get("ignore_false", self.ignore_false),
			"deduplicate": kwargs.get("deduplicate", self.deduplicate),
			"flatten": kwargs.get("flatten", self.flatten),
			"output_format": kwargs.get("output_format", self.output_format),
		}

		def process():
			seen_mem = set()
			seen_discord_ids = set()

			def _serialize(o, depth):
				if config["ignore_none"] and o is None:
					return None

				if isinstance(o, (int, float, bool, str)):
					if config["ignore_empty"] and o == "": return None
					if config["ignore_false"] and o is False: return None
					return o

				if isinstance(o, datetime.datetime):
					return o.isoformat()

				if DISCORD_TYPES and isinstance(o, DISCORD_TYPES):
					return str(o)

				if config["deduplicate"] and hasattr(o, 'id') and isinstance(o.id, int):
					if o.id in seen_discord_ids:
						ref = {"id": o.id, "$ref": True}
						if hasattr(o, 'name'):
							try:
								ref["name"] = o.name
							except Exception:
								pass
						return ref
					seen_discord_ids.add(o.id)

				if depth >= config["max_depth"]:
					if hasattr(o, 'id'):
						return {"id": getattr(o, 'id'), "$ref": True}
					return str(o) if not callable(o) else None

				mem_id = id(o)
				if mem_id in seen_mem:
					return "<Circular>"

				seen_mem.add(mem_id)
				result = None

				try:
					if isinstance(o, dict):
						result = {}
						for k, v in o.items():
							val = _serialize(v, depth + 1)
							if config["ignore_none"] and val is None: continue
							if config["ignore_empty"] and val in ({}, [], ""): continue
							result[str(k)] = val

					elif not (DISCORD_MODELS and isinstance(o, DISCORD_MODELS)):
						try:
							_ = iter(o)
							result = []
							for idx, item in enumerate(islice(o, config["max_list_len"] + 1)):
								if idx >= config["max_list_len"]:
									result.append(f"...<items omitted>")
									break
								val = _serialize(item, depth + 1)
								if config["ignore_none"] and val is None: continue
								if config["ignore_empty"] and val in ({}, [], ""): continue
								result.append(val)
						except TypeError:
							pass

					if result is None:
						result = {}
						for attr_name in dir(o):
							if attr_name.startswith('_') or attr_name in config["filter_attrs"]:
								continue

							try:
								with warnings.catch_warnings():
									warnings.simplefilter("ignore", DeprecationWarning)
									value = getattr(o, attr_name)

								if callable(value):
									continue

								serialized_val = _serialize(value, depth + 1)

								if config["ignore_none"] and serialized_val is None:
									continue
								if config["ignore_empty"] and serialized_val in ({}, [], ""):
									continue

								result[attr_name] = serialized_val
							except Exception:
								pass
				finally:
					seen_mem.discard(mem_id)

				return result

			raw_dict = _serialize(obj, 0)

			if config["flatten"] and isinstance(raw_dict, dict):
				raw_dict = self._flatten_dict(raw_dict)

			if config["output_format"] == "yaml":
				return yaml.dump(raw_dict, default_flow_style=False, sort_keys=False) # type: ignore

			return raw_dict

		return await asyncio.to_thread(process)


COMMON_FILTERS = [
	'BASE', 'key', 'DEFAULT_VALUE', 'VALID_FLAGS', 'jump_url', 'colour',
	'accent_colour', 'accent_color', 'avatar_decoration_sku_id', 'client_status',
	'desktop_status', 'web_status', 'mobile_status', 'mutual_guilds', 'flags',
	'public_flags', 'interaction', 'raw_mentions', 'raw_role_mentions', 'clean_content'
]

convert_message = Convert(
	filter_attrs=COMMON_FILTERS + ['call', 'role_subscription', 'value', 'nonce', 'guild'],
	max_depth=3,
	output_format="json"
)

convert_guild = Convert(
	filter_attrs=COMMON_FILTERS + ['me'],
	max_depth=5,
	output_format="json"
)

convert_user = Convert(
	filter_attrs=COMMON_FILTERS + ['status', 'default_avatar', 'discriminator'],
	max_depth=3,
	output_format="json"
)

convert_bot = Convert(
	filter_attrs=COMMON_FILTERS + ['cached_messages', 'cogs', 'extra_events', 'token'],
	max_depth=4,
	output_format="json"
)
